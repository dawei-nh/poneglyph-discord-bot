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


class SearchParams(StrictModel):
    q: str | None = None
    page: int = 1
    limit: int = 60
    sort: str | None = None
    order: str | None = None
    collapse: str = "card"
    lang: str = "en"


def best_variant(card: CardSummary) -> CardVariant | None:
    return card.variants[0] if card.variants else None


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
