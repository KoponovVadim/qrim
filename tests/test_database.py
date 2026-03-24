from app.config import get_settings
from app.database import (
    add_order,
    add_pack,
    get_order,
    get_pack,
    get_packs,
    get_stats,
    init_db,
    update_order_status,
    update_pack,
)


def test_database_crud(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_PATH", str(db_path))
    monkeypatch.setenv("ADMIN_IDS", "")
    get_settings.cache_clear()

    init_db()

    pack_id = add_pack(
        name="Pack One",
        genre="Drill",
        price_usdt=25,
        price_ton=9,
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

    order_id = add_order(
        user_id=12345,
        pack_id=pack_id,
        payment_method="USDT",
        tx_hash="0x123456",
        amount=25,
        status="pending",
    )

    order = get_order(order_id)
    assert order is not None
    assert order["status"] == "pending"

    update_order_status(order_id, "completed")
    assert get_order(order_id)["status"] == "completed"

    all_packs = get_packs()
    assert len(all_packs) == 1

    stats = get_stats()
    assert stats["packs_count"] == 1
    assert stats["orders_count"] == 1
    assert stats["completed_orders"] == 1
