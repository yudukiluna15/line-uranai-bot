"""
DBテーブル定義。

- User: LINEユーザー1人につき1レコード。生年月日・星座など固定情報。
- ChatLog: 鑑定のやり取り(質問・回答)を1件ずつ蓄積。
- Summary: ChatLogが一定量たまるとAIが要約して保存する。次回鑑定時のプロンプトに使う。
- Subscription: Stripeの課金状態を保持。
"""
from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime, Text, Date, Boolean, ForeignKey
from sqlalchemy.orm import relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    line_user_id = Column(String, unique=True, index=True, nullable=False)
    display_name = Column(String, nullable=True)

    birth_date = Column(Date, nullable=True)   # YYYY-MM-DD
    birth_time = Column(String, nullable=True)  # "HH:MM" 不明な場合はNone
    birth_place = Column(String, nullable=True)  # "Tokyo, Japan" など

    # 一度計算したら変わらないのでキャッシュしておく(APIコスト削減)
    sun_sign = Column(String, nullable=True)
    moon_sign = Column(String, nullable=True)
    venus_sign = Column(String, nullable=True)
    mars_sign = Column(String, nullable=True)

    # 登録フローの進行状況(生年月日をまだ聞いていない、等の管理に使う)
    onboarding_step = Column(String, default="need_birth_date")

    created_at = Column(DateTime, default=datetime.utcnow)

    chat_logs = relationship("ChatLog", back_populates="user")
    subscription = relationship("Subscription", back_populates="user", uselist=False)


class ChatLog(Base):
    __tablename__ = "chat_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    category = Column(String, nullable=True)  # "恋愛" "仕事" "健康" "総合" など
    question = Column(Text, nullable=True)     # ユーザーが実際に送った相談内容
    answer = Column(Text, nullable=True)       # AIが生成した鑑定文
    reaction = Column(String, nullable=True)   # "good" / "bad" / None

    # タロットを引いたカテゴリ(現状は「総合」のみ)で記録。
    # 今は演出に使うだけだが、将来「引いたカードの図鑑」機能を作る際の
    # 土台として、どのカードが出たかをここに残しておく。
    tarot_card = Column(String, nullable=True)         # 例: "死神"
    tarot_orientation = Column(String, nullable=True)  # "正位置" / "逆位置"

    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="chat_logs")


class Summary(Base):
    __tablename__ = "summaries"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    content = Column(Text, nullable=False)  # AIが生成した要約テキスト
    created_at = Column(DateTime, default=datetime.utcnow)


class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)

    stripe_customer_id = Column(String, nullable=True)
    stripe_subscription_id = Column(String, nullable=True)
    plan = Column(String, default="free")  # "free" / "standard" / "premium"
    status = Column(String, default="inactive")  # "active" / "trialing" / "canceled" / "inactive"
    current_period_end = Column(DateTime, nullable=True)

    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="subscription")
