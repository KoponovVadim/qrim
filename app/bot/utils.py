from aiogram.types import BufferedInputFile

from app.s3_client import get_s3_client


def pack_text(pack: dict) -> str:
    return (
        f"<b>{pack['name']}</b>\n"
        f"Genre: {pack['genre']}\n"
        f"Price: {pack['price_stars']} Stars\n\n"
        f"{pack['description']}"
    )


def build_audio_file(raw: bytes, file_name: str) -> BufferedInputFile:
    return BufferedInputFile(raw, filename=file_name)


def get_bytes_from_s3(key: str) -> bytes:
    s3 = get_s3_client()
    return s3.download_file(key)
