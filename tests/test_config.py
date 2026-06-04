import tomllib
from pathlib import Path

import pytest
from pydantic import ValidationError

import optcg_card_bot.__main__ as main_module
from optcg_card_bot.__main__ import main
from optcg_card_bot.config import Settings

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_settings_defaults(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)

    settings = Settings(discord_token="token")

    assert settings.discord_token == "token"
    assert settings.poneglyph_base_url == "https://api.poneglyph.one"
    assert settings.poneglyph_api_prefix == "/v1"
    assert settings.default_language == "en"
    assert settings.request_timeout_seconds == 10.0
    assert settings.request_min_interval_seconds == 0.25
    assert settings.enable_bracket_messages is False


def test_settings_normalizes_api_prefix(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)

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


def test_main_starts_runtime_from_settings(monkeypatch) -> None:
    seen: dict[str, Settings] = {}

    async def fake_run_bot(settings: Settings) -> None:
        seen["settings"] = settings

    monkeypatch.setenv("DISCORD_TOKEN", "from-env")
    monkeypatch.setattr(main_module, "run_bot", fake_run_bot)

    main()

    assert seen["settings"].discord_token == "from-env"


def test_project_targets_python_312_only() -> None:
    pyproject = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text())

    assert pyproject["project"]["requires-python"] == ">=3.12,<3.13"


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
