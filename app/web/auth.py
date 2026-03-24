from fastapi import Request
from fastapi.responses import RedirectResponse

from app.config import get_settings
from app.database import is_admin


def is_authenticated(request: Request) -> bool:
    return bool(request.session.get("authenticated"))


def login_by_password(password: str) -> bool:
    settings = get_settings()
    return bool(password) and password == settings.WEB_PASSWORD


def login_by_telegram_id(telegram_id_raw: str) -> bool:
    settings = get_settings()
    telegram_id_raw = telegram_id_raw.strip()
    if not telegram_id_raw or not telegram_id_raw.isdigit():
        return False

    user_id = int(telegram_id_raw)
    if user_id in settings.ADMIN_IDS:
        return True
    return is_admin(user_id)


def auth_or_redirect(request: Request):
    if not is_authenticated(request):
        return RedirectResponse(url="/login", status_code=303)
    return None
