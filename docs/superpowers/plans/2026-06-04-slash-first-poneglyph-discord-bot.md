# Slash-First Poneglyph Discord Bot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a slash-first Discord bot that searches Poneglyph, posts unambiguous cards directly, uses ephemeral pickers for ambiguous searches, posts random cards publicly, and displays official FAQ entries only.

**Architecture:** Keep Poneglyph API access, card resolution, command outcomes, Discord interactions, and embed rendering in separate modules. Most behavior is tested without Discord by using typed models, fake API clients, and command outcome objects; `interactions.py` stays thin and maps those outcomes to `discord.py` slash commands and views.

**Tech Stack:** Python 3.12, `uv`, `discord.py` 2.x, `httpx`, Pydantic 2.x, pytest, pytest-asyncio, Ruff, Pyright.

---

## File Structure

Create this structure:

```text
.github/workflows/ci.yml
.gitignore
.env.example
README.md
pyproject.toml
scripts/refresh_poneglyph_contracts.py
contracts/poneglyph/openapi.json
contracts/poneglyph/search-syntax.md
src/optcg_card_bot/
  __init__.py
  __main__.py
  bot.py
  commands.py
  config.py
  contracts.py
  embeds.py
  errors.py
  interactions.py
  logging.py
  models.py
  poneglyph.py
  search.py
  py.typed
tests/
  fixtures/poneglyph/card_op01_001.json
  fixtures/poneglyph/search_luffy.json
  fixtures/poneglyph/search_op01_001.json
  test_commands.py
  test_config.py
  test_contracts.py
  test_embeds.py
  test_interactions.py
  test_models.py
  test_poneglyph.py
  test_search.py
tests/live/
  test_live_poneglyph_contract.py
```

Responsibilities:

- `config.py`: environment parsing and defaults.
- `errors.py`: local exception hierarchy and user-facing message mapping.
- `models.py`: Pydantic models for Poneglyph card/search/random responses.
- `poneglyph.py`: async HTTP client, retries, endpoint methods, random sampling.
- `search.py`: card-number detection, bracket extraction for Phase 2, card resolution.
- `commands.py`: command outcome dataclasses and command service methods.
- `embeds.py`: Discord embed builders and formatting helpers.
- `interactions.py`: slash command registration and Discord views.
- `bot.py`: bot construction and lifecycle.
- `contracts.py`: vendored contract loading and required-endpoint validation.

---

### Task 1: Project Scaffold And Configuration

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `.env.example`
- Create: `README.md`
- Create: `src/optcg_card_bot/__init__.py`
- Create: `src/optcg_card_bot/__main__.py`
- Create: `src/optcg_card_bot/config.py`
- Create: `src/optcg_card_bot/logging.py`
- Create: `src/optcg_card_bot/py.typed`
- Create: `tests/test_config.py`

- [ ] **Step 1: Write failing configuration tests**

Create `tests/test_config.py`:

```python
from optcg_card_bot.config import Settings


def test_settings_defaults() -> None:
    settings = Settings(discord_token="token")

    assert settings.discord_token == "token"
    assert settings.poneglyph_base_url == "https://api.poneglyph.one"
    assert settings.poneglyph_api_prefix == "/v1"
    assert settings.default_language == "en"
    assert settings.request_timeout_seconds == 10.0
    assert settings.request_min_interval_seconds == 0.25
    assert settings.enable_bracket_messages is False


def test_settings_normalizes_api_prefix() -> None:
    settings = Settings(discord_token="token", poneglyph_api_prefix="v1")

    assert settings.poneglyph_api_prefix == "/v1"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest tests/test_config.py -v
```

Expected: FAIL because `pyproject.toml` and `optcg_card_bot.config` do not exist.

- [ ] **Step 3: Add Python project metadata**

Create `pyproject.toml`:

```toml
[project]
name = "poneglyph-discord-bot"
version = "0.1.0"
description = "Discord bot for sharing One Piece TCG cards from Poneglyph."
readme = "README.md"
requires-python = ">=3.12"
license = { text = "MIT" }
dependencies = [
  "discord.py>=2.5,<3",
  "httpx>=0.27,<1",
  "pydantic>=2.8,<3",
  "pydantic-settings>=2.4,<3",
]

[project.optional-dependencies]
dev = [
  "pytest>=8.3,<9",
  "pytest-asyncio>=0.24,<1",
  "ruff>=0.8,<1",
  "pyright>=1.1,<2",
]

[project.scripts]
optcg-card-bot = "optcg_card_bot.__main__:main"

[build-system]
requires = ["hatchling>=1.25"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/optcg_card_bot"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
markers = [
  "live: tests that call the live Poneglyph API",
]

[tool.ruff]
line-length = 88
target-version = "py312"
src = ["src", "tests"]

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM"]

[tool.pyright]
pythonVersion = "3.12"
typeCheckingMode = "strict"
include = ["src"]
venvPath = "."
venv = ".venv"
```

- [ ] **Step 4: Add repository support files**

Create `.gitignore`:

```gitignore
.venv/
.pytest_cache/
.ruff_cache/
__pycache__/
*.py[cod]
.env
.coverage
htmlcov/
dist/
build/
*.egg-info/
```

Create `.env.example`:

```text
DISCORD_TOKEN=
PONEGLYPH_BASE_URL=https://api.poneglyph.one
PONEGLYPH_API_PREFIX=/v1
OPTCG_DEFAULT_LANGUAGE=en
OPTCG_REQUEST_TIMEOUT_SECONDS=10
OPTCG_REQUEST_MIN_INTERVAL_SECONDS=0.25
OPTCG_ENABLE_BRACKET_MESSAGES=false
```

Create `README.md`:

```markdown
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

```bash
uv sync --extra dev
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run pyright
```
```

- [ ] **Step 5: Add package and settings implementation**

Create `src/optcg_card_bot/__init__.py`:

```python
__all__ = ["__version__"]

__version__ = "0.1.0"
```

Create empty marker file `src/optcg_card_bot/py.typed`.

Create `src/optcg_card_bot/config.py`:

```python
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="",
        extra="ignore",
        populate_by_name=True,
    )

    discord_token: str = Field(alias="DISCORD_TOKEN")
    poneglyph_base_url: str = Field(
        default="https://api.poneglyph.one",
        alias="PONEGLYPH_BASE_URL",
    )
    poneglyph_api_prefix: str = Field(default="/v1", alias="PONEGLYPH_API_PREFIX")
    default_language: str = Field(default="en", alias="OPTCG_DEFAULT_LANGUAGE")
    request_timeout_seconds: float = Field(
        default=10.0,
        alias="OPTCG_REQUEST_TIMEOUT_SECONDS",
    )
    request_min_interval_seconds: float = Field(
        default=0.25,
        alias="OPTCG_REQUEST_MIN_INTERVAL_SECONDS",
    )
    enable_bracket_messages: bool = Field(
        default=False,
        alias="OPTCG_ENABLE_BRACKET_MESSAGES",
    )

    @field_validator("poneglyph_api_prefix")
    @classmethod
    def normalize_api_prefix(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            return "/v1"
        return stripped if stripped.startswith("/") else f"/{stripped}"
```

Create `src/optcg_card_bot/logging.py`:

```python
import logging


def configure_logging(level: int = logging.INFO) -> None:
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
```

Create `src/optcg_card_bot/__main__.py`:

```python
from optcg_card_bot.config import Settings
from optcg_card_bot.logging import configure_logging


def main() -> None:
    configure_logging()
    settings = Settings()
    raise SystemExit(
        "Bot runtime is added in a later task. "
        f"Configured API: {settings.poneglyph_base_url}{settings.poneglyph_api_prefix}"
    )


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Run scaffold checks**

Run:

```bash
uv sync --extra dev
uv run pytest tests/test_config.py -v
uv run ruff check .
uv run pyright
```

Expected: all commands exit 0.

- [ ] **Step 7: Commit scaffold**

```bash
git add .gitignore .env.example README.md pyproject.toml src/optcg_card_bot tests/test_config.py
git commit -m "chore: scaffold python bot project"
```

---

### Task 2: Vendored Contracts And Fixtures

**Files:**
- Create: `contracts/poneglyph/openapi.json`
- Create: `contracts/poneglyph/search-syntax.md`
- Create: `scripts/refresh_poneglyph_contracts.py`
- Create: `src/optcg_card_bot/contracts.py`
- Create: `tests/fixtures/poneglyph/card_op01_001.json`
- Create: `tests/fixtures/poneglyph/search_op01_001.json`
- Create: `tests/fixtures/poneglyph/search_luffy.json`
- Create: `tests/test_contracts.py`

- [ ] **Step 1: Write failing contract tests**

Create `tests/test_contracts.py`:

```python
from optcg_card_bot.contracts import (
    load_poneglyph_openapi,
    require_card_detail_schema,
    require_endpoint,
    require_search_parameters,
)


def test_vendored_openapi_contains_mvp_endpoints() -> None:
    contract = load_poneglyph_openapi()

    for path in ["/v1/search", "/v1/cards/{card_number}", "/v1/random"]:
        require_endpoint(contract, path)


def test_vendored_openapi_contains_required_search_parameters() -> None:
    contract = load_poneglyph_openapi()

    assert require_search_parameters(contract) == {
        "q",
        "page",
        "limit",
        "sort",
        "order",
        "collapse",
        "lang",
    }


def test_vendored_openapi_contains_card_detail_shape() -> None:
    contract = load_poneglyph_openapi()

    required = require_card_detail_schema(contract)

    assert {"card_number", "name", "variants", "official_faq"} <= required
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest tests/test_contracts.py -v
```

Expected: FAIL because `optcg_card_bot.contracts` and vendored files do not exist.

- [ ] **Step 3: Add refresh script**

Create `scripts/refresh_poneglyph_contracts.py`:

```python
from __future__ import annotations

from pathlib import Path

import httpx


ROOT = Path(__file__).resolve().parents[1]
OPENAPI_URL = "https://api.poneglyph.one/openapi.json"
SYNTAX_URL = "https://poneglyph.one/syntax"


def fetch_text(url: str) -> str:
    response = httpx.get(url, timeout=20.0)
    response.raise_for_status()
    return response.text


def main() -> None:
    contract_dir = ROOT / "contracts" / "poneglyph"
    contract_dir.mkdir(parents=True, exist_ok=True)

    (contract_dir / "openapi.json").write_text(fetch_text(OPENAPI_URL), encoding="utf-8")
    (contract_dir / "search-syntax.md").write_text(
        "# Poneglyph Search Syntax\n\n"
        "Source: https://poneglyph.one/syntax\n\n"
        "The bot preserves Poneglyph syntax and strips only Discord command "
        "wrappers. Update this summary after reviewing the source page when "
        "the OpenAPI contract is refreshed.\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Fetch current contract and fixture JSON**

Run:

```bash
mkdir -p contracts/poneglyph tests/fixtures/poneglyph
uv run python scripts/refresh_poneglyph_contracts.py
curl -fsSL -o tests/fixtures/poneglyph/card_op01_001.json https://api.poneglyph.one/v1/cards/OP01-001
curl -fsSL -o tests/fixtures/poneglyph/search_op01_001.json "https://api.poneglyph.one/v1/search?q=OP01-001&limit=5&collapse=card"
curl -fsSL -o tests/fixtures/poneglyph/search_luffy.json "https://api.poneglyph.one/v1/search?q=luffy&limit=2&collapse=card"
```

Expected: files exist and contain JSON responses from Poneglyph.

- [ ] **Step 5: Add contract loader implementation**

Create `src/optcg_card_bot/contracts.py`:

```python
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
OPENAPI_PATH = PROJECT_ROOT / "contracts" / "poneglyph" / "openapi.json"


JsonObject = dict[str, Any]


def load_json_file(path: Path) -> JsonObject:
    return json.loads(path.read_text(encoding="utf-8"))


def load_poneglyph_openapi() -> JsonObject:
    return load_json_file(OPENAPI_PATH)


def require_endpoint(contract: JsonObject, path: str) -> JsonObject:
    paths = contract.get("paths")
    if not isinstance(paths, dict) or path not in paths:
        raise AssertionError(f"Missing Poneglyph endpoint: {path}")
    endpoint = paths[path]
    if not isinstance(endpoint, dict):
        raise AssertionError(f"Endpoint is not an object: {path}")
    return endpoint


def require_search_parameters(contract: JsonObject) -> set[str]:
    search = require_endpoint(contract, "/v1/search")
    get = search.get("get")
    if not isinstance(get, dict):
        raise AssertionError("GET /v1/search is missing")
    parameters = get.get("parameters")
    if not isinstance(parameters, list):
        raise AssertionError("GET /v1/search parameters are missing")
    names = {parameter["name"] for parameter in parameters if isinstance(parameter, dict)}
    required = {"q", "page", "limit", "sort", "order", "collapse", "lang"}
    missing = required - names
    if missing:
        raise AssertionError(f"GET /v1/search missing parameters: {sorted(missing)}")
    return required


def require_card_detail_schema(contract: JsonObject) -> set[str]:
    endpoint = require_endpoint(contract, "/v1/cards/{card_number}")
    schema = (
        endpoint["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    )
    data_schema = schema["properties"]["data"]
    required = data_schema.get("required")
    if not isinstance(required, list):
        raise AssertionError("Card detail schema has no required field list")
    return set(required)
```

- [ ] **Step 6: Run contract tests**

Run:

```bash
uv run pytest tests/test_contracts.py -v
uv run ruff check src/optcg_card_bot/contracts.py tests/test_contracts.py
uv run pyright
```

Expected: all commands exit 0.

- [ ] **Step 7: Commit contracts**

```bash
git add contracts/poneglyph scripts/refresh_poneglyph_contracts.py src/optcg_card_bot/contracts.py tests/fixtures/poneglyph tests/test_contracts.py
git commit -m "test: vendor poneglyph contracts"
```

---

### Task 3: Typed Poneglyph Models

**Files:**
- Create: `src/optcg_card_bot/models.py`
- Create: `tests/test_models.py`

- [ ] **Step 1: Write failing model tests**

Create `tests/test_models.py`:

```python
import json
from pathlib import Path

from optcg_card_bot.models import CardDetailResponse, SearchResponse


FIXTURES = Path(__file__).parent / "fixtures" / "poneglyph"


def test_card_detail_fixture_parses() -> None:
    payload = json.loads((FIXTURES / "card_op01_001.json").read_text())

    response = CardDetailResponse.model_validate(payload)

    assert response.data.card_number == "OP01-001"
    assert response.data.name == "Roronoa Zoro"
    assert response.data.variants
    assert response.data.official_faq


def test_search_fixture_parses_without_detail_only_fields() -> None:
    payload = json.loads((FIXTURES / "search_luffy.json").read_text())

    response = SearchResponse.model_validate(payload)

    assert response.pagination.limit == 2
    assert response.data[0].card_number
    assert response.meta.sort_applied in {"relevance", "card_number"}
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest tests/test_models.py -v
```

Expected: FAIL because `optcg_card_bot.models` does not exist.

- [ ] **Step 3: Add model implementation**

Create `src/optcg_card_bot/models.py`:

```python
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CropFocus(StrictModel):
    x: float | None
    y: float | None


class ProductRef(StrictModel):
    id: str | None
    slug: str | None
    name: str | None
    set_code: str | None
    released_at: str | None


class StockImages(StrictModel):
    full: str | None
    thumb: str | None


class ScanImages(StrictModel):
    display: str | None
    full: str | None
    thumb: str | None


class VariantImages(StrictModel):
    stock: StockImages
    scan: ScanImages


class Market(StrictModel):
    tcgplayer_url: str | None
    market_price: str | None
    low_price: str | None
    mid_price: str | None
    high_price: str | None


class CardVariant(StrictModel):
    index: int
    name: str | None
    label: str | None
    artist: str | None
    crop_focus: CropFocus
    product: ProductRef
    images: VariantImages
    errata: list[dict[str, Any]]
    market: Market


class LegalityEntry(BaseModel):
    model_config = ConfigDict(extra="allow")

    status: str
    banned_at: str | None = None
    reason: str | None = None
    max_copies: int | None = None
    paired_with: list[str] | None = None


class FAQEntry(StrictModel):
    question: str
    answer: str
    updated_on: str


class CardSummary(StrictModel):
    card_number: str
    name: str
    language: str
    set: str
    set_name: str
    released_at: str | None
    released: bool
    card_type: str
    rarity: str | None
    color: list[str]
    cost: int | None
    power: int | None
    counter: int | None
    life: int | None
    attribute: list[str] | None
    types: list[str]
    effect: str | None
    trigger: str | None
    block: str | None
    variants: list[CardVariant]


class CardDetail(CardSummary):
    legality: dict[str, LegalityEntry]
    available_languages: list[str]
    official_faq: list[FAQEntry]


class Pagination(StrictModel):
    page: int
    limit: int
    total: int
    has_more: bool


class SearchMeta(StrictModel):
    sort_requested: str
    sort_applied: str
    order_requested: str
    order_applied: str
    relevance_active: bool


class CardDetailResponse(StrictModel):
    data: CardDetail


class SearchResponse(StrictModel):
    data: list[CardSummary]
    pagination: Pagination
    meta: SearchMeta


class RandomCardResponse(StrictModel):
    data: CardDetail


class SearchParams(StrictModel):
    q: str | None = None
    page: int = 1
    limit: int = 60
    sort: str | None = None
    order: str | None = None
    collapse: str = "card"
    lang: str = "en"


def best_variant(card: CardSummary) -> CardVariant | None:
    return card.variants[0] if card.variants else None


def best_image_url(variant: CardVariant | None) -> str | None:
    if variant is None:
        return None
    for value in (
        variant.images.scan.display,
        variant.images.scan.full,
        variant.images.stock.full,
        variant.images.scan.thumb,
        variant.images.stock.thumb,
    ):
        if value:
            return value
    return None


def best_price(variant: CardVariant | None) -> str | None:
    if variant is None:
        return None
    for value in (
        variant.market.market_price,
        variant.market.low_price,
        variant.market.mid_price,
        variant.market.high_price,
    ):
        if value:
            return value
    return None


def poneglyph_card_url(card_number: str, lang: str = "en") -> str:
    return f"https://poneglyph.one/cards/{card_number}?lang={lang}"
```

- [ ] **Step 4: Run model tests**

Run:

```bash
uv run pytest tests/test_models.py -v
uv run ruff check src/optcg_card_bot/models.py tests/test_models.py
uv run pyright
```

Expected: all commands exit 0.

- [ ] **Step 5: Commit models**

```bash
git add src/optcg_card_bot/models.py tests/test_models.py
git commit -m "feat: add poneglyph response models"
```

---

### Task 4: Error Types And Poneglyph HTTP Client

**Files:**
- Create: `src/optcg_card_bot/errors.py`
- Create: `src/optcg_card_bot/poneglyph.py`
- Create: `tests/test_poneglyph.py`

- [ ] **Step 1: Write failing client tests**

Create `tests/test_poneglyph.py`:

```python
import json
from pathlib import Path

import httpx
import pytest

from optcg_card_bot.errors import PoneglyphNotFoundError, PoneglyphRateLimitError
from optcg_card_bot.poneglyph import PoneglyphClient


FIXTURES = Path(__file__).parent / "fixtures" / "poneglyph"


@pytest.mark.asyncio
async def test_search_url_construction() -> None:
    requests: list[httpx.Request] = []
    payload = json.loads((FIXTURES / "search_luffy.json").read_text())

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=payload)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://api.example.test",
    ) as http:
        client = PoneglyphClient(http_client=http, api_prefix="/v1", min_interval=0)
        response = await client.search_cards("luffy", limit=2)

    assert response.pagination.limit == 2
    assert requests[0].url.path == "/v1/search"
    assert requests[0].url.params["q"] == "luffy"
    assert requests[0].url.params["limit"] == "2"
    assert requests[0].url.params["collapse"] == "card"


@pytest.mark.asyncio
async def test_get_card_maps_404() -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(404)),
        base_url="https://api.example.test",
    ) as http:
        client = PoneglyphClient(http_client=http, api_prefix="/v1", min_interval=0)

        with pytest.raises(PoneglyphNotFoundError):
            await client.get_card("OP99-999")


@pytest.mark.asyncio
async def test_429_maps_to_rate_limit_after_retries() -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(429)),
        base_url="https://api.example.test",
    ) as http:
        client = PoneglyphClient(
            http_client=http,
            api_prefix="/v1",
            min_interval=0,
            max_retries=0,
        )

        with pytest.raises(PoneglyphRateLimitError):
            await client.search_cards("luffy")


@pytest.mark.asyncio
async def test_random_query_sampling_uses_search_total() -> None:
    search_payload = json.loads((FIXTURES / "search_op01_001.json").read_text())
    card_payload = json.loads((FIXTURES / "card_op01_001.json").read_text())
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) <= 2:
            return httpx.Response(200, json=search_payload)
        return httpx.Response(200, json=card_payload)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://api.example.test",
    ) as http:
        client = PoneglyphClient(http_client=http, api_prefix="/v1", min_interval=0)
        result = await client.get_random_from_query(
            "OP01-001",
            random_page=lambda total: 1,
        )

    assert result.card_number == "OP01-001"
    assert len(requests) == 3
    assert requests[0].url.params["limit"] == "1"
    assert requests[1].url.params["page"] == "1"
    assert requests[2].url.path == "/v1/cards/OP01-001"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest tests/test_poneglyph.py -v
```

Expected: FAIL because `errors.py` and `poneglyph.py` do not exist.

- [ ] **Step 3: Add error hierarchy**

Create `src/optcg_card_bot/errors.py`:

```python
from __future__ import annotations


class BotError(Exception):
    user_message = "Something went wrong. Please try again."


class PoneglyphError(BotError):
    user_message = "Poneglyph is unavailable right now. Please try again soon."


class PoneglyphValidationError(PoneglyphError):
    user_message = "Poneglyph could not understand that query."


class PoneglyphNotFoundError(PoneglyphError):
    user_message = "No matching card was found."


class PoneglyphRateLimitError(PoneglyphError):
    user_message = "Poneglyph is rate-limiting requests. Please try again soon."


class PoneglyphServerError(PoneglyphError):
    user_message = "Poneglyph returned a temporary server error."


class PoneglyphNetworkError(PoneglyphError):
    user_message = "Could not reach Poneglyph. Please try again soon."


class NoSearchResultsError(BotError):
    user_message = "No matching cards were found."
```

- [ ] **Step 4: Add Poneglyph client implementation**

Create `src/optcg_card_bot/poneglyph.py`:

```python
from __future__ import annotations

import asyncio
import random
import time
from collections.abc import Callable
from typing import Any

import httpx

from optcg_card_bot.errors import (
    NoSearchResultsError,
    PoneglyphNetworkError,
    PoneglyphNotFoundError,
    PoneglyphRateLimitError,
    PoneglyphServerError,
    PoneglyphValidationError,
)
from optcg_card_bot.models import (
    CardDetail,
    CardDetailResponse,
    RandomCardResponse,
    SearchResponse,
)


TRANSIENT_STATUSES = {429, 500, 502, 503, 504}


class PoneglyphClient:
    def __init__(
        self,
        *,
        http_client: httpx.AsyncClient | None = None,
        base_url: str = "https://api.poneglyph.one",
        api_prefix: str = "/v1",
        timeout: float = 10.0,
        min_interval: float = 0.25,
        max_retries: int = 2,
        user_agent: str = "poneglyph-discord-bot/0.1.0",
    ) -> None:
        self._owns_client = http_client is None
        self._client = http_client or httpx.AsyncClient(
            base_url=base_url,
            timeout=timeout,
            headers={"Accept": "application/json", "User-Agent": user_agent},
        )
        self._api_prefix = api_prefix.rstrip("/")
        self._min_interval = min_interval
        self._max_retries = max_retries
        self._last_request_at = 0.0

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def search_cards(
        self,
        query: str | None,
        *,
        page: int = 1,
        limit: int = 60,
        sort: str | None = None,
        order: str | None = None,
        collapse: str = "card",
        lang: str = "en",
    ) -> SearchResponse:
        params: dict[str, Any] = {
            "page": page,
            "limit": limit,
            "collapse": collapse,
            "lang": lang,
        }
        if query:
            params["q"] = query
        if sort:
            params["sort"] = sort
        if order:
            params["order"] = order
        data = await self._request_json("GET", "/search", params=params)
        return SearchResponse.model_validate(data)

    async def get_card(self, card_number: str, *, lang: str = "en") -> CardDetail:
        data = await self._request_json(
            "GET",
            f"/cards/{card_number.upper()}",
            params={"lang": lang},
        )
        return CardDetailResponse.model_validate(data).data

    async def get_random(
        self,
        *,
        lang: str = "en",
        set: str | None = None,
        color: str | None = None,
        type: str | None = None,
        rarity: str | None = None,
    ) -> CardDetail:
        params = {
            key: value
            for key, value in {
                "lang": lang,
                "set": set,
                "color": color,
                "type": type,
                "rarity": rarity,
            }.items()
            if value is not None
        }
        data = await self._request_json("GET", "/random", params=params)
        return RandomCardResponse.model_validate(data).data

    async def get_random_from_query(
        self,
        query: str,
        *,
        lang: str = "en",
        random_page: Callable[[int], int] | None = None,
    ) -> CardDetail:
        first = await self.search_cards(
            query,
            page=1,
            limit=1,
            collapse="card",
            lang=lang,
        )
        total = first.pagination.total
        if total <= 0:
            raise NoSearchResultsError()
        page_picker = random_page or (lambda count: random.randint(1, count))
        selected = await self.search_cards(
            query,
            page=page_picker(total),
            limit=1,
            collapse="card",
            lang=lang,
        )
        if not selected.data:
            raise NoSearchResultsError()
        return await self.get_card(selected.data[0].card_number, lang=lang)

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        await self._pace()
        url = f"{self._api_prefix}{path}"
        last_response: httpx.Response | None = None
        for attempt in range(self._max_retries + 1):
            try:
                response = await self._client.request(
                    method,
                    url,
                    params=params,
                    json=json_body,
                )
            except httpx.HTTPError as exc:
                if attempt >= self._max_retries:
                    raise PoneglyphNetworkError() from exc
                await asyncio.sleep(0.25 * (attempt + 1))
                continue
            last_response = response
            if response.status_code not in TRANSIENT_STATUSES:
                break
            if attempt >= self._max_retries:
                break
            await self._sleep_for_retry(response, attempt)
        if last_response is None:
            raise PoneglyphNetworkError()
        self._raise_for_status(last_response)
        payload = last_response.json()
        if not isinstance(payload, dict):
            raise PoneglyphServerError("Expected JSON object from Poneglyph")
        return payload

    async def _pace(self) -> None:
        if self._min_interval <= 0:
            return
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < self._min_interval:
            await asyncio.sleep(self._min_interval - elapsed)
        self._last_request_at = time.monotonic()

    async def _sleep_for_retry(self, response: httpx.Response, attempt: int) -> None:
        retry_after = response.headers.get("Retry-After")
        if retry_after is not None and retry_after.isdigit():
            await asyncio.sleep(float(retry_after))
            return
        await asyncio.sleep(0.25 * (attempt + 1))

    def _raise_for_status(self, response: httpx.Response) -> None:
        status = response.status_code
        if status < 400:
            return
        if status == 400:
            raise PoneglyphValidationError()
        if status == 404:
            raise PoneglyphNotFoundError()
        if status == 429:
            raise PoneglyphRateLimitError()
        if 500 <= status:
            raise PoneglyphServerError()
        raise PoneglyphValidationError()
```

- [ ] **Step 5: Run client tests**

Run:

```bash
uv run pytest tests/test_poneglyph.py -v
uv run ruff check src/optcg_card_bot/errors.py src/optcg_card_bot/poneglyph.py tests/test_poneglyph.py
uv run pyright
```

Expected: all commands exit 0.

- [ ] **Step 6: Commit client**

```bash
git add src/optcg_card_bot/errors.py src/optcg_card_bot/poneglyph.py tests/test_poneglyph.py
git commit -m "feat: add poneglyph api client"
```

---

### Task 5: Card Resolution And Query Helpers

**Files:**
- Create: `src/optcg_card_bot/search.py`
- Create: `tests/test_search.py`

- [ ] **Step 1: Write failing resolver tests**

Create `tests/test_search.py`:

```python
import json
from pathlib import Path

import pytest

from optcg_card_bot.models import CardDetailResponse, SearchResponse
from optcg_card_bot.search import (
    ResolutionKind,
    extract_bracket_queries,
    is_card_number,
    normalize_card_number,
    resolve_card_query,
)


FIXTURES = Path(__file__).parent / "fixtures" / "poneglyph"


class FakeClient:
    def __init__(self) -> None:
        self.card = CardDetailResponse.model_validate(
            json.loads((FIXTURES / "card_op01_001.json").read_text())
        ).data
        self.search_response = SearchResponse.model_validate(
            json.loads((FIXTURES / "search_luffy.json").read_text())
        )
        self.card_numbers_requested: list[str] = []
        self.queries_requested: list[str] = []

    async def get_card(self, card_number: str, *, lang: str = "en"):
        self.card_numbers_requested.append(card_number)
        return self.card

    async def search_cards(
        self,
        query: str | None,
        *,
        page: int = 1,
        limit: int = 60,
        sort: str | None = None,
        order: str | None = None,
        collapse: str = "card",
        lang: str = "en",
    ):
        self.queries_requested.append(query or "")
        return self.search_response


def test_card_number_detection() -> None:
    assert is_card_number("op01-001")
    assert is_card_number("ST01-001")
    assert is_card_number("EB01-001")
    assert not is_card_number("luffy")


def test_card_number_normalization() -> None:
    assert normalize_card_number(" op01-001 ") == "OP01-001"


@pytest.mark.asyncio
async def test_direct_card_number_resolution_fetches_detail() -> None:
    client = FakeClient()

    resolution = await resolve_card_query(client, "op01-001")

    assert resolution.kind is ResolutionKind.DIRECT
    assert resolution.card is not None
    assert resolution.card.card_number == "OP01-001"
    assert client.card_numbers_requested == ["OP01-001"]
    assert client.queries_requested == []


@pytest.mark.asyncio
async def test_ambiguous_query_returns_choices() -> None:
    client = FakeClient()

    resolution = await resolve_card_query(client, "luffy")

    assert resolution.kind is ResolutionKind.MULTIPLE
    assert resolution.card is None
    assert len(resolution.choices) == 2
    assert client.queries_requested == ["luffy"]


def test_extract_bracket_queries_for_phase_two() -> None:
    assert extract_bracket_queries("play [[luffy]] and [[OP01-001]]") == [
        "luffy",
        "OP01-001",
    ]
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest tests/test_search.py -v
```

Expected: FAIL because `optcg_card_bot.search` does not exist.

- [ ] **Step 3: Add resolution helpers**

Create `src/optcg_card_bot/search.py`:

```python
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol

from optcg_card_bot.models import CardDetail, CardSummary, SearchResponse


CARD_NUMBER_RE = re.compile(r"^(?:OP|ST|EB|PRB|P)-?\d{2}-\d{3}[A-Z]?$", re.IGNORECASE)
BRACKET_RE = re.compile(r"\[\[([^\[\]]+)\]\]")


class CardLookupClient(Protocol):
    async def get_card(self, card_number: str, *, lang: str = "en") -> CardDetail: ...

    async def search_cards(
        self,
        query: str | None,
        *,
        page: int = 1,
        limit: int = 60,
        sort: str | None = None,
        order: str | None = None,
        collapse: str = "card",
        lang: str = "en",
    ) -> SearchResponse: ...


class ResolutionKind(str, Enum):
    DIRECT = "direct"
    SINGLE = "single"
    MULTIPLE = "multiple"
    NOT_FOUND = "not_found"


@dataclass(frozen=True)
class CardChoice:
    card_number: str
    name: str
    set_code: str
    card_type: str
    color: tuple[str, ...]

    @classmethod
    def from_summary(cls, card: CardSummary) -> CardChoice:
        return cls(
            card_number=card.card_number,
            name=card.name,
            set_code=card.set,
            card_type=card.card_type,
            color=tuple(card.color),
        )


@dataclass(frozen=True)
class CardResolution:
    kind: ResolutionKind
    query: str
    card: CardDetail | None = None
    choices: tuple[CardChoice, ...] = field(default_factory=tuple)


def is_card_number(value: str) -> bool:
    return bool(CARD_NUMBER_RE.match(value.strip()))


def normalize_card_number(value: str) -> str:
    return value.strip().upper()


def extract_bracket_queries(content: str) -> list[str]:
    return [match.strip() for match in BRACKET_RE.findall(content) if match.strip()]


async def resolve_card_query(
    client: CardLookupClient,
    query: str,
    *,
    lang: str = "en",
    search_limit: int = 10,
) -> CardResolution:
    raw_query = query.strip()
    if is_card_number(raw_query):
        card_number = normalize_card_number(raw_query)
        card = await client.get_card(card_number, lang=lang)
        return CardResolution(kind=ResolutionKind.DIRECT, query=raw_query, card=card)

    response = await client.search_cards(
        raw_query,
        page=1,
        limit=search_limit,
        collapse="card",
        lang=lang,
    )
    if response.pagination.total == 0 or not response.data:
        return CardResolution(kind=ResolutionKind.NOT_FOUND, query=raw_query)
    if response.pagination.total == 1 or len(response.data) == 1:
        card = await client.get_card(response.data[0].card_number, lang=lang)
        return CardResolution(kind=ResolutionKind.SINGLE, query=raw_query, card=card)
    return CardResolution(
        kind=ResolutionKind.MULTIPLE,
        query=raw_query,
        choices=tuple(CardChoice.from_summary(card) for card in response.data),
    )
```

- [ ] **Step 4: Run search tests**

Run:

```bash
uv run pytest tests/test_search.py -v
uv run ruff check src/optcg_card_bot/search.py tests/test_search.py
uv run pyright
```

Expected: all commands exit 0.

- [ ] **Step 5: Commit search helpers**

```bash
git add src/optcg_card_bot/search.py tests/test_search.py
git commit -m "feat: add card query resolution"
```

---

### Task 6: Command Outcome Service

**Files:**
- Create: `src/optcg_card_bot/commands.py`
- Create: `tests/test_commands.py`

- [ ] **Step 1: Write failing command service tests**

Create `tests/test_commands.py`:

```python
import json
from pathlib import Path

import pytest

from optcg_card_bot.commands import CommandOutcomeKind, CommandService
from optcg_card_bot.models import CardDetailResponse, SearchResponse


FIXTURES = Path(__file__).parent / "fixtures" / "poneglyph"


class FakeClient:
    def __init__(self) -> None:
        self.card = CardDetailResponse.model_validate(
            json.loads((FIXTURES / "card_op01_001.json").read_text())
        ).data
        self.search_response = SearchResponse.model_validate(
            json.loads((FIXTURES / "search_luffy.json").read_text())
        )
        self.random_card = self.card

    async def get_card(self, card_number: str, *, lang: str = "en"):
        return self.card

    async def search_cards(
        self,
        query: str | None,
        *,
        page: int = 1,
        limit: int = 60,
        sort: str | None = None,
        order: str | None = None,
        collapse: str = "card",
        lang: str = "en",
    ):
        return self.search_response

    async def get_random(self, **kwargs):
        return self.random_card

    async def get_random_from_query(self, query: str, *, lang: str = "en"):
        return self.random_card


@pytest.mark.asyncio
async def test_card_direct_number_returns_public_card() -> None:
    service = CommandService(FakeClient())

    outcome = await service.card("OP01-001")

    assert outcome.kind is CommandOutcomeKind.PUBLIC_CARD
    assert outcome.card is not None


@pytest.mark.asyncio
async def test_card_ambiguous_returns_picker() -> None:
    service = CommandService(FakeClient())

    outcome = await service.card("luffy")

    assert outcome.kind is CommandOutcomeKind.PICKER
    assert len(outcome.choices) == 2


@pytest.mark.asyncio
async def test_search_always_returns_picker() -> None:
    service = CommandService(FakeClient())

    outcome = await service.search("luffy")

    assert outcome.kind is CommandOutcomeKind.PICKER
    assert outcome.message == "Search results"


@pytest.mark.asyncio
async def test_random_empty_query_uses_random_endpoint() -> None:
    service = CommandService(FakeClient())

    outcome = await service.random("")

    assert outcome.kind is CommandOutcomeKind.PUBLIC_CARD
    assert outcome.card is not None


@pytest.mark.asyncio
async def test_faq_uses_official_faq_only() -> None:
    service = CommandService(FakeClient())

    outcome = await service.faq("OP01-001")

    assert outcome.kind is CommandOutcomeKind.PUBLIC_FAQ
    assert outcome.card is not None
    assert outcome.faq_entries


def test_help_is_ephemeral_message() -> None:
    outcome = CommandService(FakeClient()).help()

    assert outcome.kind is CommandOutcomeKind.EPHEMERAL_MESSAGE
    assert "/card" in outcome.message
    assert "https://poneglyph.one/syntax" in outcome.message
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest tests/test_commands.py -v
```

Expected: FAIL because `optcg_card_bot.commands` does not exist.

- [ ] **Step 3: Add command service**

Create `src/optcg_card_bot/commands.py`:

```python
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol

from optcg_card_bot.models import CardDetail, FAQEntry, SearchResponse
from optcg_card_bot.search import CardChoice, ResolutionKind, resolve_card_query


class CommandClient(Protocol):
    async def get_card(self, card_number: str, *, lang: str = "en") -> CardDetail: ...

    async def search_cards(
        self,
        query: str | None,
        *,
        page: int = 1,
        limit: int = 60,
        sort: str | None = None,
        order: str | None = None,
        collapse: str = "card",
        lang: str = "en",
    ) -> SearchResponse: ...

    async def get_random(self, **kwargs: str) -> CardDetail: ...

    async def get_random_from_query(self, query: str, *, lang: str = "en") -> CardDetail: ...


class CommandOutcomeKind(str, Enum):
    PUBLIC_CARD = "public_card"
    PUBLIC_FAQ = "public_faq"
    PICKER = "picker"
    EPHEMERAL_MESSAGE = "ephemeral_message"


@dataclass(frozen=True)
class CommandOutcome:
    kind: CommandOutcomeKind
    message: str = ""
    card: CardDetail | None = None
    choices: tuple[CardChoice, ...] = field(default_factory=tuple)
    faq_entries: tuple[FAQEntry, ...] = field(default_factory=tuple)
    source_query: str = ""


SIMPLE_RANDOM_FILTER_RE = re.compile(r"^(lang|set|color|type|rarity):([^()\s]+)$")


class CommandService:
    def __init__(self, client: CommandClient, *, default_language: str = "en") -> None:
        self._client = client
        self._default_language = default_language

    async def card(self, query: str) -> CommandOutcome:
        resolution = await resolve_card_query(
            self._client,
            query,
            lang=self._default_language,
        )
        if resolution.kind in {ResolutionKind.DIRECT, ResolutionKind.SINGLE}:
            return CommandOutcome(
                kind=CommandOutcomeKind.PUBLIC_CARD,
                card=resolution.card,
                source_query=query,
            )
        if resolution.kind is ResolutionKind.MULTIPLE:
            return CommandOutcome(
                kind=CommandOutcomeKind.PICKER,
                message="Select a card to post",
                choices=resolution.choices,
                source_query=query,
            )
        return CommandOutcome(
            kind=CommandOutcomeKind.EPHEMERAL_MESSAGE,
            message="No matching cards were found.",
            source_query=query,
        )

    async def search(self, query: str, *, page: int = 1) -> CommandOutcome:
        response = await self._client.search_cards(
            query,
            page=page,
            limit=10,
            collapse="card",
            lang=self._default_language,
        )
        if not response.data:
            return CommandOutcome(
                kind=CommandOutcomeKind.EPHEMERAL_MESSAGE,
                message="No matching cards were found.",
                source_query=query,
            )
        return CommandOutcome(
            kind=CommandOutcomeKind.PICKER,
            message="Search results",
            choices=tuple(CardChoice.from_summary(card) for card in response.data),
            source_query=query,
        )

    async def random(self, query: str) -> CommandOutcome:
        stripped = query.strip()
        if not stripped:
            card = await self._client.get_random(lang=self._default_language)
        else:
            filters = self._parse_simple_random_filters(stripped)
            if filters is None:
                card = await self._client.get_random_from_query(
                    stripped,
                    lang=self._default_language,
                )
            else:
                card = await self._client.get_random(
                    lang=self._default_language,
                    **filters,
                )
        return CommandOutcome(
            kind=CommandOutcomeKind.PUBLIC_CARD,
            card=card,
            source_query=query,
        )

    async def faq(self, query: str) -> CommandOutcome:
        card_outcome = await self.card(query)
        if card_outcome.kind is CommandOutcomeKind.PICKER:
            return CommandOutcome(
                kind=CommandOutcomeKind.PICKER,
                message="Select a card for official FAQ",
                choices=card_outcome.choices,
                source_query=query,
            )
        if card_outcome.card is None:
            return card_outcome
        entries = tuple(card_outcome.card.official_faq)
        if not entries:
            return CommandOutcome(
                kind=CommandOutcomeKind.EPHEMERAL_MESSAGE,
                message=f"No official FAQ is available for {card_outcome.card.card_number}.",
                source_query=query,
            )
        return CommandOutcome(
            kind=CommandOutcomeKind.PUBLIC_FAQ,
            card=card_outcome.card,
            faq_entries=entries,
            source_query=query,
        )

    def help(self) -> CommandOutcome:
        return CommandOutcome(
            kind=CommandOutcomeKind.EPHEMERAL_MESSAGE,
            message=(
                "Commands:\n"
                "`/card query:<query>` posts an unambiguous card or opens a picker.\n"
                "`/search query:<query>` opens private search results.\n"
                "`/random query:<optional query>` posts a random card.\n"
                "`/faq card:<card>` posts official FAQ entries only.\n"
                "Poneglyph syntax: https://poneglyph.one/syntax"
            ),
        )

    def _parse_simple_random_filters(self, query: str) -> dict[str, str] | None:
        filters: dict[str, str] = {}
        for token in query.split():
            match = SIMPLE_RANDOM_FILTER_RE.match(token)
            if match is None:
                return None
            key, value = match.groups()
            filters[key] = value
        return filters
```

- [ ] **Step 4: Run command tests**

Run:

```bash
uv run pytest tests/test_commands.py -v
uv run ruff check src/optcg_card_bot/commands.py tests/test_commands.py
uv run pyright
```

Expected: all commands exit 0.

- [ ] **Step 5: Commit command service**

```bash
git add src/optcg_card_bot/commands.py tests/test_commands.py
git commit -m "feat: add slash command outcomes"
```

---

### Task 7: Discord Embed Builders

**Files:**
- Create: `src/optcg_card_bot/embeds.py`
- Create: `tests/test_embeds.py`

- [ ] **Step 1: Write failing embed tests**

Create `tests/test_embeds.py`:

```python
import json
from pathlib import Path

from optcg_card_bot.embeds import build_card_embed, build_faq_embed
from optcg_card_bot.models import CardDetailResponse


FIXTURES = Path(__file__).parent / "fixtures" / "poneglyph"


def load_card():
    return CardDetailResponse.model_validate(
        json.loads((FIXTURES / "card_op01_001.json").read_text())
    ).data


def test_card_embed_contains_identity_and_powered_by() -> None:
    embed = build_card_embed(load_card())

    assert embed.title == "Roronoa Zoro"
    assert embed.url == "https://poneglyph.one/cards/OP01-001?lang=en"
    assert embed.footer.text is not None
    assert "Powered by Poneglyph" in embed.footer.text


def test_card_embed_uses_image_fallback() -> None:
    embed = build_card_embed(load_card())

    assert embed.image.url == "https://cdn.poneglyph.one/images/OP01-001/en/stock/0/full.png"


def test_faq_embed_uses_official_faq_entries() -> None:
    card = load_card()

    embed = build_faq_embed(card, tuple(card.official_faq))

    assert embed.title == "Official FAQ: Roronoa Zoro"
    assert len(embed.fields) == len(card.official_faq)
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest tests/test_embeds.py -v
```

Expected: FAIL because `optcg_card_bot.embeds` does not exist.

- [ ] **Step 3: Add embed builders**

Create `src/optcg_card_bot/embeds.py`:

```python
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
    footer_parts = []
    if variant and variant.product.name:
        footer_parts.append(variant.product.name)
    if variant and variant.label:
        footer_parts.append(variant.label)
    if variant and variant.artist:
        footer_parts.append(f"Artist: {variant.artist}")
    footer_parts.append("Powered by Poneglyph")
    embed.set_footer(text=" • ".join(footer_parts))
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
    lines = [" • ".join(stat_parts)]
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
    return f"{value[: limit - 1]}…"
```

- [ ] **Step 4: Run embed tests**

Run:

```bash
uv run pytest tests/test_embeds.py -v
uv run ruff check src/optcg_card_bot/embeds.py tests/test_embeds.py
uv run pyright
```

Expected: all commands exit 0.

- [ ] **Step 5: Commit embeds**

```bash
git add src/optcg_card_bot/embeds.py tests/test_embeds.py
git commit -m "feat: add discord embed builders"
```

---

### Task 8: Discord Bot Wiring And Interaction Views

**Files:**
- Create: `src/optcg_card_bot/interactions.py`
- Create: `src/optcg_card_bot/bot.py`
- Modify: `src/optcg_card_bot/__main__.py`
- Create: `tests/test_interactions.py`

- [ ] **Step 1: Write failing interaction tests**

Create `tests/test_interactions.py`:

```python
from optcg_card_bot.interactions import (
    CardSelectView,
    build_choice_options,
    create_bot,
)
from optcg_card_bot.search import CardChoice


def test_choice_options_include_card_number_and_name() -> None:
    choices = (
        CardChoice(
            card_number="OP01-001",
            name="Roronoa Zoro",
            set_code="OP01",
            card_type="Leader",
            color=("Red",),
        ),
    )

    options = build_choice_options(choices)

    assert options[0].label == "Roronoa Zoro"
    assert options[0].value == "OP01-001"
    assert options[0].description == "OP01 • Leader • Red"


def test_select_view_tracks_owner_and_query() -> None:
    view = CardSelectView(
        owner_id=123,
        source_query="luffy",
        action="card",
        choices=(
            CardChoice(
                card_number="OP01-001",
                name="Roronoa Zoro",
                set_code="OP01",
                card_type="Leader",
                color=("Red",),
            ),
        ),
    )

    assert view.owner_id == 123
    assert view.source_query == "luffy"
    assert view.action == "card"
    assert view.timeout == 180


def test_create_bot_registers_expected_commands() -> None:
    bot = create_bot(command_service=None)

    names = {command.name for command in bot.tree.get_commands()}

    assert {"card", "search", "random", "faq", "help"} <= names
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest tests/test_interactions.py -v
```

Expected: FAIL because `optcg_card_bot.interactions` does not exist.

- [ ] **Step 3: Add Discord interaction module**

Create `src/optcg_card_bot/interactions.py`:

```python
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from optcg_card_bot.commands import CommandOutcome, CommandOutcomeKind, CommandService
from optcg_card_bot.embeds import build_card_embed, build_faq_embed
from optcg_card_bot.search import CardChoice


def build_choice_options(choices: tuple[CardChoice, ...]) -> list[discord.SelectOption]:
    return [
        discord.SelectOption(
            label=choice.name[:100],
            value=choice.card_number,
            description=_choice_description(choice),
        )
        for choice in choices[:25]
    ]


class CardSelect(discord.ui.Select[discord.ui.View]):
    def __init__(self, choices: tuple[CardChoice, ...]) -> None:
        super().__init__(
            placeholder="Select a card to post",
            min_values=1,
            max_values=1,
            options=build_choice_options(choices),
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.view
        if not isinstance(view, CardSelectView):
            await interaction.response.send_message(
                "This picker is not available.",
                ephemeral=True,
            )
            return
        if interaction.user.id != view.owner_id:
            await interaction.response.send_message(
                "Only the command user can use this picker.",
                ephemeral=True,
            )
            return
        await interaction.response.defer(ephemeral=False)
        card_number = self.values[0]
        if view.service is None:
            await interaction.followup.send("This picker has expired.", ephemeral=True)
            return
        if view.action == "faq":
            outcome = await view.service.faq(card_number)
        else:
            outcome = await view.service.card(card_number)
        await send_outcome(interaction, outcome)


class CardSelectView(discord.ui.View):
    def __init__(
        self,
        *,
        owner_id: int,
        source_query: str,
        action: str,
        choices: tuple[CardChoice, ...],
        service: CommandService | None = None,
    ) -> None:
        super().__init__(timeout=180)
        self.owner_id = owner_id
        self.source_query = source_query
        self.action = action
        self.service = service
        self.add_item(CardSelect(choices))


async def send_outcome(
    interaction: discord.Interaction,
    outcome: CommandOutcome,
) -> None:
    if outcome.kind is CommandOutcomeKind.PUBLIC_CARD and outcome.card is not None:
        await interaction.followup.send(
            embed=build_card_embed(outcome.card),
            ephemeral=False,
        )
        return
    if outcome.kind is CommandOutcomeKind.PUBLIC_FAQ and outcome.card is not None:
        await interaction.followup.send(
            embed=build_faq_embed(outcome.card, outcome.faq_entries),
            ephemeral=False,
        )
        return
    if outcome.kind is CommandOutcomeKind.EPHEMERAL_MESSAGE:
        await interaction.followup.send(outcome.message, ephemeral=True)
        return
    await interaction.followup.send("No response was produced.", ephemeral=True)


def create_bot(command_service: CommandService | None) -> commands.Bot:
    intents = discord.Intents.default()
    bot = commands.Bot(command_prefix=commands.when_mentioned, intents=intents)

    @bot.tree.command(name="card", description="Search and post a Poneglyph card")
    @app_commands.describe(query="Poneglyph query or card number")
    async def card(interaction: discord.Interaction, query: str) -> None:
        service = _require_service(command_service)
        await interaction.response.defer(ephemeral=True)
        outcome = await service.card(query)
        if outcome.kind is CommandOutcomeKind.PICKER:
            await interaction.followup.send(
                outcome.message,
                view=CardSelectView(
                    owner_id=interaction.user.id,
                    source_query=query,
                    action="card",
                    choices=outcome.choices,
                    service=service,
                ),
                ephemeral=True,
            )
            return
        await send_outcome(interaction, outcome)

    @bot.tree.command(name="search", description="Browse Poneglyph search results")
    @app_commands.describe(query="Poneglyph query")
    async def search(interaction: discord.Interaction, query: str) -> None:
        service = _require_service(command_service)
        await interaction.response.defer(ephemeral=True)
        outcome = await service.search(query)
        if outcome.kind is CommandOutcomeKind.PICKER:
            await interaction.followup.send(
                outcome.message,
                view=CardSelectView(
                    owner_id=interaction.user.id,
                    source_query=query,
                    action="card",
                    choices=outcome.choices,
                    service=service,
                ),
                ephemeral=True,
            )
            return
        await send_outcome(interaction, outcome)

    @bot.tree.command(name="random", description="Post a random Poneglyph card")
    @app_commands.describe(query="Optional Poneglyph query or simple random filters")
    async def random_card(interaction: discord.Interaction, query: str = "") -> None:
        service = _require_service(command_service)
        await interaction.response.defer(ephemeral=False)
        outcome = await service.random(query)
        await send_outcome(interaction, outcome)

    @bot.tree.command(name="faq", description="Post official FAQ for a card")
    @app_commands.describe(card="Card number or Poneglyph query")
    async def faq(interaction: discord.Interaction, card: str) -> None:
        service = _require_service(command_service)
        await interaction.response.defer(ephemeral=True)
        outcome = await service.faq(card)
        if outcome.kind is CommandOutcomeKind.PICKER:
            await interaction.followup.send(
                outcome.message,
                view=CardSelectView(
                    owner_id=interaction.user.id,
                    source_query=card,
                    action="faq",
                    choices=outcome.choices,
                    service=service,
                ),
                ephemeral=True,
            )
            return
        await send_outcome(interaction, outcome)

    @bot.tree.command(name="help", description="Show bot help")
    async def help_command(interaction: discord.Interaction) -> None:
        service = _require_service(command_service)
        await interaction.response.send_message(service.help().message, ephemeral=True)

    return bot


def _choice_description(choice: CardChoice) -> str:
    parts = [choice.set_code, choice.card_type]
    if choice.color:
        parts.append("/".join(choice.color))
    return " • ".join(parts)[:100]


def _require_service(service: CommandService | None) -> CommandService:
    if service is None:
        raise RuntimeError("CommandService is required for runtime command handling")
    return service
```

Create `src/optcg_card_bot/bot.py`:

```python
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
```

Modify `src/optcg_card_bot/__main__.py`:

```python
import asyncio

from optcg_card_bot.bot import run_bot
from optcg_card_bot.config import Settings
from optcg_card_bot.logging import configure_logging


def main() -> None:
    configure_logging()
    asyncio.run(run_bot(Settings()))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run interaction tests**

Run:

```bash
uv run pytest tests/test_interactions.py -v
uv run ruff check src/optcg_card_bot/interactions.py src/optcg_card_bot/bot.py tests/test_interactions.py
uv run pyright
```

Expected: all commands exit 0.

- [ ] **Step 5: Commit Discord wiring**

```bash
git add src/optcg_card_bot/interactions.py src/optcg_card_bot/bot.py src/optcg_card_bot/__main__.py tests/test_interactions.py
git commit -m "feat: wire discord slash commands"
```

---

### Task 9: Live Contract Tests And CI

**Files:**
- Create: `tests/live/test_live_poneglyph_contract.py`
- Create: `.github/workflows/ci.yml`
- Modify: `README.md`

- [ ] **Step 1: Write live smoke tests**

Create `tests/live/test_live_poneglyph_contract.py`:

```python
import httpx
import pytest


BASE_URL = "https://api.poneglyph.one"


@pytest.mark.live
def test_live_openapi_has_mvp_endpoints() -> None:
    response = httpx.get(f"{BASE_URL}/openapi.json", timeout=20.0)
    response.raise_for_status()
    contract = response.json()

    paths = contract["paths"]
    assert "/v1/search" in paths
    assert "/v1/cards/{card_number}" in paths
    assert "/v1/random" in paths


@pytest.mark.live
def test_live_direct_card_lookup_op01_001() -> None:
    response = httpx.get(f"{BASE_URL}/v1/cards/OP01-001", timeout=20.0)
    response.raise_for_status()
    payload = response.json()

    assert payload["data"]["card_number"] == "OP01-001"


@pytest.mark.live
def test_live_bare_card_number_search() -> None:
    response = httpx.get(
        f"{BASE_URL}/v1/search",
        params={"q": "OP01-001", "limit": "5", "collapse": "card"},
        timeout=20.0,
    )
    response.raise_for_status()
    payload = response.json()

    assert any(card["card_number"] == "OP01-001" for card in payload["data"])


@pytest.mark.live
def test_live_broad_luffy_search_returns_cards() -> None:
    response = httpx.get(
        f"{BASE_URL}/v1/search",
        params={"q": "luffy", "limit": "2", "collapse": "card"},
        timeout=20.0,
    )
    response.raise_for_status()
    payload = response.json()

    assert payload["data"]
```

- [ ] **Step 2: Run live tests explicitly**

Run:

```bash
uv run pytest tests/live -v
```

Expected: all tests pass when network access to Poneglyph is available.

- [ ] **Step 3: Add CI workflow**

Create `.github/workflows/ci.yml`:

```yaml
name: CI

on:
  push:
    branches: ["**"]
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - name: Set up Python
        run: uv python install 3.12
      - name: Install dependencies
        run: uv sync --extra dev
      - name: Ruff
        run: uv run ruff check .
      - name: Ruff format
        run: uv run ruff format --check .
      - name: Pyright
        run: uv run pyright
      - name: Unit tests
        run: uv run pytest tests --ignore=tests/live
      - name: Live contract smoke tests
        run: uv run pytest tests/live -v
```

- [ ] **Step 4: Document live test behavior**

Update `README.md` by adding this section:

```markdown
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
```

- [ ] **Step 5: Run full local verification**

Run:

```bash
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run pytest tests --ignore=tests/live
uv run pytest tests/live -v
```

Expected: all commands exit 0.

- [ ] **Step 6: Commit CI and live tests**

```bash
git add .github/workflows/ci.yml README.md tests/live/test_live_poneglyph_contract.py
git commit -m "ci: add bot verification gates"
```

---

### Task 10: Phase 2 Bracket Message Detection

**Files:**
- Modify: `src/optcg_card_bot/interactions.py`
- Modify: `tests/test_interactions.py`
- Modify: `README.md`

- [ ] **Step 1: Add failing tests for bracket feature flag behavior**

Append to `tests/test_interactions.py`:

```python
def test_create_bot_can_enable_bracket_listener() -> None:
    bot = create_bot(command_service=None, enable_bracket_messages=True)

    assert "on_message" in bot.extra_events
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest tests/test_interactions.py::test_create_bot_can_enable_bracket_listener -v
```

Expected: FAIL because `create_bot` does not accept `enable_bracket_messages`.

- [ ] **Step 3: Add optional message listener**

Modify the signature in `src/optcg_card_bot/interactions.py`:

```python
def create_bot(
    command_service: CommandService | None,
    *,
    enable_bracket_messages: bool = False,
) -> commands.Bot:
```

Add this import:

```python
from optcg_card_bot.search import CardChoice, extract_bracket_queries
```

Add this block before `return bot`:

```python
    if enable_bracket_messages:

        @bot.listen("on_message")
        async def on_message(message: discord.Message) -> None:
            if message.author.bot:
                return
            service = _require_service(command_service)
            for query in extract_bracket_queries(message.content):
                outcome = await service.card(query)
                if outcome.kind is CommandOutcomeKind.PUBLIC_CARD and outcome.card:
                    await message.channel.send(embed=build_card_embed(outcome.card))
                elif outcome.kind is CommandOutcomeKind.PICKER:
                    await message.channel.send(
                        f"`[[{query}]]` matched multiple cards. Use `/card` to choose."
                    )
                elif outcome.message:
                    await message.channel.send(outcome.message)
```

Modify `src/optcg_card_bot/bot.py` so `create_bot` receives the setting:

```python
    bot = create_bot(
        service,
        enable_bracket_messages=settings.enable_bracket_messages,
    )
```

- [ ] **Step 4: Update README command list**

Add this paragraph to `README.md`:

```markdown
## Phase 2 Message Lookup

Set `OPTCG_ENABLE_BRACKET_MESSAGES=true` to enable `[[card-name]]` message
detection. Bracket lookups use the same resolver as `/card`: direct and
single-result matches post publicly, while ambiguous matches tell the user to
use `/card` for selection.
```

- [ ] **Step 5: Run bracket tests and full verification**

Run:

```bash
uv run pytest tests/test_search.py tests/test_interactions.py -v
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run pytest tests --ignore=tests/live
```

Expected: all commands exit 0.

- [ ] **Step 6: Commit bracket message support**

```bash
git add README.md src/optcg_card_bot/bot.py src/optcg_card_bot/interactions.py tests/test_interactions.py
git commit -m "feat: add bracket message lookup"
```

---

## Final Verification

Run:

```bash
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run pytest tests --ignore=tests/live
uv run pytest tests/live -v
```

Expected: all commands exit 0. If live tests fail because Poneglyph or network
access is unavailable, record the failing command and rerun before merge.

Check git state:

```bash
git status --short
git log --oneline --decorate -10
```

Expected: only intentional changes are present, and each task has its own commit.

## Spec Coverage Checklist

- Slash-first `/card`, `/search`, `/random`, `/faq`, `/help`: Tasks 6 and 8.
- Direct card-number and single-result public posting: Tasks 5 and 6.
- Ambiguous ephemeral picker: Tasks 6 and 8.
- `/search` private-first browse behavior: Task 6.
- `/random` public posting and search sampling: Tasks 4 and 6.
- `/faq` official FAQ only: Tasks 6 and 7.
- Poneglyph query preservation: Tasks 4, 5, and 6.
- Embed image and price fallback: Tasks 3 and 7.
- Vendored contracts and live smoke tests: Tasks 2 and 9.
- Phase 2 `[[card-name]]`: Tasks 5 and 10.
