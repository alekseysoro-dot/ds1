"""
WB Public API client (no browser).

IMPORTANT: WB periodically changes query parameters (regions, dest).
Before deploy — verify current format via DevTools on wildberries.ru.
"""

import random
import time
import requests

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

_BASE_URL = "https://card.wb.ru/cards/detail"
_DEFAULT_PARAMS = {
    "appType": "1",
    "regions": "80,38,83",
    "dest": "-1257786",
    "spp": "30",
}

_MAX_RETRIES = 3
_RETRY_BASE = 2.0


def _get_with_retry(url: str, params: dict) -> dict:
    """GET with exponential retry on 429/network errors."""
    for attempt in range(_MAX_RETRIES):
        try:
            resp = requests.get(url, params=params, headers=_HEADERS, timeout=15)
            if resp.status_code == 429:
                wait = _RETRY_BASE ** attempt
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException:
            if attempt == _MAX_RETRIES - 1:
                raise
            time.sleep(_RETRY_BASE ** attempt)

    return {}


def fetch_product_info(article: str) -> dict | None:
    """
    Returns {name, sellers: [{seller_id, seller_name}]} or None.
    Sellers from sallerList of first product.
    """
    time.sleep(random.uniform(2, 5))
    data = _get_with_retry(_BASE_URL, {**_DEFAULT_PARAMS, "nm": article})

    products = data.get("data", {}).get("products", [])
    if not products:
        return None

    product = products[0]
    sellers = [
        {"seller_id": str(s["supplierId"]), "seller_name": s.get("name", "Unknown")}
        for s in product.get("sallerList", [])
    ]
    return {"name": product.get("name", ""), "sellers": sellers}


def fetch_seller_price(article: str, seller_id: str) -> int | None:
    """
    Returns price for specific seller in kopecks, or None.
    Filters by supplierId from WB API response.
    """
    time.sleep(random.uniform(1, 3))
    data = _get_with_retry(_BASE_URL, {**_DEFAULT_PARAMS, "nm": article})

    products = data.get("data", {}).get("products", [])
    for product in products:
        if str(product.get("supplierId")) == str(seller_id):
            return product.get("salePriceU")

    return None
