from pydantic_settings import BaseSettings
from pydantic import Field
from pydantic import SecretStr


class Settings(BaseSettings):
    """Application settings with environment variable support"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    # ============ APPLICATION SETTINGS ============
    PROJECT_NAME: str = "Invitation Project"
    VERSION: str = "1.0.0"
    DEBUG: bool = Field(default=True)
    # ============ SECURITY SETTINGS ============
    SECRET_KEY: SecretStr = Field(
        default=SecretStr("your-super-secret-key-change-this")
    )
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=30)
    ALGORITHM: str = Field(default="HS256")

    class Config:
        env_file = ".env"
        case_sensitive = True


def get_settings() -> Settings:
    return Settings()


# Export the configured settings
settings = get_settings()
