# tests/test_products.py
import pytest
from tests.conftest import HEADERS


def test_create_product(client):
    resp = client.post(
        "/api/products",
        json={"name": "Ноутбук", "wb_url": "https://wildberries.ru/catalog/123/detail.aspx"},
        headers=HEADERS,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Ноутбук"
    assert "id" in data


def test_list_products_empty(client):
    resp = client.get("/api/products", headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_products_after_create(client):
    client.post(
        "/api/products",
        json={"name": "Телефон", "wb_url": "https://wildberries.ru/catalog/456/detail.aspx"},
        headers=HEADERS,
    )
    resp = client.get("/api/products", headers=HEADERS)
    assert len(resp.json()) == 1


def test_delete_product(client):
    create = client.post(
        "/api/products",
        json={"name": "Мышь", "wb_url": "https://wildberries.ru/catalog/789/detail.aspx"},
        headers=HEADERS,
    )
    product_id = create.json()["id"]
    resp = client.delete(f"/api/products/{product_id}", headers=HEADERS)
    assert resp.status_code == 200
    assert client.get("/api/products", headers=HEADERS).json() == []


def test_delete_nonexistent_product_returns_404(client):
    resp = client.delete("/api/products/nonexistent-id", headers=HEADERS)
    assert resp.status_code == 404
