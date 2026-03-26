"""Tests for the new scheduler (Apify-based)."""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from api.models import PriceHistory, Product, Seller


class TestScheduledParse:
    def test_calls_apify_and_writes_prices(self, db):
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
        mock_check = AsyncMock(side_effect=[
            {"status": "RUNNING", "dataset_id": "ds_1"},
            {"status": "SUCCEEDED", "dataset_id": "ds_1"},
        ])
        mock_items = AsyncMock(return_value=[
            {"url": "https://www.wildberries.ru/catalog/12345/detail.aspx", "price": 99900, "supplierName": "Seller A", "supplierId": "s1"},
        ])

        seller_id = seller.id  # capture before session may expire

        # Suppress db.close() so the test session stays usable after scheduled_parse
        original_close = db.close
        db.close = lambda: None

        with patch("api.scheduler.start_actor_run", mock_start), \
             patch("api.scheduler.check_run_status", mock_check), \
             patch("api.scheduler.fetch_dataset_items", mock_items), \
             patch("api.scheduler.SessionLocal", return_value=db), \
             patch("api.scheduler.asyncio.sleep", new_callable=AsyncMock):

            from api.scheduler import scheduled_parse
            asyncio.run(scheduled_parse())

        db.close = original_close  # restore

        prices = db.query(PriceHistory).filter(PriceHistory.seller_id == seller_id).all()
        assert len(prices) == 1
        assert prices[0].price == 99900


class TestCleanupOldPrices:
    def test_deletes_old_records(self, db):
        product = Product(name="Test", wb_url="https://wb.ru/catalog/1/detail.aspx", wb_article="1")
        db.add(product)
        db.commit()

        seller = Seller(product_id=product.id, seller_name="S", seller_id="s1")
        db.add(seller)
        db.commit()

        old = PriceHistory(seller_id=seller.id, price=100, recorded_at=datetime.now(timezone.utc) - timedelta(days=200))
        fresh = PriceHistory(seller_id=seller.id, price=200, recorded_at=datetime.now(timezone.utc))
        db.add_all([old, fresh])
        db.commit()

        seller_id = seller.id  # capture before session may expire

        # Wrap db so cleanup_old_prices can call close() without invalidating
        # the test session — we just suppress the close call.
        original_close = db.close
        db.close = lambda: None  # no-op for duration of this test

        with patch("api.scheduler.SessionLocal", return_value=db):
            from api.scheduler import cleanup_old_prices
            cleanup_old_prices()

        db.close = original_close  # restore

        remaining = db.query(PriceHistory).filter(PriceHistory.seller_id == seller_id).all()
        assert len(remaining) == 1
        assert remaining[0].price == 200
