import logging

import httpx
from aiogram.types import BufferedInputFile

from app.s3_client import get_s3_client

logger = logging.getLogger(__name__)


def pack_text(pack: dict) -> str:
    return (
        f"<b>{pack['name']}</b>\n"
        f"Жанр: {pack['genre']}\n"
        f"USDT: {pack['price_usdt']}\n"
        f"TON: {pack['price_ton']}\n\n"
        f"{pack['description']}"
    )


def build_audio_file(raw: bytes, file_name: str) -> BufferedInputFile:
    return BufferedInputFile(raw, filename=file_name)


def get_bytes_from_s3(key: str) -> bytes:
    s3 = get_s3_client()
    return s3.download_file(key)


async def check_usdt_transaction(
    tx_hash: str,
    expected_amount: float,
    wallet_address: str,
    tron_api_key: str = "",
) -> tuple[bool, str]:
    headers = {}
    if tron_api_key:
        headers["TRON-PRO-API-KEY"] = tron_api_key

    url = f"https://api.trongrid.io/v1/transactions/{tx_hash}/events"
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code != 200:
                return False, f"TronGrid status={resp.status_code}"
            payload = resp.json()
    except Exception:
        logger.exception("Failed to validate USDT tx")
        return False, "network error"

    events = payload.get("data", []) or []
    wallet_l = wallet_address.strip().lower()

    for event in events:
        event_name = (event.get("event_name") or "").lower()
        result = event.get("result", {}) or {}

        to_addr = str(result.get("to") or "").lower()
        raw_value = result.get("value")

        if event_name != "transfer":
            continue
        if wallet_l and to_addr != wallet_l:
            continue

        try:
            if raw_value is None:
                continue
            amount = float(raw_value) / 1_000_000
        except Exception:
            continue

        if amount + 1e-9 >= float(expected_amount):
            return True, "ok"

    return False, "matching transfer not found"
