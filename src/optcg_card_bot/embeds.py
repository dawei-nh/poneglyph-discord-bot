from __future__ import annotations

import discord

from optcg_card_bot.models import (
    CardDetail,
    FAQEntry,
    best_image_url,
    best_price,
    best_variant,
    poneglyph_card_url,
)


def build_card_embed(card: CardDetail) -> discord.Embed:
    variant = best_variant(card)
    embed = discord.Embed(
        title=card.name,
        url=poneglyph_card_url(card.card_number, card.language),
        description=_card_description(card),
        color=discord.Color.red(),
    )
    image_url = best_image_url(variant)
    if image_url:
        embed.set_image(url=image_url)
    embed.add_field(name="Set", value=f"{card.set_name} ({card.set})", inline=True)
    embed.add_field(name="Number", value=card.card_number, inline=True)
    embed.add_field(name="Rarity", value=card.rarity or "Unknown", inline=True)
    if card.attribute:
        embed.add_field(name="Attribute", value=", ".join(card.attribute), inline=True)
    if card.types:
        embed.add_field(name="Traits", value=", ".join(card.types), inline=False)
    price = best_price(variant)
    if price:
        embed.add_field(name="Market", value=f"${price}", inline=True)
    legality = _format_legality(card)
    if legality:
        embed.add_field(name="Legality", value=legality, inline=False)
    footer_parts: list[str] = []
    if variant and variant.product.name:
        footer_parts.append(variant.product.name)
    if variant and variant.label:
        footer_parts.append(variant.label)
    if variant and variant.artist:
        footer_parts.append(f"Artist: {variant.artist}")
    footer_parts.append("Powered by Poneglyph")
    embed.set_footer(text=" | ".join(footer_parts))
    return embed


def build_faq_embed(card: CardDetail, entries: tuple[FAQEntry, ...]) -> discord.Embed:
    embed = discord.Embed(
        title=f"Official FAQ: {card.name}",
        url=poneglyph_card_url(card.card_number, card.language),
        color=discord.Color.gold(),
    )
    for index, entry in enumerate(entries[:10], start=1):
        embed.add_field(
            name=f"Q{index}: {_truncate(entry.question, 240)}",
            value=_truncate(f"{entry.answer}\nUpdated: {entry.updated_on}", 1024),
            inline=False,
        )
    embed.set_footer(text="Powered by Poneglyph")
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


def _truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return f"{value[: limit - 3]}..."
