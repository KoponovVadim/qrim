# Soundbot: Telegram Bot + Web Admin Panel

Проект: бот на aiogram 3.x + веб-панель на FastAPI для продажи сэмпл-паков.
Хранение метаданных: SQLite.
Хранение файлов: S3-совместимое хранилище (Cloudflare R2 и аналоги).
Запуск: Docker Compose.

## 1) Что было сделано

### Базовая архитектура
- Создана структура проекта с модулями:
  - `app/config.py`
  - `app/database.py`
  - `app/s3_client.py`
  - `app/bot/*`
  - `app/web/*`
- Добавлены Docker-файлы и переменные окружения:
  - `Dockerfile`
  - `docker-compose.yml`
  - `.env.example`
  - `requirements.txt`

### Конфиг
- Реализован централизованный конфиг через pydantic-settings:
  - BOT_TOKEN, ADMIN_IDS, WEB_PASSWORD, WEB_SECRET_KEY, WEB_PORT
  - S3_ENDPOINT, S3_ACCESS_KEY, S3_SECRET_KEY, S3_BUCKET, S3_REGION
  - USDT_WALLET, TON_WALLET
  - PANEL_BASE_URL, WEB_APP_URL, DATABASE_PATH, FREE_PACK_KEY
- Добавлены переменные для новых фич:
  - `TRON_API_KEY`
  - `SUBSCRIPTION_DAYS`
  - `SUBSCRIPTION_PRICE_USDT`

### База данных
- Реализованы таблицы и функции для:
  - packs
  - orders
  - settings
  - admins
- Добавлена таблица подписок:
  - subscriptions(user_id, start_date, end_date, status)
- Добавлены методы:
  - проверка активной подписки
  - продление/активация подписки
  - отмена подписки

### S3
- Реализован клиент на boto3:
  - `upload_file`
  - `generate_download_url`
  - `delete_file`
  - `download_file`

### Telegram-бот
- Реализованы пользовательские сценарии:
  - `/start`
  - витрина паков
  - детали пака
  - демо-файлы из S3
  - покупка через FSM (ввод tx hash)
  - бесплатный пак (signed URL)
  - помощь
- Реализованы админ-сценарии:
  - `/stats`
  - `/confirm <order_id>`
  - `/add_pack` (упрощенно: ссылка на веб-панель)
- Добавлено логирование ошибок уведомления админов.

### Web-панель
- Реализованы страницы:
  - `/login`
  - `/` (dashboard)
  - `/packs`
  - `/packs/add`
  - `/packs/edit/{id}`
  - `/orders`
  - подтверждение заказа из панели
- Реализована сессия через cookie + `WEB_SECRET_KEY`.
- Исправлен единый helper авторизации `auth_or_redirect`.

### Дополнительный функционал
- **Автопроверка USDT (TronGrid):**
  - Добавлена функция проверки tx hash в `app/bot/utils.py`.
  - Для платежей USDT в обычной покупке: попытка автоподтверждения и моментальная выдача ссылки.
- **Подписка:**
  - Добавлена кнопка `Подписка` в боте.
  - Добавлен сценарий продления подписки через tx hash.
  - При активной подписке покупка пака пропускается, ссылка отдается сразу.
- **Бандл 3 за 2:**
  - Добавлена кнопка `Бандл`.
  - Реализован упрощенный flow создания заказа `BUNDLE_USDT`.
  - Подтверждение бандла в боте/панели отправляет ссылки на все паки из набора.
- **Оркестратор автогенерации паков:**
  - Добавлен скрипт `scripts/pack_orchestrator.py` (заготовка под интеграцию с ComfyUI + загрузка в панель).

### Тесты
- Добавлены базовые тесты:
  - `tests/test_database.py`
  - `tests/test_s3_client.py`

## 2) Что НЕ было сделано (или сделано частично)

1. Полноценный FSM `/add_pack` в Telegram с загрузкой zip/cover/demo напрямую в боте **не реализован**.
   - Сейчас `/add_pack` в админ-командах только отправляет ссылку в веб-панель.

2. Полноценная e2e-валидация платежей (разные сети, сложные кейсы TRC20, повторная сверка в фоне, webhook-подтверждения) **не реализована**.
   - Сделан только базовый онлайн-чек через TronGrid в момент получения tx hash.

3. Реальная интеграция генерации аудио через ComfyUI в оркестраторе **не реализована**.
   - Сейчас это рабочая заготовка с плейсхолдерами.

4. Полный прогон интеграционных тестов в контейнере не выполнялся в этой сессии.

## 3) Как запустить проект

### Шаг 1. Подготовить окружение
1. Скопируйте `.env.example` в `.env`.
2. Заполните обязательные значения:
   - `BOT_TOKEN`
   - `ADMIN_IDS`
   - `USDT_WALLET`
   - `TON_WALLET`
   - `S3_ENDPOINT`
   - `S3_ACCESS_KEY`
   - `S3_SECRET_KEY`
   - `S3_BUCKET`
   - `WEB_PASSWORD`
   - `WEB_SECRET_KEY`
  - `PANEL_BASE_URL=https://bot.formsend.ru`
  - `WEB_APP_URL=https://bot.formsend.ru/app`
3. Для автопроверки USDT заполните:
   - `TRON_API_KEY`
4. При необходимости измените:
   - `WEB_PORT`
   - `DATABASE_PATH`
   - `PANEL_BASE_URL`
   - `FREE_PACK_KEY`
   - `SUBSCRIPTION_DAYS`
   - `SUBSCRIPTION_PRICE_USDT`

### Шаг 2. Запуск контейнеров на VDS
В корне проекта:

```bash
docker-compose up -d --build
```

Для вашей схемы деплоя допустим compose с пробросом `8001:8000` у приложения.

### Шаг 3. Nginx reverse proxy
На VDS в nginx должен быть прокси на контейнер приложения:

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

SSL:

```bash
sudo certbot --nginx -d bot.formsend.ru
```

### Шаг 4. Проверка
1. Админ-панель (backend интерфейс): `https://bot.formsend.ru`.
2. Telegram Mini App: `https://bot.formsend.ru/app`.
3. Оба URL должны открываться через HTTPS (обязательно для Telegram WebApp).
4. Авторизация в панели:
   - по `WEB_PASSWORD` или
   - по Telegram ID админа.
5. Бот в Telegram:
   - отправьте `/start`.

## 4) Что нужно сделать вам после запуска

1. В панели добавить минимум 1 пак через `/packs/add`:
   - zip
   - обложка (опционально)
   - демо (опционально)

2. Проверить путь покупки:
   - открыть витрину в боте
   - выбрать пак
   - пройти оплату и отправить tx hash

3. Выбрать режим подтверждения:
   - оставить ручной (`/confirm` или кнопка в панели),
   - или использовать авто-подтверждение USDT (нужен рабочий `TRON_API_KEY`).

4. Проверить доступность S3 bucket и права ключа:
   - upload/get/delete должны работать.

5. Проверить, что `PANEL_BASE_URL` указывает на реально доступный URL панели (важно для ссылок админам).

6. Проверить, что `WEB_APP_URL` указывает на Mini App URL:
  - `https://bot.formsend.ru/app`

7. В BotFather настроить кнопку Mini App на этот же URL (`https://bot.formsend.ru/app`).

## 5) Рекомендуемые дальнейшие доработки (следующий этап)

1. Реализовать полный Telegram FSM `/add_pack` (загрузка файлов в боте + запись в БД).
2. Добавить фоновые ретраи проверки tx hash и защиту от дублирующих транзакций.
3. Добавить webhook/worker для платежей вместо проверки только в момент ввода tx.
4. Добавить отдельные тарифы подписки и оплату подписки в TON.
5. Добавить unit/integration тесты для `handlers/user.py`, `handlers/admin.py`, `web/main.py`.
6. Добавить миграции БД (например, через Alembic) вместо ad-hoc schema update в `init_db()`.
7. Подключить реальную генерацию через ComfyUI в `scripts/pack_orchestrator.py`.

## 6) Быстрый чек-лист

- [ ] `.env` заполнен
- [ ] контейнер поднялся (`docker-compose ps`)
- [ ] вход в веб-панель работает
- [ ] пак добавляется через панель
- [ ] бот отвечает на `/start`
- [ ] создание заказа работает
- [ ] подтверждение заказа отправляет ссылку
- [ ] S3 signed URL открывается
