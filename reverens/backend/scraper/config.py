from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    smtp_host: str = "smtp.beget.com"
    smtp_port: int = 465
    smtp_user: str = ""
    smtp_password: str = ""
    telegram_bot_token: str = ""

    class Config:
        env_file = ".env"


settings = Settings()
