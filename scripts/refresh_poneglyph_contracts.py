from __future__ import annotations

import json
from pathlib import Path
from urllib.request import Request, urlopen

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_DIR = PROJECT_ROOT / "contracts" / "poneglyph"
FIXTURE_DIR = PROJECT_ROOT / "tests" / "fixtures" / "poneglyph"

OPENAPI_URL = "https://api.poneglyph.one/openapi.json"
SYNTAX_URL = "https://poneglyph.one/syntax"

FIXTURE_URLS = {
    "card_op01_001.json": "https://api.poneglyph.one/v1/cards/OP01-001",
    "search_op01_001.json": (
        "https://api.poneglyph.one/v1/search?q=OP01-001&limit=5&collapse=card"
    ),
    "search_luffy.json": (
        "https://api.poneglyph.one/v1/search?q=luffy&limit=2&collapse=card"
    ),
}


def fetch_json(url: str) -> object:
    request = Request(url, headers={"User-Agent": "optcg-card-bot-contract-refresh"})
    with urlopen(request, timeout=30) as response:
        return json.load(response)


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_search_syntax_note(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                "# Poneglyph Search Syntax",
                "",
                f"Source: {SYNTAX_URL}",
                "",
                "This bot preserves Poneglyph search syntax and passes user search",
                "queries through unchanged. It strips only Discord command wrappers",
                "and bot-owned options before calling the Poneglyph API.",
                "",
            ]
        ),
        encoding="utf-8",
    )


def main() -> None:
    write_json(CONTRACT_DIR / "openapi.json", fetch_json(OPENAPI_URL))
    write_search_syntax_note(CONTRACT_DIR / "search-syntax.md")

    for filename, url in FIXTURE_URLS.items():
        write_json(FIXTURE_DIR / filename, fetch_json(url))


if __name__ == "__main__":
    main()
