# QRIM Lounge Manager Bot

Telegram-бот для автоматизации бронирований и ответов на вопросы.

## Запуск

1. Клонируйте репозиторий
2. Скопируйте `.env.example` в `.env`
3. Заполните переменные окружения
4. Поместите Google credentials в корень проекта как `credentials.json`
5. Запустите:

```bash
docker compose up -d
```

6. Проверьте статус:

```bash
curl http://localhost:8001/health
```

## Настройка webhook

После запуска установите webhook:

```bash
curl "https://api.telegram.org/bot<TG_TOKEN>/setWebhook?url=https://bot.formsend.ru/webhook"
```

Проверка webhook:

```bash
curl https://bot.formsend.ru/webhook-info
```

## Nginx конфигурация

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

SSL через certbot:

```bash
sudo certbot --nginx -d bot.formsend.ru
```

## Google Sheets структура

### Лист `venue`
| key | value |
|-----|-------|

### Лист `tables`
| table_id | name | capacity | zone | active |
|----------|------|----------|------|--------|

### Лист `bookings`
| booking_id | date | time | guests | table_id | name | phone | source | status | created_at |
|------------|------|------|--------|----------|------|-------|--------|--------|------------|

### Лист `events`
| event_id | title | description | date_from | date_to | time_from | time_to | image_url | booking_cta | active |
|----------|-------|-------------|-----------|---------|-----------|---------|-----------|-------------|--------|

### Лист `prices`
| price_id | category | name | description | price | unit | active |
|----------|----------|------|-------------|-------|------|--------|

## Остановка

```bash
docker compose down
```
