from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.config import get_settings
from app.database import (
    get_pack,
    get_purchase_by_id,
    get_stats,
    is_admin,
    update_purchase_status,
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
        "Stats:\n"
        f"Packs: {stats['packs_count']}\n"
        f"Purchases: {stats['purchases_count']}\n"
        f"Revenue: {stats['revenue_stars']}⭐"
    )


@router.message(Command("confirm"))
async def cmd_confirm(message: Message) -> None:
    if not _is_allowed(message.from_user.id):
        return

    parts = (message.text or "").split()
    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer("Usage: /confirm <purchase_id>")
        return

    purchase_id = int(parts[1])
    purchase = get_purchase_by_id(purchase_id)
    if not purchase:
        await message.answer("Purchase not found.")
        return

    if purchase["status"] == "completed":
        await message.answer("Purchase is already completed.")
        return

    pack = get_pack(int(purchase["pack_id"]))
    if not pack:
        await message.answer("Pack not found.")
        return

    s3 = get_s3_client()
    try:
        url = s3.generate_download_url(pack["s3_key"], expires_in=86400)
    except Exception:
        await message.answer("Could not generate download link.")
        return

    update_purchase_status(purchase_id, "completed")

    try:
        await message.bot.send_message(
            purchase["user_id"],
            "Your purchase was confirmed manually. Download link (valid for 24 hours):\n"
            f"{url}",
        )
    except Exception:
        await message.answer("Status updated, but the user message was not sent.")
        return

    await message.answer("Purchase confirmed and download link sent to user.")


@router.message(Command("add_pack"))
async def cmd_add_pack(message: Message) -> None:
    if not _is_allowed(message.from_user.id):
        return

    settings = get_settings()
    await message.answer(
        "Use the web panel to upload new packs:\n"
        f"{settings.PANEL_BASE_URL}/packs/add"
    )
