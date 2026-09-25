"""
ユーザーが送ってくる生年月日の文字列を、できるだけ柔軟に解釈するための
パーサー。以下の形式に対応する:

- ハイフン区切り:1995-04-12
- スラッシュ区切り:1995/04/12
- 区切りなし:19950412
- 西暦の漢字表記:1995年4月12日
- 和暦(元号):平成7年4月12日 / 令和元年5月1日 のように「元年」も可
"""
import re
from datetime import date

ERA_START_YEARS = {
    "明治": 1868,
    "大正": 1912,
    "昭和": 1926,
    "平成": 1989,
    "令和": 2019,
}

_ERA_PATTERN = "|".join(ERA_START_YEARS.keys())


def parse_birth_date(text: str) -> date | None:
    """
    ユーザーが送った文字列から生年月日(date)を取り出す。
    どの形式にも当てはまらない場合、または日付として存在しない
    (2月30日など)場合はNoneを返す。
    """
    text = text.strip()

    # 和暦(元号)形式:平成7年4月12日 / 令和元年5月1日
    era_match = re.fullmatch(
        rf"({_ERA_PATTERN})\s*(元|\d{{1,2}})\s*年\s*(\d{{1,2}})\s*月\s*(\d{{1,2}})\s*日",
        text,
    )
    if era_match:
        era, era_year_str, month_str, day_str = era_match.groups()
        era_year = 1 if era_year_str == "元" else int(era_year_str)
        year = ERA_START_YEARS[era] + era_year - 1
        return _safe_date(year, int(month_str), int(day_str))

    # 西暦の漢字表記:1995年4月12日
    kanji_match = re.fullmatch(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日", text)
    if kanji_match:
        y, m, d = (int(v) for v in kanji_match.groups())
        return _safe_date(y, m, d)

    # 数字のみ・ハイフン区切り・スラッシュ区切り:1995-04-12 / 1995/04/12 / 19950412
    digit_match = re.fullmatch(r"(\d{4})[-/]?(\d{1,2})[-/]?(\d{1,2})", text)
    if digit_match:
        y, m, d = (int(v) for v in digit_match.groups())
        return _safe_date(y, m, d)

    return None


def _safe_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None
