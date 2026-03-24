from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.config import get_settings
from app.database import (
    get_setting,
    get_order,
    get_pack,
    get_stats,
    increment_pack_sold,
    is_admin,
    update_order_status,
)
from app.s3_client import get_s3_client

router = Router(name="admin")


def _is_allowed(user_id: int) -> bool:
    settings = get_settings()
    if user_id in settings.ADMIN_IDS:
        return True
    return is_admin(user_id)


@router.message(Command("stats"))
async def cmd_stats(message: Message) -> None:
    if not _is_allowed(message.from_user.id):
        return

    stats = get_stats()
    await message.answer(
        "Статистика:\n"
        f"Паков: {stats['packs_count']}\n"
        f"Заказов: {stats['orders_count']}\n"
        f"Выполнено: {stats['completed_orders']}\n"
        f"Ожидают: {stats['pending_orders']}\n"
        f"Выручка: {stats['revenue_total']}"
    )


@router.message(Command("confirm"))
async def cmd_confirm(message: Message) -> None:
    if not _is_allowed(message.from_user.id):
        return

    parts = (message.text or "").split()
    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer("Использование: /confirm <order_id>")
        return

    order_id = int(parts[1])
    order = get_order(order_id)
    if not order:
        await message.answer("Заказ не найден.")
        return

    if order["status"] == "completed":
        await message.answer("Заказ уже подтвержден.")
        return

    pack = get_pack(order["pack_id"])
    if not pack and order["payment_method"] != "BUNDLE_USDT":
        await message.answer("Пак заказа не найден.")
        return

    s3 = get_s3_client()
    try:
        if order["payment_method"] == "BUNDLE_USDT":
            bundle_raw = get_setting(f"order_bundle_{order_id}", "") or ""
            bundle_ids = [int(v) for v in bundle_raw.split(",") if v.strip().isdigit()]
            urls: list[str] = []
            for pack_id in bundle_ids:
                p = get_pack(pack_id)
                if not p:
                    continue
                urls.append(s3.generate_download_url(p["zip_key"], expires_in=3600))
            url = "\n".join(urls)
        else:
            url = s3.generate_download_url(pack["zip_key"], expires_in=3600)
    except Exception:
        await message.answer("Не удалось сгенерировать ссылку.")
        return

    update_order_status(order_id, "completed")
    if order["payment_method"] == "BUNDLE_USDT":
        bundle_raw = get_setting(f"order_bundle_{order_id}", "") or ""
        bundle_ids = [int(v) for v in bundle_raw.split(",") if v.strip().isdigit()]
        for pack_id in bundle_ids:
            increment_pack_sold(pack_id)
    else:
        increment_pack_sold(order["pack_id"])

    try:
        await message.bot.send_message(
            order["user_id"],
            f"Оплата подтверждена. Ссылка(и) на скачивание (1 час):\n{url}",
        )
    except Exception:
        await message.answer("Статус обновлен, но сообщение пользователю не отправлено.")
        return

    await message.answer("Заказ подтвержден, ссылка отправлена пользователю.")


@router.message(Command("add_pack"))
async def cmd_add_pack(message: Message) -> None:
    if not _is_allowed(message.from_user.id):
        return

    settings = get_settings()
    await message.answer(
        "Основной способ добавления паков: веб-панель.\n"
        f"Откройте: {settings.PANEL_BASE_URL}/packs/add"
    )
