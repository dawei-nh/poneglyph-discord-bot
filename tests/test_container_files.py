from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_dockerfile_runs_as_non_root_user() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text()

    assert "addgroup -S bot" in dockerfile
    assert "adduser -S -G bot -h /app -s /sbin/nologin bot" in dockerfile
    assert "USER bot" in dockerfile
    assert 'CMD ["optcg-card-bot"]' in dockerfile


def test_dockerfile_uses_pinned_alpine_bases() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text()

    assert (
        "FROM python:3.12-alpine@"
        "sha256:236173eb74001afe2f60862de935b74fcbd00adfca247b2c27051a70a6a39a2d"
    ) in dockerfile
    assert (
        "COPY --from=ghcr.io/astral-sh/uv:0.5.31-alpine@"
        "sha256:9fde210ef69f9f4b9b70b4155ca94e62accf7c53d857b6362ee5aa2236c98941"
        " /usr/local/bin/uv /usr/local/bin/uvx /bin/"
    ) in dockerfile


def test_dockerignore_excludes_secrets_and_local_artifacts() -> None:
    dockerignore = (ROOT / ".dockerignore").read_text().splitlines()

    expected_entries = {
        ".env",
        ".env.*",
        ".envrc",
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
