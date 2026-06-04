import asyncio

from optcg_card_bot.bot import run_bot
from optcg_card_bot.config import Settings
from optcg_card_bot.logging import configure_logging


def main() -> None:
    configure_logging()
    asyncio.run(run_bot(Settings()))  # pyright: ignore[reportCallIssue]


if __name__ == "__main__":
    main()
