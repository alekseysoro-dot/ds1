# Apify Integration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Заменить локальный scraper-контейнер на вызов Apify Actor (`junglee/wildberries-scraper`) через REST API — два новых endpoint'а + scheduler внутри api-контейнера.

**Architecture:** FastAPI api-контейнер получает два новых route: `POST /api/parse/run` (запуск Actor'а) и `GET /api/parse/status/{run_id}` (polling + запись результатов в БД). APScheduler переезжает из scraper-контейнера в api-контейнер. Scraper-контейнер удаляется целиком.

**Tech Stack:** Python 3.12, FastAPI, httpx (async HTTP), APScheduler 3.x, SQLAlchemy (sync), pytest + httpx (тесты)

---

## Карта файлов

```
reverens/backend/
├── api/
│   ├── config.py              ← MODIFY: добавить apify_api_token
│   ├── main.py                ← MODIFY: подключить parse router + scheduler startup
│   ├── schemas.py             ← MODIFY: добавить ParseRunOut, ParseStatusOut
│   ├── apify_client.py        ← CREATE: httpx-обёртка для Apify REST API (3 функции)
│   ├── scheduler.py           ← CREATE: APScheduler — scheduled_parse + cleanup
│   ├── routes/
│   │   └── parse.py           ← CREATE: POST /api/parse/run, GET /api/parse/status/{id}
│   └── requirements.txt       ← MODIFY: добавить httpx, apscheduler
├── scraper/                   ← DELETE: весь каталог
├── docker-compose.yml         ← MODIFY: убрать сервис scraper
├── .env.example               ← MODIFY: добавить APIFY_API_TOKEN
└── tests/
    ├── conftest.py            ← MODIFY: добавить APIFY_API_TOKEN env
    ├── test_parse.py          ← CREATE: тесты для /api/parse/* endpoint'ов
    ├── test_apify_client.py   ← CREATE: тесты для apify_client.py
    ├── test_scheduler.py      ← CREATE: тесты для scheduler.py (переписать)
    └── scraper/               ← DELETE: весь каталог
```

---

## Task 1: Config + Apify HTTP client

**Files:**
- Modify: `reverens/backend/api/config.py`
- Create: `reverens/backend/api/apify_client.py`
- Create: `reverens/backend/tests/test_apify_client.py`
- Modify: `reverens/backend/api/requirements.txt`

- [ ] **Step 1: Add `httpx` to requirements**

Open `reverens/backend/api/requirements.txt` and add `httpx` to the list of dependencies (on a new line).

- [ ] **Step 2: Add `apify_api_token` to config**

In `reverens/backend/api/config.py`, add one field to `Settings`:

```python
class Settings(BaseSettings):
    database_url: str = "sqlite:///./test.db"
    api_key: str = "dev-key"
    cors_origins: str = "http://localhost"
    apify_api_token: str = ""

    class Config:
        env_file = ".env"
```

- [ ] **Step 3: Add `APIFY_API_TOKEN` to test env in conftest**

In `reverens/backend/tests/conftest.py`, add env var near the top (next to existing `os.environ` lines):

```python
os.environ["APIFY_API_TOKEN"] = "test-apify-token"
```

- [ ] **Step 4: Write failing tests for apify_client**

Create `reverens/backend/tests/test_apify_client.py`:

```python
"""Tests for Apify REST API client (httpx wrapper)."""

from unittest.mock import AsyncMock, patch

import pytest
import httpx

from api.apify_client import start_actor_run, check_run_status, fetch_dataset_items


@pytest.fixture
def mock_response():
    """Helper to create mock httpx.Response."""
    def _make(status_code: int, json_data: dict):
        resp = httpx.Response(status_code, json=json_data, request=httpx.Request("GET", "https://test"))
        return resp
    return _make


class TestStartActorRun:
    @pytest.mark.asyncio
    async def test_returns_run_id_and_dataset_id(self, mock_response):
        resp = mock_response(201, {
            "data": {
                "id": "run_abc",
                "defaultDatasetId": "ds_xyz",
                "status": "RUNNING",
            }
        })
        with patch("api.apify_client.httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            instance.post.return_value = resp
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = instance

            result = await start_actor_run("test-token", ["https://wb.ru/catalog/123/detail.aspx"])

        assert result["run_id"] == "run_abc"
        assert result["dataset_id"] == "ds_xyz"
        assert result["status"] == "RUNNING"

    @pytest.mark.asyncio
    async def test_raises_on_401(self, mock_response):
        resp = mock_response(401, {"type": "auth", "message": "Unauthorized"})
        with patch("api.apify_client.httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            instance.post.return_value = resp
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = instance

            with pytest.raises(RuntimeError, match="Invalid Apify token"):
                await start_actor_run("bad-token", ["https://wb.ru/catalog/123/detail.aspx"])


class TestCheckRunStatus:
    @pytest.mark.asyncio
    async def test_returns_status_and_dataset(self, mock_response):
        resp = mock_response(200, {
            "data": {
                "status": "SUCCEEDED",
                "defaultDatasetId": "ds_xyz",
            }
        })
        with patch("api.apify_client.httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            instance.get.return_value = resp
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = instance

            result = await check_run_status("test-token", "run_abc")

        assert result["status"] == "SUCCEEDED"
        assert result["dataset_id"] == "ds_xyz"


class TestFetchDatasetItems:
    @pytest.mark.asyncio
    async def test_returns_list_of_items(self, mock_response):
        items = [
            {"url": "https://wb.ru/catalog/123/detail.aspx", "price": 129900, "supplierName": "Seller A"},
            {"url": "https://wb.ru/catalog/123/detail.aspx", "price": 139900, "supplierName": "Seller B"},
        ]
        resp = mock_response(200, items)
        with patch("api.apify_client.httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            instance.get.return_value = resp
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = instance

            result = await fetch_dataset_items("test-token", "ds_xyz")

        assert len(result) == 2
        assert result[0]["supplierName"] == "Seller A"
```

- [ ] **Step 5: Run tests to verify they fail**

Run: `cd reverens/backend && python -m pytest tests/test_apify_client.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'api.apify_client'`

- [ ] **Step 6: Implement apify_client.py**

Create `reverens/backend/api/apify_client.py`:

```python
"""
Thin httpx wrapper for Apify REST API.

Three functions:
- start_actor_run: POST to start the Actor
- check_run_status: GET to check if run finished
- fetch_dataset_items: GET to retrieve scraped data
"""

import httpx

_APIFY_BASE = "https://api.apify.com/v2"
_ACTOR_ID = "junglee~wildberries-scraper"


async def start_actor_run(token: str, urls: list[str]) -> dict:
    """
    Start Apify Actor run.
    Returns: {"run_id": str, "dataset_id": str, "status": str}
    Raises RuntimeError on auth failure.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{_APIFY_BASE}/acts/{_ACTOR_ID}/runs",
            headers={"Authorization": f"Bearer {token}"},
            json={"urls": urls},
            timeout=30,
        )

    if resp.status_code == 401:
        raise RuntimeError("Invalid Apify token")

    resp.raise_for_status()
    data = resp.json()["data"]
    return {
        "run_id": data["id"],
        "dataset_id": data["defaultDatasetId"],
        "status": data["status"],
    }


async def check_run_status(token: str, run_id: str) -> dict:
    """
    Check Actor run status.
    Returns: {"status": str, "dataset_id": str}
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{_APIFY_BASE}/actor-runs/{run_id}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )

    resp.raise_for_status()
    data = resp.json()["data"]
    return {
        "status": data["status"],
        "dataset_id": data["defaultDatasetId"],
    }


async def fetch_dataset_items(token: str, dataset_id: str) -> list[dict]:
    """
    Fetch all items from Apify dataset.
    Returns list of dicts (raw Apify output).
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{_APIFY_BASE}/datasets/{dataset_id}/items",
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )

    resp.raise_for_status()
    return resp.json()
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd reverens/backend && python -m pytest tests/test_apify_client.py -v`
Expected: 4 tests PASSED

- [ ] **Step 8: Commit**

```bash
git add api/config.py api/apify_client.py api/requirements.txt tests/conftest.py tests/test_apify_client.py
git commit -m "feat: add Apify REST API client with httpx"
```

---

## Task 2: Parse schemas + route — POST /api/parse/run

**Files:**
- Modify: `reverens/backend/api/schemas.py`
- Create: `reverens/backend/api/routes/parse.py`
- Modify: `reverens/backend/api/main.py`
- Create: `reverens/backend/tests/test_parse.py`

- [ ] **Step 1: Add schemas for parse endpoints**

In `reverens/backend/api/schemas.py`, add at the end:

```python
# ── Parse ────────────────────────────────────────────────────────────────────

class ParseRunOut(BaseModel):
    run_id: str
    status: str
    total_products: int


class ParseStatusOut(BaseModel):
    run_id: str
    status: str
    updated: int | None = None
    error: str | None = None
```

- [ ] **Step 2: Write failing test for POST /api/parse/run**

Create `reverens/backend/tests/test_parse.py`:

```python
"""Tests for /api/parse/* endpoints."""

from unittest.mock import AsyncMock, patch

from tests.conftest import HEADERS
from api.models import Product


class TestParseRun:
    def test_starts_run_and_returns_run_id(self, client, db):
        # Seed a product
        product = Product(name="Test Product", wb_url="https://www.wildberries.ru/catalog/12345/detail.aspx", wb_article="12345")
        db.add(product)
        db.commit()

        mock_result = {"run_id": "run_abc", "dataset_id": "ds_xyz", "status": "RUNNING"}

        with patch("api.routes.parse.start_actor_run", new_callable=AsyncMock, return_value=mock_result):
            resp = client.post("/api/parse/run", headers=HEADERS)

        assert resp.status_code == 200
        data = resp.json()
        assert data["run_id"] == "run_abc"
        assert data["status"] == "RUNNING"
        assert data["total_products"] == 1

    def test_returns_error_when_no_products(self, client, db):
        resp = client.post("/api/parse/run", headers=HEADERS)
        assert resp.status_code == 400
        assert "No products" in resp.json()["detail"]

    def test_returns_error_on_invalid_token(self, client, db):
        product = Product(name="Test", wb_url="https://www.wildberries.ru/catalog/12345/detail.aspx", wb_article="12345")
        db.add(product)
        db.commit()

        with patch("api.routes.parse.start_actor_run", new_callable=AsyncMock, side_effect=RuntimeError("Invalid Apify token")):
            resp = client.post("/api/parse/run", headers=HEADERS)

        assert resp.status_code == 502
        assert "Invalid Apify token" in resp.json()["detail"]
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd reverens/backend && python -m pytest tests/test_parse.py::TestParseRun -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'api.routes.parse'`

- [ ] **Step 4: Implement parse route — POST /api/parse/run**

Create `reverens/backend/api/routes/parse.py`:

```python
"""
Parse endpoints: start Apify Actor run, check status, write results to DB.
"""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.apify_client import start_actor_run, check_run_status, fetch_dataset_items
from api.config import settings
from api.db import get_db
from api.models import PriceHistory, Product, Seller
from api.schemas import ParseRunOut, ParseStatusOut

router = APIRouter()

# In-memory storage for active runs
_active_runs: dict[str, dict] = {}


@router.post("/parse/run", response_model=ParseRunOut)
async def run_parse(db: Session = Depends(get_db)):
    products = db.query(Product).all()
    if not products:
        raise HTTPException(status_code=400, detail="No products to parse")

    urls = [p.wb_url for p in products if p.wb_url]

    try:
        result = await start_actor_run(settings.apify_api_token, urls)
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))

    internal_id = str(uuid.uuid4())
    _active_runs[internal_id] = {
        "apify_run_id": result["run_id"],
        "dataset_id": result["dataset_id"],
        "started_at": datetime.utcnow(),
    }

    return ParseRunOut(
        run_id=internal_id,
        status="RUNNING",
        total_products=len(urls),
    )
```

- [ ] **Step 5: Register router in main.py**

In `reverens/backend/api/main.py`, add import and include:

```python
from api.routes import export, imports, parse, prices, products, settings as settings_router
```

And add the router:

```python
app.include_router(parse.router, prefix="/api")
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd reverens/backend && python -m pytest tests/test_parse.py::TestParseRun -v`
Expected: 3 tests PASSED

- [ ] **Step 7: Run full test suite to check for regressions**

Run: `cd reverens/backend && python -m pytest -v`
Expected: All existing tests + 3 new PASSED

- [ ] **Step 8: Commit**

```bash
git add api/schemas.py api/routes/parse.py api/main.py tests/test_parse.py
git commit -m "feat: add POST /api/parse/run endpoint"
```

---

## Task 3: GET /api/parse/status/{run_id} + write results to DB

**Files:**
- Modify: `reverens/backend/api/routes/parse.py`
- Modify: `reverens/backend/tests/test_parse.py`

- [ ] **Step 1: Write failing tests for status endpoint**

Add to `reverens/backend/tests/test_parse.py`:

```python
class TestParseStatus:
    def test_returns_running_status(self, client, db):
        # Manually insert a run into _active_runs
        from api.routes.parse import _active_runs
        _active_runs["test-run-1"] = {
            "apify_run_id": "apify_run_abc",
            "dataset_id": "ds_xyz",
            "started_at": datetime.utcnow(),
        }

        mock_status = {"status": "RUNNING", "dataset_id": "ds_xyz"}
        with patch("api.routes.parse.check_run_status", new_callable=AsyncMock, return_value=mock_status):
            resp = client.get("/api/parse/status/test-run-1", headers=HEADERS)

        assert resp.status_code == 200
        assert resp.json()["status"] == "RUNNING"
        _active_runs.clear()

    def test_returns_succeeded_and_writes_prices(self, client, db):
        # Seed product + seller
        product = Product(name="Test", wb_url="https://www.wildberries.ru/catalog/12345/detail.aspx", wb_article="12345")
        db.add(product)
        db.commit()

        seller = Seller(product_id=product.id, seller_name="Seller A", seller_id="s1")
        db.add(seller)
        db.commit()

        from api.routes.parse import _active_runs
        _active_runs["test-run-2"] = {
            "apify_run_id": "apify_run_abc",
            "dataset_id": "ds_xyz",
            "started_at": datetime.utcnow(),
        }

        mock_status = {"status": "SUCCEEDED", "dataset_id": "ds_xyz"}
        mock_items = [
            {"url": "https://www.wildberries.ru/catalog/12345/detail.aspx", "price": 129900, "supplierName": "Seller A", "supplierId": "s1"},
        ]

        with patch("api.routes.parse.check_run_status", new_callable=AsyncMock, return_value=mock_status), \
             patch("api.routes.parse.fetch_dataset_items", new_callable=AsyncMock, return_value=mock_items):
            resp = client.get("/api/parse/status/test-run-2", headers=HEADERS)

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "SUCCEEDED"
        assert data["updated"] == 1

        # Verify price was written to DB
        from api.models import PriceHistory
        prices = db.query(PriceHistory).filter(PriceHistory.seller_id == seller.id).all()
        assert len(prices) == 1
        assert prices[0].price == 129900

        _active_runs.clear()

    def test_returns_404_for_unknown_run(self, client):
        resp = client.get("/api/parse/status/nonexistent", headers=HEADERS)
        assert resp.status_code == 404

    def test_returns_failed_status(self, client, db):
        from api.routes.parse import _active_runs
        _active_runs["test-run-3"] = {
            "apify_run_id": "apify_run_fail",
            "dataset_id": None,
            "started_at": datetime.utcnow(),
        }

        mock_status = {"status": "FAILED", "dataset_id": None}
        with patch("api.routes.parse.check_run_status", new_callable=AsyncMock, return_value=mock_status):
            resp = client.get("/api/parse/status/test-run-3", headers=HEADERS)

        assert resp.status_code == 200
        assert resp.json()["status"] == "FAILED"
        _active_runs.clear()
```

Add missing imports at top of `tests/test_parse.py`:

```python
from datetime import datetime
from api.models import Product, Seller
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd reverens/backend && python -m pytest tests/test_parse.py::TestParseStatus -v`
Expected: FAIL — `404 Not Found` (endpoint not implemented)

- [ ] **Step 3: Implement GET /api/parse/status/{run_id}**

Add to `reverens/backend/api/routes/parse.py`:

```python
import logging
import re

logger = logging.getLogger(__name__)


def _extract_article(url: str) -> str | None:
    """Extract WB article number from URL."""
    match = re.search(r"/catalog/(\d+)", url)
    return match.group(1) if match else None


def _save_apify_results(items: list[dict], db: Session) -> int:
    """
    Parse Apify dataset items and write prices to DB.
    Returns number of price records written.

    Expected item fields (verify against real Apify output):
    - url: WB product URL
    - price / salePriceU: price (int)
    - supplierName: seller name
    - supplierId: seller ID on WB
    """
    written = 0
    for item in items:
        url = item.get("url", "")
        article = _extract_article(url)
        if not article:
            logger.warning(f"Could not extract article from URL: {url}")
            continue

        price = item.get("price") or item.get("salePriceU")
        if not price:
            logger.warning(f"No price for article {article}")
            continue

        supplier_name = item.get("supplierName", "Unknown")
        supplier_id = str(item.get("supplierId", ""))

        # Find product by article
        product = db.query(Product).filter(Product.wb_article == article).first()
        if not product:
            logger.warning(f"Product with article {article} not found in DB")
            continue

        # Upsert seller
        seller = (
            db.query(Seller)
            .filter(Seller.product_id == product.id, Seller.seller_id == supplier_id)
            .first()
        )
        if not seller:
            seller = Seller(
                product_id=product.id,
                seller_name=supplier_name,
                seller_id=supplier_id,
            )
            db.add(seller)
            db.flush()

        db.add(PriceHistory(seller_id=seller.id, price=int(price)))
        written += 1

    db.commit()
    return written


@router.get("/parse/status/{run_id}", response_model=ParseStatusOut)
async def parse_status(run_id: str, db: Session = Depends(get_db)):
    run_info = _active_runs.get(run_id)
    if not run_info:
        raise HTTPException(status_code=404, detail="Run not found")

    try:
        status = await check_run_status(
            settings.apify_api_token, run_info["apify_run_id"]
        )
    except Exception as e:
        return ParseStatusOut(run_id=run_id, status="FAILED", error=str(e))

    if status["status"] == "RUNNING":
        return ParseStatusOut(run_id=run_id, status="RUNNING")

    if status["status"] == "FAILED":
        _active_runs.pop(run_id, None)
        return ParseStatusOut(run_id=run_id, status="FAILED", error="Apify Actor failed")

    # SUCCEEDED — fetch results and write to DB
    try:
        items = await fetch_dataset_items(
            settings.apify_api_token, status["dataset_id"]
        )
        updated = _save_apify_results(items, db)
    except Exception as e:
        logger.exception("Error saving Apify results")
        return ParseStatusOut(run_id=run_id, status="FAILED", error=str(e))

    _active_runs.pop(run_id, None)
    return ParseStatusOut(run_id=run_id, status="SUCCEEDED", updated=updated)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd reverens/backend && python -m pytest tests/test_parse.py -v`
Expected: 7 tests PASSED (3 from Task 2 + 4 new)

- [ ] **Step 5: Run full test suite**

Run: `cd reverens/backend && python -m pytest -v`
Expected: All PASSED

- [ ] **Step 6: Commit**

```bash
git add api/routes/parse.py tests/test_parse.py
git commit -m "feat: add GET /api/parse/status with DB write logic"
```

---

## Task 4: Scheduler — migrate to api-контейнер

**Files:**
- Create: `reverens/backend/api/scheduler.py`
- Create: `reverens/backend/tests/test_scheduler_new.py`
- Modify: `reverens/backend/api/main.py`
- Modify: `reverens/backend/api/requirements.txt`

- [ ] **Step 1: Add `apscheduler` to requirements**

Add `apscheduler` to `reverens/backend/api/requirements.txt`.

- [ ] **Step 2: Write failing tests for scheduler**

Create `reverens/backend/tests/test_scheduler_new.py`:

```python
"""Tests for the new scheduler (Apify-based)."""

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from api.models import PriceHistory, Product, Seller


class TestScheduledParse:
    def test_calls_apify_and_writes_prices(self, db):
        """scheduled_parse should start Apify run, poll until SUCCEEDED, write results."""
        product = Product(
            name="Test",
            wb_url="https://www.wildberries.ru/catalog/12345/detail.aspx",
            wb_article="12345",
        )
        db.add(product)
        db.commit()

        seller = Seller(product_id=product.id, seller_name="Seller A", seller_id="s1")
        db.add(seller)
        db.commit()

        mock_start = AsyncMock(return_value={
            "run_id": "run_1",
            "dataset_id": "ds_1",
            "status": "RUNNING",
        })
        # First call RUNNING, second call SUCCEEDED
        mock_check = AsyncMock(side_effect=[
            {"status": "RUNNING", "dataset_id": "ds_1"},
            {"status": "SUCCEEDED", "dataset_id": "ds_1"},
        ])
        mock_items = AsyncMock(return_value=[
            {"url": "https://www.wildberries.ru/catalog/12345/detail.aspx", "price": 99900, "supplierName": "Seller A", "supplierId": "s1"},
        ])

        with patch("api.scheduler.start_actor_run", mock_start), \
             patch("api.scheduler.check_run_status", mock_check), \
             patch("api.scheduler.fetch_dataset_items", mock_items), \
             patch("api.scheduler.Session", return_value=db), \
             patch("api.scheduler.asyncio.sleep", new_callable=AsyncMock):

            from api.scheduler import scheduled_parse
            asyncio.get_event_loop().run_until_complete(scheduled_parse())

        prices = db.query(PriceHistory).filter(PriceHistory.seller_id == seller.id).all()
        assert len(prices) == 1
        assert prices[0].price == 99900


class TestCleanupOldPrices:
    def test_deletes_old_records(self, db):
        """cleanup_old_prices should delete records older than 180 days."""
        product = Product(name="Test", wb_url="https://wb.ru/catalog/1/detail.aspx", wb_article="1")
        db.add(product)
        db.commit()

        seller = Seller(product_id=product.id, seller_name="S", seller_id="s1")
        db.add(seller)
        db.commit()

        # Old record (200 days ago)
        old = PriceHistory(seller_id=seller.id, price=100, recorded_at=datetime.utcnow() - timedelta(days=200))
        # Fresh record
        fresh = PriceHistory(seller_id=seller.id, price=200, recorded_at=datetime.utcnow())
        db.add_all([old, fresh])
        db.commit()

        with patch("api.scheduler.Session", return_value=db):
            from api.scheduler import cleanup_old_prices
            cleanup_old_prices()

        remaining = db.query(PriceHistory).filter(PriceHistory.seller_id == seller.id).all()
        assert len(remaining) == 1
        assert remaining[0].price == 200
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd reverens/backend && python -m pytest tests/test_scheduler_new.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'api.scheduler'`

- [ ] **Step 4: Implement scheduler.py**

Create `reverens/backend/api/scheduler.py`:

```python
"""
APScheduler tasks:
- scheduled_parse: every 3 hours — run Apify Actor, wait, write prices to DB
- cleanup_old_prices: daily at 03:00 — delete records older than 180 days
"""

import asyncio
import logging
from datetime import datetime, timedelta

from sqlalchemy.orm import sessionmaker

from api.apify_client import start_actor_run, check_run_status, fetch_dataset_items
from api.config import settings
from api.db import engine
from api.models import PriceHistory, Product, Seller

logger = logging.getLogger(__name__)

Session = sessionmaker(bind=engine)

_POLL_INTERVAL = 10  # seconds between status checks
_POLL_TIMEOUT = 300  # 5 minutes max wait


async def scheduled_parse() -> None:
    """Start Apify Actor for all products, wait for results, write to DB."""
    db = Session()
    try:
        products = db.query(Product).all()
        urls = [p.wb_url for p in products if p.wb_url]
        if not urls:
            logger.info("No products to parse")
            return

        logger.info(f"Starting scheduled parse for {len(urls)} products")
        result = await start_actor_run(settings.apify_api_token, urls)
        run_id = result["run_id"]

        # Poll until done or timeout
        elapsed = 0
        while elapsed < _POLL_TIMEOUT:
            status = await check_run_status(settings.apify_api_token, run_id)

            if status["status"] == "SUCCEEDED":
                items = await fetch_dataset_items(settings.apify_api_token, status["dataset_id"])
                written = _save_prices(items, db)
                logger.info(f"Scheduled parse complete: {written} prices written")
                return

            if status["status"] == "FAILED":
                logger.error(f"Apify run {run_id} failed")
                return

            await asyncio.sleep(_POLL_INTERVAL)
            elapsed += _POLL_INTERVAL

        logger.error(f"Apify run {run_id} timed out after {_POLL_TIMEOUT}s")

    except Exception:
        db.rollback()
        logger.exception("Error during scheduled parse")
    finally:
        db.close()


def _save_prices(items: list[dict], db) -> int:
    """Parse Apify items and write to price_history. Returns count of records written."""
    import re

    written = 0
    for item in items:
        url = item.get("url", "")
        match = re.search(r"/catalog/(\d+)", url)
        if not match:
            continue

        article = match.group(1)
        price = item.get("price") or item.get("salePriceU")
        if not price:
            continue

        product = db.query(Product).filter(Product.wb_article == article).first()
        if not product:
            continue

        supplier_id = str(item.get("supplierId", ""))
        supplier_name = item.get("supplierName", "Unknown")

        seller = (
            db.query(Seller)
            .filter(Seller.product_id == product.id, Seller.seller_id == supplier_id)
            .first()
        )
        if not seller:
            seller = Seller(product_id=product.id, seller_name=supplier_name, seller_id=supplier_id)
            db.add(seller)
            db.flush()

        db.add(PriceHistory(seller_id=seller.id, price=int(price)))
        written += 1

    db.commit()
    return written


def cleanup_old_prices() -> None:
    """Delete price_history records older than 180 days."""
    cutoff = datetime.utcnow() - timedelta(days=180)
    db = Session()
    try:
        deleted = db.query(PriceHistory).filter(PriceHistory.recorded_at < cutoff).delete()
        db.commit()
        logger.info(f"Cleanup: deleted {deleted} old records")
    finally:
        db.close()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd reverens/backend && python -m pytest tests/test_scheduler_new.py -v`
Expected: 2 tests PASSED

- [ ] **Step 6: Wire scheduler into main.py**

In `reverens/backend/api/main.py`, add scheduler startup at the end of the file:

```python
from contextlib import asynccontextmanager
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from api.scheduler import scheduled_parse, cleanup_old_prices


def _run_scheduled_parse():
    """Wrapper to run async scheduled_parse from sync APScheduler."""
    import asyncio
    loop = asyncio.get_event_loop()
    loop.create_task(scheduled_parse())


scheduler = AsyncIOScheduler()
scheduler.add_job(_run_scheduled_parse, "interval", hours=3)
scheduler.add_job(cleanup_old_prices, "cron", hour=3, minute=0)


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler.start()
    yield
    scheduler.shutdown()
```

Then update the FastAPI app creation to use lifespan:

```python
app = FastAPI(title="Price Parser API", lifespan=lifespan)
```

- [ ] **Step 7: Run full test suite**

Run: `cd reverens/backend && python -m pytest -v`
Expected: All PASSED

- [ ] **Step 8: Commit**

```bash
git add api/scheduler.py api/main.py api/requirements.txt tests/test_scheduler_new.py
git commit -m "feat: add APScheduler with Apify-based scheduled parse"
```

---

## Task 5: Cleanup — delete scraper container + update infra

**Files:**
- Delete: `reverens/backend/scraper/` (entire directory)
- Delete: `reverens/backend/tests/scraper/` (entire directory)
- Modify: `reverens/backend/docker-compose.yml`
- Modify: `reverens/backend/.env.example`

- [ ] **Step 1: Add APIFY_API_TOKEN to .env.example**

Add to `reverens/backend/.env.example`:

```
APIFY_API_TOKEN=
```

- [ ] **Step 2: Remove scraper service from docker-compose.yml**

In `reverens/backend/docker-compose.yml`, remove the entire `scraper:` service block and its `depends_on` entries. Keep `nginx`, `api`, and `db` services.

- [ ] **Step 3: Delete scraper directory**

```bash
rm -rf reverens/backend/scraper/
rm -rf reverens/backend/tests/scraper/
```

- [ ] **Step 4: Run full test suite to confirm nothing breaks**

Run: `cd reverens/backend && python -m pytest -v`
Expected: All PASSED (scraper tests removed, no imports left)

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "chore: remove scraper container, add APIFY_API_TOKEN to env"
```

---

## Task 6: Verify end-to-end with real Apify (manual)

**Files:** None (manual verification)

- [ ] **Step 1: Set real APIFY_API_TOKEN in .env**

Create `.env` in `reverens/backend/` with a real Apify token (get from https://console.apify.com/account/integrations).

- [ ] **Step 2: Start the API locally**

```bash
cd reverens/backend && uvicorn api.main:app --reload --port 8000
```

- [ ] **Step 3: Add a test product**

```bash
curl -X POST http://localhost:8000/api/products \
  -H "X-API-Key: dev-key" \
  -H "Content-Type: application/json" \
  -d '{"name": "Test WB Product", "wb_url": "https://www.wildberries.ru/catalog/12345/detail.aspx"}'
```

- [ ] **Step 4: Trigger a parse run**

```bash
curl -X POST http://localhost:8000/api/parse/run -H "X-API-Key: dev-key"
```

Expect: `{"run_id": "...", "status": "RUNNING", "total_products": 1}`

- [ ] **Step 5: Poll status until SUCCEEDED**

```bash
curl http://localhost:8000/api/parse/status/{run_id} -H "X-API-Key: dev-key"
```

Repeat every 10 seconds. Expect: eventually `{"status": "SUCCEEDED", "updated": N}`.

- [ ] **Step 6: Verify field mapping**

If Apify returns field names different from expected (`price`, `supplierName`, `supplierId`), update `_save_apify_results()` in `parse.py` and `_save_prices()` in `scheduler.py` to match actual field names. Re-run tests.

- [ ] **Step 7: Commit any field mapping fixes**

```bash
git add -A
git commit -m "fix: adjust Apify field mapping to match real output"
```
