import inspect
import json
from pathlib import Path

import httpx
import pytest

from optcg_card_bot.errors import (
    PoneglyphNotFoundError,
    PoneglyphRateLimitError,
    PoneglyphServerError,
)
from optcg_card_bot.poneglyph import PoneglyphClient

FIXTURES = Path(__file__).parent / "fixtures" / "poneglyph"


def assert_param(
    signature: inspect.Signature,
    name: str,
    kind: inspect._ParameterKind,
    default: object = inspect.Parameter.empty,
) -> None:
    parameter = signature.parameters[name]

    assert parameter.kind is kind
    assert parameter.default == default


def test_public_methods_use_required_keyword_only_signatures() -> None:
    init_signature = inspect.signature(PoneglyphClient)
    search_signature = inspect.signature(PoneglyphClient.search_cards)
    card_signature = inspect.signature(PoneglyphClient.get_card)
    prices_signature = inspect.signature(PoneglyphClient.get_prices)
    random_signature = inspect.signature(PoneglyphClient.get_random)
    random_query_signature = inspect.signature(PoneglyphClient.get_random_from_query)

    for name, default in {
        "http_client": None,
        "base_url": "https://api.poneglyph.one",
        "api_prefix": "/v1",
        "timeout": 10.0,
        "min_interval": 0.25,
        "max_retries": 2,
        "user_agent": "poneglyph-discord-bot/0.1.0",
    }.items():
        assert_param(init_signature, name, inspect.Parameter.KEYWORD_ONLY, default)

    assert_param(search_signature, "query", inspect.Parameter.POSITIONAL_OR_KEYWORD)
    for name, default in {
        "page": 1,
        "limit": 60,
        "sort": None,
        "order": None,
        "collapse": "card",
        "lang": "en",
    }.items():
        assert_param(search_signature, name, inspect.Parameter.KEYWORD_ONLY, default)

    assert_param(
        card_signature,
        "card_number",
        inspect.Parameter.POSITIONAL_OR_KEYWORD,
    )
    assert_param(card_signature, "lang", inspect.Parameter.KEYWORD_ONLY, "en")

    assert_param(
        prices_signature,
        "card_number",
        inspect.Parameter.POSITIONAL_OR_KEYWORD,
    )
    assert_param(prices_signature, "days", inspect.Parameter.KEYWORD_ONLY, 30)

    for name, default in {
        "lang": "en",
        "set": None,
        "color": None,
        "type": None,
        "rarity": None,
    }.items():
        assert_param(random_signature, name, inspect.Parameter.KEYWORD_ONLY, default)

    assert_param(
        random_query_signature,
        "query",
        inspect.Parameter.POSITIONAL_OR_KEYWORD,
    )
    assert_param(random_query_signature, "lang", inspect.Parameter.KEYWORD_ONLY, "en")
    assert_param(
        random_query_signature,
        "random_page",
        inspect.Parameter.KEYWORD_ONLY,
        None,
    )


@pytest.mark.asyncio
async def test_owned_client_sends_json_accept_and_user_agent_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[httpx.Request] = []
    payload = json.loads((FIXTURES / "search_luffy.json").read_text())
    original_async_client = httpx.AsyncClient

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=payload)

    class ObservedAsyncClient(httpx.AsyncClient):
        def __init__(self, *args: object, **kwargs: object) -> None:
            kwargs["transport"] = httpx.MockTransport(handler)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", ObservedAsyncClient)
    client = PoneglyphClient(base_url="https://api.example.test", min_interval=0)

    try:
        await client.search_cards("luffy")

        assert requests[0].headers["Accept"] == "application/json"
        assert requests[0].headers["User-Agent"] == "poneglyph-discord-bot/0.1.0"
    finally:
        await client.aclose()
        monkeypatch.setattr(httpx, "AsyncClient", original_async_client)


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
async def test_autocomplete_url_construction() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"data": ["Monkey.D.Luffy", "Roronoa Zoro"]})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://api.example.test",
    ) as http:
        client = PoneglyphClient(http_client=http, api_prefix="/v1", min_interval=0)
        response = await client.autocomplete_cards("luffy")

    assert response == ("Monkey.D.Luffy", "Roronoa Zoro")
    assert requests[0].url.path == "/v1/cards/autocomplete"
    assert requests[0].url.params["q"] == "luffy"


@pytest.mark.asyncio
async def test_malformed_autocomplete_response_maps_to_server_error() -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"data": [123]})
        ),
        base_url="https://api.example.test",
    ) as http:
        client = PoneglyphClient(http_client=http, api_prefix="/v1", min_interval=0)

        with pytest.raises(PoneglyphServerError):
            await client.autocomplete_cards("luffy")


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
async def test_malformed_search_response_maps_to_server_error() -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={})),
        base_url="https://api.example.test",
    ) as http:
        client = PoneglyphClient(http_client=http, api_prefix="/v1", min_interval=0)

        with pytest.raises(PoneglyphServerError):
            await client.search_cards("luffy")


@pytest.mark.asyncio
async def test_get_prices_url_construction() -> None:
    requests: list[httpx.Request] = []
    payload = {
        "data": [
            {
                "variant_index": 0,
                "label": "Super Pre-Release",
                "sub_type": "Alternate Art",
                "tcgplayer_url": "https://tcgplayer.example/op01-001",
                "market_price": "1.91",
                "low_price": "1.00",
                "mid_price": "2.25",
                "high_price": "9.99",
                "fetched_at": "2026-06-04T12:00:00.000Z",
            }
        ]
    }

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=payload)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://api.example.test",
    ) as http:
        client = PoneglyphClient(http_client=http, api_prefix="/v1", min_interval=0)
        prices = await client.get_prices("op01-001", days=14)

    assert prices[0].variant_index == 0
    assert prices[0].market_price == "1.91"
    assert requests[0].url.path == "/v1/prices/OP01-001"
    assert requests[0].url.params["days"] == "14"


@pytest.mark.asyncio
async def test_malformed_prices_response_maps_to_server_error() -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={})),
        base_url="https://api.example.test",
    ) as http:
        client = PoneglyphClient(http_client=http, api_prefix="/v1", min_interval=0)

        with pytest.raises(PoneglyphServerError):
            await client.get_prices("OP01-001")


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
async def test_random_summary_response_fetches_card_detail() -> None:
    search_payload = json.loads((FIXTURES / "search_op01_001.json").read_text())
    random_payload = {"data": search_payload["data"][0]}
    card_payload = json.loads((FIXTURES / "card_op01_001.json").read_text())
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/v1/random":
            return httpx.Response(200, json=random_payload)
        return httpx.Response(200, json=card_payload)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://api.example.test",
    ) as http:
        client = PoneglyphClient(http_client=http, api_prefix="/v1", min_interval=0)
        result = await client.get_random()

    assert result.card_number == "OP01-001"
    assert [request.url.path for request in requests] == [
        "/v1/random",
        "/v1/cards/OP01-001",
    ]


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
