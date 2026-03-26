"""Tests for /api/parse/* endpoints."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from tests.conftest import HEADERS
from api.models import Product, Seller, PriceHistory


@pytest.fixture(autouse=True)
def clean_active_runs():
    yield
    from api.routes.parse import _active_runs
    _active_runs.clear()


class TestParseRun:
    def test_starts_run_and_returns_run_id(self, client, db):
        product = Product(name="Test Product", wb_url="https://www.wildberries.ru/catalog/12345/detail.aspx", wb_article="12345")
        db.add(product)
        db.commit()

        mock_result = {"run_id": "run_abc", "dataset_id": "ds_xyz", "status": "RUNNING"}

        with patch("api.routes.parse.start_actor_run", new_callable=AsyncMock, return_value=mock_result):
            resp = client.post("/api/parse/run", headers=HEADERS)

        assert resp.status_code == 200
        data = resp.json()
        assert data["run_id"]  # UUID, not empty
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


class TestParseStatus:
    def test_returns_running_status(self, client, db):
        from api.routes.parse import _active_runs
        _active_runs["test-run-1"] = {
            "apify_run_id": "apify_run_abc",
            "dataset_id": "ds_xyz",
            "started_at": datetime.now(timezone.utc),
        }

        mock_status = {"status": "RUNNING", "dataset_id": "ds_xyz"}
        with patch("api.routes.parse.check_run_status", new_callable=AsyncMock, return_value=mock_status):
            resp = client.get("/api/parse/status/test-run-1", headers=HEADERS)

        assert resp.status_code == 200
        assert resp.json()["status"] == "RUNNING"


    def test_returns_succeeded_and_writes_prices(self, client, db):
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
            "started_at": datetime.now(timezone.utc),
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

        prices = db.query(PriceHistory).filter(PriceHistory.seller_id == seller.id).all()
        assert len(prices) == 1
        assert prices[0].price == 129900


    def test_returns_404_for_unknown_run(self, client):
        resp = client.get("/api/parse/status/nonexistent", headers=HEADERS)
        assert resp.status_code == 404

    def test_returns_failed_status(self, client, db):
        from api.routes.parse import _active_runs
        _active_runs["test-run-3"] = {
            "apify_run_id": "apify_run_fail",
            "dataset_id": None,
            "started_at": datetime.now(timezone.utc),
        }

        mock_status = {"status": "FAILED", "dataset_id": None}
        with patch("api.routes.parse.check_run_status", new_callable=AsyncMock, return_value=mock_status):
            resp = client.get("/api/parse/status/test-run-3", headers=HEADERS)

        assert resp.status_code == 200
        assert resp.json()["status"] == "FAILED"

