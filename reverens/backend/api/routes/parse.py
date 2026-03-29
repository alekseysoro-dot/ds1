"""Parse endpoints: start Apify Actor run, check status, write results to DB."""

import logging
import re
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.apify_client import start_actor_run, check_run_status, fetch_dataset_items
from api.config import settings
from api.db import get_db
from api.models import Product, PriceHistory, Seller
from api.notifier import check_price_alerts
from api.schemas import ParseRunIn, ParseRunOut, ParseStatusOut

router = APIRouter()

logger = logging.getLogger(__name__)

# In-memory storage for active runs
_active_runs: dict[str, dict] = {}


def _parse_price(raw: str) -> int | None:
    """Extract integer price from scrapestorm format like '29 398 ₽'."""
    digits = re.sub(r"[^\d]", "", str(raw))
    return int(digits) if digits else None


def _save_apify_results(items: list[dict], db: Session) -> int:
    """Save all scrapestorm results: auto-create Products, Sellers, write prices."""
    written = 0
    for item in items:
        article = str(item.get("product_id", ""))
        if not article:
            continue

        price = _parse_price(item.get("current_price", ""))
        if not price:
            logger.warning(f"No price for article {article}")
            continue

        product = db.query(Product).filter(Product.wb_article == article).first()
        if not product:
            product = Product(
                name=item.get("name", ""),
                wb_article=article,
                wb_url=item.get("product_url", ""),
            )
            db.add(product)
            db.flush()

        supplier_name = item.get("supplier", "Unknown")

        seller = (
            db.query(Seller)
            .filter(Seller.product_id == product.id, Seller.seller_name == supplier_name)
            .first()
        )
        if not seller:
            seller = Seller(
                product_id=product.id,
                seller_name=supplier_name,
                seller_id=supplier_name,
            )
            db.add(seller)
            db.flush()

        db.add(PriceHistory(seller_id=seller.id, price=price))
        written += 1

    db.commit()
    return written


@router.post("/parse/run", response_model=ParseRunOut)
async def run_parse(body: ParseRunIn = None, db: Session = Depends(get_db)):
    keyword = (body.keyword if body and body.keyword else None) or settings.apify_keyword
    if not keyword:
        raise HTTPException(status_code=400, detail="Keyword not provided and APIFY_KEYWORD not configured")

    try:
        result = await start_actor_run(settings.apify_api_token, keyword)
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))

    internal_id = str(uuid.uuid4())
    _active_runs[internal_id] = {
        "apify_run_id": result["run_id"],
        "dataset_id": result["dataset_id"],
        "started_at": datetime.now(timezone.utc),
    }

    existing = db.query(Product).count()

    return ParseRunOut(
        run_id=internal_id,
        status="RUNNING",
        total_products=existing,
    )


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

    # SUCCEEDED — guard against duplicate writes on repeated polling
    if run_info.get("processing"):
        return ParseStatusOut(run_id=run_id, status="RUNNING")
    run_info["processing"] = True

    try:
        items = await fetch_dataset_items(
            settings.apify_api_token, status["dataset_id"]
        )
        updated = _save_apify_results(items, db)

        try:
            alerts = check_price_alerts(db)
            if alerts:
                logger.info(f"Sent {alerts} price alert(s)")
        except Exception:
            logger.exception("Error checking price alerts")

    except Exception as e:
        run_info.pop("processing", None)
        logger.exception("Error saving Apify results")
        return ParseStatusOut(run_id=run_id, status="FAILED", error=str(e))

    _active_runs.pop(run_id, None)
    return ParseStatusOut(run_id=run_id, status="SUCCEEDED", updated=updated)
