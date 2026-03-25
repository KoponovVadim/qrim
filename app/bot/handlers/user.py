import logging
from datetime import datetime

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.filters.command import CommandObject
from aiogram.types import CallbackQuery, LabeledPrice, Message, PreCheckoutQuery

from app.bot.keyboards import main_menu_kb, pack_detail_keyboard, packs_keyboard
from app.bot.utils import build_audio_file, get_bytes_from_s3, is_http_url, pack_text
from app.config import get_settings
from app.database import (
    add_purchase,
    get_pack,
    get_packs,
    get_purchase,
    get_purchase_by_id,
    get_user_purchases,
    update_purchase_status,
)
from app.s3_client import get_s3_client

router = Router(name="user")
logger = logging.getLogger(__name__)

LICENSE_FIELD = {
    "starter": "price_starter",
    "producer": "price_producer",
    "collector": "price_collector",
}


def _parse_buy_command(value: str) -> tuple[int, str] | None:
    if not value.startswith("buy_"):
        return None
    parts = value.split("_")
    if len(parts) < 3:
        return None
    pack_raw = parts[1]
    license_type = parts[2].strip().lower()
    if not pack_raw.isdigit() or license_type not in LICENSE_FIELD:
        return None
    return int(pack_raw), license_type


async def _send_invoice_for_pack(message: Message, pack_id: int, license_type: str) -> None:
    pack = get_pack(pack_id)
    if not pack:
        await message.answer("Pack not found.")
        return

    price_field = LICENSE_FIELD[license_type]
    stars_amount = int(pack[price_field])
    purchase_id = add_purchase(
        user_id=message.from_user.id,
        pack_id=pack_id,
        license_type=license_type,
        stars_amount=stars_amount,
        status="pending",
    )

    payload = f"pack_{pack_id}_{license_type}_{purchase_id}"
    await message.answer_invoice(
        title=pack["name"],
        description=pack.get("description") or "Sample pack",
        payload=payload,
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(label=f"Sample Pack ({license_type.title()})", amount=stars_amount)],
        start_parameter="soundbot_pack",
    )


@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject) -> None:
    if command.args:
        parsed = _parse_buy_command(command.args)
        if parsed:
            pack_id, license_type = parsed
            await _send_invoice_for_pack(message, pack_id, license_type)
            return

    await message.answer("Welcome! Choose an option below.", reply_markup=main_menu_kb())


@router.message(F.text == "🛍 Shop")
async def show_shop(message: Message) -> None:
    packs = get_packs(limit=200, offset=0)
    if not packs:
        await message.answer("No sample packs available yet.")
        return
    await message.answer("Select a sample pack:", reply_markup=packs_keyboard(packs).as_markup())


@router.message(F.text == "🎁 Free pack")
async def send_free_pack(message: Message) -> None:
    settings = get_settings()
    s3 = get_s3_client()
    try:
        url = s3.generate_download_url(settings.FREE_PACK_KEY, expires_in=86400)
    except Exception:
        logger.exception("Failed to generate free pack URL")
        await message.answer("Free pack is temporarily unavailable. Please try later.")
        return
    await message.answer(f"Your free pack link (valid 24h):\n{url}")


@router.message(F.text == "ℹ️ Help")
async def help_message(message: Message) -> None:
    await message.answer(
        "How it works:\n"
        "1. Browse the shop\n"
        "2. Pick a pack and choose license\n"
        "3. Pay with Telegram Stars\n"
        "4. Get your download link"
    )


@router.message(F.text.regexp(r"^/buy_\d+_(starter|producer|collector)$"))
async def manual_buy_command(message: Message) -> None:
    parsed = _parse_buy_command(message.text[1:])
    if not parsed:
        await message.answer("Invalid buy command.")
        return
    pack_id, license_type = parsed
    await _send_invoice_for_pack(message, pack_id, license_type)


@router.callback_query(F.data.startswith("pack:"))
async def pack_details(callback: CallbackQuery) -> None:
    pack_id = int(callback.data.split(":")[1])
    pack = get_pack(pack_id)
    if not pack:
        await callback.answer("Pack not found", show_alert=True)
        return
    await callback.message.answer(pack_text(pack), reply_markup=pack_detail_keyboard(pack).as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("demo:"))
async def send_demos(callback: CallbackQuery) -> None:
    pack_id = int(callback.data.split(":")[1])
    pack = get_pack(pack_id)
    if not pack:
        await callback.answer("Pack not found", show_alert=True)
        return

    demos = pack.get("demo_urls", [])
    if not demos:
        await callback.message.answer("No demos available for this pack yet.")
        await callback.answer()
        return

    for idx, entry in enumerate(demos, start=1):
        try:
            if is_http_url(entry):
                await callback.message.answer_audio(audio=entry)
            else:
                audio_bytes = get_bytes_from_s3(entry)
                await callback.message.answer_audio(audio=build_audio_file(audio_bytes, f"demo_{idx}.mp3"))
        except Exception:
            await callback.message.answer(f"Failed to send demo {idx}.")

    await callback.answer()


@router.callback_query(F.data.startswith("buy:"))
async def buy_pack(callback: CallbackQuery) -> None:
    _, pack_raw, license_type = callback.data.split(":", 2)
    if not pack_raw.isdigit() or license_type not in LICENSE_FIELD:
        await callback.answer("Invalid purchase data", show_alert=True)
        return

    message = callback.message
    await _send_invoice_for_pack(message, int(pack_raw), license_type)
    await callback.answer()


@router.pre_checkout_query()
async def handle_pre_checkout(pre_checkout_query: PreCheckoutQuery) -> None:
    await pre_checkout_query.answer(ok=True)


@router.message(F.successful_payment)
async def handle_successful_payment(message: Message) -> None:
    payment = message.successful_payment
    if not payment:
        return

    payload = payment.invoice_payload
    parts = payload.split("_")
    if len(parts) != 4 or parts[0] != "pack":
        await message.answer("Payment received, but payload is invalid.")
        return

    pack_raw, license_type, purchase_raw = parts[1], parts[2], parts[3]
    if not pack_raw.isdigit() or not purchase_raw.isdigit() or license_type not in LICENSE_FIELD:
        await message.answer("Payment received, but payload data is invalid.")
        return

    pack_id = int(pack_raw)
    purchase_id = int(purchase_raw)
    purchase = get_purchase_by_id(purchase_id)
    pack = get_pack(pack_id)
    if not purchase or not pack:
        await message.answer("Payment received, but purchase data is missing.")
        return

    expected_amount = int(pack[LICENSE_FIELD[license_type]])
    if int(purchase["stars_amount"]) != expected_amount:
        update_purchase_status(
            purchase_id,
            "failed",
            completed_at=datetime.utcnow().isoformat(),
            telegram_payment_charge_id=payment.telegram_payment_charge_id,
        )
        await message.answer("Payment amount mismatch. Please contact support.")
        return

    s3 = get_s3_client()
    url = s3.generate_download_url(pack["s3_key"], expires_in=86400)
    update_purchase_status(
        purchase_id,
        "completed",
        completed_at=datetime.utcnow().isoformat(),
        telegram_payment_charge_id=payment.telegram_payment_charge_id,
    )

    await message.answer(f"✅ Payment received! Download link (valid 24h):\n{url}")


@router.message(F.text == "My purchases")
async def my_purchases(message: Message) -> None:
    purchases = get_user_purchases(message.from_user.id, limit=30)
    if not purchases:
        await message.answer("You have no purchases yet.")
        return
    lines = ["Your latest purchases:"]
    for item in purchases[:10]:
        lines.append(
            f"#{item['id']} | {item.get('pack_name') or item['pack_id']} | "
            f"{item['license_type']} | {item['stars_amount']}⭐ | {item['status']}"
        )
    await message.answer("\n".join(lines))
