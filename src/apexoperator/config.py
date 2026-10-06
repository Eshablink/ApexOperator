import os

from pydantic import BaseModel, Field, field_validator


class Settings(BaseModel):
    app_env: str = Field(default_factory=lambda: os.getenv("APP_ENV", "development"))
    log_level: str = Field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))
    database_url: str = Field(
        default_factory=lambda: os.getenv("DATABASE_URL", "sqlite:///./apexoperator.db")
    )
    planner_mode: str = Field(
        default_factory=lambda: os.getenv("APEX_PLANNER", "mock")
    )
    openai_api_key: str | None = Field(
        default_factory=lambda: os.getenv("OPENAI_API_KEY")
    )
    openai_model: str = Field(
        default_factory=lambda: os.getenv("OPENAI_MODEL", "gpt-6-astra")
    )

    @field_validator("planner_mode")
    @classmethod
    def validate_planner_mode(cls, value: str) -> str:
        value = value.strip().lower()
        if value not in {"mock", "openai"}:
            raise ValueError("APEX_PLANNER must be 'mock' or 'openai'")
        return value


settings = Settings()
