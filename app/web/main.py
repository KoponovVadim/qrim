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
    get_purchase_by_id,
    get_purchases,
    get_pack,
    get_packs,
    get_user_purchases,
    get_stats,
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
        f"Pack: {product_name or purchase['pack_id']}\n"
        f"License: {purchase.get('license_type', '-') }\n"
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
    cover_key = f"packs/{pack['id']}/cover.jpg"
    s3 = get_s3_client()
    try:
        return s3.generate_download_url(cover_key, expires_in=expires_in)
    except Exception:
        return None


def _pack_demo_urls(pack: dict[str, Any], expires_in: int = 600) -> list[str]:
    result: list[str] = []
    s3 = get_s3_client()
    for entry in pack.get("demo_urls", []) or []:
        if str(entry).startswith("http://") or str(entry).startswith("https://"):
            result.append(str(entry))
        else:
            try:
                result.append(s3.generate_download_url(str(entry), expires_in=expires_in))
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
            "bot_username": "",
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
    license_type: str = Form(...),
    init_data: str = Form(...),
):
    user_id = _tg_user_id_from_init_data(init_data)
    if not user_id:
        return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)

    pack = get_pack(pack_id)
    if not pack:
        return JSONResponse({"ok": False, "error": "pack_not_found"}, status_code=404)

    price_map = {
        "starter": int(pack["price_starter"]),
        "producer": int(pack["price_producer"]),
        "collector": int(pack["price_collector"]),
    }
    if license_type not in price_map:
        return JSONResponse({"ok": False, "error": "invalid_license"}, status_code=400)

    stars_amount = int(price_map[license_type])
    purchase_id = add_purchase(
        user_id=user_id,
        pack_id=pack_id,
        license_type=license_type,
        stars_amount=stars_amount,
        status="pending",
    )
    purchase = get_purchase_by_id(purchase_id)
    if purchase:
        await _notify_admins(purchase, product_name=pack.get("name", ""))

    return JSONResponse(
        {
            "ok": True,
            "purchase_id": purchase_id,
            "status": "pending",
            "license_type": license_type,
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
            {"request": request, "error": "Invalid password or Telegram ID"},
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
    description: str = Form(default=""),
    price_starter: int = Form(...),
    price_producer: int = Form(...),
    price_collector: int = Form(...),
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
        description=description,
        price_starter=price_starter,
        price_producer=price_producer,
        price_collector=price_collector,
        s3_key="",
        demo_urls=[],
    )

    zip_key = f"packs/{pack_id}/pack.zip"
    zip_bytes = await zip_file.read()
    s3.upload_file(zip_bytes, zip_key, zip_file.content_type or "application/zip")

    if cover_file and cover_file.filename:
        cover_key = f"packs/{pack_id}/cover.jpg"
        cover_bytes = await cover_file.read()
        s3.upload_file(cover_bytes, cover_key, cover_file.content_type or "image/jpeg")

    demo_urls: list[str] = []
    public_base = settings.S3_PUBLIC_BASE_URL.rstrip("/") if settings.S3_PUBLIC_BASE_URL else ""
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
            if public_base:
                demo_urls.append(f"{public_base}/{settings.S3_BUCKET}/{demo_key}")
            else:
                demo_urls.append(demo_key)
            idx += 1

    update_pack(pack_id, s3_key=zip_key, demo_urls=demo_urls)
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
    description: str = Form(default=""),
    price_starter: int = Form(...),
    price_producer: int = Form(...),
    price_collector: int = Form(...),
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
        "description": description,
        "price_starter": int(price_starter),
        "price_producer": int(price_producer),
        "price_collector": int(price_collector),
    }

    if zip_file and zip_file.filename:
        if pack.get("s3_key"):
            try:
                s3.delete_file(pack["s3_key"])
            except Exception:
                pass

        zip_key = f"packs/{pack_id}/pack.zip"
        zip_bytes = await zip_file.read()
        s3.upload_file(zip_bytes, zip_key, zip_file.content_type or "application/zip")
        updates["s3_key"] = zip_key

    if cover_file and cover_file.filename:
        cover_key = f"packs/{pack_id}/cover.jpg"
        cover_bytes = await cover_file.read()
        s3.upload_file(cover_bytes, cover_key, cover_file.content_type or "image/jpeg")

    has_new_demo = bool(demo_files and any(df.filename for df in demo_files))
    if has_new_demo:
        new_demo_urls: list[str] = []
        public_base = settings.S3_PUBLIC_BASE_URL.rstrip("/") if settings.S3_PUBLIC_BASE_URL else ""
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
            if public_base:
                new_demo_urls.append(f"{public_base}/{settings.S3_BUCKET}/{demo_key}")
            else:
                new_demo_urls.append(demo_key)
            idx += 1

        updates["demo_urls"] = new_demo_urls

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
        for key in [pack.get("s3_key")]:
            if not key:
                continue
            try:
                s3.delete_file(key)
            except Exception:
                pass

        try:
            s3.delete_file(f"packs/{pack_id}/cover.jpg")
        except Exception:
            pass

        for demo in pack.get("demo_urls", []):
            if isinstance(demo, str) and not demo.startswith("http://") and not demo.startswith("https://"):
                try:
                    s3.delete_file(demo)
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

    purchase = get_purchase_by_id(order_id)
    if not purchase:
        return RedirectResponse(url="/orders", status_code=303)

    if purchase["status"] == "completed":
        return RedirectResponse(url="/orders", status_code=303)

    pack = get_pack(int(purchase["pack_id"]))
    if not pack:
        return RedirectResponse(url="/orders", status_code=303)

    s3 = get_s3_client()
    try:
        url = s3.generate_download_url(pack["s3_key"], expires_in=86400)
    except Exception:
        return RedirectResponse(url="/orders", status_code=303)

    update_purchase_status(order_id, "completed")
    await _send_download_link(int(purchase["user_id"]), url)

    return RedirectResponse(url="/orders", status_code=303)
