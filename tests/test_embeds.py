import json
from pathlib import Path

from optcg_card_bot.embeds import build_card_embed, build_faq_embed
from optcg_card_bot.models import CardDetailResponse, FAQEntry

FIXTURES = Path(__file__).parent / "fixtures" / "poneglyph"
EMBED_TOTAL_TEXT_LIMIT = 6000
EMBED_DESCRIPTION_LIMIT = 4096
EMBED_FIELD_NAME_LIMIT = 256
EMBED_FIELD_VALUE_LIMIT = 1024
EMBED_FIELD_LIMIT = 25


def load_card():
    return CardDetailResponse.model_validate(
        json.loads((FIXTURES / "card_op01_001.json").read_text())
    ).data


def counted_embed_text_length(embed) -> int:
    return sum(
        len(value or "")
        for value in (
            embed.title,
            embed.description,
            *(field.name for field in embed.fields),
            *(field.value for field in embed.fields),
            embed.footer.text,
        )
    )


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


def test_card_embed_truncates_long_text_within_discord_limits() -> None:
    card = load_card().model_copy(
        update={
            "name": "Roronoa Zoro " + ("X" * 500),
            "effect": "Effect " + ("X" * 8000),
            "trigger": "Trigger " + ("Y" * 2000),
        }
    )

    embed = build_card_embed(card)

    assert embed.title is not None
    assert len(embed.title) <= EMBED_FIELD_NAME_LIMIT
    assert embed.description is not None
    assert len(embed.description) <= EMBED_DESCRIPTION_LIMIT
    assert len(embed.fields) <= EMBED_FIELD_LIMIT
    assert all(len(field.name) <= EMBED_FIELD_NAME_LIMIT for field in embed.fields)
    assert all(len(field.value) <= EMBED_FIELD_VALUE_LIMIT for field in embed.fields)
    assert counted_embed_text_length(embed) <= EMBED_TOTAL_TEXT_LIMIT


def test_faq_embed_surfaces_omitted_entries_within_discord_limits() -> None:
    card = load_card()
    entries = tuple(
        FAQEntry(
            question=f"Question {index} " + ("Q" * 500),
            answer="Answer " + ("A" * 1500),
            updated_on="2026-06-04",
        )
        for index in range(40)
    )

    embed = build_faq_embed(card, entries)

    assert len(embed.fields) <= EMBED_FIELD_LIMIT
    assert all(len(field.name) <= EMBED_FIELD_NAME_LIMIT for field in embed.fields)
    assert all(len(field.value) <= EMBED_FIELD_VALUE_LIMIT for field in embed.fields)
    assert counted_embed_text_length(embed) <= EMBED_TOTAL_TEXT_LIMIT
    assert "not shown" in " ".join(
        [*(field.value for field in embed.fields), embed.footer.text or ""]
    )
