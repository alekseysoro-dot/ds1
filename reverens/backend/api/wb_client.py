"""Async HTTP client for the Wildberries search API."""

import httpx

WB_SEARCH_URL = "https://search.wb.ru/exactmatch/ru/common/v18/search"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


def _extract_price(product: dict) -> int | None:
    """Extract sale price in rubles from WB product JSON.

    WB stores prices in kopecks (price * 100), e.g. 10761000 = 107 610 RUB.
    We prefer ``sizes[0].price.product`` (sale price) over ``basic`` (original).
    """
    sizes = product.get("sizes", [])
    if not sizes:
        return None
    price_data = sizes[0].get("price", {})
    raw = price_data.get("product") or price_data.get("basic")
    if not raw:
        return None
    return raw // 100


async def search_wb(keyword: str) -> list[dict]:
    """Search Wildberries and return a normalised product list.

    Returns list of dicts compatible with the old Apify format::

        {
            "product_id": "721085645",
            "name": "Смартфон iPhone 17 ...",
            "current_price": 107610,
            "supplier": "Aurum Phones",
            "product_url": "https://www.wildberries.ru/catalog/721085645/detail.aspx",
        }

    Raises:
        RuntimeError: on 429 (rate-limit) or empty response.
    """
    params = {
        "appType": "1",
        "curr": "rub",
        "dest": "-1257786",
        "query": keyword,
        "resultset": "catalog",
    }
    headers = {"User-Agent": USER_AGENT}

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(WB_SEARCH_URL, params=params, headers=headers)

    if response.status_code == 429:
        raise RuntimeError("WB API rate limit (429). Try again later.")

    response.raise_for_status()
    data = response.json()

    items = []
    for p in data.get("products", []):
        price = _extract_price(p)
        if not price:
            continue

        # Skip out-of-stock products
        sizes = p.get("sizes", [])
        in_stock = any(s.get("stocks") for s in sizes)
        if not in_stock:
            continue

        article = str(p.get("id", ""))
        items.append({
            "product_id": article,
            "name": p.get("name", ""),
            "current_price": price,
            "supplier": p.get("supplier", "Unknown"),
            "product_url": f"https://www.wildberries.ru/catalog/{article}/detail.aspx",
        })

    return items
