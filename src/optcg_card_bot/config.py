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
