from pathlib import Path
from typing import Set, Any, Literal, List
from urllib.request import getproxies

import dotenv
from loguru import logger
from pydantic import SecretStr, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from telegram._utils.defaultvalue import DEFAULT_NONE
from telegram.constants import ParseMode
from telegram.ext import Application

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

    DIFY_APP_BASE_URL: str = Field(
        default="https://api.dify.ai/v1", description="Dify Workflow 后端连接"
    )

    DIFY_WORKFLOW_API_KEY: SecretStr = Field(
        default="",
        description="用于连接 Dify Workflow 的 API_KEY。请注意该项目仅适配 Workflow 类型 Application（非 Chatflow）。",
    )

    TELEGRAM_CHAT_WHITELIST: str = Field(
        default="", description="允许的聊天 ID，可以同时约束 channel，group，private，supergroup。"
    )

    RESPONSE_MODE: Literal["blocking", "streaming"] = Field(
        default="streaming", description="响应模式: `blocking` 或 `streaming`。"
    )

    whitelist: Set[int] = Field(
        default_factory=set,
        description="配置 TELEGRAM_CHAT_WHITELIST 后， id 被清洗到该列表方便使用",
    )

    BOT_ANSWER_PARSE_MODE: Literal["HTML"] = Field(
        default="HTML",
        description="约束模型的输出格式，默认为 HTML，要求模型用 HTML 表达富文本而非 Markdown。",
    )

    BOT_ANSWER_KEY: str = Field(
        default="answer",
        description="在 Dify Workflow 返回的 outputs 中，将哪个字段的值视为用于回复的纯文本答案。默认为 `answer` 字段。",
    )

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

    @property
    def pending_parse_mode(self):
        if self.BOT_ANSWER_PARSE_MODE == "HTML":
            return [ParseMode.HTML, DEFAULT_NONE]
        return [ParseMode.MARKDOWN, ParseMode.MARKDOWN_V2, ParseMode.HTML, DEFAULT_NONE]


settings = Settings()  # type: ignore
