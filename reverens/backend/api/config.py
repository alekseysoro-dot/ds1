from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "sqlite:///./test.db"
    api_key: str = "dev-key"
    cors_origins: str = "http://localhost"
    apify_api_token: str = ""
    apify_keyword: str = ""

    # SMTP
    smtp_host: str = ""
    smtp_port: int = 465
    smtp_user: str = ""
    smtp_password: str = ""

    class Config:
        env_file = ".env"


settings = Settings()
