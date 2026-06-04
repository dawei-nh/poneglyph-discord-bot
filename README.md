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
