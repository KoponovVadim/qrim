from fastapi import FastAPI, Request, Response
from contextlib import asynccontextmanager
from aiogram.types import Update
from app.bot.router import bot, dp, shutdown
from app.config import settings
import logging
import sys

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, stream=sys.stdout, force=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Устанавливаем webhook при старте
    try:
        result = await bot.set_webhook(settings.WEBHOOK_URL, drop_pending_updates=True)
        logger.info(f"✅ Webhook установлен: {settings.WEBHOOK_URL}, result: {result}")
        print(f"✅ Webhook установлен: {settings.WEBHOOK_URL}", flush=True)
    except Exception as e:
        logger.error(f"⚠️ Ошибка установки webhook: {e}")
        print(f"⚠️ Ошибка установки webhook: {e}", flush=True)
    
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


@app.post("/set-webhook")
async def set_webhook():
    """Установить webhook вручную"""
    try:
        await bot.set_webhook(settings.WEBHOOK_URL, drop_pending_updates=True)
        info = await bot.get_webhook_info()
        return {
            "status": "ok",
            "webhook_url": info.url,
            "pending_update_count": info.pending_update_count
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/webhook-info")
async def webhook_info():
    """Проверка webhook"""
    try:
        info = await bot.get_webhook_info()
        return {
            "url": info.url,
            "has_custom_certificate": info.has_custom_certificate,
            "pending_update_count": info.pending_update_count,
            "last_error_date": info.last_error_date,
            "last_error_message": info.last_error_message
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}
