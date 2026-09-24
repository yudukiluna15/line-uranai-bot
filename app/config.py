"""
環境変数をまとめて読み込む設定モジュール。
.env ファイル(.env.example を参考に作成)から値を読み込みます。
"""
import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    # LINE Messaging API
    LINE_CHANNEL_SECRET: str = os.getenv("LINE_CHANNEL_SECRET", "")
    LINE_CHANNEL_ACCESS_TOKEN: str = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")

    # Claude API (Anthropic)
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    CLAUDE_MODEL: str = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")

    # Stripe
    STRIPE_SECRET_KEY: str = os.getenv("STRIPE_SECRET_KEY", "")
    STRIPE_WEBHOOK_SECRET: str = os.getenv("STRIPE_WEBHOOK_SECRET", "")
    STRIPE_PRICE_ID_STANDARD: str = os.getenv("STRIPE_PRICE_ID_STANDARD", "")
    STRIPE_PRICE_ID_PREMIUM: str = os.getenv("STRIPE_PRICE_ID_PREMIUM", "")
    STRIPE_SUCCESS_URL: str = os.getenv("STRIPE_SUCCESS_URL", "https://example.com/success")
    STRIPE_CANCEL_URL: str = os.getenv("STRIPE_CANCEL_URL", "https://example.com/cancel")

    # DB
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./uranai.db")

    # 会話ログがこの件数を超えたら要約を作る
    SUMMARY_THRESHOLD: int = int(os.getenv("SUMMARY_THRESHOLD", "6"))

    # 無料ユーザーが1日に使える鑑定回数
    FREE_DAILY_LIMIT: int = int(os.getenv("FREE_DAILY_LIMIT", "1"))

    # キャラクターの表示名・アイコン画像URL(LINEのメッセージ送信者表示に使う)
    # アイコンはHTTPSで公開されたPNG/JPEG画像のURLを指定する(正方形推奨)
    LUNA_NAME: str = os.getenv("LUNA_NAME", "ルナ")
    LUNA_ICON_URL: str = os.getenv("LUNA_ICON_URL", "")
    GEN_NAME: str = os.getenv("GEN_NAME", "玄")
    GEN_ICON_URL: str = os.getenv("GEN_ICON_URL", "")

    # 毎日の自動配信(有料会員のみ)を行う時刻(24時間表記、日本時間)
    DAILY_PUSH_ENABLED: bool = os.getenv("DAILY_PUSH_ENABLED", "true").lower() == "true"
    DAILY_PUSH_HOUR: int = int(os.getenv("DAILY_PUSH_HOUR", "8"))
    DAILY_PUSH_MINUTE: int = int(os.getenv("DAILY_PUSH_MINUTE", "0"))

    # タロットカード画像を用意した場合、ここにベースURLを設定すると
    # 「今日の1枚」ボタンで画像を返信できるようになる(未設定なら画像は送らない)。
    # 例: https://example.com/tarot/ → https://example.com/tarot/死神.png のように解決する
    TAROT_IMAGE_BASE_URL: str = os.getenv("TAROT_IMAGE_BASE_URL", "")


settings = Settings()
