# tests/test_imports.py
import io
from unittest.mock import patch
from tests.conftest import HEADERS


CSV_UTF8 = b"name,url\n\xd0\xa2\xd0\xb5\xd1\x81\xd1\x82,https://wildberries.ru/catalog/100/detail.aspx\n"
CSV_CP1251 = "name,url\nТест,https://wildberries.ru/catalog/200/detail.aspx\n".encode("cp1251")
CSV_BAD_COLUMNS = b"\xd1\x82\xd0\xbe\xd0\xb2\xd0\xb0\xd1\x80,\xd1\x81\xd1\x81\xd1\x8b\xd0\xbb\xd0\xba\xd0\xb0\n\xd0\xa2\xd0\xb5\xd1\x81\xd1\x82,https://example.com\n"


def test_import_csv_utf8(client):
    resp = client.post(
        "/api/import/csv",
        files={"file": ("data.csv", io.BytesIO(CSV_UTF8), "text/csv")},
        headers=HEADERS,
    )
    assert resp.status_code == 200
    assert resp.json()["imported"] == 1


def test_import_csv_cp1251(client):
    resp = client.post(
        "/api/import/csv",
        files={"file": ("data.csv", io.BytesIO(CSV_CP1251), "text/csv")},
        headers=HEADERS,
    )
    assert resp.status_code == 200
    assert resp.json()["imported"] == 1


def test_import_csv_bad_columns_returns_400(client):
    resp = client.post(
        "/api/import/csv",
        files={"file": ("data.csv", io.BytesIO(CSV_BAD_COLUMNS), "text/csv")},
        headers=HEADERS,
    )
    assert resp.status_code == 400


def test_import_feed(client):
    csv_content = b"name,url\n\xd0\xa2\xd0\xb5\xd1\x81\xd1\x8210,https://wildberries.ru/catalog/300/detail.aspx\n"
    with patch("api.routes.imports.requests.get") as mock_get:
        mock_get.return_value.content = csv_content
        mock_get.return_value.raise_for_status = lambda: None
        resp = client.post(
            "/api/import/feed",
            json={"feed_url": "https://example.com/feed.csv"},
            headers=HEADERS,
        )
    assert resp.status_code == 200
    assert resp.json()["imported"] == 1
