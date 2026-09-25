"""
LINE Messaging APIのWebhook処理。

会話フロー:
1. 友だち追加:ルナ・玄が挨拶し、生年月日を尋ねる(YYYY-MM-DD、YYYY/MM/DD、
   YYYYMMDD、和暦「平成7年4月12日」など複数の形式に対応。app.date_parsingを参照)
2. 任意:生まれた時間・場所を尋ねる(「スキップ」で省略可)
3. 以降:カテゴリ選択(恋愛運/仕事運/金運/健康運/総合運/相性診断)のクイックリプライを出し、
   選択されたらそのまま鑑定文を生成して返信する(相性診断のみ、代わりに
   相手の名前・生年月日を尋ねる)。悩み相談機能は持たず、受け身型の
   運勢鑑定のみを提供する方針にしている。
4. プランごとに使えるカテゴリが異なる(PLAN_CATEGORIESを参照)
   - 無料:総合運のみ、1日FREE_DAILY_LIMIT回まで
   - スタンダード:総合運・恋愛運・仕事運
   - プレミアム:全カテゴリ
5. 相性診断はプランごとに月間の利用回数上限がある(COMPATIBILITY_MONTHLY_LIMIT)
6. 「プラン確認」でスタンダード/プレミアムを選んでもらい、Stripeの
   チェックアウトURLを送る
7. 同じ日に同じカテゴリを複数回見ても、内容が食い違わないよう当日分を
   キャッシュし、相性診断以外は1日1回に制限する
   (fortune_service.get_todays_cached_fortuneを参照)
8. 自傷・自殺などの深刻な相談のサインを検知した場合は、占いとして処理せず
   相談窓口の案内に切り替える(CRISIS_KEYWORDS / _handle_crisis_signal)
9. 総合運の後は「今日の1枚」ボタンで、今日引いたタロットカードの画像を
   見られる(TAROT_IMAGE_BASE_URL未設定の間はテキストでカード名を返す)

鑑定文以外の案内・エラーメッセージも、すべてルナ(優しい語り)・玄(断定的な
一言)の掛け合い口調で統一している(_reply_dialogueを経由して送信)。
"""
from linebot import LineBotApi, WebhookParser
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, FollowEvent, TextMessage, TextSendMessage, ImageSendMessage, Sender,
    QuickReply, QuickReplyButton, MessageAction,
)
from sqlalchemy.orm import Session

from app.config import settings
from app.models import User, ChatLog
from app.date_parsing import parse_birth_date
from app import fortune_service, payment, tarot

line_bot_api = LineBotApi(settings.LINE_CHANNEL_ACCESS_TOKEN)
parser = WebhookParser(settings.LINE_CHANNEL_SECRET)

CATEGORIES = ["恋愛運", "仕事運", "金運", "健康運", "総合運", "相性診断"]
FREE_CATEGORY = "総合運"
TODAYS_CARD_COMMAND = "今日の1枚"

# 表示ラベル → 内部で使うカテゴリキー(ai_service.CATEGORY_ELEMENTSのキーと対応)
CATEGORY_LABEL_TO_KEY = {
    "恋愛運": "恋愛",
    "仕事運": "仕事",
    "金運": "金運",
    "健康運": "健康",
    "総合運": "総合",
    "相性診断": "相性",
}

# プランごとに使える運勢カテゴリ(相性診断は別枠で管理するのでここには含めない)
PLAN_CATEGORIES = {
    "free": {"総合"},
    "standard": {"総合", "恋愛", "仕事"},
    "premium": {"総合", "恋愛", "仕事", "金運", "健康"},
}

# プランごとの相性診断の月間利用上限
COMPATIBILITY_MONTHLY_LIMIT = {"free": 1, "standard": 5, "premium": 15}

MAIN_MENU_QUICK_REPLY = QuickReply(
    items=[QuickReplyButton(action=MessageAction(label=c, text=c)) for c in CATEGORIES]
    + [QuickReplyButton(action=MessageAction(label="プラン確認", text="プラン確認"))]
)

PLAN_SELECT_QUICK_REPLY = QuickReply(
    items=[
        QuickReplyButton(action=MessageAction(label="スタンダード登録", text="スタンダード登録")),
        QuickReplyButton(action=MessageAction(label="プレミアム登録", text="プレミアム登録")),
    ]
)

# 深刻な相談のサイン。ここに該当する場合は占いとして処理せず、
# 相談窓口の案内を優先する(検知漏れ・誤検知はどちらもありうるため、
# あくまで一次的なセーフティネットとして扱うこと)。
CRISIS_KEYWORDS = [
    "死にたい", "消えたい", "自殺", "死のうと", "生きるのがつらい",
    "リストカット", "自傷",
]


def parse_webhook_body(body: str, signature: str):
    try:
        return parser.parse(body, signature)
    except InvalidSignatureError:
        raise


def handle_events(db: Session, events) -> None:
    for event in events:
        if isinstance(event, FollowEvent):
            _handle_follow(db, event)
        elif isinstance(event, MessageEvent) and isinstance(event.message, TextMessage):
            _handle_text_message(db, event)


def _handle_follow(db: Session, event: FollowEvent) -> None:
    """友だち追加された瞬間の、ルナ・玄からの最初の挨拶。"""
    line_user_id = event.source.user_id
    _get_or_create_user(db, line_user_id)  # ここでユーザーレコードを作成しておく

    greeting = (
        "ルナ:こんにちは、わたしルナ。星とタロットを読む魔女なの。"
        "隣にいるのは相棒の玄。ちょっと口は悪いけど、頼りになる子だよ。"
        "まずはあなたの生まれた日を、1990-05-20のような形で教えてくれる?\n"
        "玄:…早くしな。"
    )
    _reply_dialogue(event, greeting)


def _get_or_create_user(db: Session, line_user_id: str) -> User:
    user = db.query(User).filter(User.line_user_id == line_user_id).first()
    if not user:
        user = User(line_user_id=line_user_id, onboarding_step="need_birth_date")
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


def get_user_plan(user: User) -> str:
    """
    このユーザーが今使えるプランを返す("free" / "standard" / "premium")。
    Subscription.planはStripe側の登録情報をそのまま反映したものだが、
    支払い状況(status)がactive/trialingでなければ実質free扱いにする。
    """
    if payment.is_active_subscriber(user) and user.subscription and user.subscription.plan:
        return user.subscription.plan
    return "free"


def split_dialogue(fortune_text: str) -> tuple[str, str]:
    """
    「ルナ:〜\n玄:〜」形式のテキストを、ルナのセリフ・玄のセリフに分割する。
    形式が崩れていた場合は、全文をルナのセリフとして扱う(玄のセリフは空)。
    line_bot.pyだけでなく、push_service.py(毎日の自動配信)からも使う。
    """
    luna_line = fortune_text
    gen_line = ""

    if "玄:" in fortune_text:
        before, _, after = fortune_text.partition("玄:")
        luna_line = before
        gen_line = after

    luna_line = luna_line.replace("ルナ:", "").strip()
    gen_line = gen_line.strip()

    return luna_line, gen_line


def build_dialogue_messages(
    fortune_text: str, quick_reply: QuickReply | None = None
) -> list[TextSendMessage]:
    """
    鑑定文を、ルナ・玄それぞれの名前とアイコン付きのメッセージ2通に組み立てる。
    reply(返信)は何通送っても追加費用がかからないため、手動操作への
    返信ではこちらを使う。毎日の自動配信(push、通数課金あり)には
    build_combined_message(1通にまとめる版)を使うこと。
    """
    luna_line, gen_line = split_dialogue(fortune_text)

    messages = []
    luna_sender = Sender(name=settings.LUNA_NAME, icon_url=settings.LUNA_ICON_URL or None)
    messages.append(TextSendMessage(text=luna_line, sender=luna_sender))

    if gen_line:
        gen_sender = Sender(name=settings.GEN_NAME, icon_url=settings.GEN_ICON_URL or None)
        messages.append(TextSendMessage(text=gen_line, sender=gen_sender, quick_reply=quick_reply))
    else:
        messages[-1].quick_reply = quick_reply

    return messages


def build_combined_message(fortune_text: str) -> TextSendMessage:
    """
    ルナ・玄のセリフを1通のメッセージにまとめる(見出しで区切って
    掛け合い感は保つ)。LINEの配信通数は「吹き出しの数」で課金されるため、
    通数がかさむ自動配信(push)ではこちらを使ってコストを抑える。
    """
    luna_line, gen_line = split_dialogue(fortune_text)
    text = f"【魔女ルナ】\n{luna_line}"
    if gen_line:
        text += f"\n\n【黒猫・玄】\n{gen_line}"
    return TextSendMessage(text=text)


def _reply_dialogue(event, fortune_text: str, quick_reply: QuickReply | None = None) -> None:
    """
    ルナ・玄の掛け合いを、それぞれ別の吹き出し(名前・アイコン付き)として返信する。
    LINEの「sender」機能を使い、同じ公式アカウントのままキャラクターごとに
    表示名・アイコンを出し分ける。アイコンURL未設定の場合は公式アカウント名で送られる。
    """
    messages = build_dialogue_messages(fortune_text, quick_reply)
    line_bot_api.reply_message(event.reply_token, messages)


def _contains_crisis_signal(text: str) -> bool:
    return any(keyword in text for keyword in CRISIS_KEYWORDS)


def _handle_crisis_signal(event) -> None:
    """
    深刻な相談のサインを検知した場合の応答。占いのキャラクター演出は使わず、
    真摯な一つのメッセージとして、相談窓口の案内を直接届ける。
    掘り下げる質問はせず、ここで会話の踏み込みを止める。

    注意:電話番号は変更・廃止される可能性があるため、実際の運用前に
    最新の窓口情報を必ず確認すること。
    """
    message = (
        "つらい気持ちを話してくれてありがとう。占いよりも先に、"
        "今のあなたを支えてくれる人に頼ってほしいの。\n"
        "よりそいホットライン(0120-279-338、24時間)や、"
        "いのちの電話(0570-064-556)では、専門の人が話を聞いてくれます。\n"
        "一人で抱え込まないでね。"
    )
    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=message))


def _handle_text_message(db: Session, event: MessageEvent) -> None:
    line_user_id = event.source.user_id
    text = event.message.text.strip()

    # 占いの会話フローより先に、深刻な相談のサインがないか確認する
    if _contains_crisis_signal(text):
        _handle_crisis_signal(event)
        return

    user = _get_or_create_user(db, line_user_id)

    # --- オンボーディング中の処理 ---
    if user.onboarding_step == "need_birth_date":
        _handle_birth_date_input(db, event, user, text)
        return

    if user.onboarding_step == "need_time_place":
        _handle_time_place_input(db, event, user, text)
        return

    if user.onboarding_step == "awaiting_partner_birthdate":
        _handle_partner_birth_date_input(db, event, user, text)
        return

    # --- 共通コマンド ---
    if text == "プラン確認":
        _reply_dialogue(
            event,
            "ルナ:どちらのプランにする?\n"
            "玄:選びな。",
            PLAN_SELECT_QUICK_REPLY,
        )
        return

    if text in ("スタンダード登録", "プレミアム登録"):
        plan = "standard" if text == "スタンダード登録" else "premium"
        url = payment.create_checkout_session(user, plan)
        _reply_dialogue(
            event,
            f"ルナ:こちらから登録できるよ。初月は無料だから、まずは気軽に試してみてね。\n{url}\n"
            "玄:カード情報、ちゃんと入れな。",
        )
        return

    if text in ("当たってた", "ちがった"):
        _record_reaction(db, user, text)
        _reply_dialogue(
            event,
            "ルナ:教えてくれてありがとう。ちゃんと覚えておくね。\n玄:次に活かす。",
            MAIN_MENU_QUICK_REPLY,
        )
        return

    if text == TODAYS_CARD_COMMAND:
        _handle_todays_card_request(db, event, user)
        return

    # --- カテゴリ選択 ---
    if text in CATEGORIES:
        _handle_category_request(db, event, user, text)
        return

    # --- それ以外の自由な文章は、相談としては受け付けずメニューに誘導する ---
    _reply_dialogue(
        event,
        "ルナ:メニューから気になる運勢を選んでね。\n"
        "玄:文字を送られても占えない。ボタンを押しな。",
        MAIN_MENU_QUICK_REPLY,
    )


def _handle_birth_date_input(db: Session, event, user: User, text: str) -> None:
    birth_date = parse_birth_date(text)
    if birth_date is None:
        _reply_dialogue(
            event,
            "ルナ:あれ、その書き方だとわたし読めないみたい。"
            "「1990-05-20」「1990/05/20」「19900520」「平成2年5月20日」の"
            "どれかの形で、もう一度教えてくれる?\n"
            "玄:形式くらい合わせな。",
        )
        return

    user.birth_date = birth_date
    user.onboarding_step = "need_time_place"
    db.commit()

    _reply_dialogue(
        event,
        "ルナ:ありがとう。生まれた時間や場所が分かれば「14:30 東京」のように教えてくれる?"
        "分からなければ「スキップ」って送ってね。\n"
        "玄:分からないなら、無理すんな。",
    )


def _handle_time_place_input(db: Session, event, user: User, text: str) -> None:
    if text != "スキップ":
        parts = text.split()
        if len(parts) >= 1:
            user.birth_time = parts[0]
        if len(parts) >= 2:
            user.birth_place = " ".join(parts[1:])

    user.onboarding_step = "done"
    db.commit()

    _reply_dialogue(
        event,
        "ルナ:これで、あなたのことが視えるようになったよ。今日は何が気になる?\n"
        "玄:選びな。",
        MAIN_MENU_QUICK_REPLY,
    )


def _handle_partner_birth_date_input(db: Session, event, user: User, text: str) -> None:
    """
    「さくら 1993-11-02」のように、相手の名前+生年月日をまとめて受け取る。
    名前を省略して日付だけ送られた場合も、後方互換として受け付ける。
    """
    tokens = text.split()
    if not tokens:
        tokens = [text]

    date_token = tokens[-1]
    partner_name = " ".join(tokens[:-1]) if len(tokens) > 1 else None

    partner_birth_date = parse_birth_date(date_token)
    if partner_birth_date is None:
        _reply_dialogue(
            event,
            "ルナ:ごめんね、その書き方だと読めないの。"
            "「さくら 1993-11-02」「さくら 1993/11/02」「さくら 19931102」の"
            "どれかの形で、相手の名前と生まれた日を教えてくれる?\n"
            "玄:さっさと送りな。",
        )
        return

    user.onboarding_step = "done"
    db.commit()

    fortune_text = fortune_service.generate_and_log_fortune(
        db,
        user,
        category="相性",
        partner_birth_date=partner_birth_date,
        partner_name=partner_name,
    )

    reaction_quick_reply = QuickReply(
        items=[
            QuickReplyButton(action=MessageAction(label="当たってた", text="当たってた")),
            QuickReplyButton(action=MessageAction(label="ちがった", text="ちがった")),
        ]
        + list(MAIN_MENU_QUICK_REPLY.items)
    )
    _reply_dialogue(event, fortune_text, reaction_quick_reply)


def _handle_category_request(db: Session, event, user: User, category_label: str) -> None:
    category = CATEGORY_LABEL_TO_KEY.get(category_label, "総合")
    plan = get_user_plan(user)

    # --- 相性診断:プランごとの月間上限をチェック ---
    if category == "相性":
        monthly_limit = COMPATIBILITY_MONTHLY_LIMIT.get(plan, 0)
        used_this_month = fortune_service.count_compatibility_uses_this_month(db, user)
        if used_this_month >= monthly_limit:
            _reply_dialogue(
                event,
                f"ルナ:相性診断は今月もう{monthly_limit}回使ったよ。来月また試してね。\n"
                "玄:上限だ。プランを上げれば増える。",
                MAIN_MENU_QUICK_REPLY,
            )
            return

        user.onboarding_step = "awaiting_partner_birthdate"
        db.commit()
        _reply_dialogue(
            event,
            "ルナ:相性を見たい相手の名前と生まれた日を、"
            "「さくら 1993-11-02」のような形で教えてくれる?\n"
            "玄:さっさと送りな。",
        )
        return

    # --- 通常カテゴリ:プランで使えるかチェック ---
    if category not in PLAN_CATEGORIES.get(plan, PLAN_CATEGORIES["free"]):
        _reply_dialogue(
            event,
            f"ルナ:ごめんね、「{category_label}」は今のプランだと使えないの。\n"
            "玄:プランを上げな。「プラン確認」って送りな。",
            MAIN_MENU_QUICK_REPLY,
        )
        return

    # --- 無料プランは1日の総回数にも上限がある ---
    if plan == "free":
        used_today = fortune_service.count_free_uses_today(db, user)
        if used_today >= settings.FREE_DAILY_LIMIT:
            _reply_dialogue(
                event,
                "ルナ:今日はもう十分視たね、また明日来てね。\n"
                "玄:待てないなら、課金しな。",
                MAIN_MENU_QUICK_REPLY,
            )
            return

    # --- 同じ日にすでに見ていたら、その案内をして終わり(1日1回) ---
    if fortune_service.get_todays_cached_fortune(db, user, category):
        _reply_dialogue(
            event,
            f"ルナ:{category_label}はもう今日伝えたよ。続きはまた明日ね。\n"
            "玄:今日はここまでだ。",
            MAIN_MENU_QUICK_REPLY,
        )
        return

    _generate_and_reply(db, event, user, category)


def _generate_and_reply(db: Session, event, user: User, category: str) -> None:
    """鑑定文を生成し、フィードバックボタン付きで返信する共通処理。"""
    fortune_text = fortune_service.generate_and_log_fortune(db, user, category=category)

    quick_reply_items = [
        QuickReplyButton(action=MessageAction(label="当たってた", text="当たってた")),
        QuickReplyButton(action=MessageAction(label="ちがった", text="ちがった")),
    ]
    if category == "総合":
        # 総合運はタロットを引くので、カード画像を見るボタンを添える
        quick_reply_items.append(
            QuickReplyButton(action=MessageAction(label=TODAYS_CARD_COMMAND, text=TODAYS_CARD_COMMAND))
        )
    quick_reply_items += list(MAIN_MENU_QUICK_REPLY.items)

    _reply_dialogue(event, fortune_text, QuickReply(items=quick_reply_items))


def _handle_todays_card_request(db: Session, event, user: User) -> None:
    """
    「今日の1枚」ボタン。今日すでに引いたタロットカードの画像を送る
    (テキストで語った内容と矛盾しないよう、新しく引き直しはしない)。
    画像は事前に用意してTAROT_IMAGE_BASE_URLを設定した場合のみ送信できる。
    reply(返信)経由なので、画像を送ってもLINEの配信費は発生しない。
    """
    card = fortune_service.get_todays_tarot_card(db, user)
    if not card:
        _reply_dialogue(
            event,
            "ルナ:今日はまだカードを引いていないみたい。先に総合運を見てね。\n"
            "玄:順番を守りな。",
            MAIN_MENU_QUICK_REPLY,
        )
        return

    image_url = tarot.get_card_image_url(card["name"])
    if not image_url:
        # 画像がまだ用意できていない場合のフォールバック(テキストのみ)
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(
                text=f"今日引いたカードは「{card['name']}({card['orientation']})」だよ。"
                "画像はもうすぐ見られるようになる予定。"
            ),
        )
        return

    line_bot_api.reply_message(
        event.reply_token,
        ImageSendMessage(original_content_url=image_url, preview_image_url=image_url),
    )


def _record_reaction(db: Session, user: User, reaction_text: str) -> None:
    latest_log = (
        db.query(ChatLog)
        .filter(ChatLog.user_id == user.id)
        .order_by(ChatLog.created_at.desc())
        .first()
    )
    if latest_log:
        latest_log.reaction = "good" if reaction_text == "当たってた" else "bad"
        db.commit()

