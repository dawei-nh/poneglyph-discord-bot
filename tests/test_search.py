import json
from pathlib import Path

import pytest

from optcg_card_bot.models import CardDetailResponse, SearchResponse
from optcg_card_bot.search import (
    ResolutionKind,
    extract_bracket_queries,
    is_card_number,
    normalize_card_number,
    resolve_card_query,
)

FIXTURES = Path(__file__).parent / "fixtures" / "poneglyph"


class FakeClient:
    def __init__(self) -> None:
        self.card = CardDetailResponse.model_validate(
            json.loads((FIXTURES / "card_op01_001.json").read_text())
        ).data
        self.search_response = SearchResponse.model_validate(
            json.loads((FIXTURES / "search_luffy.json").read_text())
        )
        self.card_numbers_requested: list[str] = []
        self.queries_requested: list[str] = []

    async def get_card(self, card_number: str, *, lang: str = "en"):
        self.card_numbers_requested.append(card_number)
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
        self.queries_requested.append(query or "")
        return self.search_response


def test_card_number_detection() -> None:
    assert is_card_number("op01-001")
    assert is_card_number("ST01-001")
    assert is_card_number("EB01-001")
    assert not is_card_number("luffy")


def test_card_number_normalization() -> None:
    assert normalize_card_number(" op01-001 ") == "OP01-001"


@pytest.mark.asyncio
async def test_direct_card_number_resolution_fetches_detail() -> None:
    client = FakeClient()

    resolution = await resolve_card_query(client, "op01-001")

    assert resolution.kind is ResolutionKind.DIRECT
    assert resolution.card is not None
    assert resolution.card.card_number == "OP01-001"
    assert client.card_numbers_requested == ["OP01-001"]
    assert client.queries_requested == []


@pytest.mark.asyncio
async def test_ambiguous_query_returns_choices() -> None:
    client = FakeClient()

    resolution = await resolve_card_query(client, "luffy")

    assert resolution.kind is ResolutionKind.MULTIPLE
    assert resolution.card is None
    assert len(resolution.choices) == 2
    assert client.queries_requested == ["luffy"]

@pytest.mark.parametrize("query", ["Mosshead", "MOSS", "moss-head", "moss head"])
@pytest.mark.asyncio
async def test_mosshead_aliases_resolve_as_zoro_queries(query: str) -> None:
    client = FakeClient()

    resolution = await resolve_card_query(client, query)

    assert resolution.kind is ResolutionKind.MULTIPLE
    assert resolution.card is None
    assert client.queries_requested == ["Zoro"]


@pytest.mark.asyncio
async def test_exactly_one_result_resolution_fetches_detail() -> None:
    client = FakeClient()
    returned_card_number = client.search_response.data[0].card_number
    client.search_response = client.search_response.model_copy(
        update={
            "data": client.search_response.data[:1],
            "pagination": client.search_response.pagination.model_copy(
                update={"total": 1}
            ),
        }
    )

    resolution = await resolve_card_query(client, "zoro")

    assert resolution.kind is ResolutionKind.SINGLE
    assert resolution.card is not None
    assert resolution.choices == ()
    assert client.card_numbers_requested == [returned_card_number]
    assert client.queries_requested == ["zoro"]


@pytest.mark.asyncio
async def test_truncated_ambiguous_query_returns_available_choices() -> None:
    client = FakeClient()
    client.search_response = client.search_response.model_copy(
        update={
            "data": client.search_response.data[:1],
            "pagination": client.search_response.pagination.model_copy(
                update={"total": 2}
            ),
        }
    )

    resolution = await resolve_card_query(client, "luffy")

    assert resolution.kind is ResolutionKind.MULTIPLE
    assert resolution.card is None
    assert len(resolution.choices) == 1
    assert client.card_numbers_requested == []
    assert client.queries_requested == ["luffy"]


def test_extract_bracket_queries_for_phase_two() -> None:
    assert extract_bracket_queries("play [[luffy]] and [[OP01-001]]") == [
        "luffy",
        "OP01-001",
    ]
