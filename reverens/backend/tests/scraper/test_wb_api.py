# tests/scraper/test_wb_api.py
import pytest
from unittest.mock import patch, MagicMock


WB_API_RESPONSE = {
    "data": {
        "products": [
            {
                "id": 123456,
                "name": "Ноутбук игровой",
                "salePriceU": 150000,
                "sizes": [
                    {
                        "stocks": [{"wh": 117501, "qty": 5}],
                        "price": {"product": 150000},
                    }
                ],
                "sallerList": [
                    {"supplierId": "1001", "name": "ООО Продавец"},
                    {"supplierId": "1002", "name": "ИП Иванов"},
                ],
            }
        ]
    }
}

WB_SELLER_RESPONSE = {
    "data": {
        "products": [
            {
                "id": 123456,
                "salePriceU": 150000,
                "supplierId": "1001",
            }
        ]
    }
}


def test_fetch_product_info():
    from scraper.wb_api import fetch_product_info

    with patch("scraper.wb_api.requests.get") as mock_get, \
         patch("scraper.wb_api.time.sleep"):
        mock_resp = MagicMock()
        mock_resp.json.return_value = WB_API_RESPONSE
        mock_resp.raise_for_status = lambda: None
        mock_get.return_value = mock_resp

        result = fetch_product_info("123456")

    assert result["name"] == "Ноутбук игровой"
    assert len(result["sellers"]) == 2


def test_fetch_seller_price():
    from scraper.wb_api import fetch_seller_price

    with patch("scraper.wb_api.requests.get") as mock_get, \
         patch("scraper.wb_api.time.sleep"):
        mock_resp = MagicMock()
        mock_resp.json.return_value = WB_SELLER_RESPONSE
        mock_resp.raise_for_status = lambda: None
        mock_get.return_value = mock_resp

        price = fetch_seller_price("123456", "1001")

    assert price == 150000


def test_fetch_seller_price_not_found():
    from scraper.wb_api import fetch_seller_price

    with patch("scraper.wb_api.requests.get") as mock_get, \
         patch("scraper.wb_api.time.sleep"):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"data": {"products": []}}
        mock_resp.raise_for_status = lambda: None
        mock_get.return_value = mock_resp

        price = fetch_seller_price("123456", "1001")

    assert price is None
