from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol

from optcg_card_bot.errors import NoSearchResultsError
from optcg_card_bot.models import CardDetail, FAQEntry, PricePoint, SearchResponse
from optcg_card_bot.search import (
    CardChoice,
    ResolutionKind,
    resolve_card_query,
    rewrite_card_query_alias,
)


class CommandClient(Protocol):
    async def get_card(self, card_number: str, *, lang: str = "en") -> CardDetail: ...

    async def get_prices(
        self,
        card_number: str,
        *,
        days: int = 30,
    ) -> tuple[PricePoint, ...]: ...

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

    async def get_random(
        self,
        *,
        lang: str = "en",
        set: str | None = None,
        color: str | None = None,
        type: str | None = None,
        rarity: str | None = None,
    ) -> CardDetail: ...

    async def get_random_from_query(
        self, query: str, *, lang: str = "en"
    ) -> CardDetail: ...

    async def autocomplete_cards(self, query: str) -> tuple[str, ...]: ...


class CommandOutcomeKind(StrEnum):
    PUBLIC_CARD = "public_card"
    PUBLIC_FAQ = "public_faq"
    PUBLIC_PRICE = "public_price"
    PICKER = "picker"
    EPHEMERAL_MESSAGE = "ephemeral_message"


@dataclass(frozen=True)
class CommandOutcome:
    kind: CommandOutcomeKind
    message: str = ""
    card: CardDetail | None = None
    choices: tuple[CardChoice, ...] = field(default_factory=tuple)
    faq_entries: tuple[FAQEntry, ...] = field(default_factory=tuple)
    prices: tuple[PricePoint, ...] = field(default_factory=tuple)
    source_query: str = ""
    page: int = 1
    total: int = 0
    has_more: bool = False


SIMPLE_RANDOM_FILTER_RE = re.compile(r"^(lang|set|color|type|rarity):([^()\s]+)$")


class CommandService:
    def __init__(self, client: CommandClient, *, default_language: str = "en") -> None:
        self._client = client
        self._default_language = default_language

    async def card(self, query: str) -> CommandOutcome:
        resolution = await resolve_card_query(
            self._client,
            query,
            lang=self._default_language,
        )
        if resolution.kind in {ResolutionKind.DIRECT, ResolutionKind.SINGLE}:
            return CommandOutcome(
                kind=CommandOutcomeKind.PUBLIC_CARD,
                card=resolution.card,
                source_query=query,
            )
        if resolution.kind is ResolutionKind.MULTIPLE:
            return CommandOutcome(
                kind=CommandOutcomeKind.PICKER,
                message="Select a card to post",
                choices=resolution.choices,
                source_query=query,
            )
        return CommandOutcome(
            kind=CommandOutcomeKind.EPHEMERAL_MESSAGE,
            message="No matching cards were found.",
            source_query=query,
        )

    async def search(
        self,
        query: str,
        *,
        page: int = 1,
        sort: str | None = None,
        order: str | None = None,
    ) -> CommandOutcome:
        response = await self._client.search_cards(
            rewrite_card_query_alias(query),
            page=page,
            limit=10,
            sort=sort,
            order=order,
            collapse="card",
            lang=self._default_language,
        )
        if not response.data:
            return CommandOutcome(
                kind=CommandOutcomeKind.EPHEMERAL_MESSAGE,
                message="No matching cards were found.",
                source_query=query,
            )
        return CommandOutcome(
            kind=CommandOutcomeKind.PICKER,
            message=(
                "Search results"
                f" | Page {response.pagination.page}"
                f" | {response.pagination.total} total"
            ),
            choices=tuple(CardChoice.from_summary(card) for card in response.data),
            source_query=query,
            page=response.pagination.page,
            total=response.pagination.total,
            has_more=response.pagination.has_more,
        )

    async def autocomplete_cards(self, query: str) -> tuple[str, ...]:
        stripped = query.strip()
        if not stripped:
            return ()
        return tuple((await self._client.autocomplete_cards(stripped))[:25])

    async def random(self, query: str) -> CommandOutcome:
        stripped = query.strip()
        if not stripped:
            card = await self._client.get_random(lang=self._default_language)
        else:
            filters = self._parse_simple_random_filters(stripped)
            if filters is None:
                try:
                    card = await self._client.get_random_from_query(
                        stripped,
                        lang=self._default_language,
                    )
                except NoSearchResultsError:
                    return CommandOutcome(
                        kind=CommandOutcomeKind.EPHEMERAL_MESSAGE,
                        message="No matching cards were found.",
                        source_query=query,
                    )
            else:
                lang = filters.pop("lang", self._default_language)
                card = await self._client.get_random(
                    lang=lang,
                    **filters,
                )
        return CommandOutcome(
            kind=CommandOutcomeKind.PUBLIC_CARD,
            card=card,
            source_query=query,
        )

    async def faq(self, query: str) -> CommandOutcome:
        card_outcome = await self.card(query)
        if card_outcome.kind is CommandOutcomeKind.PICKER:
            return CommandOutcome(
                kind=CommandOutcomeKind.PICKER,
                message="Select a card for official FAQ",
                choices=card_outcome.choices,
                source_query=query,
            )
        if card_outcome.card is None:
            return card_outcome
        entries = tuple(card_outcome.card.official_faq)
        if not entries:
            return CommandOutcome(
                kind=CommandOutcomeKind.EPHEMERAL_MESSAGE,
                message=(
                    f"No official FAQ is available for {card_outcome.card.card_number}."
                ),
                source_query=query,
            )
        return CommandOutcome(
            kind=CommandOutcomeKind.PUBLIC_FAQ,
            card=card_outcome.card,
            faq_entries=entries,
            source_query=query,
        )

    async def price(self, query: str, *, days: int = 30) -> CommandOutcome:
        if days < 1 or days > 365:
            return CommandOutcome(
                kind=CommandOutcomeKind.EPHEMERAL_MESSAGE,
                message="Price history days must be between 1 and 365.",
                source_query=query,
            )

        card_outcome = await self.card(query)
        if card_outcome.kind is CommandOutcomeKind.PICKER:
            return CommandOutcome(
                kind=CommandOutcomeKind.PICKER,
                message="Select a card for price history",
                choices=card_outcome.choices,
                source_query=query,
            )
        if card_outcome.card is None:
            return card_outcome

        prices = await self._client.get_prices(card_outcome.card.card_number, days=days)
        if not prices:
            return CommandOutcome(
                kind=CommandOutcomeKind.EPHEMERAL_MESSAGE,
                message=(
                    f"No price history is available for "
                    f"{card_outcome.card.card_number}."
                ),
                source_query=query,
            )
        return CommandOutcome(
            kind=CommandOutcomeKind.PUBLIC_PRICE,
            card=card_outcome.card,
            prices=prices,
            source_query=query,
        )

    def help(self) -> CommandOutcome:
        return CommandOutcome(
            kind=CommandOutcomeKind.EPHEMERAL_MESSAGE,
            message=(
                "Commands:\n"
                "`/card query:<query>` posts an unambiguous card or opens a picker.\n"
                "`/search query:<query>` opens private search results.\n"
                "`/random query:<optional query>` posts a random card.\n"
                "`/faq card:<card>` posts official FAQ entries only.\n"
                "`/price card:<card> days:<optional days>` posts price history.\n"
                "Poneglyph syntax: https://poneglyph.one/syntax"
            ),
        )

    def _parse_simple_random_filters(self, query: str) -> dict[str, str] | None:
        filters: dict[str, str] = {}
        for token in query.split():
            match = SIMPLE_RANDOM_FILTER_RE.match(token)
            if match is None:
                return None
            key, value = match.groups()
            filters[key] = value
        return filters
