from datetime import datetime

from pydantic import BaseModel


class PackCreate(BaseModel):
    name: str
    description: str = ""
    price_starter: int
    price_producer: int
    price_collector: int


class PackUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    price_starter: int | None = None
    price_producer: int | None = None
    price_collector: int | None = None
    s3_key: str | None = None
    demo_urls: list[str] | None = None


class PackOut(BaseModel):
    id: int
    name: str
    description: str | None
    price_starter: int
    price_producer: int
    price_collector: int
    s3_key: str
    demo_urls: list[str]
    created_at: datetime


class PurchaseOut(BaseModel):
    id: int
    user_id: int
    pack_id: int
    license_type: str
    stars_amount: int
    status: str
    telegram_payment_charge_id: str | None
    created_at: datetime
    completed_at: datetime | None = None


class StatsOut(BaseModel):
    packs_count: int
    purchases_count: int
    revenue_stars: int
