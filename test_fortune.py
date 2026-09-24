"""
LINEやWebサーバーを使わず、ターミナル上で鑑定文が
生成されるかどけを確認するための簡易スクリプト。

使い方:
    python3 test_fortune.py
"""
from datetime import date

from app import astrology, ai_service

print("生年月日を入力してください(例: 1995-04-12)")
birth_date_str = input("> ")
birth_date = date.fromisoformat(birth_date_str)

print("\n星座を計算しています...")
natal_signs = astrology.calculate_natal_signs(birth_date=birth_date)
print(f"太陽:{natal_signs['sun']} / 月:{natal_signs['moon']} "
      f"/ 金星:{natal_signs['venus']} / 火星:{natal_signs['mars']}")

transit_moon = astrology.get_today_transit_moon_sign()

print("\nAIに鑑定文を書いてもらっています...")
fortune_text = ai_service.generate_fortune(
    category="総合",
    natal_signs=natal_signs,
    transit_moon_sign=transit_moon,
    tarot_card=None,
    user_summary=None,
    user_question=None,
)

print("\n===== 鑑定結果 =====")
print(fortune_text)
print("====================")
