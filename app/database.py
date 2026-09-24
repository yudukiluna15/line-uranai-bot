"""
SQLAlchemy のDB接続設定。
デフォルトはSQLite(ファイル1本)。本番運用ではDATABASE_URLを
PostgreSQLなどに変更するだけで移行できます。
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from app.config import settings

connect_args = {"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {}
engine = create_engine(settings.DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """FastAPIの依存性注入用。リクエストごとにセッションを生成・クローズする。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
