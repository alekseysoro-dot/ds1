import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.db import get_db
from api.models import Product
from api.schemas import ProductCreate, ProductOut

router = APIRouter()

_WB_ARTICLE_RE = re.compile(r"/catalog/(\d+)/")


def _extract_article(url: str) -> str | None:
    m = _WB_ARTICLE_RE.search(url)
    return m.group(1) if m else None


@router.post("/products", response_model=ProductOut)
def create_product(body: ProductCreate, db: Session = Depends(get_db)):
    product = Product(
        name=body.name,
        wb_url=body.wb_url,
        wb_article=_extract_article(body.wb_url),
        group_name=body.group_name,
    )
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


@router.get("/products", response_model=list[ProductOut])
def list_products(db: Session = Depends(get_db)):
    return db.query(Product).order_by(Product.created_at.desc()).all()


@router.delete("/products/{product_id}")
def delete_product(product_id: str, db: Session = Depends(get_db)):
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    db.delete(product)
    db.commit()
    return {"deleted": product_id}
