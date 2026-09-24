"""
「ユーザーが鑑定を求めてきたときに何をするか」をまとめた層。

1. ユーザーの星座情報を取得(なければ計算してキャッシュ)
2. 同じ日・同じカテゴリをすでに鑑定済みなら、その結果をそのまま返す
   (同じ日に見るたびに内容が食い違わないようにするため)
3. 過去ログの要約・直近の反応傾向・本日の他カテゴリの結果を取得
4. カテゴリに応じてタロットも引く(総合運のみ)。引いたカードは
   ChatLogに記録し、将来の「タロット図鑑」機能や、「今日の1枚」
   ボタンでの画像返信(同じカードの画像を出すため)に使えるようにする
5. AIに鑑定文を生成させる
6. ChatLogに保存し、一定件数たまったら要約を更新する
"""
from datetime import date, datetime
from sqlalchemy.orm import Session

from app import astrology, tarot, ai_service
from app.config import settings
from app.models import User, ChatLog, Summary


def ensure_natal_signs(db: Session, user: User) -> dict:
    """星座が未計算ならここで計算してDBにキャッシュする。"""
    if not user.sun_sign:
        signs = astrology.calculate_natal_signs(
            birth_date=user.birth_date,
            birth_time=user.birth_time,
            birth_place=user.birth_place,
        )
        user.sun_sign = signs["sun"]
        user.moon_sign = signs["moon"]
        user.venus_sign = signs["venus"]
        user.mars_sign = signs["mars"]
        db.commit()
        return signs

    return {
        "sun": user.sun_sign,
        "moon": user.moon_sign,
        "venus": user.venus_sign,
        "mars": user.mars_sign,
    }


def get_latest_summary(db: Session, user: User) -> str | None:
    summary = (
        db.query(Summary)
        .filter(Summary.user_id == user.id)
        .order_by(Summary.created_at.desc())
        .first()
    )
    return summary.content if summary else None


def get_last_opening(db: Session, user: User, category: str) -> str | None:
    """
    同じカテゴリの直近の鑑定文から、ルナのセリフの書き出し(最初の一文)だけを
    取り出す。SYSTEM_PROMPTに渡し、同じ場面の書き出しが連続しないようにする。
    """
    last_log = (
        db.query(ChatLog)
        .filter(ChatLog.user_id == user.id, ChatLog.category == category)
        .order_by(ChatLog.created_at.desc())
        .first()
    )
    if not last_log or not last_log.answer:
        return None

    # 「ルナ:〜\n玄:〜」形式から、ルナの部分だけ取り出す
    luna_part = last_log.answer.split("玄:")[0].replace("ルナ:", "").strip()
    if not luna_part:
        return None

    # 最初の一文(句点まで)だけを渡せば十分
    first_sentence = luna_part.split("。")[0]
    return first_sentence[:60]  # 念のため長さの上限も設ける


def get_todays_cached_fortune(db: Session, user: User, category: str) -> str | None:
    """
    「今日、このカテゴリをすでに鑑定済みか」を確認し、あれば同じ結果を返す。
    同じ日に同じカテゴリを何度見ても、内容が食い違わないようにするための仕組み。
    相性診断(category="相性")は相手が毎回変わりうるため、キャッシュの対象外にする。
    """
    if category == "相性":
        return None

    today_start = datetime.combine(date.today(), datetime.min.time())
    log = (
        db.query(ChatLog)
        .filter(
            ChatLog.user_id == user.id,
            ChatLog.category == category,
            ChatLog.created_at >= today_start,
        )
        .order_by(ChatLog.created_at.desc())
        .first()
    )
    return log.answer if log else None


def get_reaction_hint(db: Session, user: User, category: str) -> str | None:
    """
    同じカテゴリの直近の「当たってた/ちがった」の反応を見て、
    「ちがった」が多い場合はAIへ表現を見直すヒントを渡す。
    """
    recent_logs = (
        db.query(ChatLog)
        .filter(
            ChatLog.user_id == user.id,
            ChatLog.category == category,
            ChatLog.reaction.isnot(None),
        )
        .order_by(ChatLog.created_at.desc())
        .limit(5)
        .all()
    )
    if len(recent_logs) < 3:
        return None  # サンプルが少なすぎる場合は判定しない

    bad_count = sum(1 for log in recent_logs if log.reaction == "bad")
    if bad_count / len(recent_logs) >= 0.5:
        return "直近、このカテゴリで「ちがった」という反応が多め"
    return None


def get_todays_other_categories(db: Session, user: User, category: str) -> str | None:
    """
    今日すでに生成した「他のカテゴリ」の結果を短くまとめて返す。
    総合運と各カテゴリ(恋愛運・仕事運など)が、同じ日に矛盾した
    運勢を出さないようにするために使う。
    """
    today_start = datetime.combine(date.today(), datetime.min.time())
    logs = (
        db.query(ChatLog)
        .filter(
            ChatLog.user_id == user.id,
            ChatLog.category != category,
            ChatLog.category != "相性",  # 相性診断は毎回相手が違うので対象外
            ChatLog.created_at >= today_start,
        )
        .order_by(ChatLog.created_at.desc())
        .limit(3)
        .all()
    )
    if not logs:
        return None

    lines = []
    for log in logs:
        luna_part = (log.answer or "").split("玄:")[0].replace("ルナ:", "").strip()
        first_sentence = luna_part.split("。")[0][:60]
        if first_sentence:
            lines.append(f"{log.category}運:{first_sentence}")

    return "\n".join(lines) if lines else None


def count_free_uses_today(db: Session, user: User) -> int:
    today_start = datetime.combine(date.today(), datetime.min.time())
    return (
        db.query(ChatLog)
        .filter(ChatLog.user_id == user.id, ChatLog.created_at >= today_start)
        .count()
    )


def count_compatibility_uses_this_month(db: Session, user: User) -> int:
    """今月すでに使った相性診断の回数(プランごとの月間上限のチェックに使う)。"""
    month_start = date.today().replace(day=1)
    month_start_dt = datetime.combine(month_start, datetime.min.time())
    return (
        db.query(ChatLog)
        .filter(
            ChatLog.user_id == user.id,
            ChatLog.category == "相性",
            ChatLog.created_at >= month_start_dt,
        )
        .count()
    )


def generate_and_log_fortune(
    db: Session,
    user: User,
    category: str,
    user_question: str | None = None,
    partner_birth_date: date | None = None,
    partner_name: str | None = None,
) -> str:
    """鑑定文を生成し、ChatLogに保存して返す。
    category="相性" のときは partner_birth_date(相手の生年月日)・
    partner_name(相手の名前)を渡す。
    user_questionを指定しない通常のカテゴリ選択の場合、当日すでに同じ
    カテゴリを鑑定済みならAIを再度呼ばず、その結果をそのまま返す
    (同じ日に内容が食い違うのを防ぐため)。
    """
    if user_question is None:
        cached = get_todays_cached_fortune(db, user, category)
        if cached:
            return cached

    natal_signs = ensure_natal_signs(db, user)
    transit_moon_sign = astrology.get_today_transit_moon_sign()

    tarot_card = tarot.draw_card() if category == "総合" else None
    summary = get_latest_summary(db, user)
    avoid_opening = get_last_opening(db, user, category)
    reaction_hint = get_reaction_hint(db, user, category)
    todays_other_categories = get_todays_other_categories(db, user, category)

    partner_signs = None
    if category == "相性" and partner_birth_date:
        # 相手の情報はDBに保存せず、その場で計算するだけに留める
        partner_signs = astrology.calculate_natal_signs(birth_date=partner_birth_date)

    fortune_text = ai_service.generate_fortune(
        category=category,
        natal_signs=natal_signs,
        transit_moon_sign=transit_moon_sign,
        tarot_card=tarot_card,
        user_summary=summary,
        user_question=user_question,
        partner_signs=partner_signs,
        partner_name=partner_name,
        avoid_opening=avoid_opening,
        reaction_hint=reaction_hint,
        todays_other_categories=todays_other_categories,
    )

    log = ChatLog(
        user_id=user.id,
        category=category,
        question=user_question,
        answer=fortune_text,
        tarot_card=tarot_card["name"] if tarot_card else None,
        tarot_orientation=tarot_card["orientation"] if tarot_card else None,
    )
    db.add(log)
    db.commit()

    maybe_update_summary(db, user)

    return fortune_text


def get_todays_tarot_card(db: Session, user: User) -> dict | None:
    """
    今日すでに引いた総合運のタロットカードを取得する。
    「今日の1枚」ボタンで画像を返信する際、テキストで語った内容と
    違うカードの画像を出してしまわないよう、同じカードを引き当てるために使う。
    """
    today_start = datetime.combine(date.today(), datetime.min.time())
    log = (
        db.query(ChatLog)
        .filter(
            ChatLog.user_id == user.id,
            ChatLog.category == "総合",
            ChatLog.created_at >= today_start,
            ChatLog.tarot_card.isnot(None),
        )
        .order_by(ChatLog.created_at.desc())
        .first()
    )
    if not log:
        return None
    return {"name": log.tarot_card, "orientation": log.tarot_orientation}


def get_drawn_card_names(db: Session, user: User) -> set[str]:
    """
    このユーザーが今までに引いたことのあるカード名の集合を返す。
    今はまだどこにも表示しないが、将来「タロット図鑑」機能
    (まだ引いていないカードを教える、コンプリート状況を見せる等)を
    作る際に、そのままこの関数を使える。
    """
    rows = (
        db.query(ChatLog.tarot_card)
        .filter(ChatLog.user_id == user.id, ChatLog.tarot_card.isnot(None))
        .distinct()
        .all()
    )
    return {row[0] for row in rows}


def maybe_update_summary(db: Session, user: User) -> None:
    """ChatLogが閾値を超えたら要約を作り直す(古いログはそのまま保持、要約だけ追加)。"""
    latest_summary = (
        db.query(Summary)
        .filter(Summary.user_id == user.id)
        .order_by(Summary.created_at.desc())
        .first()
    )
    since = latest_summary.created_at if latest_summary else datetime.min

    unsummarized_logs = (
        db.query(ChatLog)
        .filter(ChatLog.user_id == user.id, ChatLog.created_at > since)
        .order_by(ChatLog.created_at.asc())
        .all()
    )

    if len(unsummarized_logs) < settings.SUMMARY_THRESHOLD:
        return

    log_dicts = [
        {"category": log.category, "answer": log.answer}
        for log in unsummarized_logs
    ]
    # 前回の要約があれば、それも文脈として含めて要約し直す
    if latest_summary:
        log_dicts.insert(0, {"category": "これまでの要約", "answer": latest_summary.content})

    new_summary_text = ai_service.summarize_chat_history(log_dicts)

    db.add(Summary(user_id=user.id, content=new_summary_text))
    db.commit()
