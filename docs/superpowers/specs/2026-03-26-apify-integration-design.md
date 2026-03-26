# Apify Integration Design — Price Parser (Reverens)

**Дата:** 2026-03-26
**Статус:** Approved
**Проект:** reverens/price-parser
**Предыдущий дизайн:** [2026-03-24-backend-design.md](2026-03-24-backend-design.md)

---

## Контекст

Бэкенд уже спроектирован: FastAPI + PostgreSQL + scraper-контейнер с WB API + Playwright.
Задача: **заменить локальный scraper-контейнер на Apify** — внешний сервис для парсинга.

Пользователь передаёт ссылку → Apify Actor парсит цену → результат записывается в БД.

---

## Ключевые решения

| Решение | Выбор |
|---|---|
| Apify Actor | `junglee/wildberries-scraper` |
| Где API Route | FastAPI (существующий api-контейнер) |
| Токен | `.env` → `APIFY_API_TOKEN` |
| Ручной запуск | `POST /api/parse/run` → polling `GET /api/parse/status/{id}` |
| Автозапуск | APScheduler каждые 3ч внутри api-контейнера |
| Apify SDK | Не используем — чистый httpx |
| Scraper-контейнер | Удаляется |

---

## Архитектура и Data Flow

### Что меняется

Scraper-контейнер удаляется. Вместо него API-контейнер сам вызывает Apify REST API.

```
[Фронтенд] ──► POST /api/parse/run ──► [FastAPI]
                                            │
                                      httpx → Apify REST API
                                            │
                                      Apify Actor (junglee/wildberries-scraper)
                                            │
[Фронтенд] ◄── GET /api/parse/status/{id}  │
                                            │
                                      GET dataset items ──► записываем в БД
                                            │
                                        PostgreSQL
```

### Поток данных — кнопка "Парсить"

1. Фронтенд → `POST /api/parse/run` (тело пустое — парсим все товары)
2. FastAPI берёт все `products` из БД, собирает список WB URL-ов
3. FastAPI → Apify REST API: `POST /v2/acts/junglee~wildberries-scraper/runs` с input `{urls: [...]}`
4. Apify возвращает `run_id` → FastAPI сохраняет в in-memory dict, возвращает фронтенду `{run_id, status: "RUNNING"}`
5. Фронтенд поллит `GET /api/parse/status/{run_id}` каждые 5 секунд
6. FastAPI → Apify: `GET /v2/actor-runs/{run_id}` — проверяет статус
7. Когда `status == "SUCCEEDED"` → FastAPI забирает dataset: `GET /v2/datasets/{id}/items`
8. Парсит результат, записывает цены в `price_history`, возвращает `{status: "SUCCEEDED", updated: N}`

### Поток данных — расписание (каждые 3ч)

APScheduler вызывает `scheduled_parse()` — та же логика, но:
- Не создаёт запись в `_active_runs` (некому поллить)
- Сам ждёт завершения в цикле (sleep 10 сек, таймаут 5 мин)
- При успехе — забирает данные и пишет в БД
- При ошибке — логирует, следующая попытка через 3ч

---

## Новые endpoint'ы

### POST /api/parse/run

- **Вход:** ничего (парсим все товары из БД)
- **Выход:** `{run_id: "abc123", status: "RUNNING", total_products: 12}`
- **Логика:**
  1. SELECT все products из БД
  2. Собрать список WB URL-ов
  3. POST к Apify API — запустить Actor
  4. Сохранить run_id в in-memory dict с метаданными
  5. Вернуть ответ

### GET /api/parse/status/{run_id}

- **Вход:** `run_id` в URL
- **Выход:** `{run_id, status, updated?, error?}`
- **Логика:**
  1. GET к Apify API — проверить статус run
  2. Если `RUNNING` → вернуть `{status: "RUNNING"}`
  3. Если `SUCCEEDED` → забрать dataset, записать цены в БД, вернуть `{status: "SUCCEEDED", updated: N}`
  4. Если `FAILED` → вернуть `{status: "FAILED", error: "..."}`

---

## Взаимодействие с Apify REST API

Три HTTP-запроса через `httpx`:

### 1. Запуск Actor'а

```
POST https://api.apify.com/v2/acts/junglee~wildberries-scraper/runs
Headers: Authorization: Bearer {APIFY_API_TOKEN}
Body: {"urls": ["https://www.wildberries.ru/catalog/12345/detail.aspx", ...]}
→ Response: {data: {id: "run_abc", defaultDatasetId: "ds_xyz", status: "RUNNING"}}
```

### 2. Проверка статуса

```
GET https://api.apify.com/v2/actor-runs/{run_id}
Headers: Authorization: Bearer {APIFY_API_TOKEN}
→ Response: {data: {status: "SUCCEEDED" | "RUNNING" | "FAILED", defaultDatasetId: "ds_xyz"}}
```

### 3. Забор результатов

```
GET https://api.apify.com/v2/datasets/{dataset_id}/items
Headers: Authorization: Bearer {APIFY_API_TOKEN}
→ Response: [{name: "...", price: 1299, seller: "...", url: "..."}, ...]
```

### Маппинг результатов Apify → БД

| Поле Apify | Поле в БД | Таблица |
|---|---|---|
| `url` → извлекаем артикул | `wb_article` | `products` (поиск) |
| `seller` / `supplierName` | `seller_name` | `sellers` (upsert) |
| `price` / `salePriceU` | `price` (в копейках) | `price_history` (insert) |

**Важно:** точные имена полей в ответе Apify нужно верифицировать при реализации — запустить тестовый run и посмотреть реальный ответ.

---

## Структура файлов — изменения

### Новые файлы

```
reverens/backend/
├── api/
│   ├── routes/
│   │   └── parse.py          ← POST /api/parse/run, GET /api/parse/status/{id}
│   └── scheduler.py          ← APScheduler: scheduled_parse каждые 3ч, cleanup в 3:00
```

### Изменения в существующих файлах

| Файл | Что меняется |
|---|---|
| `api/main.py` | Подключить `routes/parse.py` роутер, запуск scheduler |
| `api/config.py` | Добавить `APIFY_API_TOKEN` в Settings |
| `.env.example` | Добавить `APIFY_API_TOKEN=` |
| `docker-compose.yml` | Убрать сервис `scraper` |

### Удаляемые файлы

```
reverens/backend/scraper/     ← весь каталог (заменён Apify)
```

---

## Хранение активных run'ов

Простой in-memory dict в `parse.py`:

```python
_active_runs: dict[str, dict] = {}
# Ключ: внутренний run_id
# Значение: {"apify_run_id": "...", "dataset_id": None, "started_at": datetime}
```

Для MVP достаточно. Если сервер перезапустится — run теряется, но через 3ч scheduler запустит новый.

---

## Обработка ошибок

| Ситуация | Действие |
|---|---|
| Apify вернул 401 | Ошибка токена → `{status: "FAILED", error: "Invalid Apify token"}` |
| Apify вернул 429 | Rate limit → retry через 10 сек (максимум 2 раза) |
| Actor FAILED | Вернуть ошибку фронтенду, не писать в БД |
| Товар не найден в dataset | Пропустить, залогировать warning |
| Цена = 0 или null | Пропустить запись, залогировать warning |

---

## Scheduler (APScheduler)

Переезжает из `scraper/scheduler.py` → `api/scheduler.py`.

```python
scheduler.add_job(scheduled_parse, 'interval', hours=3)
scheduler.add_job(cleanup_old_prices, 'cron', hour=3)
```

`scheduled_parse()` отличается от ручного запуска:
- Не создаёт запись в `_active_runs`
- Сам ждёт завершения Actor'а (sleep 10 сек между проверками, таймаут 5 мин)
- При успехе — забирает данные и пишет в БД
- При ошибке — логирует, следующая попытка через 3ч

---

## Фронтенд — изменения в `price-parser.html`

Кнопка **"▶ Парсить"** — замена mock-логики на реальный вызов:

1. Клик → `POST /api/parse/run` → получить `run_id`
2. Показать прогресс-бар (уже реализован)
3. Polling: `GET /api/parse/status/{run_id}` каждые 5 сек
4. `SUCCEEDED` → скрыть прогресс-бар, toast "Обновлено N товаров", перезагрузить таблицу
5. `FAILED` → скрыть прогресс-бар, toast с ошибкой (красный)

Автообновление по расписанию — фронтенд не участвует. Scheduler делает всё сам.

---

## Вне скоупа

- Apify Python SDK (используем чистый httpx)
- Webhook от Apify (используем polling)
- Персистентное хранение run'ов (in-memory достаточно для MVP)
- Уведомления о результатах парсинга (email/TG — остаётся из предыдущего дизайна, подключается позже)
