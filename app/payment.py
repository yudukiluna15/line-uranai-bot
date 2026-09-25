"""
Stripeを使った月額課金の連携。

- create_checkout_session(): ユーザーに送るチェックアウトURLを発行する
  (LINEでこのURLをメッセージとして送信し、外部の決済画面に誘導する)
- handle_webhook_event(): Stripeからのwebhookを受けて、DBのSubscriptionを更新する
  (支払い成功・失敗・解約などのイベントに対応)

スタンダード/プレミアムの2プランに対応する。どちらを選んだかは
チェックアウトセッションのmetadataに埋め込み、webhook側でそれを
読み取ってSubscription.planに反映する(Stripeのline_itemsから逆引き
するより単純で確実なため)。
"""
from datetime import datetime

import stripe
from sqlalchemy.orm import Session

from app.config import settings
from app.models import User, Subscription

stripe.api_key = settings.STRIPE_SECRET_KEY

PLAN_PRICE_IDS = {
    "standard": settings.STRIPE_PRICE_ID_STANDARD,
    "premium": settings.STRIPE_PRICE_ID_PREMIUM,
}


def create_checkout_session(user: User, plan: str) -> str:
    """
    サブスクのチェックアウトセッションを作成し、決済ページのURLを返す。
    plan は "standard" か "premium"。
    client_reference_id にLINEのuser_idを、metadataにplanを入れておき、
    webhook側でどちらのプランが購入されたか判定する。
    """
    price_id = PLAN_PRICE_IDS.get(plan, settings.STRIPE_PRICE_ID_STANDARD)

    session = stripe.checkout.Session.create(
        mode="subscription",
        payment_method_types=["card"],
        line_items=[{"price": price_id, "quantity": 1}],
        client_reference_id=user.line_user_id,
        metadata={"plan": plan},
        success_url=settings.STRIPE_SUCCESS_URL,
        cancel_url=settings.STRIPE_CANCEL_URL,
        subscription_data={
            # 初月無料キャンペーンをやる場合はここで trial_period_days を設定
            "trial_period_days": 30,
            "metadata": {"plan": plan},
        },
    )
    return session.url


def verify_and_parse_event(payload: bytes, sig_header: str):
    """Stripeの署名検証を行い、イベントオブジェクトを返す。"""
    return stripe.Webhook.construct_event(
        payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
    )


def handle_webhook_event(db: Session, event: dict) -> None:
    event_type = event["type"]
    # 新しいバージョンのstripeライブラリでは、event["data"]["object"]が
    # 辞書(dict)ではなく専用オブジェクトになり、.get()が使えなくなった。
    # to_dict()で辞書に変換してから、これまで通り.get()で扱う。
    data = event["data"]["object"].to_dict()

    if event_type == "checkout.session.completed":
        line_user_id = data.get("client_reference_id")
        user = db.query(User).filter(User.line_user_id == line_user_id).first()
        if not user:
            return

        plan = data.get("metadata", {}).get("plan", "standard")

        sub = user.subscription or Subscription(user_id=user.id)
        sub.stripe_customer_id = data.get("customer")
        sub.stripe_subscription_id = data.get("subscription")
        sub.plan = plan
        sub.status = "trialing"
        db.add(sub)
        db.commit()

    elif event_type in ("customer.subscription.updated", "customer.subscription.deleted"):
        stripe_sub_id = data.get("id")
        sub = (
            db.query(Subscription)
            .filter(Subscription.stripe_subscription_id == stripe_sub_id)
            .first()
        )
        if not sub:
            return

        sub.status = data.get("status", sub.status)

        # プラン変更(アップグレード/ダウングレード)があった場合もここで反映する
        new_plan = data.get("metadata", {}).get("plan")
        if new_plan:
            sub.plan = new_plan

        period_end = data.get("current_period_end")
        if period_end:
            sub.current_period_end = datetime.utcfromtimestamp(period_end)
        if event_type == "customer.subscription.deleted":
            sub.status = "canceled"
            sub.plan = "free"
        db.commit()


def is_active_subscriber(user: User) -> bool:
    if not user.subscription:
        return False
    return user.subscription.status in ("active", "trialing")
