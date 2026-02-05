from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from app.config import settings
from app.bot.handlers import router


bot = Bot(
    token=settings.TG_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)

dp = Dispatcher()
dp.include_router(router)


async def setup_webhook():
    await bot.set_webhook(settings.WEBHOOK_URL, drop_pending_updates=True)


async def shutdown():
    await bot.delete_webhook(drop_pending_updates=True)
    await bot.session.close()
