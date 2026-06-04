from __future__ import annotations

from optcg_card_bot.commands import CommandService
from optcg_card_bot.config import Settings
from optcg_card_bot.interactions import create_bot
from optcg_card_bot.poneglyph import PoneglyphClient


async def run_bot(settings: Settings) -> None:
    client = PoneglyphClient(
        base_url=settings.poneglyph_base_url,
        api_prefix=settings.poneglyph_api_prefix,
        timeout=settings.request_timeout_seconds,
        min_interval=settings.request_min_interval_seconds,
    )
    service = CommandService(client, default_language=settings.default_language)
    bot = create_bot(service)
    try:
        async with bot:
            await bot.start(settings.discord_token)
    finally:
        await client.aclose()
