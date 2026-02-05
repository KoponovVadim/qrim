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
    await message.answer(
        "Привет! 👋 Я онлайн-менеджер QRIM Lounge.\n\n"
        "Могу:\n"
        "📍 Рассказать о заведении\n"
        "📅 Забронировать стол\n"
        "🎉 Показать афишу\n"
        "💰 Сообщить цены\n\n"
        "Просто напиши, что тебя интересует!"
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
    await handle_menu(message, ai_response)


@router.message(F.text)
async def handle_message(message: Message):
    user_id = message.from_user.id
    user_text = message.text
    
    # Получаем контекст
    context = redis_client.get_context(user_id)
    
    # Обрабатываем через AI
    ai_response = ai_service.process_message(user_text, context)
    
    # Сохраняем в контекст
    redis_client.add_to_context(user_id, {"role": "user", "content": user_text})
    redis_client.add_to_context(user_id, {"role": "assistant", "content": ai_response.response_text})
    
    # Обработка по intent
    if ai_response.intent == "info":
        await handle_info(message, ai_response)
    
    elif ai_response.intent == "events":
        await handle_events(message)
    
    elif ai_response.intent == "prices":
        await handle_prices(message)
    
    elif ai_response.intent == "book":
        await handle_booking(message, ai_response)
    
    elif ai_response.intent == "cancel":
        await handle_cancel(message, ai_response)
    
    elif ai_response.intent == "modify":
        await handle_modify(message, ai_response)
    
    elif ai_response.intent == "menu":
        await handle_menu(message, ai_response)
    
    elif ai_response.intent == "order":
        await handle_order(message, ai_response)
    
    else:
        await message.answer(ai_response.response_text)


async def handle_info(message: Message, ai_response):
    venue = sheets_client.get_venue_info()
    info_text = f"📍 {venue.name}\n\n"
    info_text += f"Город: {venue.city}\n"
    info_text += f"Адрес: {venue.address}\n"
    info_text += f"Телефон: {venue.phone}\n\n"
    info_text += f"⏰ Режим работы:\n"
    info_text += f"Вс-Чт: {venue.work_sun_thu}\n"
    info_text += f"Пт-Сб: {venue.work_fri_sat}\n\n"
    info_text += ai_response.response_text
    
    await message.answer(info_text)


async def handle_events(message: Message):
    events = sheets_client.get_events(limit=5)
    
    if not events:
        await message.answer("Пока нет запланированных мероприятий 📅")
        return
    
    await message.answer("🎉 Ближайшие мероприятия:")
    
    for event in events:
        text = f"🎊 {event.title}\n\n"
        text += f"{event.description}\n\n"
        text += f"📅 {event.date_from}"
        if event.date_from != event.date_to:
            text += f" - {event.date_to}"
        text += f"\n⏰ {event.time_from} - {event.time_to}"
        
        if event.booking_cta:
            text += "\n\n💬 Напишите 'хочу забронировать' для бронирования"
        
        if event.image_url:
            try:
                await message.answer_photo(photo=event.image_url, caption=text)
            except Exception:
                await message.answer(text)
        else:
            await message.answer(text)


async def handle_prices(message: Message):
    try:
        prices = sheets_client.get_prices()
        print(f"DEBUG: got {len(prices) if prices else 0} prices", flush=True)
    except Exception as e:
        print(f"ERROR getting prices: {e}", flush=True)
        await message.answer("Уточню прайс у администратора!")
        return
    
    if not prices:
        await message.answer("Уточню прайс у администратора!")
        return
    
    # Группируем по категориям
    categories = {
        'hookah': '🔥 Кальяны',
        'table': '🪑 Столы и зоны',
        'drinks': '🍹 Напитки',
        'balloons': '🎈 Дополнительно',
        'extra': '✨ Ещё'
    }
    
    text = "💰 Наши цены:\n"
    
    for cat_key, cat_name in categories.items():
        cat_prices = [p for p in prices if p.category == cat_key]
        if cat_prices:
            text += f"\n{cat_name}:\n"
            for price in cat_prices:
                text += f"  • {price.name}: {price.price}"
                if price.description:
                    text += f" ({price.description})"
                text += "\n"
    
    # Убираем дублирование - отправляем только прайс
    await message.answer(text)


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


async def handle_menu(message: Message, ai_response):
    slots = ai_response.slots
    category = slots.get('category')
    
    menu_items = sheets_client.get_menu(category)
    
    if not menu_items:
        await message.answer("Меню временно недоступно 🤷")
        return
    
    # Группируем по категориям
    categories = {}
    for item in menu_items:
        if item.category not in categories:
            categories[item.category] = []
        categories[item.category].append(item)
    
    # Названия категорий
    category_names = {
        'cocktails': '🍸 Коктейли',
        'soft_drinks': '🥤 Безалкогольные',
        'hookah': '💨 Кальяны',
        'shots': '🥃 Шоты',
        'beer': '🍺 Пиво',
        'alcohol': '🍾 Алкоголь',
        'snacks': '🍿 Закуски'
    }
    
    text = "📋 Наше меню:\n\n"
    
    for cat, items in categories.items():
        cat_name = category_names.get(cat, cat)
        text += f"{cat_name}:\n"
        for item in items:
            text += f"  • {item.name}"
            if item.description:
                text += f" - {item.description}"
            text += f" — {item.price} ₽\n"
        text += "\n"
    
    text += "Для заказа напишите что хотите заказать 🔥"
    await message.answer(text)


async def handle_order(message: Message, ai_response):
    slots = ai_response.slots
    
    # Нужен телефон для поиска брони
    if not slots.get('phone'):
        await message.answer("Укажите номер телефона, на который оформлена бронь")
        return
    
    # Ищем активные брони
    bookings = sheets_client.find_booking_by_phone(slots['phone'])
    
    if not bookings:
        await message.answer("Сначала забронируйте столик! 😊")
        return
    
    # Если несколько броней - берём первую активную
    booking = bookings[0]
    
    # Обрабатываем заказ (пока просто список items)
    items = slots.get('items', [])
    
    if not items:
        await message.answer("Что именно хотите заказать? Могу показать меню!")
        return
    
    # Создаём заказы
    total = 0
    created_orders = []
    
    # Получаем меню для проверки цен
    menu = sheets_client.get_menu()
    menu_dict = {item.name.lower(): item for item in menu}
    
    for item in items:
        item_name = item.get('name', '')
        quantity = item.get('quantity', 1)
        
        # Ищем в меню
        menu_item = menu_dict.get(item_name.lower())
        if menu_item:
            order_id = sheets_client.create_order(
                booking.booking_id,
                menu_item.name,
                quantity,
                menu_item.price * quantity
            )
            total += menu_item.price * quantity
            created_orders.append(f"{menu_item.name} x{quantity} — {menu_item.price * quantity} ₽")
    
    if created_orders:
        text = f"✅ Заказ оформлен к брони {booking.booking_id}:\n\n"
        text += "\n".join(created_orders)
        text += f"\n\n💰 Итого: {total} ₽\n\nПриготовим к вашему приходу!"
        await message.answer(text)
    else:
        await message.answer("Не удалось найти указанные позиции в меню. Проверьте название или посмотрите меню: /menu")
