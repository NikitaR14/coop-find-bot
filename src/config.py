from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    TOKEN: str
    DB_NAME: str
    DB_USER: str
    DB_PASSWORD: str
    DB_HOST: str
    DB_PORT: str
    DB_DRIVER: str
    GOOGLE_SHEET_CREDENTIALS_PATH: str
    GOOGLE_SHEET_ID: str
    GOOGLE_SHEET_WORKSHEET_NAME: str
    PRIVATE_PHOTO_GROUP_ID: int

    # Discord is an optional second transport.  Keeping defaults here lets the
    # Telegram service continue to start before Discord is configured.
    DISCORD_TOKEN: str | None = None
    DISCORD_APPLICATION_ID: int | None = None
    PRIMARY_GUILD_ID: int | None = None
    TEST_GUILD_ID: int | None = None
    DISCORD_STATS_WORKSHEET_NAME: str = "Discord"
    MEDIA_DIR: str = "var/media"
    TELEGRAM_PROXY_URL: str | None = None
    WEBSITE_URL: str = "https://gg.markets/s-TeamSeek"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )

    @property
    def db_url(self) -> str:
        return f"postgresql+{self.DB_DRIVER}://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"


settings = Settings()
