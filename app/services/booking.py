from datetime import datetime, timedelta
from typing import Optional
from app.services.sheets import sheets_client
from app.models.schemas import BookingSlot, BookingRequest


class BookingService:
    def __init__(self):
        self.sheets = sheets_client
    
    def check_availability(self, date: str, time: str, guests: int) -> BookingSlot:
        """Проверяет доступность столов на дату и время"""
        # Получаем активные столы и брони
        tables = self.sheets.get_tables()
        bookings = self.sheets.get_bookings(date)
        
        # Ищем свободный стол подходящей вместимости
        for table in tables:
            if table.capacity < guests:
                continue
            
            # Проверяем занятость (буфер 2 часа)
            occupied = False
            for booking in bookings:
                if booking.table_id == table.table_id and booking.status != 'cancelled':
                    booking_time = datetime.strptime(booking.time, '%H:%M')
                    request_time = datetime.strptime(time, '%H:%M')
                    diff = abs((booking_time - request_time).total_seconds() / 60)
                    if diff < 120:  # 2 часа буфер
                        occupied = True
                        break
            
            if not occupied:
                return BookingSlot(
                    date=date,
                    time=time,
                    guests=guests,
                    available=True,
                    table_id=table.table_id
                )
        
        return BookingSlot(
            date=date,
            time=time,
            guests=guests,
            available=False
        )
    
    def create_booking(self, booking: BookingRequest, table_id: str) -> str:
        """Создаёт бронь, возвращает booking_id"""
        booking_data = {
            'date': booking.date,
            'time': booking.time,
            'guests': booking.guests,
            'table_id': table_id,
            'name': booking.name,
            'phone': booking.phone,
            'source': 'telegram',
            'status': 'confirmed'
        }
        return self.sheets.create_booking(booking_data)


booking_service = BookingService()
