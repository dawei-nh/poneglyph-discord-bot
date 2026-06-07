import httpx
import pytest

from optcg_card_bot.models import AutocompleteResponse, PriceHistoryResponse

BASE_URL = "https://api.poneglyph.one"


@pytest.mark.live
def test_live_openapi_has_mvp_endpoints() -> None:
    response = httpx.get(f"{BASE_URL}/openapi.json", timeout=20.0)
    response.raise_for_status()
    contract = response.json()

    paths = contract["paths"]
    assert "/v1/search" in paths
    assert "/v1/cards/{card_number}" in paths
    assert "/v1/random" in paths
    assert "/v1/cards/autocomplete" in paths
    assert "/v1/prices/{card_number}" in paths


@pytest.mark.live
def test_live_direct_card_lookup_op01_001() -> None:
    response = httpx.get(f"{BASE_URL}/v1/cards/OP01-001", timeout=20.0)
    response.raise_for_status()
    payload = response.json()

    assert payload["data"]["card_number"] == "OP01-001"


@pytest.mark.live
def test_live_bare_card_number_search() -> None:
    response = httpx.get(
        f"{BASE_URL}/v1/search",
        params={"q": "OP01-001", "limit": "5", "collapse": "card"},
        timeout=20.0,
    )
    response.raise_for_status()
    payload = response.json()

    assert any(card["card_number"] == "OP01-001" for card in payload["data"])


@pytest.mark.live
def test_live_broad_luffy_search_returns_cards() -> None:
    response = httpx.get(
        f"{BASE_URL}/v1/search",
        params={"q": "luffy", "limit": "2", "collapse": "card"},
        timeout=20.0,
    )
    response.raise_for_status()
    payload = response.json()

    assert payload["data"]


@pytest.mark.live
def test_live_autocomplete_returns_supported_shape() -> None:
    response = httpx.get(
        f"{BASE_URL}/v1/cards/autocomplete",
        params={"q": "luffy"},
        timeout=20.0,
    )
    response.raise_for_status()
    payload = response.json()

    autocomplete = AutocompleteResponse.model_validate(payload)

    assert autocomplete.data
    assert all(value.strip() for value in autocomplete.data)


@pytest.mark.live
def test_live_price_history_returns_supported_shape() -> None:
    response = httpx.get(
        f"{BASE_URL}/v1/prices/OP01-001",
        params={"days": "7"},
        timeout=20.0,
    )
    response.raise_for_status()
    payload = response.json()

    PriceHistoryResponse.model_validate(payload)
