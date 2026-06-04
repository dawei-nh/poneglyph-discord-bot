from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol

from optcg_card_bot.models import CardDetail, CardSummary, SearchResponse

CARD_NUMBER_RE = re.compile(r"^(?:OP|ST|EB|PRB|P)-?\d{2}-\d{3}[A-Z]?$", re.IGNORECASE)
BRACKET_RE = re.compile(r"\[\[([^\[\]]+)\]\]")


class CardLookupClient(Protocol):
    async def get_card(self, card_number: str, *, lang: str = "en") -> CardDetail: ...

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
    ) -> SearchResponse: ...


class ResolutionKind(StrEnum):
    DIRECT = "direct"
    SINGLE = "single"
    MULTIPLE = "multiple"
    NOT_FOUND = "not_found"


@dataclass(frozen=True)
class CardChoice:
    card_number: str
    name: str
    set_code: str
    card_type: str
    color: tuple[str, ...]

    @classmethod
    def from_summary(cls, card: CardSummary) -> CardChoice:
        return cls(
            card_number=card.card_number,
            name=card.name,
            set_code=card.set,
            card_type=card.card_type,
            color=tuple(card.color),
        )


@dataclass(frozen=True)
class CardResolution:
    kind: ResolutionKind
    query: str
    card: CardDetail | None = None
    choices: tuple[CardChoice, ...] = field(default_factory=tuple)


def is_card_number(value: str) -> bool:
    return bool(CARD_NUMBER_RE.match(value.strip()))


def normalize_card_number(value: str) -> str:
    return value.strip().upper()


def extract_bracket_queries(content: str) -> list[str]:
    return [match.strip() for match in BRACKET_RE.findall(content) if match.strip()]


async def resolve_card_query(
    client: CardLookupClient,
    query: str,
    *,
    lang: str = "en",
    search_limit: int = 10,
) -> CardResolution:
    raw_query = query.strip()
    if is_card_number(raw_query):
        card_number = normalize_card_number(raw_query)
        card = await client.get_card(card_number, lang=lang)
        return CardResolution(kind=ResolutionKind.DIRECT, query=raw_query, card=card)

    response = await client.search_cards(
        raw_query,
        page=1,
        limit=search_limit,
        collapse="card",
        lang=lang,
    )
    if response.pagination.total == 0 or not response.data:
        return CardResolution(kind=ResolutionKind.NOT_FOUND, query=raw_query)
    if response.pagination.total == 1:
        card = await client.get_card(response.data[0].card_number, lang=lang)
        return CardResolution(kind=ResolutionKind.SINGLE, query=raw_query, card=card)
    return CardResolution(
        kind=ResolutionKind.MULTIPLE,
        query=raw_query,
        choices=tuple(CardChoice.from_summary(card) for card in response.data),
    )
