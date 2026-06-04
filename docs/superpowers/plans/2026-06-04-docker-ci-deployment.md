# Docker CI Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build, validate, scan, document, and publish a production Docker image for the Poneglyph Discord bot.

**Architecture:** Keep runtime configuration in `Settings`, adding explicit `DISCORD_TOKEN_FILE` support for Docker secrets. Add a production Dockerfile and Compose example, then extend CI so pull requests build and scan the image while pushes to `main` publish to Docker Hub. Keep publishing in a separate workflow from PR validation.

**Tech Stack:** Python 3.12, `uv`, Docker Buildx, Docker Hub, GitHub Actions, Trivy, pip-audit, pytest, Ruff, Pyright.

---

## File Structure

Create or modify these files:

```text
Dockerfile
.dockerignore
compose.yaml
docs/deployment/docker.md
.env.example
README.md
.github/workflows/ci.yml
.github/workflows/publish-image.yml
src/optcg_card_bot/config.py
tests/test_config.py
tests/test_container_files.py
tests/test_deployment_docs.py
tests/test_workflows.py
```

Responsibilities:

- `Dockerfile`: production container image definition.
- `.dockerignore`: excludes local, secret, cache, test, and Git metadata from Docker build context.
- `compose.yaml`: self-hosted Compose example using Docker secrets.
- `docs/deployment/docker.md`: Docker run, Compose, Docker Hub tags, and GitHub secret documentation.
- `.env.example`: documents `DISCORD_TOKEN_FILE`.
- `README.md`: links to Docker deployment documentation.
- `.github/workflows/ci.yml`: PR and branch validation, including image build and security scans.
- `.github/workflows/publish-image.yml`: publish image to Docker Hub on push to `main`.
- `config.py`: explicit Discord token file support.
- `tests/test_config.py`: settings behavior tests.
- `tests/test_container_files.py`: repository-level Dockerfile and `.dockerignore` guardrails.
- `tests/test_deployment_docs.py`: deployment docs and Compose guardrails.
- `tests/test_workflows.py`: workflow guardrails for scan and publish behavior.

---

### Task 1: Add Discord Token File Settings Support

**Files:**
- Modify: `src/optcg_card_bot/config.py`
- Modify: `tests/test_config.py`

- [ ] **Step 1: Add failing tests for Discord token files**

Append these tests to `tests/test_config.py`:

```python
import pytest
from pydantic import ValidationError


def test_settings_loads_discord_token_file(tmp_path) -> None:
    token_file = tmp_path / "discord_token"
    token_file.write_text("from-file\n")

    settings = Settings(discord_token_file=token_file)

    assert settings.discord_token == "from-file"


def test_settings_token_file_takes_precedence(tmp_path) -> None:
    token_file = tmp_path / "discord_token"
    token_file.write_text("from-file\n")

    settings = Settings(discord_token="from-env", discord_token_file=token_file)

    assert settings.discord_token == "from-file"


def test_settings_rejects_missing_token_file(tmp_path) -> None:
    missing_file = tmp_path / "missing"

    with pytest.raises(ValidationError, match="DISCORD_TOKEN_FILE could not be read"):
        Settings(discord_token_file=missing_file)


def test_settings_rejects_empty_token_file(tmp_path) -> None:
    token_file = tmp_path / "discord_token"
    token_file.write_text("\n")

    with pytest.raises(ValidationError, match="DISCORD_TOKEN_FILE is empty"):
        Settings(discord_token_file=token_file)
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
nix develop --command uv run pytest tests/test_config.py -v
```

Expected: FAIL because `Settings` does not accept or load `discord_token_file`.

- [ ] **Step 3: Implement token file loading**

Update `src/optcg_card_bot/config.py` to include these imports:

```python
from pathlib import Path
from typing import Self

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
```

Update the `Settings` fields so `discord_token` has an empty default and add `discord_token_file`:

```python
    discord_token: str = Field(default="", alias="DISCORD_TOKEN")
    discord_token_file: Path | None = Field(
        default=None,
        alias="DISCORD_TOKEN_FILE",
        exclude=True,
    )
```

Add this validator inside `Settings`:

```python
    @model_validator(mode="after")
    def load_discord_token_file(self) -> Self:
        if self.discord_token_file is not None:
            try:
                token = self.discord_token_file.read_text(encoding="utf-8").strip()
            except OSError as exc:
                raise ValueError(
                    f"DISCORD_TOKEN_FILE could not be read: {self.discord_token_file}"
                ) from exc
            if not token:
                raise ValueError("DISCORD_TOKEN_FILE is empty")
            self.discord_token = token

        if not self.discord_token.strip():
            raise ValueError("DISCORD_TOKEN is required")
        self.discord_token = self.discord_token.strip()
        return self
```

- [ ] **Step 4: Run config tests**

Run:

```bash
nix develop --command uv run pytest tests/test_config.py -v
```

Expected: PASS.

- [ ] **Step 5: Run type and lint checks for the config change**

Run:

```bash
nix develop --command uv run ruff check src/optcg_card_bot/config.py tests/test_config.py
nix develop --command uv run pyright
```

Expected: both commands exit 0.

- [ ] **Step 6: Commit token file support**

Run:

```bash
git add src/optcg_card_bot/config.py tests/test_config.py
git commit -m "feat: support docker token secrets"
```

---

### Task 2: Add Production Docker Image

**Files:**
- Create: `Dockerfile`
- Create: `.dockerignore`
- Create: `tests/test_container_files.py`

- [ ] **Step 1: Add failing container file guardrail tests**

Create `tests/test_container_files.py`:

```python
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_dockerfile_runs_as_non_root_user() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text()

    assert "USER bot" in dockerfile
    assert 'CMD ["optcg-card-bot"]' in dockerfile


def test_dockerignore_excludes_secrets_and_local_artifacts() -> None:
    dockerignore = (ROOT / ".dockerignore").read_text().splitlines()

    expected_entries = {
        ".env",
        ".git",
        ".venv",
        "__pycache__",
        ".pytest_cache",
        ".ruff_cache",
        "tests",
        "docs",
        "contracts",
    }

    assert expected_entries <= set(dockerignore)
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
nix develop --command uv run pytest tests/test_container_files.py -v
```

Expected: FAIL because `Dockerfile` and `.dockerignore` do not exist.

- [ ] **Step 3: Add Dockerfile**

Create `Dockerfile`:

```dockerfile
# syntax=docker/dockerfile:1.7

FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.5.31 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
COPY src ./src

RUN uv sync --frozen --no-dev --no-editable

FROM python:3.12-slim AS runtime

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN groupadd --system bot \
    && useradd --system --gid bot --home-dir /app --shell /usr/sbin/nologin bot

WORKDIR /app

COPY --from=builder --chown=bot:bot /app/.venv /app/.venv

USER bot

CMD ["optcg-card-bot"]
```

- [ ] **Step 4: Add Docker ignore file**

Create `.dockerignore`:

```dockerignore
.env
.git
.github
.mypy_cache
.nix
.pytest_cache
.ruff_cache
.venv
__pycache__
*.py[cod]
*.egg-info
build
contracts
dist
docs
htmlcov
result
result-*
secrets
tests
```

- [ ] **Step 5: Run container file tests**

Run:

```bash
nix develop --command uv run pytest tests/test_container_files.py -v
```

Expected: PASS.

- [ ] **Step 6: Build the image locally**

Run:

```bash
docker build -t poneglyph-discord-bot:local .
```

Expected: build exits 0 and creates `poneglyph-discord-bot:local`.

- [ ] **Step 7: Verify the image entrypoint exists**

Run:

```bash
docker run --rm --entrypoint python poneglyph-discord-bot:local -c "import shutil; assert shutil.which('optcg-card-bot')"
```

Expected: command exits 0, proving the installed console entrypoint is on `PATH`.

- [ ] **Step 8: Commit Docker image files**

Run:

```bash
git add Dockerfile .dockerignore tests/test_container_files.py
git commit -m "build: add production docker image"
```

---

### Task 3: Add Docker Usage Documentation

**Files:**
- Create: `compose.yaml`
- Create: `docs/deployment/docker.md`
- Create: `tests/test_deployment_docs.py`
- Modify: `.env.example`
- Modify: `README.md`

- [ ] **Step 1: Add failing deployment documentation tests**

Create `tests/test_deployment_docs.py`:

```python
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_compose_uses_discord_token_file_secret() -> None:
    compose = (ROOT / "compose.yaml").read_text()

    assert "DISCORD_TOKEN_FILE: /run/secrets/discord_token" in compose
    assert "secrets:" in compose
    assert "file: ./secrets/discord_token.txt" in compose
    assert "restart: unless-stopped" in compose


def test_docker_docs_cover_runtime_and_publish_secrets() -> None:
    docs = (ROOT / "docs" / "deployment" / "docker.md").read_text()

    assert "DISCORD_TOKEN_FILE" in docs
    assert "DOCKERHUB_USERNAME" in docs
    assert "DOCKERHUB_TOKEN" in docs
    assert "DOCKERHUB_REPOSITORY" in docs
    assert "sha-<shortsha>" in docs


def test_env_example_documents_token_file() -> None:
    env_example = (ROOT / ".env.example").read_text()

    assert "DISCORD_TOKEN_FILE=" in env_example
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
nix develop --command uv run pytest tests/test_deployment_docs.py -v
```

Expected: FAIL because the Compose file and deployment docs do not exist.

- [ ] **Step 3: Add Compose example**

Create `compose.yaml`:

```yaml
services:
  bot:
    image: poneglyph-discord-bot:local
    environment:
      DISCORD_TOKEN_FILE: /run/secrets/discord_token
      PONEGLYPH_BASE_URL: https://api.poneglyph.one
      PONEGLYPH_API_PREFIX: /v1
      OPTCG_DEFAULT_LANGUAGE: en
      OPTCG_REQUEST_TIMEOUT_SECONDS: "10"
      OPTCG_REQUEST_MIN_INTERVAL_SECONDS: "0.25"
      OPTCG_ENABLE_BRACKET_MESSAGES: "false"
    secrets:
      - discord_token
    restart: unless-stopped

secrets:
  discord_token:
    file: ./secrets/discord_token.txt
```

- [ ] **Step 4: Add Docker deployment docs**

Create `docs/deployment/docker.md`:

```markdown
# Docker Deployment

The bot can run as a self-hosted Docker container. The image expects runtime
configuration through environment variables.

## Build Locally

```bash
docker build -t poneglyph-discord-bot:local .
```

## Run With Environment Variables

```bash
docker run --rm \
  --env DISCORD_TOKEN="$DISCORD_TOKEN" \
  poneglyph-discord-bot:local
```

## Run With Docker Compose Secrets

Create a local secret file that is not committed:

```bash
mkdir -p secrets
printf '%s\n' "$DISCORD_TOKEN" > secrets/discord_token.txt
```

Start the bot:

```bash
docker compose up -d
```

The Compose example mounts the secret at `/run/secrets/discord_token` and sets
`DISCORD_TOKEN_FILE` to that path. If `DISCORD_TOKEN_FILE` is set, it takes
precedence over `DISCORD_TOKEN`.

## Docker Hub Publishing

The publish workflow pushes images only after code lands on `main`.

Required GitHub Actions secrets:

```text
DOCKERHUB_USERNAME
DOCKERHUB_TOKEN
DOCKERHUB_REPOSITORY
```

`DOCKERHUB_REPOSITORY` should be the Docker Hub repository in `owner/name`
format, such as `my-dockerhub-user/poneglyph-discord-bot`.

Published tags:

- `latest`
- `main`
- `sha-<shortsha>`

Use `sha-<shortsha>` for rollbacks because it is immutable for a specific
commit. Use `latest` or `main` only when you want the newest published image.

## Runtime Settings

```text
DISCORD_TOKEN=
DISCORD_TOKEN_FILE=
PONEGLYPH_BASE_URL=https://api.poneglyph.one
PONEGLYPH_API_PREFIX=/v1
OPTCG_DEFAULT_LANGUAGE=en
OPTCG_REQUEST_TIMEOUT_SECONDS=10
OPTCG_REQUEST_MIN_INTERVAL_SECONDS=0.25
OPTCG_ENABLE_BRACKET_MESSAGES=false
```
```

- [ ] **Step 5: Update `.env.example`**

Add `DISCORD_TOKEN_FILE=` after `DISCORD_TOKEN=`:

```text
DISCORD_TOKEN=
DISCORD_TOKEN_FILE=
PONEGLYPH_BASE_URL=https://api.poneglyph.one
PONEGLYPH_API_PREFIX=/v1
OPTCG_DEFAULT_LANGUAGE=en
OPTCG_REQUEST_TIMEOUT_SECONDS=10
OPTCG_REQUEST_MIN_INTERVAL_SECONDS=0.25
OPTCG_ENABLE_BRACKET_MESSAGES=false
```

- [ ] **Step 6: Link Docker docs from README**

Add this section to `README.md` after the MVP commands:

```markdown
## Docker

See [Docker Deployment](docs/deployment/docker.md) for local image builds,
Compose secrets, and Docker Hub publish behavior.
```

- [ ] **Step 7: Run deployment documentation tests**

Run:

```bash
nix develop --command uv run pytest tests/test_deployment_docs.py -v
```

Expected: PASS.

- [ ] **Step 8: Commit deployment docs**

Run:

```bash
git add compose.yaml docs/deployment/docker.md .env.example README.md tests/test_deployment_docs.py
git commit -m "docs: add docker deployment guide"
```

---

### Task 4: Add PR Container And Security Checks

**Files:**
- Modify: `.github/workflows/ci.yml`
- Create: `tests/test_workflows.py`

- [ ] **Step 1: Add failing workflow guardrail tests**

Create `tests/test_workflows.py`:

```python
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_ci_builds_and_scans_container_without_pushing() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text()

    assert "docker/build-push-action@v7" in workflow
    assert "push: false" in workflow
    assert "load: true" in workflow
    assert "aquasecurity/trivy-action@v0.36.0" in workflow
    assert "scan-type: fs" in workflow
    assert "scan-type: image" in workflow
    assert "severity: HIGH,CRITICAL" in workflow
    assert "uvx --from pip-audit pip-audit" in workflow


def test_ci_does_not_reference_dockerhub_publish_secrets() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text()

    assert "DOCKERHUB_TOKEN" not in workflow
    assert "DOCKERHUB_USERNAME" not in workflow
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
nix develop --command uv run pytest tests/test_workflows.py -v
```

Expected: FAIL because CI does not build or scan the Docker image yet.

- [ ] **Step 3: Replace CI workflow**

Replace `.github/workflows/ci.yml` with:

```yaml
name: CI

on:
  push:
    branches: ["**"]
  pull_request:

permissions:
  contents: read

jobs:
  python:
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

  container-security:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - name: Set up Python
        run: uv python install 3.12
      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v4
      - name: Build image
        uses: docker/build-push-action@v7
        with:
          context: .
          push: false
          load: true
          tags: poneglyph-discord-bot:ci
      - name: Trivy filesystem scan
        uses: aquasecurity/trivy-action@v0.36.0
        with:
          scan-type: fs
          scan-ref: .
          severity: HIGH,CRITICAL
          exit-code: "1"
      - name: Trivy image scan
        uses: aquasecurity/trivy-action@v0.36.0
        with:
          scan-type: image
          image-ref: poneglyph-discord-bot:ci
          severity: HIGH,CRITICAL
          exit-code: "1"
      - name: Python dependency audit
        run: |
          uv export --frozen --no-dev --no-hashes --format requirements-txt --output-file requirements-audit.txt
          uvx --from pip-audit pip-audit -r requirements-audit.txt --strict
```

- [ ] **Step 4: Run workflow guardrail tests**

Run:

```bash
nix develop --command uv run pytest tests/test_workflows.py -v
```

Expected: PASS.

- [ ] **Step 5: Run local Python verification**

Run:

```bash
nix develop --command uv run ruff check .
nix develop --command uv run ruff format --check .
nix develop --command uv run pyright
nix develop --command uv run pytest tests --ignore=tests/live
```

Expected: all commands exit 0.

- [ ] **Step 6: Commit PR security checks**

Run:

```bash
git add .github/workflows/ci.yml tests/test_workflows.py
git commit -m "ci: add container security checks"
```

---

### Task 5: Add Docker Hub Publish Workflow

**Files:**
- Create: `.github/workflows/publish-image.yml`
- Modify: `tests/test_workflows.py`

- [ ] **Step 1: Add failing publish workflow tests**

Append these tests to `tests/test_workflows.py`:

```python
def test_publish_workflow_only_runs_on_main_push() -> None:
    workflow = (ROOT / ".github" / "workflows" / "publish-image.yml").read_text()

    assert "branches: [main]" in workflow
    assert "pull_request" not in workflow
    assert "docker/login-action@v4" in workflow
    assert "DOCKERHUB_USERNAME" in workflow
    assert "DOCKERHUB_TOKEN" in workflow
    assert "DOCKERHUB_REPOSITORY" in workflow


def test_publish_workflow_pushes_expected_tags_after_scan() -> None:
    workflow = (ROOT / ".github" / "workflows" / "publish-image.yml").read_text()

    assert "${{ secrets.DOCKERHUB_REPOSITORY }}:latest" in workflow
    assert "${{ secrets.DOCKERHUB_REPOSITORY }}:main" in workflow
    assert "${{ secrets.DOCKERHUB_REPOSITORY }}:sha-${{ steps.vars.outputs.short_sha }}" in workflow
    assert workflow.index("Trivy image scan") < workflow.index("Build and push image")
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
nix develop --command uv run pytest tests/test_workflows.py -v
```

Expected: FAIL because `publish-image.yml` does not exist.

- [ ] **Step 3: Add Docker Hub publish workflow**

Create `.github/workflows/publish-image.yml`:

```yaml
name: Publish Docker Image

on:
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  publish:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v4
      - name: Compute image metadata
        id: vars
        run: echo "short_sha=${GITHUB_SHA::12}" >> "$GITHUB_OUTPUT"
      - name: Build image for scan
        uses: docker/build-push-action@v7
        with:
          context: .
          push: false
          load: true
          tags: ${{ secrets.DOCKERHUB_REPOSITORY }}:scan
      - name: Trivy image scan
        uses: aquasecurity/trivy-action@v0.36.0
        with:
          scan-type: image
          image-ref: ${{ secrets.DOCKERHUB_REPOSITORY }}:scan
          severity: HIGH,CRITICAL
          exit-code: "1"
      - name: Login to Docker Hub
        uses: docker/login-action@v4
        with:
          username: ${{ secrets.DOCKERHUB_USERNAME }}
          password: ${{ secrets.DOCKERHUB_TOKEN }}
      - name: Build and push image
        uses: docker/build-push-action@v7
        with:
          context: .
          push: true
          tags: |
            ${{ secrets.DOCKERHUB_REPOSITORY }}:latest
            ${{ secrets.DOCKERHUB_REPOSITORY }}:main
            ${{ secrets.DOCKERHUB_REPOSITORY }}:sha-${{ steps.vars.outputs.short_sha }}
```

- [ ] **Step 4: Run publish workflow tests**

Run:

```bash
nix develop --command uv run pytest tests/test_workflows.py -v
```

Expected: PASS.

- [ ] **Step 5: Run full local verification**

Run:

```bash
nix develop --command uv run ruff check .
nix develop --command uv run ruff format --check .
nix develop --command uv run pyright
nix develop --command uv run pytest tests --ignore=tests/live
docker build -t poneglyph-discord-bot:local .
```

Expected: all commands exit 0.

- [ ] **Step 6: Commit publish workflow**

Run:

```bash
git add .github/workflows/publish-image.yml tests/test_workflows.py
git commit -m "ci: publish docker image on main"
```

---

### Task 6: Final Verification And Handoff

**Files:**
- No expected source changes.

- [ ] **Step 1: Run final Python checks**

Run:

```bash
nix develop --command uv run ruff check .
nix develop --command uv run ruff format --check .
nix develop --command uv run pyright
nix develop --command uv run pytest tests --ignore=tests/live
```

Expected: all commands exit 0.

- [ ] **Step 2: Run live smoke tests**

Run:

```bash
nix develop --command uv run pytest tests/live -v
```

Expected: PASS. If Poneglyph or network access is unavailable, record the exact failure and rerun before merge.

- [ ] **Step 3: Run local image build**

Run:

```bash
docker build -t poneglyph-discord-bot:local .
```

Expected: build exits 0.

- [ ] **Step 4: Run local Trivy scan when available**

Run:

```bash
trivy image --severity HIGH,CRITICAL --exit-code 1 poneglyph-discord-bot:local
```

Expected: exit 0. If `trivy` is not installed locally, note that GitHub Actions remains the authoritative Trivy gate.

- [ ] **Step 5: Inspect git state and commit history**

Run:

```bash
git status --short
git log --oneline --decorate -8
```

Expected: only intentional changes are present, and the deployment work is split into the task commits above.

---

## Spec Coverage Checklist

- Production Docker image: Task 2.
- Non-root runtime and runtime-only dependencies: Task 2.
- Docker build context exclusions: Task 2.
- Environment variable configuration: Task 3.
- `DISCORD_TOKEN_FILE` support: Task 1.
- Compose secret example: Task 3.
- PR Docker build: Task 4.
- PR Trivy filesystem and image scans: Task 4.
- PR Python dependency audit: Task 4.
- Publish on push to `main`: Task 5.
- Docker Hub secrets and tags: Tasks 3 and 5.
- Documentation: Task 3.
