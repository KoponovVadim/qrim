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
    return dict(row) if row else None


def _parse_demo_urls(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(v) for v in raw]
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return [str(v) for v in parsed]
        except json.JSONDecodeError:
            return []
    return []


def init_db() -> None:
    settings = get_settings()
    with _DB_LOCK, closing(_get_connection()) as conn:
        conn.executescript(
            """
            DROP TABLE IF EXISTS orders;
            DROP TABLE IF EXISTS subscriptions;
            DROP TABLE IF EXISTS products;

            CREATE TABLE IF NOT EXISTS packs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT,
                price_starter INTEGER NOT NULL,
                price_producer INTEGER NOT NULL,
                price_collector INTEGER NOT NULL,
                s3_key TEXT NOT NULL,
                demo_urls TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS purchases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                pack_id INTEGER NOT NULL,
                license_type TEXT NOT NULL,
                stars_amount INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                telegram_payment_charge_id TEXT UNIQUE,
                created_at TEXT NOT NULL,
                completed_at TEXT,
                FOREIGN KEY(pack_id) REFERENCES packs(id)
            );

            CREATE INDEX IF NOT EXISTS idx_purchases_status ON purchases(status);
            CREATE INDEX IF NOT EXISTS idx_purchases_pack_id ON purchases(pack_id);
            CREATE INDEX IF NOT EXISTS idx_purchases_user_id ON purchases(user_id);

            CREATE TABLE IF NOT EXISTS admins (
                user_id INTEGER PRIMARY KEY
            );
            """
        )

        for admin_id in settings.ADMIN_IDS:
            conn.execute("INSERT OR IGNORE INTO admins(user_id) VALUES (?)", (int(admin_id),))

        conn.commit()


def add_pack(
    name: str,
    description: str,
    price_starter: int,
    price_producer: int,
    price_collector: int,
    s3_key: str,
    demo_urls: list[str] | None = None,
) -> int:
    now = datetime.utcnow().isoformat()
    payload = json.dumps(demo_urls or [])
    with _DB_LOCK, closing(_get_connection()) as conn:
        cur = conn.execute(
            """
            INSERT INTO packs(
                name, description, price_starter, price_producer, price_collector, s3_key, demo_urls, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                name,
                description,
                int(price_starter),
                int(price_producer),
                int(price_collector),
                s3_key,
                payload,
                now,
            ),
        )
        conn.commit()
        return int(cur.lastrowid)


def get_pack(pack_id: int) -> dict[str, Any] | None:
    with closing(_get_connection()) as conn:
        row = conn.execute("SELECT * FROM packs WHERE id = ?", (pack_id,)).fetchone()
    item = _to_dict(row)
    if not item:
        return None
    item["demo_urls"] = _parse_demo_urls(item.get("demo_urls"))
    return item


def get_packs(limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
    with closing(_get_connection()) as conn:
        rows = conn.execute(
            "SELECT * FROM packs ORDER BY id DESC LIMIT ? OFFSET ?",
            (int(limit), int(offset)),
        ).fetchall()
    result: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["demo_urls"] = _parse_demo_urls(item.get("demo_urls"))
        result.append(item)
    return result


def update_pack(pack_id: int, **fields: Any) -> bool:
    if not fields:
        return False

    if "demo_urls" in fields:
        fields["demo_urls"] = json.dumps(_parse_demo_urls(fields["demo_urls"]))

    assignments = ", ".join([f"{key} = ?" for key in fields])
    values = [fields[key] for key in fields]
    with _DB_LOCK, closing(_get_connection()) as conn:
        cur = conn.execute(
            f"UPDATE packs SET {assignments} WHERE id = ?",
            (*values, int(pack_id)),
        )
        conn.commit()
        return cur.rowcount > 0


def delete_pack(pack_id: int) -> bool:
    with _DB_LOCK, closing(_get_connection()) as conn:
        cur = conn.execute("DELETE FROM packs WHERE id = ?", (int(pack_id),))
        conn.commit()
        return cur.rowcount > 0


def add_purchase(
    user_id: int,
    pack_id: int,
    license_type: str,
    stars_amount: int,
    status: str = "pending",
    telegram_payment_charge_id: str | None = None,
) -> int:
    now = datetime.utcnow().isoformat()
    with _DB_LOCK, closing(_get_connection()) as conn:
        cur = conn.execute(
            """
            INSERT INTO purchases(
                user_id, pack_id, license_type, stars_amount, status,
                telegram_payment_charge_id, created_at, completed_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, NULL)
            """,
            (
                int(user_id),
                int(pack_id),
                license_type,
                int(stars_amount),
                status,
                telegram_payment_charge_id,
                now,
            ),
        )
        conn.commit()
        return int(cur.lastrowid)


def get_purchase(charge_id: str) -> dict[str, Any] | None:
    with closing(_get_connection()) as conn:
        row = conn.execute(
            """
            SELECT p.*, k.name AS pack_name
            FROM purchases p
            LEFT JOIN packs k ON k.id = p.pack_id
            WHERE p.telegram_payment_charge_id = ?
            """,
            (charge_id,),
        ).fetchone()
    return _to_dict(row)


def get_purchase_by_id(purchase_id: int) -> dict[str, Any] | None:
    with closing(_get_connection()) as conn:
        row = conn.execute(
            """
            SELECT p.*, k.name AS pack_name
            FROM purchases p
            LEFT JOIN packs k ON k.id = p.pack_id
            WHERE p.id = ?
            """,
            (int(purchase_id),),
        ).fetchone()
    return _to_dict(row)


def update_purchase_status(
    purchase_id: int,
    status: str,
    completed_at: str | None = None,
    telegram_payment_charge_id: str | None = None,
) -> bool:
    if completed_at is None and status == "completed":
        completed_at = datetime.utcnow().isoformat()
    with _DB_LOCK, closing(_get_connection()) as conn:
        cur = conn.execute(
            """
            UPDATE purchases
            SET status = ?,
                completed_at = ?,
                telegram_payment_charge_id = COALESCE(?, telegram_payment_charge_id)
            WHERE id = ?
            """,
            (status, completed_at, telegram_payment_charge_id, int(purchase_id)),
        )
        conn.commit()
        return cur.rowcount > 0


def get_purchases(status: str | None = None, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
    query = (
        "SELECT p.*, k.name AS pack_name "
        "FROM purchases p "
        "LEFT JOIN packs k ON k.id = p.pack_id"
    )
    params: list[Any] = []
    if status:
        query += " WHERE p.status = ?"
        params.append(status)
    query += " ORDER BY p.id DESC LIMIT ? OFFSET ?"
    params.extend([int(limit), int(offset)])
    with closing(_get_connection()) as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def get_user_purchases(user_id: int, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
    with closing(_get_connection()) as conn:
        rows = conn.execute(
            """
            SELECT p.*, k.name AS pack_name
            FROM purchases p
            LEFT JOIN packs k ON k.id = p.pack_id
            WHERE p.user_id = ?
            ORDER BY p.id DESC
            LIMIT ? OFFSET ?
            """,
            (int(user_id), int(limit), int(offset)),
        ).fetchall()
    return [dict(row) for row in rows]


def add_admin(user_id: int) -> None:
    with _DB_LOCK, closing(_get_connection()) as conn:
        conn.execute("INSERT OR IGNORE INTO admins(user_id) VALUES (?)", (int(user_id),))
        conn.commit()


def get_admins() -> list[int]:
    with closing(_get_connection()) as conn:
        rows = conn.execute("SELECT user_id FROM admins ORDER BY user_id").fetchall()
    return [int(row[0]) for row in rows]


def is_admin(user_id: int) -> bool:
    with closing(_get_connection()) as conn:
        row = conn.execute("SELECT 1 FROM admins WHERE user_id = ?", (int(user_id),)).fetchone()
    return row is not None


def get_stats() -> dict[str, int]:
    with closing(_get_connection()) as conn:
        packs_count = int(conn.execute("SELECT COUNT(*) FROM packs").fetchone()[0])
        purchases_count = int(conn.execute("SELECT COUNT(*) FROM purchases").fetchone()[0])
        revenue_stars = int(
            conn.execute(
                "SELECT COALESCE(SUM(stars_amount), 0) FROM purchases WHERE status = 'completed'"
            ).fetchone()[0]
            or 0
        )
    return {
        "packs_count": packs_count,
        "purchases_count": purchases_count,
        "revenue_stars": revenue_stars,
    }
