import json
from pathlib import Path

from optcg_card_bot.embeds import build_card_embed, build_faq_embed, build_price_embed
from optcg_card_bot.models import CardDetailResponse, FAQEntry, PricePoint

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


def test_card_embed_lists_variant_context() -> None:
    embed = build_card_embed(load_card())

    variants = next(field for field in embed.fields if field.name == "Variants")

    assert "#0 Standard | Romance Dawn | Market: $1.91" in variants.value
    assert "#1 Alternate Art | Romance Dawn | Market: $558.38" in variants.value
    assert "#2 Alternate Art | 25th Edition | Market: $62.19" in variants.value


def test_faq_embed_uses_official_faq_entries() -> None:
    card = load_card()

    embed = build_faq_embed(card, tuple(card.official_faq))

    assert embed.title == "Official FAQ: Roronoa Zoro"
    assert len(embed.fields) == len(card.official_faq)


def test_price_embed_lists_variant_prices() -> None:
    card = load_card()
    prices = (
        PricePoint(
            variant_index=0,
            label="Super Pre-Release",
            sub_type="Alternate Art",
            tcgplayer_url="https://tcgplayer.example/op01-001",
            market_price="1.91",
            low_price="1.00",
            mid_price="2.25",
            high_price="9.99",
            fetched_at="2026-06-04T12:00:00.000Z",
        ),
        PricePoint(
            variant_index=1,
            label=None,
            sub_type=None,
            tcgplayer_url=None,
            market_price=None,
            low_price="490.00",
            mid_price=None,
            high_price=None,
            fetched_at="2026-06-04T12:00:00.000Z",
        ),
    )

    embed = build_price_embed(card, prices)

    assert embed.title == "Prices: Roronoa Zoro"
    assert embed.url == "https://poneglyph.one/cards/OP01-001?lang=en"
    assert embed.footer.text == "Powered by Poneglyph"
    assert embed.fields[0].name == "Variant 0: Super Pre-Release (Alternate Art)"
    assert "Market: $1.91" in embed.fields[0].value
    assert "Low: $1.00" in embed.fields[0].value
    assert "Mid: $2.25" in embed.fields[0].value
    assert "High: $9.99" in embed.fields[0].value
    assert "Fetched: 2026-06-04T12:00:00.000Z" in embed.fields[0].value
    assert embed.fields[1].name == "Variant 1"
    assert embed.fields[1].value == "Low: $490.00\nFetched: 2026-06-04T12:00:00.000Z"


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
