from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol

from optcg_card_bot.errors import NoSearchResultsError
from optcg_card_bot.models import CardDetail, FAQEntry, SearchResponse
from optcg_card_bot.search import CardChoice, ResolutionKind, resolve_card_query


class CommandClient(Protocol):
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


class CommandOutcomeKind(StrEnum):
    PUBLIC_CARD = "public_card"
    PUBLIC_FAQ = "public_faq"
    PICKER = "picker"
    EPHEMERAL_MESSAGE = "ephemeral_message"


@dataclass(frozen=True)
class CommandOutcome:
    kind: CommandOutcomeKind
    message: str = ""
    card: CardDetail | None = None
    choices: tuple[CardChoice, ...] = field(default_factory=tuple)
    faq_entries: tuple[FAQEntry, ...] = field(default_factory=tuple)
    source_query: str = ""


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

    async def search(self, query: str, *, page: int = 1) -> CommandOutcome:
        response = await self._client.search_cards(
            query,
            page=page,
            limit=10,
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
            message="Search results",
            choices=tuple(CardChoice.from_summary(card) for card in response.data),
            source_query=query,
        )

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
                    "No official FAQ is available for "
                    f"{card_outcome.card.card_number}."
                ),
                source_query=query,
            )
        return CommandOutcome(
            kind=CommandOutcomeKind.PUBLIC_FAQ,
            card=card_outcome.card,
            faq_entries=entries,
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
