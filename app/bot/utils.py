from aiogram.types import BufferedInputFile

from app.s3_client import get_s3_client


def pack_text(pack: dict) -> str:
    return (
        f"<b>{pack['name']}</b>\n"
        f"{pack.get('description') or ''}\n\n"
        f"Prices:\n"
        f"Starter: {int(pack.get('price_starter', 100))}⭐\n"
        f"Producer: {int(pack.get('price_producer', 300))}⭐\n"
        f"Collector: {int(pack.get('price_collector', 600))}⭐"
    )


def build_audio_file(raw: bytes, file_name: str) -> BufferedInputFile:
    return BufferedInputFile(raw, filename=file_name)


def get_bytes_from_s3(key: str) -> bytes:
    s3 = get_s3_client()
    return s3.download_file(key)


def is_http_url(value: str) -> bool:
    return value.startswith("http://") or value.startswith("https://")
