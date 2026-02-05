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
    prices = sheets_client.get_prices()
    
    if not prices:
        await message.answer("Уточню прайс у администратора!")
        return
    
    # Группируем по категориям
    categories = {
        'hookah': '🔥 Кальяны',
        'table': '🪑 Столы и зоны',
        'drinks': '🍹 Напитки',
        'extra': '✨ Дополнительно'
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
    
    await message.answer(text)


async def handle_booking(message: Message, ai_response):
    user_id = message.from_user.id
    state = redis_client.get_state(user_id) or {}
    slots = ai_response.slots
    
    # Обновляем state
    state.update(slots)
    
    # Проверяем наличие всех данных
    required = ['date', 'time', 'guests', 'name', 'phone']
    missing = [f for f in required if f not in state]
    
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
