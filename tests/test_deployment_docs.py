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
    normalized_docs = " ".join(docs.split())

    assert "docker build -t poneglyph-discord-bot:local ." in docs
    assert "docker run --rm" in docs
    assert "secrets/discord_token.txt" in docs
    assert "DISCORD_TOKEN_FILE" in docs
    assert "takes precedence over `DISCORD_TOKEN`" in normalized_docs
    assert "DOCKERHUB_USERNAME" in docs
    assert "DOCKERHUB_TOKEN" in docs
    assert "DOCKERHUB_REPOSITORY" in docs
    assert "- `latest`" in docs
    assert "- `main`" in docs
    assert "sha-<shortsha>" in docs


def test_env_example_documents_token_file() -> None:
    env_example = (ROOT / ".env.example").read_text().splitlines()

    assert env_example[:2] == ["DISCORD_TOKEN=", "DISCORD_TOKEN_FILE="]


def test_compose_secret_file_is_gitignored() -> None:
    gitignore = (ROOT / ".gitignore").read_text().splitlines()

    assert "secrets/" in gitignore


def test_readme_links_to_docker_docs() -> None:
    readme = (ROOT / "README.md").read_text()

    assert "[Docker Deployment](docs/deployment/docker.md)" in readme
