from pathlib import Path
from typing import Set, Any
from urllib.request import getproxies

import dotenv
from pydantic import SecretStr, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from telegram.ext import Application
from loguru import logger


dotenv.load_dotenv()


PROJECT_DIR = Path(__file__).parent
CACHE_DIR = PROJECT_DIR.joinpath(".cache")
LOG_DIR = PROJECT_DIR.joinpath("logs")
DATA_DIR = PROJECT_DIR.joinpath("data")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True, extra="ignore")

    TELEGRAM_BOT_API_TOKEN: SecretStr = Field(
        default="", description="通过 https://t.me/BotFather 获取机器人的 API_TOKEN"
    )

    DIFY_APP_BASE_URL: str = Field(default="https://api.dify.ai/v1")
    DIFY_WORKFLOW_API_KEY: SecretStr = Field(default="")

    TELEGRAM_CHAT_WHITELIST: str = Field(default="")

    whitelist: Set[int] = Field(default_factory=set)

    def model_post_init(self, context: Any, /) -> None:
        try:
            if not self.whitelist and self.TELEGRAM_CHAT_WHITELIST:
                self.whitelist = {
                    int(i.strip()) for i in filter(None, self.TELEGRAM_CHAT_WHITELIST.split(","))
                }
        except Exception as err:
            logger.warning(f"解析 TELEGRAM_CHAT_WHITELIST 失败 - {err}")

    def get_default_application(self) -> Application:
        if proxy_url := getproxies().get("http"):
            print(f"PROXY_URL={proxy_url}")
            application = (
                Application.builder()
                .token(self.TELEGRAM_BOT_API_TOKEN.get_secret_value())
                .proxy(proxy_url)
                .get_updates_proxy(proxy_url)
                .build()
            )
        else:
            application = (
                Application.builder().token(self.TELEGRAM_BOT_API_TOKEN.get_secret_value()).build()
            )

        return application


settings = Settings()  # type: ignore
