"""
有料会員(active/trialing)に対して、毎朝「総合運」を自動配信する処理。

ユーザーごとに星座が異なるため、全員に同じ内容を送るマルチキャストではなく、
1人ずつ鑑定文を生成してpush messageで送る(その分、AI APIの呼び出しは
有料会員の人数分だけ毎日発生する)。

LINEの配信通数は「吹き出しの数」でカウントされ、push messageは通数分の
課金対象になる。そのため、reply(手動操作への返信)ではルナ・玄を別々の
吹き出しにしているが、ここ(push)ではbuild_combined_messageで1通に
まとめてコストを半分にしている。

main.py起動時にAPSchedulerへ登録され、設定した時刻(DAILY_PUSH_HOUR等)に
自動実行される。
"""
import logging

from linebot import LineBotApi
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models import User, Subscription
from app import fortune_service, line_bot

logger = logging.getLogger(__name__)

line_bot_api = LineBotApi(settings.LINE_CHANNEL_ACCESS_TOKEN)


def get_active_subscriber_users(db: Session) -> list[User]:
    """自動配信の対象となる、有料会員(active/trialing)のユーザー一覧を取得する。"""
    return (
        db.query(User)
        .join(Subscription, Subscription.user_id == User.id)
        .filter(Subscription.status.in_(["active", "trialing"]))
        .all()
    )


def send_daily_fortune_to_subscribers() -> None:
    """
    スケジューラから呼ばれるエントリーポイント。
    有料会員1人ずつに、その日の「総合運」を生成してpush送信する。
    1人の失敗が他の人への配信を止めないよう、失敗はログに残して処理を続ける。
    """
    db = SessionLocal()
    try:
        users = get_active_subscriber_users(db)
        logger.info("daily push: %d 人の有料会員に配信します", len(users))

        for user in users:
            try:
                _send_to_one_user(db, user)
            except Exception:
                logger.exception("daily push failed for user_id=%s", user.id)
    finally:
        db.close()


def _send_to_one_user(db: Session, user: User) -> None:
    fortune_text = fortune_service.generate_and_log_fortune(db, user, category="総合")
    message = line_bot.build_combined_message(fortune_text)
    line_bot_api.push_message(user.line_user_id, message)
