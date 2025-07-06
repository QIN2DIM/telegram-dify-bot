from pathlib import Path
from typing import List, Literal, Any

import dotenv
from loguru import logger
from pydantic import SecretStr, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

dotenv.load_dotenv()


PROJECT_DIR = Path(__file__).parent
CACHE_DIR = PROJECT_DIR.joinpath(".cache")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_ignore_empty=True, extra="ignore"
    )

    TELEGRAM_BOT_API_TOKEN: SecretStr = Field(
        default="", description="通过 https://t.me/BotFather 获取机器人的 API_TOKEN"
    )


settings = Settings()  # type: ignore
