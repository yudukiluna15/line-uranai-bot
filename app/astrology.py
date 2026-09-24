"""
占星術の計算ロジック。

- kerykeion ライブラリで太陽・月・金星・火星の星座を計算する(実際の天体暦ベース)。
- 生まれた時間や場所が不明な場合は正午・東京を仮定して計算する
  (月星座は数時間のズレで変わることがあるため、時間不明の場合は
   「目安」であることをユーザーに伝えるのが望ましい)。
- kerykeionの初期化に失敗した場合(不正な日付など)は、太陽星座だけ
  日付レンジによる簡易計算にフォールバックする。
"""
from datetime import date
from typing import Optional

from kerykeion import AstrologicalSubject

# 太陽星座の簡易フォールバック用(生年月日のみでの近似計算)
_SUN_SIGN_RANGES = [
    ((1, 20), (2, 18), "水瓶座"),
    ((2, 19), (3, 20), "魚座"),
    ((3, 21), (4, 19), "牡羊座"),
    ((4, 20), (5, 20), "牡牛座"),
    ((5, 21), (6, 21), "双子座"),
    ((6, 22), (7, 22), "蟹座"),
    ((7, 23), (8, 22), "獅子座"),
    ((8, 23), (9, 22), "乙女座"),
    ((9, 23), (10, 23), "天秤座"),
    ((10, 24), (11, 22), "蠍座"),
    ((11, 23), (12, 21), "射手座"),
    ((12, 22), (1, 19), "山羊座"),
]

# kerykeionが返す英語サイン名 → 日本語表記
_SIGN_JA = {
    "Ari": "牡羊座", "Tau": "牡牛座", "Gem": "双子座", "Can": "蟹座",
    "Leo": "獅子座", "Vir": "乙女座", "Lib": "天秤座", "Sco": "蠍座",
    "Sag": "射手座", "Cap": "山羊座", "Aqu": "水瓶座", "Pis": "魚座",
}


def _fallback_sun_sign(birth_date: date) -> str:
    md = (birth_date.month, birth_date.day)
    for start, end, sign in _SUN_SIGN_RANGES:
        if start <= end:
            if start <= md <= end:
                return sign
        else:  # 山羊座のように年をまたぐ場合
            if md >= start or md <= end:
                return sign
    return "不明"


def calculate_natal_signs(
    birth_date: date,
    birth_time: Optional[str] = None,
    birth_place: Optional[str] = None,
) -> dict:
    """
    生年月日(と可能なら時間・場所)から主要天体の星座を計算する。
    戻り値: {"sun": "牡羊座", "moon": "...", "venus": "...", "mars": "..."}
    """
    hour, minute = 12, 0
    if birth_time:
        try:
            hour, minute = map(int, birth_time.split(":"))
        except ValueError:
            pass

    city = birth_place or "Tokyo"

    try:
        subject = AstrologicalSubject(
            name="user",
            year=birth_date.year,
            month=birth_date.month,
            day=birth_date.day,
            hour=hour,
            minute=minute,
            city=city,
            nation="JP" if city == "Tokyo" else None,
        )
        return {
            "sun": _SIGN_JA.get(subject.sun["sign"], subject.sun["sign"]),
            "moon": _SIGN_JA.get(subject.moon["sign"], subject.moon["sign"]),
            "venus": _SIGN_JA.get(subject.venus["sign"], subject.venus["sign"]),
            "mars": _SIGN_JA.get(subject.mars["sign"], subject.mars["sign"]),
        }
    except Exception:
        # 都市名の解決に失敗した場合などのフォールバック
        # (太陽星座のみ簡易計算、他は不明として扱う)
        return {
            "sun": _fallback_sun_sign(birth_date),
            "moon": "不明",
            "venus": "不明",
            "mars": "不明",
        }


def get_today_transit_moon_sign() -> str:
    """今日の「今この瞬間の月」の星座を計算する(総合運・健康運の日替わり要素に使う)。"""
    today = date.today()
    try:
        subject = AstrologicalSubject(
            name="today", year=today.year, month=today.month, day=today.day,
            hour=12, minute=0, city="Tokyo", nation="JP",
        )
        return _SIGN_JA.get(subject.moon["sign"], subject.moon["sign"])
    except Exception:
        return "不明"
