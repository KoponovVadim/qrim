import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties

from app.bot.handlers import get_routers
from app.config import get_settings
from app.database import init_db


async def run_bot() -> None:
    settings = get_settings()
    if not settings.BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is required")

    init_db()

    bot = Bot(token=settings.BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
    dp = Dispatcher()

    for router in get_routers():
        dp.include_router(router)

    await dp.start_polling(bot)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_bot())


if __name__ == "__main__":
    main()
