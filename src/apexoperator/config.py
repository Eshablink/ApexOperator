import os

from pydantic import BaseModel, Field, field_validator, model_validator


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
    jwt_secret: str | None = Field(
        default_factory=lambda: os.getenv("JWT_SECRET")
    )
    jwt_issuer: str | None = Field(
        default_factory=lambda: os.getenv("JWT_ISSUER")
    )
    jwt_audience: str | None = Field(
        default_factory=lambda: os.getenv("JWT_AUDIENCE")
    )
    bootstrap_email: str | None = Field(
        default_factory=lambda: os.getenv("APEX_BOOTSTRAP_EMAIL")
    )
    bootstrap_password_hash: str | None = Field(
        default_factory=lambda: os.getenv("APEX_BOOTSTRAP_PASSWORD_HASH")
    )
    bootstrap_role: str = Field(
        default_factory=lambda: os.getenv("APEX_BOOTSTRAP_ROLE", "FINANCE_MANAGER")
    )
    session_minutes: int = Field(
        default_factory=lambda: int(os.getenv("APEX_SESSION_MINUTES", "60"))
    )

    @field_validator("app_env", "log_level", "planner_mode")
    @classmethod
    def strip_lower(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("bootstrap_role")
    @classmethod
    def validate_bootstrap_role(cls, value: str) -> str:
        value = value.strip().upper()
        allowed = {"AP_CLERK", "FINANCE_MANAGER", "SYSTEM_ADMIN"}
        if value not in allowed:
            raise ValueError("APEX_BOOTSTRAP_ROLE is unsupported")
        return value

    @model_validator(mode="after")
    def validate_production_security_boundary(self):
        if self.app_env == "production":
            if not self.database_url.strip() or self.database_url.lower().startswith("sqlite"):
                raise ValueError("APP_ENV=production requires a persistent non-SQLite DATABASE_URL")
            if not self.jwt_secret or len(self.jwt_secret) < 32:
                raise ValueError("APP_ENV=production requires JWT_SECRET with at least 32 characters")
            if not self.bootstrap_email or not self.bootstrap_email.strip():
                raise ValueError("APP_ENV=production requires APEX_BOOTSTRAP_EMAIL")
            if not self.bootstrap_password_hash or not self.bootstrap_password_hash.startswith("scrypt$v1$"):
                raise ValueError("APP_ENV=production requires APEX_BOOTSTRAP_PASSWORD_HASH")
            if self.session_minutes < 15 or self.session_minutes > 24 * 60:
                raise ValueError("APEX_SESSION_MINUTES must be between 15 and 1440")
        return self

    @field_validator("planner_mode")
    @classmethod
    def validate_planner_mode(cls, value: str) -> str:
        if value not in {"mock", "openai"}:
            raise ValueError("APEX_PLANNER must be 'mock' or 'openai'")
        return value


settings = Settings()
