from app.config import get_settings
from app.database import (
    add_pack,
    add_purchase,
    get_pack,
    get_packs,
    get_purchase,
    get_stats,
    init_db,
    update_purchase_status,
    update_pack,
)


def test_database_crud(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_PATH", str(db_path))
    monkeypatch.setenv("ADMIN_IDS", "[]")
    get_settings.cache_clear()

    init_db()

    pack_id = add_pack(
        name="Pack One",
        genre="Drill",
        price_stars=250,
        description="Desc",
        zip_key="packs/1/pack.zip",
        cover_key="packs/1/cover.jpg",
        demo_keys=["packs/1/demos/demo_1.mp3"],
    )

    pack = get_pack(pack_id)
    assert pack is not None
    assert pack["name"] == "Pack One"

    update_pack(pack_id, name="Pack X")
    updated = get_pack(pack_id)
    assert updated["name"] == "Pack X"

    purchase_id = add_purchase(
        user_id=12345,
        product_id=pack_id,
        stars_amount=250,
        status="pending",
    )

    purchase = get_purchase(purchase_id)
    assert purchase is not None
    assert purchase["status"] == "pending"

    update_purchase_status(purchase_id, "completed", telegram_payment_charge_id="chg_123")
    completed = get_purchase(purchase_id)
    assert completed["status"] == "completed"
    assert completed["telegram_payment_charge_id"] == "chg_123"

    all_packs = get_packs()
    assert len(all_packs) == 1

    stats = get_stats()
    assert stats["products_count"] == 1
    assert stats["purchases_count"] == 1
    assert stats["completed_purchases"] == 1
    assert stats["stars_total"] == 250
