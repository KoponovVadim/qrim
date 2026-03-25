# Soundbot: Telegram Stars Store

Soundbot is a Telegram bot + FastAPI admin panel for selling sample packs with Telegram Stars only.

## Stack
- Bot: aiogram 3.x
- Web panel and Mini App backend: FastAPI
- Database: SQLite
- File storage: S3-compatible storage (Cloudflare R2, MinIO, etc.)
- Deployment: Docker Compose behind Nginx

## Payment Model
- Only Telegram Stars are supported.
- No USDT, TON, subscriptions, or tx-hash verification flow.
- Purchase is created in pending status, paid through Telegram invoice (XTR), then completed automatically on successful payment callback.
- After successful payment, user receives a signed download URL (24h).

## Data Model
- products
- purchases
- settings
- admins

Main stats keys:
- products_count
- purchases_count
- completed_purchases
- pending_purchases
- stars_total

## Environment
Copy .env.example to .env and fill:
- BOT_TOKEN
- ADMIN_IDS
- WEB_PASSWORD
- WEB_SECRET_KEY
- DATABASE_PATH
- S3_ENDPOINT
- S3_ACCESS_KEY
- S3_SECRET_KEY
- S3_BUCKET
- S3_REGION
- PANEL_BASE_URL
- WEB_APP_URL

Mini App URL should be HTTPS and usually set to:
- https://bot.formsend.ru/app

## Local Run
```bash
docker-compose up -d --build
```

## VDS Deploy (pull + rebuild + restart)
```bash
cd /opt/qrim && git pull --ff-only && docker-compose up -d --build
```

## Nginx Example
```nginx
server {
    server_name bot.formsend.ru;

    location / {
        proxy_pass http://127.0.0.1:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Then issue SSL:
```bash
sudo certbot --nginx -d bot.formsend.ru
```

## Tests
Run tests with:
```bash
python -m pytest -q
```

Current test files:
- tests/test_database.py
- tests/test_s3_client.py

## Manual QA Scenarios
See:
- tests/payment_scenarios.md
