import logging

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, LabeledPrice, Message, PreCheckoutQuery

from app.bot.keyboards import main_menu_kb, pack_detail_keyboard, packs_keyboard
from app.bot.utils import build_audio_file, get_bytes_from_s3, pack_text
from app.config import get_settings
from app.database import (
    add_purchase,
    get_pack,
    get_packs,
    get_purchase,
    increment_pack_sold,
    update_purchase_status,
)
from app.s3_client import get_s3_client

router = Router(name="user")
logger = logging.getLogger(__name__)


def _parse_purchase_payload(payload: str) -> int | None:
    if not payload.startswith("purchase_"):
        return None
    purchase_raw = payload.split("_", 1)[1]
    if not purchase_raw.isdigit():
        return None
    return int(purchase_raw)


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(
        "Welcome to Soundbot Marketplace. Open the Store App or use the menu below.",
        reply_markup=main_menu_kb(),
    )


@router.message(F.text == "Browse Packs")
async def show_catalog(message: Message) -> None:
    packs = get_packs(limit=100, offset=0)
    if not packs:
        await message.answer("No packs are available yet.")
        return

    kb = packs_keyboard(packs)
    await message.answer("Choose a pack:", reply_markup=kb.as_markup())


@router.callback_query(F.data.startswith("pack:"))
async def pack_details(callback: CallbackQuery) -> None:
    pack_id = int(callback.data.split(":")[1])
    pack = get_pack(pack_id)
    if not pack:
        await callback.answer("Pack not found.", show_alert=True)
        return

    kb = pack_detail_keyboard(pack_id)
    text = pack_text(pack)

    try:
        if pack.get("cover_key"):
            cover_bytes = get_bytes_from_s3(pack["cover_key"])
            photo = build_audio_file(cover_bytes, "cover.jpg")
            await callback.message.answer_photo(photo=photo, caption=text, reply_markup=kb.as_markup())
        else:
            await callback.message.answer(text, reply_markup=kb.as_markup())
    except Exception:
        await callback.message.answer(text, reply_markup=kb.as_markup())

    await callback.answer()


@router.callback_query(F.data.startswith("demo:"))
async def send_demo(callback: CallbackQuery) -> None:
    pack_id = int(callback.data.split(":")[1])
    pack = get_pack(pack_id)
    if not pack:
        await callback.answer("Pack not found.", show_alert=True)
        return

    demo_keys = pack.get("demo_keys", [])
    if not demo_keys:
        await callback.message.answer("No demo files are available for this pack yet.")
        await callback.answer()
        return

    await callback.message.answer("Sending demo tracks...")

    for i, key in enumerate(demo_keys, start=1):
        try:
            audio_bytes = get_bytes_from_s3(key)
            audio_file = build_audio_file(audio_bytes, f"demo_{i}.mp3")
            await callback.message.answer_audio(audio=audio_file)
        except Exception:
            await callback.message.answer(f"Could not send demo #{i}.")

    await callback.answer()


@router.callback_query(F.data.startswith("buy:"))
async def buy_with_stars(callback: CallbackQuery) -> None:
    pack_id = int(callback.data.split(":")[1])
    pack = get_pack(pack_id)
    if not pack:
        await callback.answer("Pack not found.", show_alert=True)
        return

    stars_amount = int(pack["price_stars"])
    purchase_id = add_purchase(
        user_id=callback.from_user.id,
        product_id=pack_id,
        stars_amount=stars_amount,
        status="pending",
    )

    try:
        await callback.message.answer_invoice(
            title=pack["name"],
            description=pack.get("description") or "Sample pack",
            payload=f"purchase_{purchase_id}",
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice(label="Sample Pack", amount=stars_amount)],
            start_parameter="buy_pack",
            need_name=False,
            need_phone_number=False,
            need_email=False,
            need_shipping_address=False,
        )
    except Exception:
        logger.exception("Failed to send invoice for purchase %s", purchase_id)
        update_purchase_status(purchase_id, "failed")
        await callback.message.answer("Could not create invoice. Please try again later.")

    await callback.answer()


@router.pre_checkout_query()
async def handle_pre_checkout(pre_checkout_query: PreCheckoutQuery) -> None:
    await pre_checkout_query.answer(ok=True)


@router.message(F.successful_payment)
async def handle_successful_payment(message: Message) -> None:
    successful_payment = message.successful_payment
    if not successful_payment:
        return

    purchase_id = _parse_purchase_payload(successful_payment.invoice_payload)
    if not purchase_id:
        await message.answer("Payment received, but payload is invalid. Please contact support.")
        logger.error("Invalid invoice payload: %s", successful_payment.invoice_payload)
        return

    purchase = get_purchase(purchase_id)
    if not purchase:
        await message.answer("Payment received, but purchase record is missing. Please contact support.")
        logger.error("Purchase %s not found after successful payment", purchase_id)
        return

    if purchase["status"] == "completed":
        await message.answer("Payment was already processed. Please check your previous message for the download link.")
        return

    pack = get_pack(int(purchase["product_id"]))
    if not pack:
        update_purchase_status(
            purchase_id,
            "failed",
            telegram_payment_charge_id=successful_payment.telegram_payment_charge_id,
        )
        await message.answer("Payment received, but the pack is no longer available. Please contact support.")
        logger.error("Pack %s not found for purchase %s", purchase["product_id"], purchase_id)
        return

    s3 = get_s3_client()
    try:
        url = s3.generate_download_url(pack["zip_key"], expires_in=86400)
    except Exception:
        logger.exception("Failed to generate signed URL for purchase %s", purchase_id)
        await message.answer("Payment was successful, but we could not generate a download link. Please contact support.")
        return

    update_purchase_status(
        purchase_id,
        "completed",
        telegram_payment_charge_id=successful_payment.telegram_payment_charge_id,
    )
    increment_pack_sold(int(purchase["product_id"]))

    await message.answer(
        "Payment successful. Your download link is valid for 24 hours:\n"
        f"{url}\n\n"
        "If the link expires, contact support and include your payment receipt."
    )


@router.message(F.text == "Help")
async def help_message(message: Message) -> None:
    await message.answer(
        "How it works:\n"
        "1. Open Store App or tap Browse Packs\n"
        "2. Listen to demos\n"
        "3. Tap Buy with Stars and complete payment\n"
        "4. Get your temporary download link automatically"
    )
