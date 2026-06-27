import json
from pathlib import Path

from optcg_card_bot.models import (
    CardDetailResponse,
    SearchResponse,
    resolve_variant_position,
)

FIXTURES = Path(__file__).parent / "fixtures" / "poneglyph"


def test_card_detail_fixture_parses() -> None:
    payload = json.loads((FIXTURES / "card_op01_001.json").read_text())

    response = CardDetailResponse.model_validate(payload)

    assert response.data.card_number == "OP01-001"
    assert response.data.name == "Roronoa Zoro"
    assert response.data.variants
    assert response.data.official_faq


def test_card_detail_accepts_upstream_card_image_ids() -> None:
    payload = json.loads((FIXTURES / "card_op01_001.json").read_text())
    payload["data"]["variants"][0]["card_image_id"] = (
        "0eb669e0-c50b-4076-b734-150d6952f0ef"
    )

    response = CardDetailResponse.model_validate(payload)

    assert response.data.variants[0].card_image_id == (
        "0eb669e0-c50b-4076-b734-150d6952f0ef"
    )


def test_search_fixture_parses_without_detail_only_fields() -> None:
    payload = json.loads((FIXTURES / "search_luffy.json").read_text())

    response = SearchResponse.model_validate(payload)

    assert response.pagination.limit == 2
    assert response.data[0].card_number
    assert response.meta.sort_applied in {"relevance", "card_number"}


def test_variant_position_resolves_numeric_strings_and_clamps() -> None:
    payload = json.loads((FIXTURES / "card_op01_001.json").read_text())
    card = CardDetailResponse.model_validate(payload).data

    assert resolve_variant_position(card, "1") == 1
    assert resolve_variant_position(card, "99") == 2
    assert resolve_variant_position(card, "-5") == 0
    assert resolve_variant_position(card, "") == 0


def test_variant_position_resolves_named_aliases() -> None:
    detail_payload = json.loads((FIXTURES / "card_op01_001.json").read_text())
    card = CardDetailResponse.model_validate(detail_payload).data
    card.variants[2].name = "Manga Rare"

    search_payload = json.loads((FIXTURES / "search_luffy.json").read_text())
    summary = SearchResponse.model_validate(search_payload).data[0]

    assert resolve_variant_position(card, "alt") == 1
    assert resolve_variant_position(summary, "sp") == 1
    assert resolve_variant_position(card, "manga") == 2
    assert resolve_variant_position(card, "missing") == 0
