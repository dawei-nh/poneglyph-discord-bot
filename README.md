# Poneglyph Discord Bot

Slash-first Discord bot for searching Poneglyph and sharing One Piece TCG card
embeds.

## MVP Commands

- `/card query:<poneglyph query>` posts direct or single-result cards, otherwise
  opens an ephemeral picker.
- `/search query:<poneglyph query>` opens ephemeral paged results.
- `/random query:<optional query>` posts a random matching card publicly.
- `/faq card:<card number or query>` posts official FAQ entries only.
- `/help` shows command help and links to Poneglyph syntax docs.

## Phase 2 Message Lookup

Set `OPTCG_ENABLE_BRACKET_MESSAGES=true` to enable `[[card-name]]` message
detection. Bracket lookups use the same resolver as `/card`: direct and
single-result matches post publicly, while ambiguous matches tell the user to
use `/card` for selection.

## Development

Enter the Nix development shell first:

```bash
nix develop
```

Then install Python dependencies and run checks:

```bash
uv sync --extra dev
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run pyright
```

## Contract Checks

The repository vendors Poneglyph's OpenAPI document under
`contracts/poneglyph/openapi.json`.

Refresh deliberately:

```bash
uv run python scripts/refresh_poneglyph_contracts.py
```

Run live smoke tests:

```bash
uv run pytest tests/live -v
```

Live tests verify endpoint presence, direct `OP01-001` lookup, bare `OP01-001`
search, and a broad `luffy` search. They do not assert prices, total counts, or
the currently inconsistent `card_number:OP01-001` search form.
