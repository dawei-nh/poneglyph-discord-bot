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
