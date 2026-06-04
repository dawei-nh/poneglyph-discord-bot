import json
from pathlib import Path

from optcg_card_bot.embeds import build_card_embed, build_faq_embed
from optcg_card_bot.models import CardDetailResponse

FIXTURES = Path(__file__).parent / "fixtures" / "poneglyph"


def load_card():
    return CardDetailResponse.model_validate(
        json.loads((FIXTURES / "card_op01_001.json").read_text())
    ).data


def test_card_embed_contains_identity_and_powered_by() -> None:
    embed = build_card_embed(load_card())

    assert embed.title == "Roronoa Zoro"
    assert embed.url == "https://poneglyph.one/cards/OP01-001?lang=en"
    assert embed.footer.text is not None
    assert "Powered by Poneglyph" in embed.footer.text


def test_card_embed_uses_image_fallback() -> None:
    embed = build_card_embed(load_card())

    assert embed.image.url == (
        "https://cdn.poneglyph.one/images/OP01-001/en/stock/0/full.png"
    )


def test_faq_embed_uses_official_faq_entries() -> None:
    card = load_card()

    embed = build_faq_embed(card, tuple(card.official_faq))

    assert embed.title == "Official FAQ: Roronoa Zoro"
    assert len(embed.fields) == len(card.official_faq)
