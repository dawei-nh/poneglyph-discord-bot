import tomllib
from pathlib import Path

from optcg_card_bot.__main__ import main
from optcg_card_bot.config import Settings

PROJECT_ROOT = Path(__file__).resolve().parents[1]


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


def test_settings_loads_environment_aliases(monkeypatch) -> None:
    monkeypatch.setenv("DISCORD_TOKEN", "from-env")
    monkeypatch.setenv("PONEGLYPH_API_PREFIX", "v2")
    monkeypatch.setenv("OPTCG_ENABLE_BRACKET_MESSAGES", "true")

    settings = Settings()

    assert settings.discord_token == "from-env"
    assert settings.poneglyph_api_prefix == "/v2"
    assert settings.enable_bracket_messages is True


def test_placeholder_main_does_not_require_discord_token(monkeypatch) -> None:
    monkeypatch.delenv("DISCORD_TOKEN", raising=False)

    try:
        main()
    except SystemExit as exc:
        message = str(exc)
    else:
        raise AssertionError("main() should raise SystemExit during scaffold phase")

    assert "Bot runtime is added in a later task." in message
    assert "https://api.poneglyph.one/v1" in message


def test_project_targets_python_312_only() -> None:
    pyproject = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text())

    assert pyproject["project"]["requires-python"] == ">=3.12,<3.13"
