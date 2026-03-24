# Backend Design — Price Parser (Reverens)

**Дата:** 2026-03-24
**Статус:** Approved
**Проект:** reverens/price-parser

---

## Контекст

Фронтенд (`price-parser.html`) уже существует — это single-page приложение с мониторингом цен WB.
Задача: добавить бэкенд для реального парсинга, хранения истории цен и уведомлений.

---

## Инфраструктура

- **Хостинг:** VPS на Бегет
- **Оркестрация:** Docker Compose
- **Язык бэкенда:** Python
- **Reverse proxy:** Nginx (SSL termination, проксирует запросы на порт 8000)

---

## Архитектура — Четыре контейнера

```
[HTML фронтенд] ──HTTPS──► [Nginx]
                               │
                           [FastAPI API :8000]
                               │
                           PostgreSQL :5432
                               │
                        [Scraper + Scheduler]
                       (APScheduler, каждые 3ч)
                               │
                           WB API + Playwright
```

| Контейнер | Роль | Порт |
|---|---|---|
| `nginx` | Reverse proxy, SSL | 80, 443 |
| `api` | FastAPI REST | 8000 (внутренний) |
| `scraper` | Фоновый планировщик + парсинг | — |
| `db` | PostgreSQL 16 | 5432 (внутренний) |

---

## Структура репозитория

```
reverens/
├── price-parser.html
├── backend/
│   ├── docker-compose.yml
│   ├── .env.example           # шаблон переменных окружения
│   ├── nginx/
│   │   └── nginx.conf
│   ├── api/
│   │   ├── Dockerfile
│   │   ├── main.py
│   │   ├── routes/
│   │   │   ├── products.py
│   │   │   ├── prices.py
│   │   │   └── import.py
│   │   ├── models.py
│   │   └── db.py
│   ├── scraper/
│   │   ├── Dockerfile         # базовый образ: mcr.microsoft.com/playwright/python
│   │   ├── scheduler.py
│   │   ├── wb_api.py
│   │   └── wb_scraper.py
│   └── postgres/
│       └── init.sql
```

---

## Схема базы данных

```sql
-- Товары
products
├── id          UUID  PK
├── name        TEXT
├── wb_article  TEXT        -- артикул WB
├── wb_url      TEXT        -- оригинальная ссылка
├── group_name  TEXT NULL   -- группа товаров
├── is_favorite BOOL
├── created_at  TIMESTAMP

-- Продавцы (один товар → много продавцов)
sellers
├── id          UUID  PK
├── product_id  UUID  FK → products.id
├── seller_name TEXT
├── seller_id   TEXT        -- ID продавца на WB

-- История цен (пишется каждые 3ч)
price_history
├── id          UUID  PK
├── seller_id   UUID  FK → sellers.id
├── price       INTEGER     -- цена в копейках
├── recorded_at TIMESTAMP

-- Настройки уведомлений (глобальные — одна строка на всю систему)
-- Порог единый для всех товаров (упрощение MVP)
notification_settings
├── id          UUID  PK
├── email       TEXT NULL
├── tg_chat_id  TEXT NULL
├── threshold   INTEGER     -- % порог (по умолчанию 5, применяется ко всем товарам)
```

**Очистка истории:** ежедневно удаляем записи старше 180 дней.
**Цена в копейках:** integer вместо float — избегаем погрешности.

---

## REST API эндпоинты

```
# Товары
POST   /api/products              body: {name, wb_url}
GET    /api/products              → [{id, name, wb_article, group_name, ...}]
DELETE /api/products/{id}

# Импорт
POST   /api/import/csv            multipart/form-data, файл с колонками: name, url
POST   /api/import/feed           body: {feed_url} — скачивает CSV по URL, парсит

# Цены — агрегация по продавцам
GET    /api/products
  → [
      {
        "id": "uuid",
        "name": "string",
        "wb_article": "string",
        "wb_url": "string",
        "group_name": "string | null",
        "is_favorite": "bool",
        "created_at": "ISO8601"
      }
    ]

GET    /api/prices/{product_id}
  → [
      {
        "seller_name": "string",
        "seller_id": "string",
        "latest_price": "int (копейки)",
        "prev_price": "int | null",   -- null если только одна запись по продавцу
        "delta_pct": "float | null"   -- null если prev_price == null
      }
    ]
  Логика: для каждого seller в product → последняя и предпоследняя запись из price_history

GET    /api/prices/{product_id}/history?days=30
  → [{seller_name, price, recorded_at}] — все записи за N дней по всем продавцам

GET    /api/prices/{product_id}/delta
  → {min_delta, max_delta, avg_delta, sellers: [{seller_name, delta_pct}]}
  Логика: delta между последней и предпоследней ценой по каждому продавцу

# Экспорт
GET    /api/export/csv            → CSV со всеми товарами и последними ценами

# Настройки
GET    /api/settings
PUT    /api/settings              body: {email, tg_chat_id, threshold}
```

---

## Безопасность

### CORS
```python
# FastAPI main.py
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://your-domain.com"],  # конкретный домен, не "*"
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)
```

### Аутентификация (MVP)
Простой API-ключ через заголовок `X-API-Key`, значение задаётся в `.env`.
Валидация ключа — в FastAPI middleware (не в Nginx):
```python
@app.middleware("http")
async def api_key_middleware(request: Request, call_next):
    if request.headers.get("X-API-Key") != settings.API_KEY:
        return JSONResponse(status_code=401, content={"detail": "Unauthorized"})
    return await call_next(request)
```

### Хранение секретов
Все чувствительные данные — через переменные окружения в `.env` (не в коде):
```
POSTGRES_PASSWORD=
API_KEY=
SMTP_PASSWORD=
TELEGRAM_BOT_TOKEN=
```
`.env` добавлен в `.gitignore`, в репо хранится только `.env.example`.

---

## Логика скрапера WB

### Шаг 1 — WB Public API (без браузера)
```
GET https://card.wb.ru/cards/detail?appType=1&nm={article}
→ название, базовая цена, список продавцов (sallerList с seller_id)
```

### Шаг 2 — WB API по конкретному продавцу
```
Для каждого seller_id из шага 1:
GET https://card.wb.ru/cards/detail?appType=1&nm={article}&spp=30&regions=80,38,83&dest=-1257786
    + фильтрация ответа по полю `supplierId == seller_id`
→ цена конкретного продавца из поля `salePriceU` (в копейках)
```
**Примечание:** точные query-параметры WB API (`regions`, `dest`) могут меняться.
Во время реализации необходимо верифицировать актуальный формат запроса через
DevTools на странице wildberries.ru. Playwright используется только как fallback
если API не вернул данные по продавцу.

### Антибот-меры
- Случайная задержка между запросами: `random.uniform(2, 5)` секунд
- Реалистичный User-Agent (актуальный Chrome)
- Playwright в режиме headless с `--no-sandbox` для Docker
- При получении 429/блокировке: экспоненциальный retry (3 попытки)

### Docker-образ для scraper
```dockerfile
FROM mcr.microsoft.com/playwright/python:v1.44.0-jammy
```
Этот официальный образ включает все зависимости Playwright + браузеры.

### Расписание (APScheduler)
```python
scheduler.add_job(update_all_prices, 'interval', hours=3)
scheduler.add_job(cleanup_old_prices, 'cron', hour=3)
# После update_all_prices → check_and_notify()
```

---

## CSV-парсер

Ожидаемые колонки: `name`, `url`. Поддержка кодировок UTF-8 и CP1251 (Windows Excel).

```python
def parse_csv(file_bytes: bytes) -> list[dict]:
    for encoding in ('utf-8', 'cp1251'):
        try:
            text = file_bytes.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError("Не удалось определить кодировку файла")

    reader = csv.DictReader(io.StringIO(text))
    if not {'name', 'url'}.issubset(reader.fieldnames or []):
        raise ValueError("CSV должен содержать колонки: name, url")

    return [
        {"name": row["name"].strip(), "wb_url": row["url"].strip()}
        for row in reader if row.get("url", "").strip()
    ]
```

---

## Расчёт дельты цен

```python
def price_delta(old_price: int | None, new_price: int) -> float | None:
    if not old_price:  # None или 0 — дельта неизвестна
        return None
    return round((new_price - old_price) / old_price * 100, 2)
# delta(1000, 1150) → +15.0%
# delta(1000, 900)  → -10.0%
# delta(None, 900)  → None  (продавец встречается впервые)
# delta(0, 900)     → None  (защита от деления на ноль)
```

---

## Уведомления

Триггер: `|delta| >= threshold` (по умолчанию 5%)
Каналы: Email (SMTP через `smtplib`) + Telegram Bot API (`requests`)
Момент проверки: сразу после каждого цикла скрапинга

### Email-уведомления — конфигурация SMTP
```
SMTP_HOST=smtp.beget.com      # хост SMTP-сервера
SMTP_PORT=465                 # порт (465 SSL или 587 TLS)
SMTP_USER=noreply@your-domain.com   # системный адрес отправителя
SMTP_PASSWORD=                # пароль SMTP (в .env, не в коде)
```

В таблице `notification_settings`:
- `email` — адрес **получателя** (куда приходят алерты, вводит пользователь)
- отправитель — всегда `SMTP_USER` из окружения

Все SMTP-параметры добавлены в `.env.example`.

---

## Фронтенд — интеграция

Фронтенд (`price-parser.html`) делает polling к API через `X-API-Key` заголовок:
- При загрузке страницы: `GET /api/products` + `GET /api/prices/{id}`
- При добавлении товара: `POST /api/products`
- При импорте: `POST /api/import/csv` или `POST /api/import/feed`
- Автообновление данных: раз в 3 часа (совпадает с расписанием скрапера)
