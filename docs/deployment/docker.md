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
