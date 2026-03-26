"""Parse endpoints: start Apify Actor run, check status, write results to DB."""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.apify_client import start_actor_run
from api.config import settings
from api.db import get_db
from api.models import Product
from api.schemas import ParseRunOut

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
        "started_at": datetime.now(timezone.utc),
    }

    return ParseRunOut(
        run_id=internal_id,
        status="RUNNING",
        total_products=len(urls),
    )
