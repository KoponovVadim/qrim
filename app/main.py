from fastapi import FastAPI, Request, Response
from contextlib import asynccontextmanager
from aiogram.types import Update
from app.bot.router import bot, dp, setup_webhook, shutdown
from app.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    await setup_webhook()
    yield
    await shutdown()


app = FastAPI(lifespan=lifespan, debug=settings.DEBUG)


@app.get("/")
async def root():
    return {"status": "ok", "bot": "qrimlounge_bot"}


@app.post("/webhook")
async def webhook(request: Request):
    update_data = await request.json()
    update = Update(**update_data)
    await dp.feed_update(bot, update)
    return Response(status_code=200)


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.get("/webhook-info")
async def webhook_info():
    """Проверка webhook"""
    info = await bot.get_webhook_info()
    return {
        "url": info.url,
        "has_custom_certificate": info.has_custom_certificate,
        "pending_update_count": info.pending_update_count,
        "last_error_date": info.last_error_date,
        "last_error_message": info.last_error_message
    }
