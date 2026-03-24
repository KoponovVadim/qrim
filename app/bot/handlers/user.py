import logging

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.keyboards import (
    main_menu_kb,
    pack_detail_keyboard,
    packs_keyboard,
    paid_keyboard,
    payment_method_keyboard,
)
from app.bot.states import PurchaseStates
from app.bot.utils import build_audio_file, check_usdt_transaction, get_bytes_from_s3, pack_text
from app.config import get_settings
from app.database import (
    add_order,
    cancel_subscription,
    create_or_extend_subscription,
    get_admins,
    get_pack,
    get_packs,
    get_subscription,
    has_active_subscription,
    increment_pack_sold,
    set_setting,
    update_order_status,
)
from app.s3_client import get_s3_client

router = Router(name="user")
logger = logging.getLogger(__name__)


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(
        "Привет! Это магазин музыкальных паков. Открой Store App или используй меню ниже.",
        reply_markup=main_menu_kb(),
    )


@router.message(F.text == "Витрина")
async def show_catalog(message: Message) -> None:
    packs = get_packs(limit=100, offset=0)
    if not packs:
        await message.answer("Паки пока не добавлены.")
        return

    kb = packs_keyboard(packs)
    await message.answer("Выбери пак:", reply_markup=kb.as_markup())


@router.callback_query(F.data.startswith("pack:"))
async def pack_details(callback: CallbackQuery) -> None:
    pack_id = int(callback.data.split(":")[1])
    pack = get_pack(pack_id)
    if not pack:
        await callback.answer("Пак не найден", show_alert=True)
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
        await callback.answer("Пак не найден", show_alert=True)
        return

    demo_keys = pack.get("demo_keys", [])
    if not demo_keys:
        await callback.message.answer("Для этого пака пока нет демо.")
        await callback.answer()
        return

    await callback.message.answer("Отправляю демо...")

    for i, key in enumerate(demo_keys, start=1):
        try:
            audio_bytes = get_bytes_from_s3(key)
            audio_file = build_audio_file(audio_bytes, f"demo_{i}.mp3")
            await callback.message.answer_audio(audio=audio_file)
        except Exception:
            await callback.message.answer(f"Не удалось отправить демо #{i}.")

    await callback.answer()


@router.callback_query(F.data.startswith("buy:"))
async def choose_currency(callback: CallbackQuery, state: FSMContext) -> None:
    pack_id = int(callback.data.split(":")[1])
    pack = get_pack(pack_id)
    if not pack:
        await callback.answer("Пак не найден", show_alert=True)
        return

    if has_active_subscription(callback.from_user.id):
        s3 = get_s3_client()
        try:
            url = s3.generate_download_url(pack["zip_key"], expires_in=3600)
            await callback.message.answer(
                "У вас активная подписка. Вот ссылка на скачивание (1 час):\n"
                f"{url}"
            )
        except Exception:
            await callback.message.answer("Не удалось сгенерировать ссылку.")
        await callback.answer()
        return

    await state.update_data(pack_id=pack_id)
    kb = payment_method_keyboard(pack_id)
    await callback.message.answer("Выберите валюту для оплаты:", reply_markup=kb.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("paycur:"))
async def payment_instructions(callback: CallbackQuery, state: FSMContext) -> None:
    _, pack_id_raw, method = callback.data.split(":")
    pack_id = int(pack_id_raw)
    pack = get_pack(pack_id)
    if not pack:
        await callback.answer("Пак не найден", show_alert=True)
        return

    settings = get_settings()
    wallet = settings.USDT_WALLET if method.upper() == "USDT" else settings.TON_WALLET
    amount = pack["price_usdt"] if method.upper() == "USDT" else pack["price_ton"]

    await state.set_state(PurchaseStates.waiting_for_tx_hash)
    await state.update_data(pack_id=pack_id, payment_method=method.upper(), amount=amount)

    kb = paid_keyboard(pack_id)
    await callback.message.answer(
        f"Оплатите заказ:\n"
        f"Валюта: {method.upper()}\n"
        f"Сумма: {amount}\n"
        f"Кошелек: {wallet}\n\n"
        f"После оплаты нажмите кнопку ниже.",
        reply_markup=kb.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("paid:"))
async def ask_tx_hash(callback: CallbackQuery, state: FSMContext) -> None:
    if await state.get_state() != PurchaseStates.waiting_for_tx_hash.state:
        await callback.message.answer("Сначала выберите валюту оплаты.")
        await callback.answer()
        return

    await callback.message.answer("Отправьте хеш транзакции одним сообщением.")
    await callback.answer()


@router.message(PurchaseStates.waiting_for_tx_hash)
async def receive_tx_hash(message: Message, state: FSMContext) -> None:
    tx_hash = (message.text or "").strip()
    if len(tx_hash) < 8:
        await message.answer("Хеш слишком короткий. Проверьте и отправьте снова.")
        return

    data = await state.get_data()
    purchase_type = str(data.get("purchase_type", "pack"))

    if purchase_type == "subscription":
        settings = get_settings()
        ok, reason = await check_usdt_transaction(
            tx_hash=tx_hash,
            expected_amount=settings.SUBSCRIPTION_PRICE_USDT,
            wallet_address=settings.USDT_WALLET,
            tron_api_key=settings.TRON_API_KEY,
        )
        if not ok:
            await message.answer(
                "Не удалось автоматически подтвердить подписку по TX. "
                "Попробуйте позже или обратитесь к администратору."
            )
            logger.info("Subscription tx check failed for user %s: %s", message.from_user.id, reason)
            await state.clear()
            return

        sub = create_or_extend_subscription(message.from_user.id, days=settings.SUBSCRIPTION_DAYS)
        await message.answer("Подписка активирована.\n" f"Действует до: {sub['end_date']}")
        await state.clear()
        return

    pack_id = int(data["pack_id"])
    payment_method = str(data["payment_method"])
    amount = float(data["amount"])
    bundle_ids = data.get("bundle_pack_ids", []) if purchase_type == "bundle" else []

    order_id = add_order(
        user_id=message.from_user.id,
        pack_id=pack_id,
        payment_method=payment_method,
        tx_hash=tx_hash,
        amount=amount,
        status="pending",
    )

    if bundle_ids:
        set_setting(f"order_bundle_{order_id}", ",".join(str(v) for v in bundle_ids))

    settings = get_settings()

    # Auto-confirm USDT via TronGrid when transaction matches destination and amount.
    if purchase_type == "pack" and payment_method.upper() == "USDT":
        ok, reason = await check_usdt_transaction(
            tx_hash=tx_hash,
            expected_amount=amount,
            wallet_address=settings.USDT_WALLET,
            tron_api_key=settings.TRON_API_KEY,
        )
        if ok:
            pack = get_pack(pack_id)
            if pack:
                s3 = get_s3_client()
                try:
                    url = s3.generate_download_url(pack["zip_key"], expires_in=3600)
                    update_order_status(order_id, "completed")
                    increment_pack_sold(pack_id)
                    await message.answer(
                        f"Оплата подтверждена автоматически. Ссылка (1 час):\n{url}"
                    )
                    await state.clear()
                    return
                except Exception:
                    logger.exception("Failed to auto-confirm and send USDT link")
        else:
            logger.info("USDT auto-check failed for order %s: %s", order_id, reason)

    admins = set(get_admins() + settings.ADMIN_IDS)
    bundle_line = f"Бандл паки: {', '.join(str(v) for v in bundle_ids)}\n" if bundle_ids else ""
    admin_text = (
        f"Новый заказ #{order_id}\n"
        f"Пользователь: {message.from_user.id}\n"
        f"Пак: {pack_id}\n"
        f"Метод: {payment_method}\n"
        f"Сумма: {amount}\n"
        f"TX: {tx_hash}\n"
        f"{bundle_line}"
        f"Подтвердить: /confirm {order_id}\n"
        f"Панель: {settings.PANEL_BASE_URL}/orders"
    )

    for admin_id in admins:
        try:
            await message.bot.send_message(admin_id, admin_text)
        except Exception as exc:
            logger.warning("Failed to notify admin %s for order %s: %s", admin_id, order_id, exc)
            continue

    await message.answer(f"Заказ #{order_id} создан и отправлен на проверку администратору.")
    await state.clear()


@router.message(F.text == "Бесплатный пак")
async def send_free_pack(message: Message) -> None:
    settings = get_settings()
    s3 = get_s3_client()
    try:
        url = s3.generate_download_url(settings.FREE_PACK_KEY, expires_in=3600)
        await message.answer(f"Вот ссылка на бесплатный пак (действует 1 час):\n{url}")
    except Exception:
        await message.answer("Не удалось получить ссылку на бесплатный пак.")


@router.message(F.text == "Помощь")
async def help_message(message: Message) -> None:
    await message.answer(
        "Как это работает:\n"
        "1) Нажми '🚀 Открыть Store App' или 'Витрина'\n"
        "2) Послушай демо\n"
        "3) Нажми 'Купить', выбери валюту, оплати и отправь tx hash"
    )


@router.message(F.text == "Подписка")
async def subscription_menu(message: Message, state: FSMContext) -> None:
    settings = get_settings()
    sub = get_subscription(message.from_user.id)
    status_text = "Нет активной подписки"
    if sub and sub.get("status") == "active":
        status_text = f"Активна до: {sub['end_date']}"

    await state.set_state(PurchaseStates.waiting_for_tx_hash)
    await state.update_data(
        purchase_type="subscription",
        payment_method="USDT",
        amount=settings.SUBSCRIPTION_PRICE_USDT,
        pack_id=0,
    )

    await message.answer(
        f"Подписка\n{status_text}\n\n"
        f"Цена: {settings.SUBSCRIPTION_PRICE_USDT} USDT за {settings.SUBSCRIPTION_DAYS} дней.\n"
        "Чтобы продлить подписку, отправьте tx hash платежа в USDT на основной кошелек.\n"
        "Для отмены напишите: Отменить подписку"
    )


@router.message(F.text == "Отменить подписку")
async def subscription_cancel(message: Message) -> None:
    if cancel_subscription(message.from_user.id):
        await message.answer("Подписка отменена.")
    else:
        await message.answer("Активной подписки не найдено.")


@router.message(F.text == "Бандл")
async def bundle_offer(message: Message, state: FSMContext) -> None:
    packs = get_packs(limit=3, offset=0)
    if len(packs) < 3:
        await message.answer("Для бандла нужно минимум 3 пака в каталоге.")
        return

    usdt_prices = sorted([float(p["price_usdt"]) for p in packs], reverse=True)
    ton_prices = sorted([float(p["price_ton"]) for p in packs], reverse=True)
    usdt_amount = usdt_prices[0] + usdt_prices[1]
    ton_amount = ton_prices[0] + ton_prices[1]

    pack_ids = [int(p["id"]) for p in packs]
    await state.set_state(PurchaseStates.waiting_for_tx_hash)
    await state.update_data(
        purchase_type="bundle",
        payment_method="BUNDLE_USDT",
        amount=usdt_amount,
        pack_id=pack_ids[0],
        bundle_pack_ids=pack_ids,
    )

    names = "\n".join([f"- {p['name']}" for p in packs])
    await message.answer(
        "Бандл 3 за цену 2 (фиксированный набор):\n"
        f"{names}\n\n"
        f"Сумма USDT: {usdt_amount}\n"
        f"Сумма TON: {ton_amount}\n"
        "Отправьте tx hash для ручной проверки админом."
    )
