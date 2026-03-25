from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "sqlite:///./test.db"
    api_key: str = "dev-key"
    cors_origins: str = "http://localhost"

    class Config:
        env_file = ".env"


settings = Settings()
