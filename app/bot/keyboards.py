from aiogram.types import InlineKeyboardButton, KeyboardButton, ReplyKeyboardMarkup, WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.config import get_settings


def main_menu_kb() -> ReplyKeyboardMarkup:
    settings = get_settings()
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🚀 Открыть Store App", web_app=WebAppInfo(url=settings.WEB_APP_URL))],
            [KeyboardButton(text="Витрина")],
            [KeyboardButton(text="Подписка"), KeyboardButton(text="Бандл")],
            [KeyboardButton(text="Бесплатный пак"), KeyboardButton(text="Помощь")],
        ],
        resize_keyboard=True,
    )


def packs_keyboard(packs: list[dict]) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    for pack in packs:
        kb.row(
            InlineKeyboardButton(
                text=f"{pack['name']} | {pack['price_usdt']} USDT / {pack['price_ton']} TON",
                callback_data=f"pack:{pack['id']}",
            )
        )
    return kb


def pack_detail_keyboard(pack_id: int) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="🎧 Демо", callback_data=f"demo:{pack_id}"))
    kb.row(InlineKeyboardButton(text="💰 Купить", callback_data=f"buy:{pack_id}"))
    return kb


def payment_method_keyboard(pack_id: int) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="USDT", callback_data=f"paycur:{pack_id}:USDT"))
    kb.row(InlineKeyboardButton(text="TON", callback_data=f"paycur:{pack_id}:TON"))
    return kb


def paid_keyboard(pack_id: int) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="Я оплатил", callback_data=f"paid:{pack_id}"))
    return kb
