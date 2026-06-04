# Docker CI Deployment Design

## Purpose

Add a practical production path for running the Poneglyph Discord bot as a Docker
container. The repository should build and validate the image in pull requests,
run security checks before merge, and publish a Docker Hub image only after code
lands on the protected default branch.

The deployment model is intentionally narrow: this remains a Discord bot for
Poneglyph. The repo should not grow a generic hosting platform, provider
framework, or orchestration layer.

## Runtime Target

The primary runtime target is a self-hosted Docker container. Users may run it
directly with `docker run`, through Docker Compose, Portainer, Unraid, Synology,
or similar Docker-compatible hosts.

The repo should include a Compose example because it documents the expected
runtime contract clearly, but the image itself should not depend on Compose.

## Container Image

The production image should:

- Use a slim Python runtime appropriate for the project's supported Python
  version.
- Install only runtime dependencies.
- Run as a non-root user.
- Start the bot through the existing package entrypoint.
- Exclude local development files, caches, test artifacts, Git metadata, Nix
  artifacts, `.env`, and virtual environments from the build context.
- Keep build behavior reproducible from the committed lockfile.

The image should not include a Discord token or any other runtime secret.

## Configuration And Secrets

Environment variables remain the main configuration interface. Existing
settings should keep working unchanged:

```text
DISCORD_TOKEN=
PONEGLYPH_BASE_URL=https://api.poneglyph.one
PONEGLYPH_API_PREFIX=/v1
OPTCG_DEFAULT_LANGUAGE=en
OPTCG_REQUEST_TIMEOUT_SECONDS=10
OPTCG_REQUEST_MIN_INTERVAL_SECONDS=0.25
OPTCG_ENABLE_BRACKET_MESSAGES=false
```

Add explicit Docker secret file support for the Discord token:

```text
DISCORD_TOKEN_FILE=/run/secrets/discord_token
```

If `DISCORD_TOKEN_FILE` is set, the settings loader should read the token from
that file and prefer it over `DISCORD_TOKEN`. This support should be explicit to
the Discord token instead of a broad generic secret loader.

Token file handling should:

- Strip one trailing newline and surrounding whitespace from the mounted secret.
- Raise a clear configuration error if the file path is set but unreadable.
- Raise a clear configuration error if the file is empty after stripping.
- Avoid logging the token value.

## Local Docker Usage

Documentation should show both supported secret styles.

Direct environment variable:

```bash
docker run --rm \
  --env DISCORD_TOKEN="$DISCORD_TOKEN" \
  poneglyph-discord-bot:local
```

Mounted secret file through Compose:

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

The local examples should use `poneglyph-discord-bot:local`. Docker Hub publish
docs should use the repository configured through `DOCKERHUB_REPOSITORY`.

## Pull Request Checks

Pull requests should run the existing Python verification gates and add
container/security checks.

Required PR checks:

- Ruff lint.
- Ruff format check.
- Pyright.
- Unit tests.
- Live Poneglyph smoke tests, unless the project later decides to move live
  tests to scheduled or manual CI.
- Docker image build.
- Trivy filesystem scan.
- Trivy image scan.
- Python dependency vulnerability audit.

Security scans should fail the PR for high and critical findings. If the tools
require suppressions, suppressions should live in a committed ignore file with
comments explaining each entry.

## Publish On Main

Publishing should happen only on push to the protected default branch, currently
`main`. Pull requests should never push images.

The publish workflow should authenticate to Docker Hub using GitHub Actions
secrets:

```text
DOCKERHUB_USERNAME
DOCKERHUB_TOKEN
DOCKERHUB_REPOSITORY
```

The workflow should push these tags:

- `latest`
- `main`
- `sha-<shortsha>`

`sha-<shortsha>` is the immutable rollback tag. `latest` and `main` are moving
convenience tags.

## CI Shape

The existing CI workflow may remain the main PR workflow. Image publishing
should live in a separate workflow so PR validation and release side effects are
easy to reason about.

Expected workflows:

```text
.github/workflows/ci.yml
.github/workflows/publish-image.yml
```

The CI workflow should build the image but not push it. The publish workflow
should build the image, run the same container security scan, and push only if
the scan passes.

## Repository Additions

Expected files:

```text
Dockerfile
.dockerignore
compose.yaml
docs/deployment/docker.md
.github/workflows/publish-image.yml
```

Expected modified files:

```text
.env.example
.github/workflows/ci.yml
README.md
src/optcg_card_bot/config.py
tests/test_config.py
```

## Testing Strategy

Configuration tests should cover:

- `DISCORD_TOKEN` still works.
- `DISCORD_TOKEN_FILE` loads a mounted token file.
- `DISCORD_TOKEN_FILE` takes precedence over `DISCORD_TOKEN`.
- Empty token files fail clearly.
- Missing token files fail clearly.

CI changes should be validated by running the local Python checks and a local
Docker build. The implementation plan should include a local Trivy command if
Trivy is available, while recognizing that GitHub Actions is the authoritative
security gate.

## Out Of Scope

- Kubernetes, Nomad, or Helm manifests.
- Automated deployment to a host after Docker Hub publish.
- Image signing, provenance attestations, or SBOM publishing.
- A generic secret-file loader for all settings.
- A generic multi-provider card service.
