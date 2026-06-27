from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CropFocus(StrictModel):
    x: float | None
    y: float | None


class ProductRef(StrictModel):
    id: str | None
    slug: str | None
    name: str | None
    set_code: str | None
    released_at: str | None


class StockImages(StrictModel):
    full: str | None
    thumb: str | None


class ScanImages(StrictModel):
    display: str | None
    full: str | None
    thumb: str | None


class VariantImages(StrictModel):
    stock: StockImages
    scan: ScanImages


class Market(StrictModel):
    tcgplayer_url: str | None
    market_price: str | None
    low_price: str | None
    mid_price: str | None
    high_price: str | None


class PricePoint(StrictModel):
    variant_index: int
    label: str | None
    sub_type: str | None
    tcgplayer_url: str | None
    market_price: str | None
    low_price: str | None
    mid_price: str | None
    high_price: str | None
    fetched_at: str


class CardVariant(StrictModel):
    index: int
    name: str | None
    label: str | None
    artist: str | None
    crop_focus: CropFocus
    product: ProductRef
    images: VariantImages
    errata: list[dict[str, Any]]
    market: Market
    card_image_id: str | None = None


class LegalityEntry(BaseModel):
    model_config = ConfigDict(extra="allow")

    status: str
    banned_at: str | None = None
    reason: str | None = None
    max_copies: int | None = None
    paired_with: list[str] | None = None


class FAQEntry(StrictModel):
    question: str
    answer: str
    updated_on: str


class CardSummary(StrictModel):
    card_number: str
    name: str
    language: str
    set: str
    set_name: str
    released_at: str | None
    released: bool
    card_type: str
    rarity: str | None
    color: list[str]
    cost: int | None
    power: int | None
    counter: int | None
    life: int | None
    attribute: list[str] | None
    types: list[str]
    effect: str | None
    trigger: str | None
    block: str | None
    variants: list[CardVariant]


class CardDetail(CardSummary):
    legality: dict[str, LegalityEntry]
    available_languages: list[str]
    official_faq: list[FAQEntry]


class Pagination(StrictModel):
    page: int
    limit: int
    total: int
    has_more: bool


class SearchMeta(StrictModel):
    sort_requested: str
    sort_applied: str
    order_requested: str
    order_applied: str
    relevance_active: bool


class CardDetailResponse(StrictModel):
    data: CardDetail


class SearchResponse(StrictModel):
    data: list[CardSummary]
    pagination: Pagination
    meta: SearchMeta


class RandomCardResponse(StrictModel):
    data: CardDetail


class RandomCardSummaryResponse(StrictModel):
    data: CardSummary


class AutocompleteResponse(StrictModel):
    data: list[str]


class PriceHistoryResponse(StrictModel):
    data: list[PricePoint]


class SearchParams(StrictModel):
    q: str | None = None
    page: int = 1
    limit: int = 60
    sort: str | None = None
    order: str | None = None
    collapse: str = "card"
    lang: str = "en"


VariantRequest = int | str | None

_VARIANT_QUERY_ALIASES = {
    "alt": ("alternate", "alternate art", "alt art", "parallel"),
    "sp": ("sp", "special", "special rare"),
    "manga": ("manga", "manga rare"),
}


def resolve_variant_position(
    card: CardSummary,
    variant_position: VariantRequest = 0,
) -> int:
    if isinstance(variant_position, int):
        return clamp_variant_position(card, variant_position)
    if variant_position is None:
        return 0

    raw_query = variant_position.strip()
    if not raw_query:
        return 0
    try:
        return clamp_variant_position(card, int(raw_query))
    except ValueError:
        pass

    query = _normalize_variant_query(raw_query)
    if not query:
        return 0
    queries = {query, *_VARIANT_QUERY_ALIASES.get(query, ())}

    for position, variant in enumerate(card.variants):
        for term in _variant_search_terms(variant):
            if term in queries or queries.intersection(term.split()):
                return position
    return 0


def _variant_search_terms(variant: CardVariant) -> tuple[str, ...]:
    values = (
        variant.name,
        variant.label,
        variant.product.name,
        variant.product.slug,
        variant.product.set_code,
        str(variant.index),
    )
    return tuple(
        normalized
        for value in values
        if value and (normalized := _normalize_variant_query(value))
    )


def _normalize_variant_query(value: str) -> str:
    parts: list[str] = []
    previous_was_space = True
    for character in value.lower():
        if character.isalnum():
            parts.append(character)
            previous_was_space = False
        elif not previous_was_space:
            parts.append(" ")
            previous_was_space = True
    return "".join(parts).strip()


def clamp_variant_position(card: CardSummary, variant_position: int) -> int:
    if not card.variants:
        return 0
    return max(0, min(variant_position, len(card.variants) - 1))


def variant_at_position(
    card: CardSummary,
    variant_position: VariantRequest = 0,
) -> CardVariant | None:
    if not card.variants:
        return None
    return card.variants[resolve_variant_position(card, variant_position)]


def best_variant(card: CardSummary) -> CardVariant | None:
    return variant_at_position(card, 0)


def best_image_url(variant: CardVariant | None) -> str | None:
    if variant is None:
        return None
    for value in (
        variant.images.scan.display,
        variant.images.scan.full,
        variant.images.stock.full,
        variant.images.scan.thumb,
        variant.images.stock.thumb,
    ):
        if value:
            return value
    return None


def best_price(variant: CardVariant | None) -> str | None:
    if variant is None:
        return None
    for value in (
        variant.market.market_price,
        variant.market.low_price,
        variant.market.mid_price,
        variant.market.high_price,
    ):
        if value:
            return value
    return None


def poneglyph_card_url(card_number: str, lang: str = "en") -> str:
    return f"https://poneglyph.one/cards/{card_number}?lang={lang}"
