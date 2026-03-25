import csv
import io

import requests
from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.orm import Session

from api.db import get_db
from api.models import Product
from api.schemas import FeedImportRequest, ImportResult

router = APIRouter()


def _parse_csv(file_bytes: bytes) -> list[dict]:
    text = None
    for encoding in ("utf-8", "cp1251"):
        try:
            text = file_bytes.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise ValueError("Не удалось определить кодировку файла")

    reader = csv.DictReader(io.StringIO(text))
    if not {"name", "url"}.issubset(set(reader.fieldnames or [])):
        raise ValueError("CSV должен содержать колонки: name, url")

    return [
        {"name": row["name"].strip(), "wb_url": row["url"].strip()}
        for row in reader
        if row.get("url", "").strip()
    ]


def _import_rows(rows: list[dict], db: Session) -> ImportResult:
    imported = 0
    errors = []
    for row in rows:
        try:
            product = Product(name=row["name"], wb_url=row["wb_url"])
            db.add(product)
            imported += 1
        except Exception as e:
            errors.append(str(e))
    db.commit()
    return ImportResult(imported=imported, errors=errors)


@router.post("/import/csv", response_model=ImportResult)
async def import_csv(file: UploadFile, db: Session = Depends(get_db)):
    content = await file.read()
    try:
        rows = _parse_csv(content)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _import_rows(rows, db)


@router.post("/import/feed", response_model=ImportResult)
def import_feed(body: FeedImportRequest, db: Session = Depends(get_db)):
    try:
        resp = requests.get(body.feed_url, timeout=30)
        resp.raise_for_status()
        rows = _parse_csv(resp.content)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Ошибка загрузки фида: {e}")
    return _import_rows(rows, db)
