from aiogram.types import InlineKeyboardButton, KeyboardButton, ReplyKeyboardMarkup, WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.config import get_settings


def main_menu_kb() -> ReplyKeyboardMarkup:
    settings = get_settings()
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Open Store App", web_app=WebAppInfo(url=settings.WEB_APP_URL))],
            [KeyboardButton(text="Browse Packs")],
            [KeyboardButton(text="Help")],
        ],
        resize_keyboard=True,
    )


def packs_keyboard(packs: list[dict]) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    for pack in packs:
        kb.row(
            InlineKeyboardButton(
                text=f"{pack['name']} | {pack['price_stars']} Stars",
                callback_data=f"pack:{pack['id']}",
            )
        )
    return kb


def pack_detail_keyboard(pack_id: int) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="Listen Demo", callback_data=f"demo:{pack_id}"))
    kb.row(InlineKeyboardButton(text="Buy with Stars", callback_data=f"buy:{pack_id}"))
    return kb
