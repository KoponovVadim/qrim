from aiogram.types import InlineKeyboardButton, KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def main_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🛍 Shop")],
            [KeyboardButton(text="🎁 Free pack")],
            [KeyboardButton(text="ℹ️ Help")],
        ],
        resize_keyboard=True,
    )


def packs_keyboard(packs: list[dict]) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    for pack in packs:
        kb.row(InlineKeyboardButton(text=pack["name"], callback_data=f"pack:{pack['id']}"))
    return kb


def pack_detail_keyboard(pack: dict) -> InlineKeyboardBuilder:
    pack_id = int(pack["id"])
    starter = int(pack.get("price_starter", 100))
    producer = int(pack.get("price_producer", 300))
    collector = int(pack.get("price_collector", 600))

    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="🎧 Demos", callback_data=f"demo:{pack_id}"))
    kb.row(
        InlineKeyboardButton(text=f"Buy Starter ({starter}⭐)", callback_data=f"buy:{pack_id}:starter")
    )
    kb.row(
        InlineKeyboardButton(text=f"Buy Producer ({producer}⭐)", callback_data=f"buy:{pack_id}:producer")
    )
    kb.row(
        InlineKeyboardButton(text=f"Buy Collector ({collector}⭐)", callback_data=f"buy:{pack_id}:collector")
    )
    return kb
