from datetime import datetime

from pydantic import BaseModel


# ── Products ──────────────────────────────────────────────────────────────────

class ProductCreate(BaseModel):
    name: str
    wb_url: str
    group_name: str | None = None


class ProductOut(BaseModel):
    id: str
    name: str
    wb_article: str | None
    wb_url: str
    group_name: str | None
    is_favorite: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Prices ────────────────────────────────────────────────────────────────────

class SellerPriceOut(BaseModel):
    seller_name: str
    seller_id: str
    latest_price: int
    prev_price: int | None
    delta_pct: float | None


class PriceHistoryPoint(BaseModel):
    seller_name: str
    price: int
    recorded_at: datetime

    model_config = {"from_attributes": True}


class DeltaSummary(BaseModel):
    min_delta: float | None
    max_delta: float | None
    avg_delta: float | None
    sellers: list[dict]


# ── Import ────────────────────────────────────────────────────────────────────

class FeedImportRequest(BaseModel):
    feed_url: str


class ImportResult(BaseModel):
    imported: int
    errors: list[str]


# ── Settings ──────────────────────────────────────────────────────────────────

class SettingsOut(BaseModel):
    id: str
    email: str | None
    tg_chat_id: str | None
    threshold: int

    model_config = {"from_attributes": True}


class SettingsUpdate(BaseModel):
    email: str | None = None
    tg_chat_id: str | None = None
    threshold: int = 5


# ── Parse ────────────────────────────────────────────────────────────────────

class ParseRunIn(BaseModel):
    keyword: str | None = None


class ParseRunOut(BaseModel):
    run_id: str
    status: str
    total_products: int


class ParseStatusOut(BaseModel):
    run_id: str
    status: str
    updated: int | None = None
    error: str | None = None
