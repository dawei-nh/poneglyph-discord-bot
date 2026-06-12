import json
from pathlib import Path

import pytest

from optcg_card_bot.commands import CommandOutcomeKind, CommandService
from optcg_card_bot.errors import NoSearchResultsError
from optcg_card_bot.models import CardDetailResponse, PricePoint, SearchResponse

FIXTURES = Path(__file__).parent / "fixtures" / "poneglyph"


class FakeClient:
    def __init__(self) -> None:
        self.card = CardDetailResponse.model_validate(
            json.loads((FIXTURES / "card_op01_001.json").read_text())
        ).data
        self.search_response = SearchResponse.model_validate(
            json.loads((FIXTURES / "search_luffy.json").read_text())
        )
        self.random_card = self.card
        self.search_kwargs: dict[str, object] = {}
        self.search_cards_kwargs: dict[str, object] = {}
        self.prices = (
            PricePoint(
                variant_index=0,
                label="Super Pre-Release",
                sub_type="Alternate Art",
                tcgplayer_url="https://tcgplayer.example/op01-001",
                market_price="1.91",
                low_price="1.00",
                mid_price="2.25",
                high_price="9.99",
                fetched_at="2026-06-04T12:00:00.000Z",
            ),
        )
        self.get_random_kwargs: dict[str, str] = {}
        self.get_random_from_query_args: tuple[str, str] | None = None
        self.get_prices_args: tuple[str, int] | None = None
        self.raise_no_search_results = False
        self.autocomplete_queries: list[str] = []
        self.autocomplete_response = tuple(f"Card {index}" for index in range(30))

    async def get_card(self, card_number: str, *, lang: str = "en"):
        return self.card

    async def search_cards(
        self,
        query: str | None,
        *,
        page: int = 1,
        limit: int = 60,
        sort: str | None = None,
        order: str | None = None,
        collapse: str = "card",
        lang: str = "en",
    ):
        self.search_kwargs = {
            "query": query,
            "page": page,
            "limit": limit,
            "sort": sort,
            "order": order,
            "collapse": collapse,
            "lang": lang,
        }
        self.search_cards_kwargs = self.search_kwargs
        return self.search_response

    async def get_random(self, **kwargs):
        self.get_random_kwargs = kwargs
        return self.random_card

    async def get_random_from_query(self, query: str, *, lang: str = "en"):
        self.get_random_from_query_args = (query, lang)
        if self.raise_no_search_results:
            raise NoSearchResultsError
        return self.random_card

    async def autocomplete_cards(self, query: str):
        self.autocomplete_queries.append(query)
        return self.autocomplete_response

    async def get_prices(self, card_number: str, *, days: int = 30):
        self.get_prices_args = (card_number, days)
        return self.prices


@pytest.mark.asyncio
async def test_card_direct_number_returns_public_card() -> None:
    service = CommandService(FakeClient())

    outcome = await service.card("OP01-001")

    assert outcome.kind is CommandOutcomeKind.PUBLIC_CARD
    assert outcome.card is not None


@pytest.mark.asyncio
async def test_card_ambiguous_returns_picker() -> None:
    service = CommandService(FakeClient())

    outcome = await service.card("luffy")

    assert outcome.kind is CommandOutcomeKind.PICKER
    assert len(outcome.choices) == 2


@pytest.mark.asyncio
async def test_search_always_returns_picker() -> None:
    service = CommandService(FakeClient())

    outcome = await service.search("luffy")

    assert outcome.kind is CommandOutcomeKind.PICKER
    assert outcome.message == "Search results | Page 1 | 126 total"


@pytest.mark.parametrize(
    ("query", "backend_query"),
    [
        ("Mosshead", "Zoro"),
        ("MOSS", "Zoro"),
        ("moss-head", "Zoro"),
        ("moss head", "Zoro"),
        ("curlybrows", "Sanji"),
        ("dumdum", "Gum-Gum"),
        ("dum-dum", "Gum-Gum"),
        ("dum dum", "Gum-Gum"),
        ("mamaregan", "mamaragan"),
        ("mama-regan", "mamaragan"),
        ("mama regan", "mamaragan"),
        ("curly-brows", "Sanji"),
        ("curly brows", "Sanji"),
    ],
)
@pytest.mark.asyncio
async def test_search_card_query_aliases_use_backend_query(
    query: str,
    backend_query: str,
) -> None:
    client = FakeClient()
    service = CommandService(client)

    outcome = await service.search(query)

    assert outcome.kind is CommandOutcomeKind.PICKER
    assert client.search_kwargs["query"] == backend_query


@pytest.mark.asyncio
async def test_search_outcome_includes_pagination() -> None:
    client = FakeClient()
    client.search_response = client.search_response.model_copy(
        update={
            "pagination": client.search_response.pagination.model_copy(
                update={"page": 3, "total": 30, "has_more": True}
            )
        }
    )
    service = CommandService(client)

    outcome = await service.search("luffy", page=3)

    assert client.search_cards_kwargs["page"] == 3
    assert outcome.page == 3
    assert outcome.total == 30
    assert outcome.has_more is True
    assert outcome.message == "Search results | Page 3 | 30 total"


@pytest.mark.asyncio
async def test_autocomplete_returns_trimmed_choices() -> None:
    client = FakeClient()
    service = CommandService(client)

    choices = await service.autocomplete_cards("  luffy  ")

    assert client.autocomplete_queries == ["luffy"]
    assert choices == tuple(f"Card {index}" for index in range(25))


@pytest.mark.asyncio
async def test_autocomplete_blank_query_returns_empty_tuple() -> None:
    client = FakeClient()
    service = CommandService(client)

    choices = await service.autocomplete_cards("   ")

    assert choices == ()
    assert client.autocomplete_queries == []


@pytest.mark.asyncio
async def test_search_passes_sort_and_order_to_client() -> None:
    client = FakeClient()
    service = CommandService(client)

    outcome = await service.search(
        "type:leader",
        page=2,
        sort="market_price",
        order="desc",
    )

    assert outcome.kind is CommandOutcomeKind.PICKER
    assert client.search_kwargs == {
        "query": "type:leader",
        "page": 2,
        "limit": 10,
        "sort": "market_price",
        "order": "desc",
        "collapse": "card",
        "lang": "en",
    }


@pytest.mark.asyncio
async def test_random_empty_query_uses_random_endpoint() -> None:
    service = CommandService(FakeClient())

    outcome = await service.random("")

    assert outcome.kind is CommandOutcomeKind.PUBLIC_CARD
    assert outcome.card is not None


@pytest.mark.asyncio
async def test_random_filter_lang_overrides_default_language() -> None:
    client = FakeClient()
    service = CommandService(client)

    outcome = await service.random("lang:ja")

    assert outcome.kind is CommandOutcomeKind.PUBLIC_CARD
    assert client.get_random_kwargs == {"lang": "ja"}


@pytest.mark.asyncio
async def test_random_filter_uses_default_language_without_lang_filter() -> None:
    client = FakeClient()
    service = CommandService(client)

    outcome = await service.random("color:red")

    assert outcome.kind is CommandOutcomeKind.PUBLIC_CARD
    assert client.get_random_kwargs == {"lang": "en", "color": "red"}


@pytest.mark.asyncio
async def test_random_query_no_results_returns_ephemeral_message() -> None:
    client = FakeClient()
    client.raise_no_search_results = True
    service = CommandService(client)

    outcome = await service.random("does-not-exist")

    assert outcome.kind is CommandOutcomeKind.EPHEMERAL_MESSAGE
    assert outcome.message == "No matching cards were found."
    assert outcome.source_query == "does-not-exist"
    assert client.get_random_from_query_args == ("does-not-exist", "en")


@pytest.mark.asyncio
async def test_faq_uses_official_faq_only() -> None:
    service = CommandService(FakeClient())

    outcome = await service.faq("OP01-001")

    assert outcome.kind is CommandOutcomeKind.PUBLIC_FAQ
    assert outcome.card is not None
    assert outcome.faq_entries


@pytest.mark.asyncio
async def test_price_direct_number_returns_public_price() -> None:
    client = FakeClient()
    service = CommandService(client)

    outcome = await service.price("OP01-001", days=7)

    assert outcome.kind is CommandOutcomeKind.PUBLIC_PRICE
    assert outcome.card is not None
    assert outcome.prices == client.prices
    assert client.get_prices_args == ("OP01-001", 7)


@pytest.mark.parametrize("days", [0, 366])
@pytest.mark.asyncio
async def test_price_rejects_days_outside_api_range(days: int) -> None:
    client = FakeClient()
    service = CommandService(client)

    outcome = await service.price("OP01-001", days=days)

    assert outcome.kind is CommandOutcomeKind.EPHEMERAL_MESSAGE
    assert outcome.message == "Price history days must be between 1 and 365."
    assert client.get_prices_args is None


@pytest.mark.asyncio
async def test_price_ambiguous_returns_price_picker() -> None:
    service = CommandService(FakeClient())

    outcome = await service.price("luffy")

    assert outcome.kind is CommandOutcomeKind.PICKER
    assert outcome.message == "Select a card for price history"
    assert len(outcome.choices) == 2


@pytest.mark.asyncio
async def test_price_no_rows_returns_ephemeral_message() -> None:
    client = FakeClient()
    client.prices = ()
    service = CommandService(client)

    outcome = await service.price("OP01-001")

    assert outcome.kind is CommandOutcomeKind.EPHEMERAL_MESSAGE
    assert outcome.message == "No price history is available for OP01-001."


def test_help_is_ephemeral_message() -> None:
    outcome = CommandService(FakeClient()).help()

    assert outcome.kind is CommandOutcomeKind.EPHEMERAL_MESSAGE
    assert "/card" in outcome.message
    assert "/price" in outcome.message
    assert "https://poneglyph.one/syntax" in outcome.message
