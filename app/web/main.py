from typing import Any

from aiogram import Bot
from fastapi import FastAPI, Form, Request, UploadFile
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from app.config import get_settings
from app.database import (
    add_pack,
    add_purchase,
    delete_pack,
    get_admins,
    get_purchase,
    get_purchases,
    get_pack,
    get_packs,
    get_user_purchases,
    get_stats,
    increment_pack_sold,
    init_db,
    update_purchase_status,
    update_pack,
)
from app.s3_client import get_s3_client
from app.web.auth import auth_or_redirect, login_by_password, login_by_telegram_id
from app.web.tg_auth import parse_and_validate_init_data

settings = get_settings()
app = FastAPI(title="Soundbot Admin")
app.add_middleware(SessionMiddleware, secret_key=settings.WEB_SECRET_KEY)
app.mount("/static", StaticFiles(directory="app/web/static"), name="static")
templates = Jinja2Templates(directory="app/web/templates")


@app.on_event("startup")
def startup_event() -> None:
    init_db()


async def _send_download_link(user_id: int, url: str) -> None:
    if not settings.BOT_TOKEN:
        return

    bot = Bot(token=settings.BOT_TOKEN)
    try:
        await bot.send_message(
            chat_id=user_id,
            text=f"Payment confirmed. Download link (24 hours):\n{url}",
        )
    finally:
        await bot.session.close()


async def _notify_admins(purchase: dict[str, Any], product_name: str = "") -> None:
    if not settings.BOT_TOKEN:
        return

    text = (
        f"New purchase #{purchase['id']}\n"
        f"User ID: {purchase['user_id']}\n"
        f"Product: {product_name or purchase['product_id']}\n"
        f"Stars: {purchase['stars_amount']}\n"
        f"Status: {purchase['status']}\n"
        f"Panel: {settings.PANEL_BASE_URL}/orders"
    )

    bot = Bot(token=settings.BOT_TOKEN)
    try:
        admin_ids = set(settings.ADMIN_IDS + get_admins())
        for admin_id in admin_ids:
            try:
                await bot.send_message(chat_id=admin_id, text=text)
            except Exception:
                continue
    finally:
        await bot.session.close()


def _pack_cover_url(pack: dict[str, Any], expires_in: int = 600) -> str | None:
    if not pack.get("cover_key"):
        return None
    s3 = get_s3_client()
    try:
        return s3.generate_download_url(pack["cover_key"], expires_in=expires_in)
    except Exception:
        return None


def _pack_demo_urls(pack: dict[str, Any], expires_in: int = 600) -> list[str]:
    result: list[str] = []
    s3 = get_s3_client()
    for key in pack.get("demo_keys", []) or []:
        try:
            result.append(s3.generate_download_url(key, expires_in=expires_in))
        except Exception:
            continue
    return result


def _tg_user_id_from_init_data(init_data: str) -> int | None:
    payload = parse_and_validate_init_data(init_data=init_data, bot_token=settings.BOT_TOKEN)
    if not payload:
        return None
    return int(payload["user_id"])


@app.get("/login")
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "error": ""})


@app.get("/app")
async def tgapp_home(request: Request, init_data: str = ""):
    user_id = _tg_user_id_from_init_data(init_data)
    packs = get_packs(limit=200, offset=0)
    for pack in packs:
        pack["cover_url"] = _pack_cover_url(pack)

    return templates.TemplateResponse(
        "tgapp_home.html",
        {
            "request": request,
            "packs": packs,
            "user_id": user_id,
            "init_data": init_data,
        },
    )


@app.get("/app/pack/{pack_id}")
async def tgapp_pack_page(request: Request, pack_id: int, init_data: str = ""):
    user_id = _tg_user_id_from_init_data(init_data)
    pack = get_pack(pack_id)
    if not pack:
        return RedirectResponse(url="/app", status_code=303)

    pack["cover_url"] = _pack_cover_url(pack)
    pack["demo_urls"] = _pack_demo_urls(pack)

    return templates.TemplateResponse(
        "tgapp_pack.html",
        {
            "request": request,
            "pack": pack,
            "user_id": user_id,
            "init_data": init_data,
        },
    )


@app.get("/app/orders")
async def tgapp_orders_page(request: Request, init_data: str = ""):
    user_id = _tg_user_id_from_init_data(init_data)
    if not user_id:
        return templates.TemplateResponse(
            "tgapp_orders.html",
            {"request": request, "orders": [], "user_id": None, "init_data": init_data},
        )

    orders = get_user_purchases(user_id=user_id, limit=200, offset=0)
    return templates.TemplateResponse(
        "tgapp_orders.html",
        {"request": request, "orders": orders, "user_id": user_id, "init_data": init_data},
    )


@app.post("/app/order")
async def tgapp_create_order(
    pack_id: int = Form(...),
    init_data: str = Form(...),
):
    user_id = _tg_user_id_from_init_data(init_data)
    if not user_id:
        return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)

    pack = get_pack(pack_id)
    if not pack:
        return JSONResponse({"ok": False, "error": "pack_not_found"}, status_code=404)

    stars_amount = int(pack["price_stars"])
    purchase_id = add_purchase(
        user_id=user_id,
        product_id=pack_id,
        stars_amount=stars_amount,
        status="pending",
    )
    purchase = get_purchase(purchase_id)
    if purchase:
        await _notify_admins(purchase, product_name=pack.get("name", ""))

    return JSONResponse(
        {
            "ok": True,
            "order_id": purchase_id,
            "status": "pending",
            "stars_amount": stars_amount,
        }
    )


@app.post("/login")
async def login_action(
    request: Request,
    password: str = Form(default=""),
    telegram_id: str = Form(default=""),
):
    valid = login_by_password(password) or login_by_telegram_id(telegram_id)
    if not valid:
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Неверный пароль или Telegram ID"},
            status_code=401,
        )

    request.session["authenticated"] = True
    request.session["admin_telegram_id"] = telegram_id.strip()
    return RedirectResponse(url="/", status_code=303)


@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)


@app.get("/")
async def dashboard(request: Request):
    redirect = auth_or_redirect(request)
    if redirect:
        return redirect

    stats = get_stats()
    return templates.TemplateResponse("dashboard.html", {"request": request, "stats": stats})


@app.get("/packs")
async def packs_list(request: Request):
    redirect = auth_or_redirect(request)
    if redirect:
        return redirect

    packs = get_packs(limit=500, offset=0)
    return templates.TemplateResponse("packs.html", {"request": request, "packs": packs})


@app.get("/packs/add")
async def packs_add_page(request: Request):
    redirect = auth_or_redirect(request)
    if redirect:
        return redirect

    return templates.TemplateResponse(
        "pack_form.html",
        {"request": request, "mode": "add", "pack": None},
    )


@app.post("/packs/add")
async def packs_add_action(
    request: Request,
    name: str = Form(...),
    genre: str = Form(...),
    price_stars: int = Form(...),
    description: str = Form(default=""),
    zip_file: UploadFile = Form(...),
    cover_file: UploadFile | None = Form(default=None),
    demo_files: list[UploadFile] | None = Form(default=None),
):
    redirect = auth_or_redirect(request)
    if redirect:
        return redirect

    s3 = get_s3_client()

    pack_id = add_pack(
        name=name,
        genre=genre,
        price_stars=price_stars,
        description=description,
        zip_key="",
        cover_key=None,
        demo_keys=[],
    )

    zip_key = f"packs/{pack_id}/pack.zip"
    zip_bytes = await zip_file.read()
    s3.upload_file(zip_bytes, zip_key, zip_file.content_type or "application/zip")

    cover_key = None
    if cover_file and cover_file.filename:
        ext = "jpg"
        if "." in cover_file.filename:
            ext = cover_file.filename.rsplit(".", 1)[-1]
        cover_key = f"packs/{pack_id}/cover.{ext}"
        cover_bytes = await cover_file.read()
        s3.upload_file(cover_bytes, cover_key, cover_file.content_type or "image/jpeg")

    demo_keys: list[str] = []
    if demo_files:
        idx = 1
        for demo in demo_files:
            if not demo.filename:
                continue
            ext = "mp3"
            if "." in demo.filename:
                ext = demo.filename.rsplit(".", 1)[-1]
            demo_key = f"packs/{pack_id}/demos/demo_{idx}.{ext}"
            demo_bytes = await demo.read()
            s3.upload_file(demo_bytes, demo_key, demo.content_type or "audio/mpeg")
            demo_keys.append(demo_key)
            idx += 1

    update_pack(pack_id, zip_key=zip_key, cover_key=cover_key, demo_keys=demo_keys)
    return RedirectResponse(url="/packs", status_code=303)


@app.get("/packs/edit/{pack_id}")
async def packs_edit_page(request: Request, pack_id: int):
    redirect = auth_or_redirect(request)
    if redirect:
        return redirect

    pack = get_pack(pack_id)
    if not pack:
        return RedirectResponse(url="/packs", status_code=303)

    return templates.TemplateResponse(
        "pack_form.html",
        {"request": request, "mode": "edit", "pack": pack},
    )


@app.post("/packs/edit/{pack_id}")
async def packs_edit_action(
    request: Request,
    pack_id: int,
    name: str = Form(...),
    genre: str = Form(...),
    price_stars: int = Form(...),
    description: str = Form(default=""),
    zip_file: UploadFile | None = Form(default=None),
    cover_file: UploadFile | None = Form(default=None),
    demo_files: list[UploadFile] | None = Form(default=None),
):
    redirect = auth_or_redirect(request)
    if redirect:
        return redirect

    pack = get_pack(pack_id)
    if not pack:
        return RedirectResponse(url="/packs", status_code=303)

    s3 = get_s3_client()
    updates: dict[str, Any] = {
        "name": name,
        "genre": genre,
        "price_stars": int(price_stars),
        "description": description,
    }

    if zip_file and zip_file.filename:
        if pack.get("zip_key"):
            try:
                s3.delete_file(pack["zip_key"])
            except Exception:
                pass

        zip_key = f"packs/{pack_id}/pack.zip"
        zip_bytes = await zip_file.read()
        s3.upload_file(zip_bytes, zip_key, zip_file.content_type or "application/zip")
        updates["zip_key"] = zip_key

    if cover_file and cover_file.filename:
        if pack.get("cover_key"):
            try:
                s3.delete_file(pack["cover_key"])
            except Exception:
                pass

        ext = "jpg"
        if "." in cover_file.filename:
            ext = cover_file.filename.rsplit(".", 1)[-1]
        cover_key = f"packs/{pack_id}/cover.{ext}"
        cover_bytes = await cover_file.read()
        s3.upload_file(cover_bytes, cover_key, cover_file.content_type or "image/jpeg")
        updates["cover_key"] = cover_key

    has_new_demo = bool(demo_files and any(df.filename for df in demo_files))
    if has_new_demo:
        for old_demo_key in pack.get("demo_keys", []):
            try:
                s3.delete_file(old_demo_key)
            except Exception:
                pass

        new_demo_keys: list[str] = []
        idx = 1
        for demo in demo_files or []:
            if not demo.filename:
                continue
            ext = "mp3"
            if "." in demo.filename:
                ext = demo.filename.rsplit(".", 1)[-1]
            demo_key = f"packs/{pack_id}/demos/demo_{idx}.{ext}"
            demo_bytes = await demo.read()
            s3.upload_file(demo_bytes, demo_key, demo.content_type or "audio/mpeg")
            new_demo_keys.append(demo_key)
            idx += 1

        updates["demo_keys"] = new_demo_keys

    update_pack(pack_id, **updates)
    return RedirectResponse(url="/packs", status_code=303)


@app.post("/packs/delete/{pack_id}")
async def packs_delete_action(request: Request, pack_id: int):
    redirect = auth_or_redirect(request)
    if redirect:
        return redirect

    pack = get_pack(pack_id)
    if pack:
        s3 = get_s3_client()
        for key in [pack.get("zip_key"), pack.get("cover_key"), *(pack.get("demo_keys", []))]:
            if not key:
                continue
            try:
                s3.delete_file(key)
            except Exception:
                pass
        delete_pack(pack_id)

    return RedirectResponse(url="/packs", status_code=303)


@app.get("/orders")
async def orders_page(request: Request, status: str = ""):
    redirect = auth_or_redirect(request)
    if redirect:
        return redirect

    orders = get_purchases(status=status or None, limit=500, offset=0)
    return templates.TemplateResponse(
        "orders.html",
        {"request": request, "orders": orders, "status": status},
    )


@app.post("/orders/{order_id}/confirm")
async def confirm_order(request: Request, order_id: int):
    redirect = auth_or_redirect(request)
    if redirect:
        return redirect

    purchase = get_purchase(order_id)
    if not purchase:
        return RedirectResponse(url="/orders", status_code=303)

    if purchase["status"] == "completed":
        return RedirectResponse(url="/orders", status_code=303)

    pack = get_pack(int(purchase["product_id"]))
    if not pack:
        return RedirectResponse(url="/orders", status_code=303)

    s3 = get_s3_client()
    try:
        url = s3.generate_download_url(pack["zip_key"], expires_in=86400)
    except Exception:
        return RedirectResponse(url="/orders", status_code=303)

    update_purchase_status(order_id, "completed")
    increment_pack_sold(int(purchase["product_id"]))
    await _send_download_link(int(purchase["user_id"]), url)

    return RedirectResponse(url="/orders", status_code=303)
