import json
from pathlib import Path

import pytest

from optcg_card_bot.commands import CommandOutcomeKind, CommandService
from optcg_card_bot.errors import NoSearchResultsError
from optcg_card_bot.models import CardDetailResponse, SearchResponse

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
        self.get_random_kwargs: dict[str, str] = {}
        self.get_random_from_query_args: tuple[str, str] | None = None
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
    assert outcome.message == "Search results"


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


def test_help_is_ephemeral_message() -> None:
    outcome = CommandService(FakeClient()).help()

    assert outcome.kind is CommandOutcomeKind.EPHEMERAL_MESSAGE
    assert "/card" in outcome.message
    assert "https://poneglyph.one/syntax" in outcome.message
