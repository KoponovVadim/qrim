from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, date


class AIIntent(BaseModel):
    intent: str  # info | book | events | prices
    slots: dict = {}
    response_text: str


class BookingRequest(BaseModel):
    date: str
    time: str
    guests: int
    name: str
    phone: str


class BookingSlot(BaseModel):
    date: str
    time: str
    guests: int
    available: bool
    table_id: Optional[str] = None


class VenueInfo(BaseModel):
    name: str
    city: str
    address: str
    phone: str
    timezone: str
    work_sun_thu: str
    work_fri_sat: str


class Table(BaseModel):
    table_id: str
    name: str
    capacity: int
    zone: str
    active: bool


class Booking(BaseModel):
    booking_id: str
    date: str
    time: str
    guests: int
    table_id: str
    name: str
    phone: str
    source: str
    status: str
    created_at: str


class Event(BaseModel):
    event_id: str
    title: str
    description: str
    date_from: str
    date_to: str
    time_from: str
    time_to: str
    image_url: Optional[str] = None
    booking_cta: bool
    active: bool


class Promo(BaseModel):
    promo_id: str
    title: str
    description: str
    date_from: str
    date_to: str
    time_from: str
    time_to: str
    image_url: Optional[str] = None
    booking_cta: bool
    active: bool


class Price(BaseModel):
    price_id: str
    category: str
    name: str
    description: str
    price: str
    unit: str
    min_qty: Optional[str] = None
    active: bool


class MenuItem(BaseModel):
    category: str
    name: str
    description: Optional[str] = None
    price: int
    unit: str
    active: bool


class Order(BaseModel):
    order_id: str
    booking_id: str
    item_name: str
    quantity: int
    price: int
    created_at: str
    status: str  # pending, confirmed, completed, cancelled
