from google.oauth2 import service_account
from googleapiclient.discovery import build
from typing import List, Optional, Dict
from datetime import datetime
import json
from app.config import settings
from app.models.schemas import VenueInfo, Event, Price, Table, Booking


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
    
    def get_bookings(self, date: str) -> List[Booking]:
        """Возвращает брони на конкретную дату"""
        rows = self._read_range('bookings!A2:J')
        bookings = []
        for row in rows:
            if len(row) >= 10 and row[1] == date:
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
    
    def create_booking(self, booking_data: dict) -> str:
        """Создаёт новую бронь и возвращает booking_id"""
        booking_id = f"B{datetime.now().strftime('%Y%m%d%H%M%S')}"
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


sheets_client = SheetsClient()
