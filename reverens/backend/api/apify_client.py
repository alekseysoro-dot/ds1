# api/apify_client.py
"""Thin async HTTP client for the Apify API."""

import httpx

BASE_URL = "https://api.apify.com/v2"
ACTOR_ID = "junglee~wildberries-scraper"


async def start_actor_run(token: str, urls: list[str]) -> dict:
    """Start an Apify actor run for the given URLs.

    Returns:
        dict with keys: run_id, dataset_id, status

    Raises:
        RuntimeError: if the API returns HTTP 401 (invalid token).
    """
    endpoint = f"{BASE_URL}/acts/{ACTOR_ID}/runs"
    headers = {"Authorization": f"Bearer {token}"}
    payload = {"startUrls": [{"url": u} for u in urls]}

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(endpoint, headers=headers, json=payload)

    if response.status_code == 401:
        raise RuntimeError(f"Apify authentication failed: 401 Unauthorized")

    response.raise_for_status()
    data = response.json()["data"]
    return {
        "run_id": data["id"],
        "dataset_id": data["defaultDatasetId"],
        "status": data["status"],
    }


async def check_run_status(token: str, run_id: str) -> dict:
    """Get the current status of an Apify run.

    Returns:
        dict with keys: status, dataset_id
    """
    endpoint = f"{BASE_URL}/actor-runs/{run_id}"
    headers = {"Authorization": f"Bearer {token}"}

    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(endpoint, headers=headers)

    response.raise_for_status()
    data = response.json()["data"]
    return {
        "status": data["status"],
        "dataset_id": data["defaultDatasetId"],
    }


async def fetch_dataset_items(token: str, dataset_id: str) -> list[dict]:
    """Fetch all items from an Apify dataset.

    Returns:
        List of item dicts as returned by the Apify dataset API.
    """
    endpoint = f"{BASE_URL}/datasets/{dataset_id}/items"
    headers = {"Authorization": f"Bearer {token}"}

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(endpoint, headers=headers, params={"format": "json"})

    response.raise_for_status()
    return response.json()
