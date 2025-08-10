import sys
from pathlib import Path
from typing import Set, Any, Literal
from urllib.request import getproxies
from uuid import uuid4

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

YT_DLP_DIR = DATA_DIR.joinpath("yt_dlp")
YT_DLP_COOKIES = YT_DLP_DIR.joinpath("cookies")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True, extra="ignore")

    TELEGRAM_BOT_API_TOKEN: SecretStr = Field(
        default="", description="Get the bot's API_TOKEN from https://t.me/BotFather"
    )

    TELEGRAM_BOT_API_URL: str = Field(default="http://nginx:80")

    ENABLE_TELEGRAM_BOT_LOCAL_MODE: bool = Field(default=True)

    DIFY_APP_BASE_URL: str = Field(
        default="https://api.dify.ai/v1", description="Dify Workflow backend connection"
    )

    DIFY_WORKFLOW_API_KEY: SecretStr = Field(
        default="",
        description="API_KEY for connecting to Dify Workflow. Note that this project only supports Workflow type Application (not Chatflow).",
    )

    XHS_DOWNLOADER_BASE_URL: str = Field(
        default="http://xhs-downloader:5556",
        description="XHS Downloader base URL. Project: https://github.com/JoeanAmier/XHS-Downloader",
    )
    XHS_CONNECTION_TIMEOUT: int = Field(default=300)

    # Cookie files directory for various video sources
    # Expected format: {domain}.cookie (e.g., youtube.cookie, bilibili.cookie, twitter.com.cookie)

    SAFE_ZLIBRARY_WIKI_URL: str = Field(default="https://en.wikipedia.org/wiki/Z-Library")

    # Database configuration
    DATABASE_URL: str = Field(
        default="postgresql://postgres:YHMovFEM82o4Ys6n@localhost:27429/telegram_dify_bot",
        description="PostgreSQL database connection URL",
    )

    INIT_PLUGIN_STORAGE: bool = Field(default=True)

    TELEGRAM_CHAT_WHITELIST: str = Field(
        default="",
        description="Allowed chat IDs, can simultaneously constrain channel, group, private, supergroup.",
    )

    RESPONSE_MODE: Literal["blocking", "streaming"] = Field(
        default="streaming", description="Response mode: `blocking` or `streaming`."
    )

    whitelist: Set[int] = Field(
        default_factory=set,
        description="After configuring TELEGRAM_CHAT_WHITELIST, IDs are cleaned into this list for easy use",
    )

    BOT_ANSWER_PARSE_MODE: Literal["HTML"] = Field(
        default="HTML",
        description="Constrains the model's output format, defaults to HTML, requiring the model to express rich text in HTML rather than Markdown.",
    )

    BOT_OUTPUTS_TYPE_KEY: str = Field(
        default="type",
        description="In the outputs returned by Dify Workflow, which field is used to distinguish task types. Defaults to the `type` field.",
    )

    BOT_OUTPUTS_ANSWER_KEY: str = Field(
        default="answer",
        description="In the outputs returned by Dify Workflow, which field's value is considered as the plain text answer for replies. Defaults to the `answer` field.",
    )

    BOT_OUTPUTS_EXTRAS_KEY: str = Field(
        default="extras", description="Field in the outputs of Dify Workflow as additional data."
    )

    # New: HTTP request timeout configuration
    HTTP_REQUEST_TIMEOUT: float = Field(
        default=3600,
        description="HTTP request timeout (seconds), used for Telegram API calls. Default 75 seconds. "
        "The default value at the interface layer is 5 seconds, here we increase this value to support bot responses to some larger full-modal media groups, such as: documents and audio/video",
    )

    ENABLE_DEV_MODE: bool = Field(
        default=False,
        description="""
        Whether it's development mode, in development mode MOCK model call requests will be made, immediately responding with template information.
        Messages won't be sent to Dify, all requests are local loopback. Generally started on-demand when only developing Bot-side functionality.
        """,
    )

    ENABLE_TEST_MODE: bool = Field(
        default=False,
        description="""
        Whether it's test mode, default False means test mode is off.
        In test mode, messages will be sent to Dify but will trigger the forced_command protocol standard, immediately returning a pre-set paragraph result.
        For example: directly assuming a large paragraph of text is model-generated, directly returning through the end node.
        Can facilitate testing interface protocol standards and protocol boundary value issues.
        """,
    )

    DEV_MODE_MOCKED_TEMPLATE: str = Field(
        default="<b>in the dev mode!</b>",
        description="When development mode is enabled, this template will be returned as a reply.",
    )

    # Telegraph configuration
    TELEGRAPH_SHORT_NAME: str | None = Field(
        default=None,
        description="Short name of the Telegraph account, displayed above the edit button",
    )

    TELEGRAPH_AUTHOR_NAME: str | None = Field(
        default=None, description="Default author name for Telegraph pages"
    )

    TELEGRAPH_AUTHOR_URL: str | None = Field(
        default=None, description="Default author link for Telegraph pages"
    )

    # New: Binders configuration
    BINDERS_YAML_PATH: Path = Field(
        default=PROJECT_DIR / "config" / "binders.yaml",
        description="Binders configuration file path",
    )

    SUPER_ADMIN_ID: int = Field(
        default=0, description="Super admin Telegram User ID, has all permissions"
    )

    SUPER_ADMIN_COMMAND: str = Field(
        default="__acl_sync", description="Super admin panel call command, defaults to __acl_sync"
    )

    SHA256_SALT: str = Field(
        default="❤TelegramBot❤",
        description="SHA256 hash salt value, used for encrypted storage of user IDs",
    )

    def model_post_init(self, context: Any, /) -> None:
        try:
            if not self.whitelist and self.TELEGRAM_CHAT_WHITELIST:
                self.whitelist = {
                    int(i.strip()) for i in filter(None, self.TELEGRAM_CHAT_WHITELIST.split(","))
                }
        except Exception as err:
            logger.warning(f"Failed to parse TELEGRAM_CHAT_WHITELIST - {err}")

        # Foolproof settings, assuming Linux as production environment deployment
        if "linux" in sys.platform:
            if self.ENABLE_DEV_MODE:
                logger.warning(
                    "Development mode has been automatically turned off, please do not run development mode on Linux"
                )
                self.ENABLE_DEV_MODE = False

            if self.ENABLE_TEST_MODE:
                logger.warning(
                    "Test mode has been automatically turned off, please do not run test mode on Linux"
                )
                self.ENABLE_TEST_MODE = False

        # In test mode, automatically turn off development mode and force blocking mode
        if self.ENABLE_TEST_MODE:
            if self.ENABLE_DEV_MODE:
                logger.warning(
                    "Development mode has been automatically turned off, development mode and test mode cannot be enabled simultaneously"
                )
            self.ENABLE_DEV_MODE = False
            # self.RESPONSE_MODE = "blocking"

        # Development environment defaults to blocking mode
        if self.ENABLE_DEV_MODE:
            self.RESPONSE_MODE = "blocking"

        if not self.TELEGRAPH_SHORT_NAME:
            self.TELEGRAPH_SHORT_NAME = f"{uuid4().hex[:8]}"

        # Ensure cookies directory exists
        if not YT_DLP_COOKIES.exists():
            YT_DLP_COOKIES.mkdir(exist_ok=True, parents=True)

        self.TELEGRAM_BOT_API_URL = self.TELEGRAM_BOT_API_URL.rstrip("/")

    def get_default_application(self) -> Application:
        _base_builder = (
            Application.builder()
            .token(self.TELEGRAM_BOT_API_TOKEN.get_secret_value())
            .connect_timeout(self.HTTP_REQUEST_TIMEOUT)
            .write_timeout(self.HTTP_REQUEST_TIMEOUT)
            .read_timeout(self.HTTP_REQUEST_TIMEOUT)
            # Note: local_mode needs to be used with a local Bot API server.
            # If you are not running a local server, set local_mode to False
            .base_url(f"{self.TELEGRAM_BOT_API_URL}/bot")
            .base_file_url(f"{self.TELEGRAM_BOT_API_URL}/file/bot")
            .local_mode(True)
        )

        if proxy_url := getproxies().get("http"):
            logger.success(f"Using proxy: {proxy_url}")
            application = _base_builder.proxy(proxy_url).get_updates_proxy(proxy_url).build()
        else:
            application = _base_builder.build()

        return application

    @property
    def pending_parse_mode(self):
        if self.BOT_ANSWER_PARSE_MODE == "HTML":
            return [ParseMode.HTML, DEFAULT_NONE]
        return [ParseMode.MARKDOWN, ParseMode.MARKDOWN_V2, ParseMode.HTML, DEFAULT_NONE]


settings = Settings()  # type: ignore
