from __future__ import annotations

import discord

from optcg_card_bot.models import (
    CardDetail,
    CardVariant,
    FAQEntry,
    PricePoint,
    best_image_url,
    best_price,
    best_variant,
    poneglyph_card_url,
)

EMBED_TITLE_LIMIT = 256
EMBED_DESCRIPTION_LIMIT = 4096
EMBED_FIELD_NAME_LIMIT = 256
EMBED_FIELD_VALUE_LIMIT = 1024
EMBED_FOOTER_LIMIT = 2048
EMBED_FIELD_LIMIT = 25
EMBED_TOTAL_TEXT_LIMIT = 6000
POWERED_BY = "Powered by Poneglyph"


def build_card_embed(card: CardDetail) -> discord.Embed:
    variant = best_variant(card)
    embed = discord.Embed(
        title=_truncate(card.name, EMBED_TITLE_LIMIT),
        url=poneglyph_card_url(card.card_number, card.language),
        color=discord.Color.red(),
    )
    embed.set_footer(
        text=_truncate(_card_footer(card), _remaining_footer_budget(embed))
    )
    embed.description = _truncate(
        _card_description(card),
        min(EMBED_DESCRIPTION_LIMIT, _remaining_text_budget(embed)),
    )
    image_url = best_image_url(variant)
    if image_url:
        embed.set_image(url=image_url)
    _add_field_if_fits(embed, "Set", f"{card.set_name} ({card.set})", inline=True)
    _add_field_if_fits(embed, "Number", card.card_number, inline=True)
    _add_field_if_fits(embed, "Rarity", card.rarity or "Unknown", inline=True)
    if card.attribute:
        _add_field_if_fits(
            embed,
            "Attribute",
            ", ".join(card.attribute),
            inline=True,
        )
    if card.types:
        _add_field_if_fits(embed, "Traits", ", ".join(card.types), inline=False)
    price = best_price(variant)
    if price:
        _add_field_if_fits(embed, "Market", f"${price}", inline=True)
    variants = _variant_field_value(card)
    if variants:
        _add_field_if_fits(embed, "Variants", variants, inline=False)
    legality = _format_legality(card)
    if legality:
        _add_field_if_fits(embed, "Legality", legality, inline=False)
    return embed


def _card_footer(card: CardDetail) -> str:
    variant = best_variant(card)
    footer_parts: list[str] = []
    if variant and variant.product.name:
        footer_parts.append(variant.product.name)
    if variant and variant.label:
        footer_parts.append(variant.label)
    if variant and variant.artist:
        footer_parts.append(f"Artist: {variant.artist}")
    footer_parts.append(POWERED_BY)
    return " | ".join(footer_parts)


def build_faq_embed(card: CardDetail, entries: tuple[FAQEntry, ...]) -> discord.Embed:
    embed = discord.Embed(
        title=_truncate(f"Official FAQ: {card.name}", EMBED_TITLE_LIMIT),
        url=poneglyph_card_url(card.card_number, card.language),
        color=discord.Color.gold(),
    )
    shown_count = 0
    for index, entry in enumerate(entries, start=1):
        omitted_if_added = len(entries) - index
        footer_reserve = len(_faq_footer(omitted_if_added))
        if not _add_field_if_fits(
            embed,
            f"Q{index}: {entry.question}",
            f"{entry.answer}\nUpdated: {entry.updated_on}",
            inline=False,
            reserved_budget=footer_reserve,
        ):
            break
        shown_count += 1
        if len(embed.fields) >= EMBED_FIELD_LIMIT:
            break
    omitted_count = len(entries) - shown_count
    footer = _faq_footer(omitted_count) if omitted_count else POWERED_BY
    embed.set_footer(
        text=_truncate(
            footer,
            _remaining_footer_budget(embed),
        )
    )
    return embed


def build_price_embed(
    card: CardDetail,
    prices: tuple[PricePoint, ...],
) -> discord.Embed:
    embed = discord.Embed(
        title=_truncate(f"Prices: {card.name}", EMBED_TITLE_LIMIT),
        url=poneglyph_card_url(card.card_number, card.language),
        color=discord.Color.green(),
    )
    embed.set_footer(text=POWERED_BY)
    for price in prices:
        if not _add_field_if_fits(
            embed,
            _price_field_name(price),
            _price_field_value(price),
            inline=False,
        ):
            break
    return embed


def _card_description(card: CardDetail) -> str:
    stat_parts = [card.card_type]
    if card.color:
        stat_parts.append("/".join(card.color))
    if card.cost is not None:
        stat_parts.append(f"Cost {card.cost}")
    if card.power is not None:
        stat_parts.append(f"Power {card.power}")
    if card.counter is not None:
        stat_parts.append(f"Counter {card.counter}")
    if card.life is not None:
        stat_parts.append(f"Life {card.life}")
    lines = [" | ".join(stat_parts)]
    if card.effect:
        lines.append(card.effect)
    if card.trigger:
        lines.append(f"Trigger: {card.trigger}")
    return "\n\n".join(lines)


def _format_legality(card: CardDetail) -> str:
    if not card.legality:
        return ""
    return "\n".join(
        f"{format_name}: {entry.status.replace('_', ' ')}"
        for format_name, entry in card.legality.items()
    )


def _variant_field_value(card: CardDetail) -> str:
    lines = [_variant_line(variant) for variant in card.variants]
    return "\n".join(line for line in lines if line)


def _variant_line(variant: CardVariant) -> str:
    heading = f"#{variant.index}"
    if variant.label:
        heading = f"{heading} {variant.label}"
    parts = [heading]
    if variant.product.name:
        parts.append(variant.product.name)
    price = best_price(variant)
    if price:
        parts.append(f"Market: ${price}")
    return " | ".join(parts)


def _faq_footer(omitted_count: int) -> str:
    if omitted_count <= 0:
        return POWERED_BY
    return f"{POWERED_BY} | {omitted_count} official FAQ entries not shown"


def _price_field_name(price: PricePoint) -> str:
    name = f"Variant {price.variant_index}"
    if price.label:
        name = f"{name}: {price.label}"
    if price.sub_type:
        name = f"{name} ({price.sub_type})"
    return name


def _price_field_value(price: PricePoint) -> str:
    lines: list[str] = []
    for label, value in (
        ("Market", price.market_price),
        ("Low", price.low_price),
        ("Mid", price.mid_price),
        ("High", price.high_price),
    ):
        if value:
            lines.append(f"{label}: ${value}")
    lines.append(f"Fetched: {price.fetched_at}")
    return "\n".join(lines)


def _add_field_if_fits(
    embed: discord.Embed,
    name: str,
    value: str,
    *,
    inline: bool,
    reserved_budget: int = 0,
) -> bool:
    if len(embed.fields) >= EMBED_FIELD_LIMIT:
        return False
    name = _truncate(name, EMBED_FIELD_NAME_LIMIT)
    remaining = _remaining_text_budget(embed) - reserved_budget - len(name)
    value_limit = min(EMBED_FIELD_VALUE_LIMIT, remaining)
    if value_limit <= 0:
        return False
    embed.add_field(name=name, value=_truncate(value, value_limit), inline=inline)
    return True


def _remaining_footer_budget(embed: discord.Embed) -> int:
    return min(EMBED_FOOTER_LIMIT, _remaining_text_budget(embed))


def _remaining_text_budget(embed: discord.Embed) -> int:
    return max(0, EMBED_TOTAL_TEXT_LIMIT - _counted_text_length(embed))


def _counted_text_length(embed: discord.Embed) -> int:
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


def _truncate(value: str, limit: int) -> str:
    if limit <= 0:
        return ""
    if len(value) <= limit:
        return value
    if limit <= 3:
        return value[:limit]
    return f"{value[: limit - 3]}..."
