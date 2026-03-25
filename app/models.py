from datetime import datetime

from pydantic import BaseModel


class PackCreate(BaseModel):
    name: str
    genre: str
    price_stars: int
    description: str = ""


class PackUpdate(BaseModel):
    name: str | None = None
    genre: str | None = None
    price_stars: int | None = None
    description: str | None = None
    zip_key: str | None = None
    cover_key: str | None = None
    demo_keys: list[str] | None = None


class PackOut(BaseModel):
    id: int
    name: str
    genre: str
    price_stars: int
    description: str
    zip_key: str
    cover_key: str | None
    demo_keys: list[str]
    created_at: datetime
    sold: int


class PurchaseOut(BaseModel):
    id: int
    user_id: int
    product_id: int
    stars_amount: int
    status: str
    telegram_payment_charge_id: str | None
    created_at: datetime
    completed_at: datetime | None = None


class StatsOut(BaseModel):
    products_count: int
    purchases_count: int
    completed_purchases: int
    pending_purchases: int
    stars_total: int
