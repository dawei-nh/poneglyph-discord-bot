# Architecture Reference

This document is the durable design reference for the Poneglyph Discord bot.
It captures current product rules, module boundaries, API assumptions, and test
guardrails. Historical implementation plans and dated design specs should not be
used as source-of-truth documentation once their durable decisions are recorded
here.

## Product Shape

The bot is a thin Discord interface over Poneglyph for One Piece TCG card
lookup. It preserves Poneglyph search syntax instead of creating a bot-specific
query language.

Supported commands:

- `/card query:<poneglyph query>` posts direct card-number and exactly-one-result
  matches publicly. Ambiguous matches use an ephemeral picker.
- `/search query:<poneglyph query> sort:<optional field> order:<optional asc|desc>`
  opens private paged browse results and lets the user post a selected card.
- `/random query:<optional query>` posts one random matching card publicly.
- `/faq card:<card number or query>` posts official FAQ entries for an
  unambiguous or selected card.
- `/price card:<card number or query> days:<optional days>` posts price history
  for an unambiguous or selected card.
- `/help` responds ephemerally with command help and a Poneglyph syntax link.

Bracket message lookup is controlled by `OPTCG_ENABLE_BRACKET_MESSAGES`.
When enabled, `[[card-name]]` detection uses the same resolver and embed pipeline
as `/card`. Direct and single-result matches post publicly; ambiguous matches
tell the user to use `/card` for selection.

## Discord Interaction Rules

- `/card`, `/search`, `/faq`, `/price`, and `/help` keep exploratory or ambiguous
  work ephemeral.
- `/random` posts publicly immediately.
- `/card` may post publicly immediately only when a direct card-number lookup or
  exactly-one search result is unambiguous.
- `/search` remains private-first even when a page contains one result because
  its intent is browsing.
- `/card`, `/search`, and `/random` accept an optional `variant` selector for
  the initial card image. Numeric selectors clamp to the nearest available
  variant; named selectors match variant names, labels, product context, and
  short aliases such as `alt`, `sp`, and `manga`. Missing or unmatched values use
  variant `0`.
- Pickers and paged controls are scoped to the user who invoked the command.
- Selected picker cards post through the same public channel path as direct
  matches, then replace the ephemeral picker with owner-only variant controls
  when the selected card has alternate images.
- Expired or invalid interactions should fail with short, actionable messages.
- Missing images, missing prices, and missing optional card fields must degrade
  gracefully instead of blocking the response.

## Query Handling

Preserve Poneglyph search semantics. Strip only Discord command wrappers and
bot-owned options, then pass the remaining query through unchanged.

Important rules:

- Bare words are broad Poneglyph free-text searches.
- Quoted phrases, boolean operators, parentheses, negation, aliases, inline
  sorting, and comparison operators must be preserved.
- Slash command options such as `sort`, `order`, `page`, or `days` may map to
  explicit endpoint parameters only when they are separate bot-owned options.
- The bot should not parse or rewrite Poneglyph's full query language.
- Card-number detection is allowed for direct safe lookups. Examples include
  `OP01-001`, `ST01-001`, and `EB01-001`, case-insensitive.

## Poneglyph API Contract

The vendored OpenAPI contract under `contracts/poneglyph/openapi.json` is the
local source of truth for upstream API shape. Refresh it deliberately and review
the diff before committing.

Default API settings:

```text
PONEGLYPH_BASE_URL=https://api.poneglyph.one
PONEGLYPH_API_PREFIX=/v1
```

Current endpoint dependencies:

- `GET /v1/search`
- `GET /v1/cards/{card_number}`
- `GET /v1/random`
- `GET /v1/cards/autocomplete`
- `GET /v1/prices/{card_number}`

Known upstream caveat: direct `GET /v1/cards/OP01-001` works, and
`/v1/search?q=OP01-001` returns the card, but
`/v1/search?q=card_number:OP01-001` has been inconsistent. Preserve
`card_number:` queries exactly, but do not depend on that form in live smoke
tests unless upstream behavior is confirmed.

## Module Boundaries

Runtime code lives in `src/optcg_card_bot/`.

- `bot.py`: wires the Discord client, command tree, and optional bracket
  listener.
- `commands.py`: defines normalized bot intents from Discord slash-command
  inputs.
- `config.py`: loads runtime settings from environment variables, including
  Docker secret-file support for `DISCORD_TOKEN_FILE`.
- `contracts.py`: loads and validates vendored Poneglyph contracts.
- `embeds.py`: builds card, FAQ, price, search-result, and help embeds.
- `errors.py`: maps upstream, validation, timeout, and Discord interaction
  failures into local errors and user-facing messages.
- `interactions.py`: owns Discord command handlers, ephemeral views, select
  menus, pagination, autocomplete, and interaction lifecycle behavior.
- `models.py`: defines typed local models for cards, variants, FAQ entries,
  prices, pagination, autocomplete, and display data.
- `poneglyph.py`: owns raw Poneglyph HTTP paths, request construction, retries,
  rate-limit handling, and response decoding.
- `search.py`: detects card numbers, preserves raw Poneglyph queries, resolves
  one-result versus ambiguous results, and supports bracket lookup.

Keep feature work aligned with these boundaries. Add new modules only when they
remove real complexity or match an established boundary.

## Embed Rules

Single-card embeds should include the card name, Poneglyph card URL, best
available image, compact gameplay/card text, set and card number, rarity, type
and color, core stats, traits, legality, price when available, variant context,
and a Poneglyph footer.

Image selection order:

1. `variant.images.scan.display`
2. `variant.images.scan.full`
3. `variant.images.stock.full`
4. `variant.images.scan.thumb`
5. `variant.images.stock.thumb`

FAQ embeds must include only official FAQ entries from `official_faq`. Do not
fall back to `/v1/cards/{card_number}/text`; card text is not FAQ.

Price output must avoid asserting that volatile market data is present. If a
price response lacks optional values, render the useful available fields or a
clear no-data message.

Variant output should stay compact: show variant indexes, labels, products, and
best available market value when present so users can distinguish standard,
alternate-art, promo, and product-specific printings. Public card embeds keep
variant controls out of the public component row; cards with multiple images
provide owner-only ephemeral controls that cycle the public embed's primary
image, footer context, and market value without changing the selected card.

## Deployment Shape

Docker is the supported production packaging path. The active deployment
reference is `docs/deployment/docker.md`.

The image should run through the package entrypoint, install only runtime
dependencies, avoid committing or baking in secrets, support `DISCORD_TOKEN`
and `DISCORD_TOKEN_FILE`, and publish only through the protected `main` branch
workflow.

## Testing Guardrails

Use the local unit and contract tests as the main regression suite. Live smoke
tests should stay narrow and avoid volatile assertions.

Do not assert:

- volatile prices
- market URLs
- total result counts
- `card_number:OP01-001` search behavior

Stable live card-number checks:

- direct `GET /v1/cards/OP01-001`
- bare search `q=OP01-001`

Before reporting a scoped task complete, run the relevant verification commands
through `nix develop` and inspect their output.
