from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # =========================
    # Gemini
    # =========================
    GEMINI_API_KEY: str
    GEMINI_MODEL: str = "gemini-3.5-flash"

    # =========================
    # OpenAI - kept optional
    # for compatibility with
    # older parts of the project
    # =========================
    OPENAI_API_KEY: Optional[str] = None
    GPT_MODEL: str = "gpt-3.5-turbo"

    # =========================
    # AI / Rate Limiting
    # =========================
    MAX_TOKENS_PER_REQUEST: int = 4000
    RATE_LIMIT_PER_MIN: int = 50

    # =========================
    # Legacy cost settings
    # =========================
    COST_PER_1K_INPUT_TOKENS: float = 0.0
    COST_PER_1K_OUTPUT_TOKENS: float = 0.0

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache()
def get_settings() -> Settings:
    return Settings()