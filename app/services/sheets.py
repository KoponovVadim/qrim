from google.oauth2 import service_account
from googleapiclient.discovery import build
from typing import List, Optional, Dict
from datetime import datetime
import json
from app.config import settings
from app.models.schemas import VenueInfo, Event, Price, Table, Booking, MenuItem, Order


class SheetsClient:
    def __init__(self):
        # Загружаем credentials из файла
        credentials = service_account.Credentials.from_service_account_file(
            settings.GOOGLE_CREDENTIALS_JSON,
            scopes=['https://www.googleapis.com/auth/spreadsheets']
        )
        self.service = build('sheets', 'v4', credentials=credentials)
        self.spreadsheet_id = settings.GOOGLE_SHEETS_ID
    
    def _read_range(self, range_name: str) -> List[List]:
        result = self.service.spreadsheets().values().get(
            spreadsheetId=self.spreadsheet_id,
            range=range_name
        ).execute()
        return result.get('values', [])
    
    def _append_range(self, range_name: str, values: List[List]):
        self.service.spreadsheets().values().append(
            spreadsheetId=self.spreadsheet_id,
            range=range_name,
            valueInputOption='RAW',
            insertDataOption='INSERT_ROWS',
            body={'values': values}
        ).execute()
    
    def get_venue_info(self) -> VenueInfo:
        """Читает key-value пары из листа venue"""
        rows = self._read_range('venue!A2:B')
        venue_dict = {}
        for row in rows:
            if len(row) >= 2:
                venue_dict[row[0]] = row[1]
        
        return VenueInfo(
            name=venue_dict.get('name', 'QRIM Lounge'),
            city=venue_dict.get('city', ''),
            address=venue_dict.get('address', ''),
            phone=venue_dict.get('phone', ''),
            timezone=venue_dict.get('timezone', 'Europe/Moscow'),
            work_sun_thu=venue_dict.get('work_sun_thu', ''),
            work_fri_sat=venue_dict.get('work_fri_sat', '')
        )
    
    def get_tables(self) -> List[Table]:
        """Возвращает список активных столов"""
        rows = self._read_range('tables!A2:E')
        tables = []
        for row in rows:
            if len(row) >= 5:
                active = row[4].upper() == 'TRUE'
                if active:
                    tables.append(Table(
                        table_id=row[0],
                        name=row[1],
                        capacity=int(row[2]),
                        zone=row[3],
                        active=active
                    ))
        return tables
    
    def get_bookings(self, date: str = None) -> List[Booking]:
        """Возвращает брони на конкретную дату или все активные"""
        rows = self._read_range('bookings!A2:J')
        bookings = []
        for row in rows:
            if len(row) >= 10:
                if date is None or row[1] == date:
                    bookings.append(Booking(
                        booking_id=row[0],
                        date=row[1],
                        time=row[2],
                        guests=int(row[3]),
                        table_id=row[4],
                        name=row[5],
                        phone=row[6],
                        source=row[7],
                        status=row[8],
                        created_at=row[9]
                    ))
        return bookings
    
    def check_duplicate_booking(self, phone: str, date: str) -> bool:
        """Проверяет есть ли активная бронь у клиента на эту дату"""
        rows = self._read_range('bookings!A2:J')
        for row in rows:
            if len(row) >= 10:
                # Проверяем телефон, дату и статус confirmed
                if row[6] == phone and row[1] == date and row[8] == 'confirmed':
                    return True
        return False
    
    def find_booking_by_phone(self, phone: str) -> List[Booking]:
        """Находит все активные брони по телефону"""
        rows = self._read_range('bookings!A2:J')
        bookings = []
        for row in rows:
            if len(row) >= 10 and row[6] == phone and row[8] == 'confirmed':
                bookings.append(Booking(
                    booking_id=row[0],
                    date=row[1],
                    time=row[2],
                    guests=int(row[3]),
                    table_id=row[4],
                    name=row[5],
                    phone=row[6],
                    source=row[7],
                    status=row[8],
                    created_at=row[9]
                ))
        return bookings
    
    def cancel_booking(self, booking_id: str) -> bool:
        """Отменяет бронь (меняет статус на cancelled)"""
        try:
            rows = self._read_range('bookings!A2:J')
            for idx, row in enumerate(rows, start=2):
                if len(row) >= 10 and row[0] == booking_id:
                    # Обновляем статус
                    self.service.spreadsheets().values().update(
                        spreadsheetId=settings.GOOGLE_SHEETS_ID,
                        range=f'bookings!I{idx}',
                        valueInputOption='RAW',
                        body={'values': [['cancelled']]}
                    ).execute()
                    return True
            return False
        except Exception as e:
            print(f"Error cancelling booking: {e}", flush=True)
            return False
    
    def update_booking(self, booking_id: str, updates: dict) -> bool:
        """Обновляет бронь (гостей или время)"""
        try:
            rows = self._read_range('bookings!A2:J')
            for idx, row in enumerate(rows, start=2):
                if len(row) >= 10 and row[0] == booking_id:
                    # Обновляем нужные поля
                    if 'guests' in updates:
                        self.service.spreadsheets().values().update(
                            spreadsheetId=settings.GOOGLE_SHEETS_ID,
                            range=f'bookings!D{idx}',
                            valueInputOption='RAW',
                            body={'values': [[updates['guests']]]}
                        ).execute()
                    if 'time' in updates:
                        self.service.spreadsheets().values().update(
                            spreadsheetId=settings.GOOGLE_SHEETS_ID,
                            range=f'bookings!C{idx}',
                            valueInputOption='RAW',
                            body={'values': [[updates['time']]]}
                        ).execute()
                    return True
            return False
        except Exception as e:
            print(f"Error updating booking: {e}", flush=True)
            return False
    
    def create_booking(self, booking_data: dict) -> str:
        """Создаёт новую бронь и возвращает booking_id"""
        # Получаем последний ID из таблицы
        rows = self._read_range('bookings!A2:A')
        last_num = 0
        
        for row in rows:
            if row and row[0].startswith('B'):
                try:
                    # Извлекаем число из ID (B0001 -> 1, B0123 -> 123)
                    num = int(row[0][1:])
                    if num > last_num:
                        last_num = num
                except ValueError:
                    continue
        
        # Генерируем новый ID
        booking_id = f"B{last_num + 1:04d}"  # B0001, B0002, etc.
        created_at = datetime.now().strftime('%Y-%m-%d %H:%M')
        
        row = [[
            booking_id,
            booking_data['date'],
            booking_data['time'],
            booking_data['guests'],
            booking_data['table_id'],
            booking_data['name'],
            booking_data['phone'],
            booking_data.get('source', 'telegram'),
            booking_data.get('status', 'confirmed'),
            created_at
        ]]
        
        self._append_range('bookings!A:J', row)
        return booking_id
    
    def get_events(self, limit: int = 5) -> List[Event]:
        """Возвращает активные мероприятия"""
        rows = self._read_range('events!A2:J')
        events = []
        today = datetime.now().strftime('%Y-%m-%d')
        
        for row in rows:
            if len(row) >= 10:
                active = row[9].upper() == 'TRUE'
                date_to = row[4]
                
                # Показываем только активные и не завершившиеся
                if active and date_to >= today:
                    events.append(Event(
                        event_id=row[0],
                        title=row[1],
                        description=row[2],
                        date_from=row[3],
                        date_to=row[4],
                        time_from=row[5],
                        time_to=row[6],
                        image_url=row[7] if len(row) > 7 and row[7] else None,
                        booking_cta=row[8].upper() == 'TRUE',
                        active=active
                    ))
        
        return events[:limit]
    
    def get_prices(self, category: Optional[str] = None) -> List[Price]:
        """Возвращает активные цены, опционально по категории"""
        rows = self._read_range('prices!A2:H')
        print(f"DEBUG: read {len(rows)} rows from prices sheet", flush=True)
        prices = []
        
        for idx, row in enumerate(rows):
            print(f"DEBUG: row {idx}: len={len(row)}, data={row}", flush=True)
            if len(row) >= 8:
                active = row[7].upper() == 'TRUE'
                price_category = row[1]
                
                if active and (category is None or price_category == category):
                    prices.append(Price(
                        price_id=row[0],
                        category=price_category,
                        name=row[2],
                        description=row[3],
                        price=row[4],
                        unit=row[5],
                        min_qty=row[6] if len(row) > 6 else None,
                        active=active
                    ))
        
        print(f"DEBUG: returning {len(prices)} prices", flush=True)
        return prices
    
    def get_menu(self, category: Optional[str] = None) -> List[MenuItem]:
        """Возвращает меню, опционально по категории"""
        rows = self._read_range('menu!A2:F')
        menu_items = []
        for row in rows:
            if len(row) >= 6:
                active = row[5].upper() == 'TRUE'
                item_category = row[0]
                
                if active and (category is None or item_category == category):
                    menu_items.append(MenuItem(
                        category=item_category,
                        name=row[1],
                        description=row[2] if row[2] else None,
                        price=int(row[3]),
                        unit=row[4],
                        active=active
                    ))
        return menu_items
    
    def create_order(self, booking_id: str, item_name: str, quantity: int, price: int) -> str:
        """Создаёт заказ к брони"""
        # Получаем последний order ID
        rows = self._read_range('orders!A2:A')
        last_num = 0
        
        for row in rows:
            if row and row[0].startswith('O'):
                try:
                    num = int(row[0][1:])
                    if num > last_num:
                        last_num = num
                except ValueError:
                    continue
        
        order_id = f"O{last_num + 1:04d}"
        created_at = datetime.now().strftime('%Y-%m-%d %H:%M')
        
        row = [[
            order_id,
            booking_id,
            item_name,
            quantity,
            price,
            created_at,
            'pending'
        ]]
        
        self._append_range('orders!A:G', row)
        return order_id
    
    def get_orders_by_booking(self, booking_id: str) -> List[Order]:
        """Возвращает заказы по ID брони"""
        rows = self._read_range('orders!A2:G')
        orders = []
        for row in rows:
            if len(row) >= 7 and row[1] == booking_id:
                orders.append(Order(
                    order_id=row[0],
                    booking_id=row[1],
                    item_name=row[2],
                    quantity=int(row[3]),
                    price=int(row[4]),
                    created_at=row[5],
                    status=row[6]
                ))
        return orders


sheets_client = SheetsClient()
