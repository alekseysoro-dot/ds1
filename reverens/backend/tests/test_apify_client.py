# tests/test_apify_client.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_response(status_code: int, json_data: dict):
    """Build a mock httpx.Response-like object."""
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.json.return_value = json_data
    return mock_resp


# ---------------------------------------------------------------------------
# TestStartActorRun
# ---------------------------------------------------------------------------

class TestStartActorRun:
    @pytest.mark.asyncio
    async def test_returns_run_id_and_dataset_id(self):
        from api.apify_client import start_actor_run

        response_payload = {
            "data": {
                "id": "run-abc-123",
                "status": "READY",
                "defaultDatasetId": "dataset-xyz-456",
            }
        }
        mock_resp = _make_response(201, response_payload)

        with patch("api.apify_client.httpx.AsyncClient") as MockClient:
            mock_instance = AsyncMock()
            mock_instance.post = AsyncMock(return_value=mock_resp)
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await start_actor_run(
                token="test-token",
                urls=["https://wildberries.ru/catalog/12345/detail.aspx"],
            )

        assert result["run_id"] == "run-abc-123"
        assert result["dataset_id"] == "dataset-xyz-456"
        assert result["status"] == "READY"

    @pytest.mark.asyncio
    async def test_raises_on_401(self):
        from api.apify_client import start_actor_run

        mock_resp = _make_response(401, {"error": {"message": "Unauthorized"}})

        with patch("api.apify_client.httpx.AsyncClient") as MockClient:
            mock_instance = AsyncMock()
            mock_instance.post = AsyncMock(return_value=mock_resp)
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            with pytest.raises(RuntimeError, match="401"):
                await start_actor_run(token="bad-token", urls=["https://example.com"])


# ---------------------------------------------------------------------------
# TestCheckRunStatus
# ---------------------------------------------------------------------------

class TestCheckRunStatus:
    @pytest.mark.asyncio
    async def test_returns_status_and_dataset(self):
        from api.apify_client import check_run_status

        response_payload = {
            "data": {
                "id": "run-abc-123",
                "status": "SUCCEEDED",
                "defaultDatasetId": "dataset-xyz-456",
            }
        }
        mock_resp = _make_response(200, response_payload)

        with patch("api.apify_client.httpx.AsyncClient") as MockClient:
            mock_instance = AsyncMock()
            mock_instance.get = AsyncMock(return_value=mock_resp)
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await check_run_status(token="test-token", run_id="run-abc-123")

        assert result["status"] == "SUCCEEDED"
        assert result["dataset_id"] == "dataset-xyz-456"


# ---------------------------------------------------------------------------
# TestFetchDatasetItems
# ---------------------------------------------------------------------------

class TestFetchDatasetItems:
    @pytest.mark.asyncio
    async def test_returns_list_of_items(self):
        from api.apify_client import fetch_dataset_items

        items = [
            {"url": "https://wildberries.ru/catalog/1", "price": 999},
            {"url": "https://wildberries.ru/catalog/2", "price": 1299},
        ]
        response_payload = {"items": items}
        mock_resp = _make_response(200, response_payload)

        with patch("api.apify_client.httpx.AsyncClient") as MockClient:
            mock_instance = AsyncMock()
            mock_instance.get = AsyncMock(return_value=mock_resp)
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await fetch_dataset_items(
                token="test-token", dataset_id="dataset-xyz-456"
            )

        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["price"] == 999
