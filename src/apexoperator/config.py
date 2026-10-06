from pydantic import BaseModel

class Settings(BaseModel):
    app_env: str = "development"
    log_level: str = "INFO"
    database_url: str = "sqlite:///./apexoperator.db"

settings = Settings()
