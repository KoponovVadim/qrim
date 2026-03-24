import json
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta
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
            CREATE TABLE IF NOT EXISTS packs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                genre TEXT NOT NULL,
                price_usdt REAL NOT NULL DEFAULT 0,
                price_ton REAL NOT NULL DEFAULT 0,
                description TEXT NOT NULL DEFAULT '',
                zip_key TEXT NOT NULL,
                cover_key TEXT,
                demo_keys TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL,
                sold INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                pack_id INTEGER NOT NULL,
                payment_method TEXT NOT NULL,
                tx_hash TEXT NOT NULL,
                amount REAL NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(pack_id) REFERENCES packs(id)
            );

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS admins (
                user_id INTEGER PRIMARY KEY
            );

            CREATE TABLE IF NOT EXISTS subscriptions (
                user_id INTEGER PRIMARY KEY,
                start_date TEXT NOT NULL,
                end_date TEXT NOT NULL,
                status TEXT NOT NULL
            );
            """
        )

        for admin_id in settings.ADMIN_IDS:
            conn.execute("INSERT OR IGNORE INTO admins(user_id) VALUES (?)", (admin_id,))

        conn.commit()


def add_pack(
    name: str,
    genre: str,
    price_usdt: float,
    price_ton: float,
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
            INSERT INTO packs(name, genre, price_usdt, price_ton, description, zip_key, cover_key, demo_keys, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (name, genre, price_usdt, price_ton, description, zip_key, cover_key, json.dumps(demo_keys), now),
        )
        conn.commit()
        return int(cur.lastrowid)


def get_pack(pack_id: int) -> dict[str, Any] | None:
    with closing(_get_connection()) as conn:
        row = conn.execute("SELECT * FROM packs WHERE id = ?", (pack_id,)).fetchone()
    item = _to_dict(row)
    if item:
        item["demo_keys"] = json.loads(item.get("demo_keys") or "[]")
    return item


def get_packs(limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
    with closing(_get_connection()) as conn:
        rows = conn.execute(
            "SELECT * FROM packs ORDER BY id DESC LIMIT ? OFFSET ?",
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
            f"UPDATE packs SET {assignments} WHERE id = ?",
            (*values, pack_id),
        )
        conn.commit()
        return cur.rowcount > 0


def delete_pack(pack_id: int) -> bool:
    with _DB_LOCK, closing(_get_connection()) as conn:
        cur = conn.execute("DELETE FROM packs WHERE id = ?", (pack_id,))
        conn.commit()
        return cur.rowcount > 0


def add_order(
    user_id: int,
    pack_id: int,
    payment_method: str,
    tx_hash: str,
    amount: float,
    status: str = "pending",
) -> int:
    now = datetime.utcnow().isoformat()
    with _DB_LOCK, closing(_get_connection()) as conn:
        cur = conn.execute(
            """
            INSERT INTO orders(user_id, pack_id, payment_method, tx_hash, amount, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, pack_id, payment_method, tx_hash, amount, status, now),
        )
        conn.commit()
        return int(cur.lastrowid)


def get_order(order_id: int) -> dict[str, Any] | None:
    with closing(_get_connection()) as conn:
        row = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    return _to_dict(row)


def get_orders(status: str | None = None, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
    query = """
        SELECT o.*, p.name AS pack_name
        FROM orders o
        LEFT JOIN packs p ON p.id = o.pack_id
    """
    params: list[Any] = []
    if status:
        query += " WHERE o.status = ?"
        params.append(status)

    query += " ORDER BY o.id DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    with closing(_get_connection()) as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def get_user_orders(user_id: int, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
    query = """
        SELECT o.*, p.name AS pack_name
        FROM orders o
        LEFT JOIN packs p ON p.id = o.pack_id
        WHERE o.user_id = ?
        ORDER BY o.id DESC
        LIMIT ? OFFSET ?
    """
    with closing(_get_connection()) as conn:
        rows = conn.execute(query, (user_id, limit, offset)).fetchall()
    return [dict(row) for row in rows]


def update_order_status(order_id: int, status: str) -> bool:
    with _DB_LOCK, closing(_get_connection()) as conn:
        cur = conn.execute(
            "UPDATE orders SET status = ? WHERE id = ?",
            (status, order_id),
        )
        conn.commit()
        return cur.rowcount > 0


def increment_pack_sold(pack_id: int) -> None:
    with _DB_LOCK, closing(_get_connection()) as conn:
        conn.execute("UPDATE packs SET sold = sold + 1 WHERE id = ?", (pack_id,))
        conn.commit()


def get_stats() -> dict[str, Any]:
    with closing(_get_connection()) as conn:
        packs_count = conn.execute("SELECT COUNT(*) FROM packs").fetchone()[0]
        orders_count = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
        completed_orders = conn.execute("SELECT COUNT(*) FROM orders WHERE status = 'completed'").fetchone()[0]
        pending_orders = conn.execute("SELECT COUNT(*) FROM orders WHERE status = 'pending'").fetchone()[0]
        revenue_total = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM orders WHERE status = 'completed'"
        ).fetchone()[0]

    return {
        "packs_count": packs_count,
        "orders_count": orders_count,
        "completed_orders": completed_orders,
        "pending_orders": pending_orders,
        "revenue_total": float(revenue_total or 0),
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


def get_subscription(user_id: int) -> dict[str, Any] | None:
    with closing(_get_connection()) as conn:
        row = conn.execute(
            "SELECT user_id, start_date, end_date, status FROM subscriptions WHERE user_id = ?",
            (user_id,),
        ).fetchone()
    return _to_dict(row)


def has_active_subscription(user_id: int) -> bool:
    sub = get_subscription(user_id)
    if not sub:
        return False
    if sub.get("status") != "active":
        return False
    try:
        end_dt = datetime.fromisoformat(sub["end_date"])
    except Exception:
        return False
    return end_dt > datetime.utcnow()


def create_or_extend_subscription(user_id: int, days: int = 30) -> dict[str, Any]:
    now = datetime.utcnow()
    current = get_subscription(user_id)
    if current and current.get("status") == "active":
        try:
            current_end = datetime.fromisoformat(current["end_date"])
        except Exception:
            current_end = now
        start_dt = now
        base = current_end if current_end > now else now
        end_dt = base + timedelta(days=days)
    else:
        start_dt = now
        end_dt = now + timedelta(days=days)

    with _DB_LOCK, closing(_get_connection()) as conn:
        conn.execute(
            """
            INSERT INTO subscriptions(user_id, start_date, end_date, status)
            VALUES (?, ?, ?, 'active')
            ON CONFLICT(user_id) DO UPDATE SET
                start_date = excluded.start_date,
                end_date = excluded.end_date,
                status = 'active'
            """,
            (user_id, start_dt.isoformat(), end_dt.isoformat()),
        )
        conn.commit()

    return {
        "user_id": user_id,
        "start_date": start_dt.isoformat(),
        "end_date": end_dt.isoformat(),
        "status": "active",
    }


def cancel_subscription(user_id: int) -> bool:
    with _DB_LOCK, closing(_get_connection()) as conn:
        cur = conn.execute(
            "UPDATE subscriptions SET status = 'cancelled' WHERE user_id = ?",
            (user_id,),
        )
        conn.commit()
        return cur.rowcount > 0
