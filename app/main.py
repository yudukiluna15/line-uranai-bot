"""
FastAPIアプリのエントリーポイント。

エンドポイント:
- POST /webhook/line   : LINEからのメッセージイベントを受信
- POST /webhook/stripe : Stripeからの決済イベントを受信
- GET  /health         : 死活監視用

起動時にAPSchedulerを開始し、DAILY_PUSH_ENABLEDがtrueの場合、
毎日DAILY_PUSH_HOUR:DAILY_PUSH_MINUTE(日本時間)に
有料会員への自動配信(push_service)を実行する。
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Header, Depends, HTTPException
from sqlalchemy.orm import Session
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import settings
from app.database import Base, engine, get_db
from app import line_bot, payment, push_service

# 初回起動時にテーブルを作成(本番ではAlembic等でのマイグレーション管理を推奨)
Base.metadata.create_all(bind=engine)

scheduler = BackgroundScheduler(timezone="Asia/Tokyo")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.DAILY_PUSH_ENABLED:
        scheduler.add_job(
            push_service.send_daily_fortune_to_subscribers,
            trigger=CronTrigger(
                hour=settings.DAILY_PUSH_HOUR,
                minute=settings.DAILY_PUSH_MINUTE,
                timezone="Asia/Tokyo",
            ),
            id="daily_fortune_push",
            replace_existing=True,
        )
        scheduler.start()
    yield
    if scheduler.running:
        scheduler.shutdown(wait=False)


app = FastAPI(title="AI占いLINEボット", lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/webhook/line")
async def line_webhook(
    request: Request,
    x_line_signature: str = Header(None),
    db: Session = Depends(get_db),
):
    body = (await request.body()).decode("utf-8")
    try:
        events = line_bot.parse_webhook_body(body, x_line_signature)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid signature")

    line_bot.handle_events(db, events)
    return {"status": "ok"}


@app.post("/webhook/stripe")
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(None, alias="Stripe-Signature"),
    db: Session = Depends(get_db),
):
    payload = await request.body()
    try:
        event = payment.verify_and_parse_event(payload, stripe_signature)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid Stripe signature")

    payment.handle_webhook_event(db, event)
    return {"status": "ok"}
