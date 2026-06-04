# Slash-First Poneglyph Discord Bot Design

## Purpose

Build a Discord bot that lets One Piece TCG players search Poneglyph from chat
and share card embeds with minimal friction. The MVP is slash-command first,
keeps broad searches private until a card is selected, and preserves Poneglyph's
search language instead of creating a separate bot query syntax.

The bot should feel like a thin Discord interface over Poneglyph, not a second
card database.

## Product Scope

MVP commands:

- `/card query:<poneglyph query>` searches for one card and posts it publicly
  when the result is unambiguous.
- `/search query:<poneglyph query>` shows private paged search results and lets
  the user select a card to post publicly.
- `/random query:<optional poneglyph query or simple filters>` posts one random
  matching card publicly.
- `/faq card:<card number or query>` posts official FAQ entries for an
  unambiguous or selected card.
- `/help` summarizes commands and links to Poneglyph syntax documentation.

Out of MVP:

- Bang-prefix commands such as `!luffy`.
- Full API browsing commands for sets, products, formats, DON, meta, scan
  progress, or reporting.
- Message parsing, except as the Phase 2 `[[card-name]]` feature.
- Public multi-card image grids.

Phase 2 should add `[[card-name]]` message detection shortly after MVP. It must
reuse the same resolver and embed pipeline as `/card` so message lookups do not
develop different search behavior.

## External API Contract

The Poneglyph API is the upstream source of truth.

Default API settings:

```text
PONEGLYPH_BASE_URL=https://api.poneglyph.one
PONEGLYPH_API_PREFIX=/v1
```

MVP endpoint dependencies:

- `GET /v1/search`
- `GET /v1/cards/{card_number}`
- `GET /v1/random`
- `GET /v1/cards/autocomplete`, optional for later autocomplete polish

Useful but non-MVP endpoints:

- `GET /v1/cards/{card_number}/text`
- `POST /v1/cards/batch`
- `GET /v1/sets`
- `GET /v1/products`
- `GET /v1/formats`
- `GET /v1/prices/{card_number}`
- `GET /v1/don`

The OpenAPI contract should be vendored deliberately and checked for drift.
Live smoke tests should be narrow and avoid volatile assertions.

One current contract edge to account for: direct `GET /v1/cards/OP01-001` works,
and `/v1/search?q=OP01-001` returns the card, but
`/v1/search?q=card_number:OP01-001` currently returns zero results despite being
advertised in Poneglyph's syntax guide. The bot should still preserve
`card_number:` queries exactly, but smoke tests should not depend on that form
until upstream behavior is confirmed.

## Architecture

Recommended package modules:

```text
src/optcg_card_bot/
  __init__.py
  __main__.py
  config.py
  errors.py
  models.py
  poneglyph.py
  commands.py
  search.py
  interactions.py
  embeds.py
  logging.py
  contracts.py
  py.typed
tests/
```

Module responsibilities:

- `poneglyph.py`: owns raw Poneglyph HTTP paths, request construction, retries,
  rate-limit handling, and response decoding.
- `models.py`: defines typed local models for cards, variants, FAQ entries,
  search responses, pagination, and selected display data.
- `commands.py`: defines normalized bot intents from Discord slash command
  inputs.
- `search.py`: detects card numbers, preserves raw Poneglyph queries, resolves
  one-result versus ambiguous results, and supports Phase 2 message parsing.
- `interactions.py`: owns Discord slash command handlers, ephemeral views,
  select menus, buttons, pagination, and interaction lifecycle.
- `embeds.py`: builds public card embeds and FAQ embeds from normalized models.
- `config.py`: loads runtime settings from environment variables.
- `errors.py`: maps API, validation, timeout, and Discord interaction failures
  into local error types and user-facing messages.
- `contracts.py`: loads and validates vendored contracts and fixtures.

`grid.py` and public multi-card image generation should be deferred. The MVP
search flow uses ephemeral Discord components instead of public result grids.

## Query Handling

The bot must preserve Poneglyph search semantics. It should strip only Discord
command wrappers and bot-owned options, then pass the remaining query through
unchanged.

Important rules:

- Bare words are broad Poneglyph free-text searches.
- Quoted phrases, boolean operators, parentheses, negation, aliases, inline
  sorting, and comparison operators must be preserved.
- Slash command options such as `page`, `sort`, or `order` may map to explicit
  endpoint parameters only when separate from the raw query.
- The bot should not parse or rewrite Poneglyph's full query language.
- Card-number detection is allowed for direct safe lookups. Examples include
  `OP01-001`, `ST01-001`, and `EB01-001`, case-insensitive.

## Command Behavior

### `/card`

`/card` is for sharing one card.

Flow:

1. Defer the interaction ephemerally unless a direct public response is already
   safe.
2. If the query is a card number, normalize casing, fetch
   `/v1/cards/{card_number}`, and post the card embed publicly immediately.
3. Otherwise call `/v1/search` with the raw query.
4. If there are zero results, respond ephemerally with a no-results message.
5. If there is exactly one result, fetch full card detail and post publicly
   immediately.
6. If there are multiple results, show an ephemeral picker. Selecting a result
   fetches full card detail and posts the selected card publicly.

### `/search`

`/search` is for browsing results.

Flow:

1. Defer ephemerally.
2. Call `/v1/search` with the raw query and requested paging options.
3. Show an ephemeral paged list with enough detail to distinguish cards: name,
   card number, set, type, color, and other compact metadata when available.
4. Provide next/previous controls when more results are available.
5. Selecting a card fetches full detail and posts that card publicly.

`/search` should stay private-first even if the first page has a single result,
because the command intent is browsing rather than immediate sharing.

### `/random`

`/random` is a public share command.

Flow:

1. If the query only uses simple filters accepted by `/v1/random` (`lang`, `set`,
   `color`, `type`, `rarity`), call `/v1/random`.
2. If the query uses broader Poneglyph syntax, sample through `/v1/search`:
   fetch one result to read `pagination.total`, pick a random page, then fetch
   that page with `limit=1`.
3. Post the resulting card publicly immediately.
4. If no cards match, respond with a clear no-results message.

### `/faq`

`/faq` only shows official FAQ content.

Flow:

1. Resolve the card number or query using the same ambiguity rules as `/card`.
2. If the query is ambiguous, show an ephemeral picker before posting any FAQ
   content.
3. Fetch card detail for the direct, single, or selected card.
4. Post `official_faq` entries publicly when present.
5. If there are no official FAQ entries, respond ephemerally that no official
   FAQ is available for that card.

`/faq` must not fall back to `/v1/cards/{card_number}/text`; card text is not
FAQ. A separate card-text command can be considered later, but it is out of MVP.

### `/help`

`/help` should be concise and ephemeral. It should list MVP commands, explain
that Poneglyph search syntax is preserved, and link to the Poneglyph syntax
guide.

## Discord UX

- `/card`, `/search`, `/faq`, and `/help` use ephemeral interaction responses
  until a card or official FAQ entry is unambiguous or intentionally selected
  for public posting.
- `/random` posts publicly immediately.
- Pickers and paged result controls should expire.
- Expired components should tell the user to rerun the command.
- Only the command user can use their picker.
- Public card embeds should include a Poneglyph card link and "Powered by
  Poneglyph".
- Missing images, missing prices, or missing optional fields should degrade
  gracefully.
- User-facing error messages should be short and actionable.

## Embed Contract

Single-card embeds should include:

- Title: card name.
- URL: Poneglyph card page.
- Image: best available variant image.
- Description: compact gameplay summary and card text.
- Fields: set and card number, rarity, type/color, cost, power, counter/life,
  attribute, traits, market price when available, and legality summary when
  available.
- Footer: variant/product context, artist when available, and "Powered by
  Poneglyph".

Image selection order:

1. `variant.images.scan.display`
2. `variant.images.scan.full`
3. `variant.images.stock.full`
4. `variant.images.scan.thumb`
5. `variant.images.stock.thumb`

Price display order:

1. `market.market_price`
2. `market.low_price`
3. `market.mid_price`
4. `market.high_price`

FAQ embeds should include only official FAQ entries from `official_faq`, grouped
or paged if needed to stay within Discord limits.

## Error Handling

`PoneglyphClient` should map upstream and network failures into local errors:

- `400`: validation or invalid query.
- `404`: not found.
- `429`: rate limit.
- `5xx`: upstream API failure.
- timeout/connect errors: network failure.

Retry only transient network failures and HTTP `429`, `500`, `502`, `503`, and
`504`. Honor `Retry-After` when present. Keep request pacing conservative.

Discord handlers should edit deferred responses on failure instead of leaving
interactions unresolved.

## Testing

Contract tests:

- Vendored OpenAPI is readable.
- Required MVP endpoints exist.
- `/v1/search` exposes `q`, `page`, `limit`, `sort`, `order`, `collapse`, and
  `lang`.
- Card detail schema includes required card, variant, image, market, legality,
  language, and FAQ fields.

Live smoke tests:

- Fetch `https://api.poneglyph.one/openapi.json`.
- Direct card lookup for `OP01-001`.
- Bare search for `OP01-001`.
- Broad search for `luffy`.

Live tests must not assert volatile prices, market URLs, total counts, or the
currently inconsistent `card_number:` search form.

Command tests:

- `/card OP01-001` posts immediately.
- `/card` with exactly one search result posts immediately.
- `/card` with multiple results shows an ephemeral picker.
- `/card` with zero results responds ephemerally.
- `/search` always returns ephemeral browse results.
- Picker selection posts the selected card publicly.
- `/random` posts publicly.
- `/random` broad-query sampling handles zero results.
- `/faq` displays only official FAQ entries.
- `/faq` with no official FAQ reports that clearly.

Embed tests:

- Scan image selected when present.
- Stock image fallback.
- Missing image.
- Trigger text.
- Leader life.
- Character power and counter.
- Variant price present and missing.
- Legality summary.
- Official FAQ formatting.

Phase 2 tests should cover `[[card-name]]` message parsing and prove it uses the
same resolver as `/card`.

## Implementation Phases

1. Add contracts, fixtures, project metadata, and package scaffold.
2. Implement Poneglyph client and typed models.
3. Implement slash command intents and card resolution.
4. Implement Discord interaction handlers and ephemeral picker views.
5. Implement card and FAQ embeds.
6. Implement `/random` direct and search-sampling behavior.
7. Add CI checks and narrow live smoke tests.
8. Add Phase 2 `[[card-name]]` message detection shortly after MVP.

## Open Decisions

- Whether to add a separate card-text command after MVP.
- Whether to expose `/sets`, `/formats`, `/products`, or price commands later.
- Whether any bang-prefix commands are worth supporting after `[[card-name]]`.
