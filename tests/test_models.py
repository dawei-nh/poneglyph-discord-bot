import json
from pathlib import Path

from optcg_card_bot.models import CardDetailResponse, SearchResponse

FIXTURES = Path(__file__).parent / "fixtures" / "poneglyph"


def test_card_detail_fixture_parses() -> None:
    payload = json.loads((FIXTURES / "card_op01_001.json").read_text())

    response = CardDetailResponse.model_validate(payload)

    assert response.data.card_number == "OP01-001"
    assert response.data.name == "Roronoa Zoro"
    assert response.data.variants
    assert response.data.official_faq


def test_search_fixture_parses_without_detail_only_fields() -> None:
    payload = json.loads((FIXTURES / "search_luffy.json").read_text())

    response = SearchResponse.model_validate(payload)

    assert response.pagination.limit == 2
    assert response.data[0].card_number
    assert response.meta.sort_applied in {"relevance", "card_number"}
