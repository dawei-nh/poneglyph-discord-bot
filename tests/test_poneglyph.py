import inspect
import json
from pathlib import Path

import httpx
import pytest

from optcg_card_bot.errors import PoneglyphNotFoundError, PoneglyphRateLimitError
from optcg_card_bot.poneglyph import PoneglyphClient

FIXTURES = Path(__file__).parent / "fixtures" / "poneglyph"


def test_public_methods_use_required_keyword_only_signatures() -> None:
    assert str(inspect.signature(PoneglyphClient)) == (
        "(*, http_client: 'httpx.AsyncClient | None' = None, "
        "base_url: 'str' = 'https://api.poneglyph.one', "
        "api_prefix: 'str' = '/v1', timeout: 'float' = 10.0, "
        "min_interval: 'float' = 0.25, max_retries: 'int' = 2, "
        "user_agent: 'str' = 'poneglyph-discord-bot/0.1.0') -> 'None'"
    )
    assert str(inspect.signature(PoneglyphClient.search_cards)) == (
        "(self, query: 'str | None', *, page: 'int' = 1, limit: 'int' = 60, "
        "sort: 'str | None' = None, order: 'str | None' = None, "
        "collapse: 'str' = 'card', lang: 'str' = 'en') -> 'SearchResponse'"
    )
    assert str(inspect.signature(PoneglyphClient.get_card)) == (
        "(self, card_number: 'str', *, lang: 'str' = 'en') -> 'CardDetail'"
    )
    assert str(inspect.signature(PoneglyphClient.get_random)) == (
        "(self, *, lang: 'str' = 'en', set: 'str | None' = None, "
        "color: 'str | None' = None, type: 'str | None' = None, "
        "rarity: 'str | None' = None) -> 'CardDetail'"
    )
    assert str(inspect.signature(PoneglyphClient.get_random_from_query)) == (
        "(self, query: 'str', *, lang: 'str' = 'en', "
        "random_page: 'Callable[[int], int] | None' = None) -> 'CardDetail'"
    )


@pytest.mark.asyncio
async def test_owned_client_sets_json_accept_and_user_agent_headers() -> None:
    client = PoneglyphClient(min_interval=0)

    try:
        headers = client._http.headers

        assert headers["Accept"] == "application/json"
        assert headers["User-Agent"] == "poneglyph-discord-bot/0.1.0"
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_search_url_construction() -> None:
    requests: list[httpx.Request] = []
    payload = json.loads((FIXTURES / "search_luffy.json").read_text())

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=payload)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://api.example.test",
    ) as http:
        client = PoneglyphClient(http_client=http, api_prefix="/v1", min_interval=0)
        response = await client.search_cards("luffy", limit=2)

    assert response.pagination.limit == 2
    assert requests[0].url.path == "/v1/search"
    assert requests[0].url.params["q"] == "luffy"
    assert requests[0].url.params["limit"] == "2"
    assert requests[0].url.params["collapse"] == "card"


@pytest.mark.asyncio
async def test_search_omits_falsey_optional_params() -> None:
    requests: list[httpx.Request] = []
    payload = json.loads((FIXTURES / "search_luffy.json").read_text())

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=payload)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://api.example.test",
    ) as http:
        client = PoneglyphClient(http_client=http, api_prefix="/v1", min_interval=0)
        await client.search_cards(None, sort="", order="")

    assert "q" not in requests[0].url.params
    assert "sort" not in requests[0].url.params
    assert "order" not in requests[0].url.params


@pytest.mark.asyncio
async def test_get_card_maps_404() -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(404)),
        base_url="https://api.example.test",
    ) as http:
        client = PoneglyphClient(http_client=http, api_prefix="/v1", min_interval=0)

        with pytest.raises(PoneglyphNotFoundError):
            await client.get_card("OP99-999")


@pytest.mark.asyncio
async def test_429_maps_to_rate_limit_after_retries() -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(429)),
        base_url="https://api.example.test",
    ) as http:
        client = PoneglyphClient(
            http_client=http,
            api_prefix="/v1",
            min_interval=0,
            max_retries=0,
        )

        with pytest.raises(PoneglyphRateLimitError):
            await client.search_cards("luffy")


@pytest.mark.asyncio
async def test_random_query_sampling_uses_search_total() -> None:
    search_payload = json.loads((FIXTURES / "search_op01_001.json").read_text())
    card_payload = json.loads((FIXTURES / "card_op01_001.json").read_text())
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) <= 2:
            return httpx.Response(200, json=search_payload)
        return httpx.Response(200, json=card_payload)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://api.example.test",
    ) as http:
        client = PoneglyphClient(http_client=http, api_prefix="/v1", min_interval=0)
        result = await client.get_random_from_query(
            "OP01-001",
            random_page=lambda total: 1,
        )

    assert result.card_number == "OP01-001"
    assert len(requests) == 3
    assert requests[0].url.params["limit"] == "1"
    assert requests[1].url.params["page"] == "1"
    assert requests[2].url.path == "/v1/cards/OP01-001"
