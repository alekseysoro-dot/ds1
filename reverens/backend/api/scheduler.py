"""
APScheduler tasks:
- scheduled_parse: every 3 hours — run Apify Actor, wait, write prices to DB
- cleanup_old_prices: daily at 03:00 — delete records older than 180 days
"""

import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import sessionmaker

from api.apify_client import start_actor_run, check_run_status, fetch_dataset_items
from api.config import settings
from api.db import engine
from api.models import PriceHistory, Product, Seller

logger = logging.getLogger(__name__)

SessionLocal = sessionmaker(bind=engine)

_POLL_INTERVAL = 10  # seconds between status checks
_POLL_TIMEOUT = 300  # 5 minutes max wait


def _extract_article(url: str) -> str | None:
    match = re.search(r"/catalog/(\d+)", url)
    return match.group(1) if match else None


async def scheduled_parse() -> None:
    """Start Apify Actor for all products, wait for results, write to DB."""
    db = SessionLocal()
    try:
        products = db.query(Product).all()
        urls = [p.wb_url for p in products if p.wb_url]
        if not urls:
            logger.info("No products to parse")
            return

        logger.info(f"Starting scheduled parse for {len(urls)} products")
        result = await start_actor_run(settings.apify_api_token, urls)
        run_id = result["run_id"]

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
    """Parse Apify items and write to price_history."""
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

        product = db.query(Product).filter(Product.wb_article == article).first()
        if not product:
            logger.warning(f"Product with article {article} not found in DB")
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
        elif seller.seller_name != supplier_name:
            seller.seller_name = supplier_name

        db.add(PriceHistory(seller_id=seller.id, price=int(price)))
        written += 1

    db.commit()
    return written


def cleanup_old_prices() -> None:
    """Delete price_history records older than 180 days."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=180)
    db = SessionLocal()
    try:
        deleted = db.query(PriceHistory).filter(PriceHistory.recorded_at < cutoff).delete()
        db.commit()
        logger.info(f"Cleanup: deleted {deleted} old records")
    finally:
        db.close()
