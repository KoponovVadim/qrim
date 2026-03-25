import json
import sqlite3
from contextlib import closing
from datetime import datetime
from threading import Lock
from typing import Any

from app.config import get_settings

_DB_LOCK = Lock()


def _get_connection() -> sqlite3.Connection:
    settings = get_settings()
    conn = sqlite3.connect(settings.DATABASE_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return dict(row)


def init_db() -> None:
    settings = get_settings()
    with _DB_LOCK, closing(_get_connection()) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                genre TEXT NOT NULL,
                price_stars INTEGER NOT NULL DEFAULT 0,
                description TEXT NOT NULL DEFAULT '',
                zip_key TEXT NOT NULL,
                cover_key TEXT,
                demo_keys TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL,
                sold INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS purchases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                product_id INTEGER NOT NULL,
                stars_amount INTEGER NOT NULL,
                status TEXT NOT NULL,
                telegram_payment_charge_id TEXT,
                created_at TEXT NOT NULL,
                completed_at TEXT,
                FOREIGN KEY(product_id) REFERENCES products(id)
            );

            CREATE INDEX IF NOT EXISTS idx_purchases_user_id ON purchases(user_id);
            CREATE INDEX IF NOT EXISTS idx_purchases_product_id ON purchases(product_id);
            CREATE INDEX IF NOT EXISTS idx_purchases_status ON purchases(status);
            CREATE INDEX IF NOT EXISTS idx_purchases_tg_charge ON purchases(telegram_payment_charge_id);

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS admins (
                user_id INTEGER PRIMARY KEY
            );
            """
        )

        for admin_id in settings.ADMIN_IDS:
            conn.execute("INSERT OR IGNORE INTO admins(user_id) VALUES (?)", (admin_id,))

        conn.commit()


def add_pack(
    name: str,
    genre: str,
    price_stars: int,
    description: str,
    zip_key: str,
    cover_key: str | None = None,
    demo_keys: list[str] | None = None,
) -> int:
    demo_keys = demo_keys or []
    now = datetime.utcnow().isoformat()

    with _DB_LOCK, closing(_get_connection()) as conn:
        cur = conn.execute(
            """
            INSERT INTO products(name, genre, price_stars, description, zip_key, cover_key, demo_keys, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (name, genre, int(price_stars), description, zip_key, cover_key, json.dumps(demo_keys), now),
        )
        conn.commit()
        return int(cur.lastrowid)


def get_pack(pack_id: int) -> dict[str, Any] | None:
    with closing(_get_connection()) as conn:
        row = conn.execute("SELECT * FROM products WHERE id = ?", (pack_id,)).fetchone()
    item = _to_dict(row)
    if item:
        item["demo_keys"] = json.loads(item.get("demo_keys") or "[]")
    return item


def get_packs(limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
    with closing(_get_connection()) as conn:
        rows = conn.execute(
            "SELECT * FROM products ORDER BY id DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["demo_keys"] = json.loads(item.get("demo_keys") or "[]")
        result.append(item)
    return result


def update_pack(pack_id: int, **fields: Any) -> bool:
    if not fields:
        return False

    if "demo_keys" in fields and isinstance(fields["demo_keys"], list):
        fields["demo_keys"] = json.dumps(fields["demo_keys"])

    keys = list(fields.keys())
    values = [fields[k] for k in keys]

    assignments = ", ".join([f"{k} = ?" for k in keys])

    with _DB_LOCK, closing(_get_connection()) as conn:
        cur = conn.execute(
            f"UPDATE products SET {assignments} WHERE id = ?",
            (*values, pack_id),
        )
        conn.commit()
        return cur.rowcount > 0


def delete_pack(pack_id: int) -> bool:
    with _DB_LOCK, closing(_get_connection()) as conn:
        cur = conn.execute("DELETE FROM products WHERE id = ?", (pack_id,))
        conn.commit()
        return cur.rowcount > 0


def add_purchase(
    user_id: int,
    product_id: int,
    stars_amount: int,
    status: str = "pending",
    telegram_payment_charge_id: str | None = None,
) -> int:
    now = datetime.utcnow().isoformat()
    with _DB_LOCK, closing(_get_connection()) as conn:
        cur = conn.execute(
            """
            INSERT INTO purchases(user_id, product_id, stars_amount, status, telegram_payment_charge_id, created_at, completed_at)
            VALUES (?, ?, ?, ?, ?, ?, NULL)
            """,
            (user_id, product_id, int(stars_amount), status, telegram_payment_charge_id, now),
        )
        conn.commit()
        return int(cur.lastrowid)


def get_purchase(purchase_id: int) -> dict[str, Any] | None:
    with closing(_get_connection()) as conn:
        row = conn.execute("SELECT * FROM purchases WHERE id = ?", (purchase_id,)).fetchone()
    return _to_dict(row)


def get_purchases(status: str | None = None, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
    query = """
        SELECT pch.*, pr.name AS product_name
        FROM purchases pch
        LEFT JOIN products pr ON pr.id = pch.product_id
    """
    params: list[Any] = []
    if status:
        query += " WHERE pch.status = ?"
        params.append(status)

    query += " ORDER BY pch.id DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    with closing(_get_connection()) as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def get_user_purchases(user_id: int, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
    query = """
        SELECT pch.*, pr.name AS product_name
        FROM purchases pch
        LEFT JOIN products pr ON pr.id = pch.product_id
        WHERE pch.user_id = ?
        ORDER BY pch.id DESC
        LIMIT ? OFFSET ?
    """
    with closing(_get_connection()) as conn:
        rows = conn.execute(query, (user_id, limit, offset)).fetchall()
    return [dict(row) for row in rows]


def update_purchase_status(
    purchase_id: int,
    status: str,
    telegram_payment_charge_id: str | None = None,
) -> bool:
    with _DB_LOCK, closing(_get_connection()) as conn:
        completed_at = datetime.utcnow().isoformat() if status == "completed" else None
        cur = conn.execute(
            """
            UPDATE purchases
            SET status = ?,
                telegram_payment_charge_id = COALESCE(?, telegram_payment_charge_id),
                completed_at = CASE WHEN ? IS NOT NULL THEN ? ELSE completed_at END
            WHERE id = ?
            """,
            (status, telegram_payment_charge_id, completed_at, completed_at, purchase_id),
        )
        conn.commit()
        return cur.rowcount > 0


def get_purchase_by_charge_id(telegram_payment_charge_id: str) -> dict[str, Any] | None:
    with closing(_get_connection()) as conn:
        row = conn.execute(
            "SELECT * FROM purchases WHERE telegram_payment_charge_id = ?",
            (telegram_payment_charge_id,),
        ).fetchone()
    return _to_dict(row)


def increment_pack_sold(pack_id: int) -> None:
    with _DB_LOCK, closing(_get_connection()) as conn:
        conn.execute("UPDATE products SET sold = sold + 1 WHERE id = ?", (pack_id,))
        conn.commit()


def get_stats() -> dict[str, Any]:
    with closing(_get_connection()) as conn:
        products_count = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
        purchases_count = conn.execute("SELECT COUNT(*) FROM purchases").fetchone()[0]
        completed_purchases = conn.execute("SELECT COUNT(*) FROM purchases WHERE status = 'completed'").fetchone()[0]
        pending_purchases = conn.execute("SELECT COUNT(*) FROM purchases WHERE status = 'pending'").fetchone()[0]
        stars_total = conn.execute(
            "SELECT COALESCE(SUM(stars_amount), 0) FROM purchases WHERE status = 'completed'"
        ).fetchone()[0]

    return {
        "products_count": products_count,
        "purchases_count": purchases_count,
        "completed_purchases": completed_purchases,
        "pending_purchases": pending_purchases,
        "stars_total": int(stars_total or 0),
    }


def set_setting(key: str, value: str) -> None:
    with _DB_LOCK, closing(_get_connection()) as conn:
        conn.execute(
            "INSERT INTO settings(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        conn.commit()


def get_setting(key: str, default: str | None = None) -> str | None:
    with closing(_get_connection()) as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    if not row:
        return default
    return row[0]


def add_admin(user_id: int) -> None:
    with _DB_LOCK, closing(_get_connection()) as conn:
        conn.execute("INSERT OR IGNORE INTO admins(user_id) VALUES (?)", (user_id,))
        conn.commit()


def get_admins() -> list[int]:
    with closing(_get_connection()) as conn:
        rows = conn.execute("SELECT user_id FROM admins ORDER BY user_id").fetchall()
    return [int(row[0]) for row in rows]


def is_admin(user_id: int) -> bool:
    with closing(_get_connection()) as conn:
        row = conn.execute("SELECT 1 FROM admins WHERE user_id = ?", (user_id,)).fetchone()
    return row is not None
