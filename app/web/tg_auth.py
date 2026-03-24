import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl


def parse_and_validate_init_data(
    init_data: str,
    bot_token: str,
    max_age_seconds: int = 60 * 60 * 24,
) -> dict | None:
    if not init_data or not bot_token:
        return None

    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = pairs.pop("hash", "")
    if not received_hash:
        return None

    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    calculated_hash = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(calculated_hash, received_hash):
        return None

    auth_date_raw = pairs.get("auth_date", "")
    if not auth_date_raw.isdigit():
        return None

    auth_date = int(auth_date_raw)
    if int(time.time()) - auth_date > max_age_seconds:
        return None

    user_raw = pairs.get("user", "")
    if not user_raw:
        return None

    try:
        user_obj = json.loads(user_raw)
        user_id = int(user_obj["id"])
    except Exception:
        return None

    return {
        "user_id": user_id,
        "auth_date": auth_date,
        "raw": pairs,
    }
