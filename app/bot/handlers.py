from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command
from app.services.ai import ai_service
from app.services.redis_client import redis_client
from app.services.sheets import sheets_client
from app.services.booking import booking_service
from app.models.schemas import BookingRequest


router = Router()


@router.message(Command("start"))
async def cmd_start(message: Message):
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📅 Забронировать", callback_data="action_book"),
            InlineKeyboardButton(text="📋 Меню", callback_data="action_menu")
        ]
    ])
    
    await message.answer(
        "Привет! 👋 Я онлайн-менеджер QRIM Lounge.\n\n"
        "Могу:\n"
        "📍 Рассказать о заведении\n"
        "📅 Забронировать стол\n"
        "🎉 Показать афишу\n"
        "💰 Сообщить цены\n\n"
        "Просто напиши, что тебя интересует!",
        reply_markup=keyboard
    )


@router.message(Command("reset"))
async def cmd_reset(message: Message):
    redis_client.delete_state(message.from_user.id)
    await message.answer("Диалог сброшен ✅")


@router.message(Command("menu"))
async def cmd_menu(message: Message):
    # Перенаправляем на обработчик меню
    from app.models.schemas import AIIntent
    ai_response = AIIntent(intent="menu", slots={}, response_text="")
    await handle_menu(message, ai_response, "покажи меню")


@router.callback_query(F.data == "action_book")
async def callback_book(callback):
    await callback.message.answer("Отлично! Давайте забронируем столик 🎉\n\nНапишите дату, время и количество гостей.\nНапример: 'Хочу забронировать на завтра в 20:00, будет 4 человека'")
    await callback.answer()


@router.callback_query(F.data == "action_menu")
async def callback_menu(callback):
    from app.models.schemas import AIIntent
    ai_response = AIIntent(intent="menu", slots={}, response_text="")
    await handle_menu(callback.message, ai_response, "покажи меню")
    await callback.answer()


@router.message(F.text)
async def handle_message(message: Message):
    user_id = message.from_user.id
    user_text = message.text
    
    # Получаем контекст
    context = redis_client.get_context(user_id)
    
    # Сначала определяем intent без данных
    ai_response = ai_service.process_message(user_text, context)
    
    # Сохраняем в контекст
    redis_client.add_to_context(user_id, {"role": "user", "content": user_text})
    
    # Обработка по intent
    if ai_response.intent == "info":
        await handle_info(message, ai_response, user_text, context)
    
    elif ai_response.intent == "events":
        await handle_events(message, user_text, context)
    
    elif ai_response.intent == "prices":
        await handle_prices(message, user_text, context)
    
    elif ai_response.intent == "book":
        await handle_booking(message, ai_response)
    
    elif ai_response.intent == "cancel":
        await handle_cancel(message, ai_response)
    
    elif ai_response.intent == "modify":
        await handle_modify(message, ai_response)
    
    elif ai_response.intent == "menu":
        await handle_menu(message, ai_response, user_text, context)
    
    elif ai_response.intent == "order":
        await handle_order(message, ai_response)
    
    else:
        redis_client.add_to_context(user_id, {"role": "assistant", "content": ai_response.response_text})
        await message.answer(ai_response.response_text)


async def handle_info(message: Message, ai_response, user_text: str, context: list):
    venue = sheets_client.get_venue_info()
    
    # Формируем данные для AI
    data_context = {
        "venue_name": venue.name,
        "city": venue.city,
        "address": venue.address,
        "phone": venue.phone,
        "timezone": venue.timezone,
        "work_sun_thu": venue.work_sun_thu,
        "work_fri_sat": venue.work_fri_sat
    }
    
    # Пересоздаем ответ с данными
    ai_response = ai_service.process_message(user_text, context, data_context)
    
    redis_client.add_to_context(message.from_user.id, {"role": "assistant", "content": ai_response.response_text})
    await message.answer(ai_response.response_text)


async def handle_events(message: Message, user_text: str, context: list):
    events = sheets_client.get_events(limit=5)
    
    if not events:
        data_context = {"events": "Нет запланированных мероприятий"}
    else:
        events_list = []
        for event in events:
            events_list.append(f"{event.title} ({event.date_from} {event.time_from}-{event.time_to}): {event.description}")
        data_context = {"events": "; ".join(events_list)}
    
    # AI формирует ответ
    ai_response = ai_service.process_message(user_text, context, data_context)
    
    redis_client.add_to_context(message.from_user.id, {"role": "assistant", "content": ai_response.response_text})
    await message.answer(ai_response.response_text)


async def handle_prices(message: Message, user_text: str, context: list):
    try:
        prices = sheets_client.get_prices()
    except Exception as e:
        print(f"ERROR getting prices: {e}", flush=True)
        await message.answer("Уточню прайс у администратора!")
        return
    
    if not prices:
        await message.answer("Уточню прайс у администратора!")
        return
    
    # Формируем данные для AI
    prices_by_category = {}
    for price in prices:
        if price.category not in prices_by_category:
            prices_by_category[price.category] = []
        price_str = f"{price.name} - {price.price} руб"
        if price.description:
            price_str += f" ({price.description})"
        prices_by_category[price.category].append(price_str)
    
    data_context = {
        "prices_hookah": ", ".join(prices_by_category.get('hookah', [])),
        "prices_table": ", ".join(prices_by_category.get('table', [])),
        "prices_drinks": ", ".join(prices_by_category.get('drinks', [])),
        "prices_balloons": ", ".join(prices_by_category.get('balloons', [])),
        "prices_extra": ", ".join(prices_by_category.get('extra', []))
    }
    
    # AI формирует ответ
    ai_response = ai_service.process_message(user_text, context, data_context)
    
    redis_client.add_to_context(message.from_user.id, {"role": "assistant", "content": ai_response.response_text})
    await message.answer(ai_response.response_text)


async def handle_booking(message: Message, ai_response):
    user_id = message.from_user.id
    state = redis_client.get_state(user_id) or {}
    slots = ai_response.slots
    
    # Обновляем state (только непустые значения)
    for key, value in slots.items():
        if value is not None:
            state[key] = value
    
    # Проверяем наличие всех данных
    required = ['date', 'time', 'guests', 'name', 'phone']
    missing = [f for f in required if f not in state or state[f] is None]
    
    if missing:
        redis_client.set_state(user_id, state)
        
        prompts = {
            'date': 'Укажите дату бронирования (например, 2026-02-15)',
            'time': 'Укажите время (например, 19:00)',
            'guests': 'Сколько будет гостей?',
            'name': 'Как вас зовут?',
            'phone': 'Оставьте номер телефона для связи'
        }
        
        await message.answer(prompts.get(missing[0], f"Укажите {missing[0]}"))
        return
    
    # Проверяем дубликаты - уже есть бронь на эту дату?
    if sheets_client.check_duplicate_booking(state['phone'], state['date']):
        await message.answer(
            f"У вас уже есть подтверждённая бронь на {state['date']} 📅\n"
            "Если нужно изменить — позвоните нам или напишите /reset для новой брони."
        )
        redis_client.delete_state(user_id)
        return
    
    # Все данные есть — проверяем доступность
    availability = booking_service.check_availability(
        state['date'],
        state['time'],
        int(state['guests'])
    )
    
    if not availability.available:
        await message.answer(
            f"К сожалению, на {state['date']} в {state['time']} нет свободных мест 😔\n"
            "Попробуйте другое время или дату."
        )
        redis_client.delete_state(user_id)
        return
    
    # Создаём бронь
    booking_request = BookingRequest(
        date=state['date'],
        time=state['time'],
        guests=int(state['guests']),
        name=state['name'],
        phone=state['phone']
    )
    
    booking_id = booking_service.create_booking(booking_request, availability.table_id)
    
    if booking_id:
        await message.answer(
            f"✅ Отлично! Столик забронирован:\n\n"
            f"📋 Номер брони: {booking_id}\n"
            f"📅 {state['date']} в {state['time']}\n"
            f"👥 Гостей: {state['guests']}\n"
            f"👤 {state['name']}\n"
            f"📱 {state['phone']}\n\n"
            "Ждём вас! Если планы изменятся — напишите нам."
        )
    else:
        await message.answer("Произошла ошибка при бронировании. Позвоните нам напрямую!")
    
    redis_client.delete_state(user_id)


async def handle_cancel(message: Message, ai_response):
    user_id = message.from_user.id
    slots = ai_response.slots
    
    # Нужен телефон для поиска брони
    if not slots.get('phone'):
        await message.answer("Укажите номер телефона, на который оформлена бронь")
        return
    
    # Ищем брони по телефону
    bookings = sheets_client.find_booking_by_phone(slots['phone'])
    
    if not bookings:
        await message.answer("Активных броней на этот номер не найдено 🤷")
        return
    
    # Если одна бронь - отменяем сразу
    if len(bookings) == 1:
        booking = bookings[0]
        if sheets_client.cancel_booking(booking.booking_id):
            await message.answer(
                f"✅ Бронь отменена:\n\n"
                f"📋 {booking.booking_id}\n"
                f"📅 {booking.date} в {booking.time}\n"
                f"👥 Гостей: {booking.guests}\n\n"
                "Будем рады видеть вас в другой раз!"
            )
        else:
            await message.answer("Ошибка отмены брони. Позвоните нам напрямую.")
        return
    
    # Если несколько броней - показываем список
    text = "У вас несколько активных броней:\n\n"
    for b in bookings:
        text += f"📋 {b.booking_id}\n📅 {b.date} в {b.time}, {b.guests} чел.\n\n"
    text += "Укажите номер брони (например, B001) для отмены"
    await message.answer(text)


async def handle_modify(message: Message, ai_response):
    user_id = message.from_user.id
    slots = ai_response.slots
    
    # Нужен телефон для поиска брони
    if not slots.get('phone'):
        await message.answer("Укажите номер телефона, на который оформлена бронь")
        return
    
    # Ищем брони по телефону
    bookings = sheets_client.find_booking_by_phone(slots['phone'])
    
    if not bookings:
        await message.answer("Активных броней на этот номер не найдено 🤷")
        return
    
    # Если одна бронь и есть что менять
    if len(bookings) == 1 and (slots.get('guests') or slots.get('time')):
        booking = bookings[0]
        updates = {}
        if slots.get('guests'):
            updates['guests'] = slots['guests']
        if slots.get('time'):
            updates['time'] = slots['time']
        
        if sheets_client.update_booking(booking.booking_id, updates):
            text = f"✅ Бронь обновлена:\n\n📋 {booking.booking_id}\n📅 {booking.date}"
            if 'time' in updates:
                text += f" в {updates['time']}"
            else:
                text += f" в {booking.time}"
            if 'guests' in updates:
                text += f"\n👥 Гостей: {updates['guests']}"
            await message.answer(text)
        else:
            await message.answer("Ошибка обновления брони. Позвоните нам напрямую.")
        return
    
    # Если несколько броней - показываем список
    text = "У вас несколько активных броней:\n\n"
    for b in bookings:
        text += f"📋 {b.booking_id}\n📅 {b.date} в {b.time}, {b.guests} чел.\n\n"
    text += "Укажите номер брони и что хотите изменить"
    await message.answer(text)


async def handle_menu(message: Message, ai_response, user_text: str = None, context: list = None):
    slots = ai_response.slots
    category = slots.get('category')
    
    menu_items = sheets_client.get_menu(category)
    
    if not menu_items:
        await message.answer("Меню временно недоступно 🤷")
        return
    
    # Группируем по категориям
    menu_by_category = {}
    for item in menu_items:
        if item.category not in menu_by_category:
            menu_by_category[item.category] = []
        item_str = f"{item.name}"
        if item.description:
            item_str += f" ({item.description})"
        item_str += f" - {item.price} руб"
        menu_by_category[item.category].append(item_str)
    
    # Формируем данные для AI
    data_context = {}
    for cat, items in menu_by_category.items():
        data_context[f"menu_{cat}"] = "; ".join(items)
    
    # AI формирует ответ
    ai_response = ai_service.process_message(user_text or "покажи меню", context or [], data_context)
    
    redis_client.add_to_context(message.from_user.id, {"role": "assistant", "content": ai_response.response_text})
    await message.answer(ai_response.response_text)


async def handle_order(message: Message, ai_response):
    slots = ai_response.slots
    
    # Нужен телефон для поиска брони
    if not slots.get('phone'):
        await message.answer("Укажите номер телефона, на который оформлена бронь 📱")
        return
    
    # Ищем активные брони
    try:
        bookings = sheets_client.find_booking_by_phone(slots['phone'])
    except Exception as e:
        print(f"ERROR finding booking: {e}", flush=True)
        await message.answer("Произошла ошибка при поиске брони. Попробуйте еще раз.")
        return
    
    if not bookings:
        await message.answer("Сначала забронируйте столик! 😊\n\nНапишите 'хочу забронировать' или нажмите кнопку 📅 Забронировать")
        return
    
    # Если несколько броней - берём первую активную
    booking = bookings[0]
    
    # Обрабатываем заказ
    items = slots.get('items', [])
    
    if not items:
        await message.answer("Что именно хотите заказать? Могу показать меню! 📋")
        return
    
    # Создаём заказы
    total = 0
    created_orders = []
    not_found = []
    
    # Получаем меню для проверки цен
    try:
        menu = sheets_client.get_menu()
        menu_dict = {item.name.lower(): item for item in menu}
        
        for item in items:
            item_name = item.get('name', '').strip()
            quantity = int(item.get('quantity', 1))
            
            # Ищем в меню (нечеткий поиск)
            menu_item = None
            item_name_lower = item_name.lower()
            
            # Точное совпадение
            if item_name_lower in menu_dict:
                menu_item = menu_dict[item_name_lower]
            else:
                # Частичное совпадение
                for menu_key, menu_val in menu_dict.items():
                    if item_name_lower in menu_key or menu_key in item_name_lower:
                        menu_item = menu_val
                        break
            
            if menu_item:
                order_id = sheets_client.create_order(
                    booking.booking_id,
                    menu_item.name,
                    quantity,
                    menu_item.price * quantity
                )
                total += menu_item.price * quantity
                created_orders.append(f"{menu_item.name} x{quantity} — {menu_item.price * quantity} ₽")
            else:
                not_found.append(item_name)
        
        if created_orders:
            text = f"✅ Заказ оформлен к брони {booking.booking_id}:\n\n"
            text += "\n".join(created_orders)
            text += f"\n\n💰 Итого: {total} ₽"
            if not_found:
                text += f"\n\n⚠️ Не найдено в меню: {', '.join(not_found)}"
            text += "\n\nПриготовим к вашему приходу! 🔥"
            redis_client.add_to_context(message.from_user.id, {"role": "assistant", "content": text})
            await message.answer(text)
        else:
            await message.answer("Не удалось найти указанные позиции в меню 🤷\n\nПосмотрите меню: /menu")
    
    except Exception as e:
        print(f"ERROR creating order: {e}", flush=True)
        await message.answer("Произошла ошибка при оформлении заказа. Попробуйте еще раз или позвоните нам.")
