from optcg_card_bot.config import Settings
from optcg_card_bot.logging import configure_logging


def main() -> None:
    configure_logging()
    settings = Settings(DISCORD_TOKEN="")
    raise SystemExit(
        "Bot runtime is added in a later task. "
        f"Configured API: {settings.poneglyph_base_url}{settings.poneglyph_api_prefix}"
    )


if __name__ == "__main__":
    main()
