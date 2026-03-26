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
from api.schemas import ParseRunOut, ParseStatusOut

router = APIRouter()

logger = logging.getLogger(__name__)

# In-memory storage for active runs
_active_runs: dict[str, dict] = {}


def _extract_article(url: str) -> str | None:
    match = re.search(r"/catalog/(\d+)", url)
    return match.group(1) if match else None


def _save_apify_results(items: list[dict], db: Session) -> int:
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

        product = db.query(Product).filter(Product.wb_article == article).first()
        if not product:
            logger.warning(f"Product with article {article} not found in DB")
            continue

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
        elif seller.seller_name != supplier_name:
            seller.seller_name = supplier_name

        db.add(PriceHistory(seller_id=seller.id, price=int(price)))
        written += 1

    db.commit()
    return written


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
        "started_at": datetime.now(timezone.utc),
    }

    return ParseRunOut(
        run_id=internal_id,
        status="RUNNING",
        total_products=len(urls),
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
    except Exception as e:
        run_info.pop("processing", None)
        logger.exception("Error saving Apify results")
        return ParseStatusOut(run_id=run_id, status="FAILED", error=str(e))

    _active_runs.pop(run_id, None)
    return ParseStatusOut(run_id=run_id, status="SUCCEEDED", updated=updated)
