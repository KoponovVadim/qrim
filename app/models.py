from datetime import datetime

from pydantic import BaseModel


class PackCreate(BaseModel):
    name: str
    genre: str
    price_usdt: float
    price_ton: float
    description: str = ""


class PackUpdate(BaseModel):
    name: str | None = None
    genre: str | None = None
    price_usdt: float | None = None
    price_ton: float | None = None
    description: str | None = None
    zip_key: str | None = None
    cover_key: str | None = None
    demo_keys: list[str] | None = None


class PackOut(BaseModel):
    id: int
    name: str
    genre: str
    price_usdt: float
    price_ton: float
    description: str
    zip_key: str
    cover_key: str | None
    demo_keys: list[str]
    created_at: datetime
    sold: int


class OrderOut(BaseModel):
    id: int
    user_id: int
    pack_id: int
    payment_method: str
    tx_hash: str
    amount: float
    status: str
    created_at: datetime


class StatsOut(BaseModel):
    packs_count: int
    orders_count: int
    completed_orders: int
    pending_orders: int
    revenue_total: float
