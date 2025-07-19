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

    SAFE_ZLIBRARY_WIKI_URL: str = Field(default="https://en.wikipedia.org/wiki/Z-Library")

    # 数据库配置
    DATABASE_URL: str = Field(
        default="postgresql://postgres:YHMovFEM82o4Ys6n@localhost:27429/telegram_dify_bot",
        description="PostgreSQL 数据库连接 URL",
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

    BOT_OUTPUTS_TYPE_KEY: str = Field(
        default="type",
        description="在 Dify Workflow 返回的 outputs 中，哪个字段在区分任务类型。默认为 `type` 字段。",
    )

    BOT_OUTPUTS_ANSWER_KEY: str = Field(
        default="answer",
        description="在 Dify Workflow 返回的 outputs 中，将哪个字段的值视为用于回复的纯文本答案。默认为 `answer` 字段。",
    )

    BOT_OUTPUTS_EXTRAS_KEY: str = Field(
        default="extras", description="在 Dify Workflow 输出的 outputs 中，作为额外数据的字段。"
    )

    # 新增：HTTP 请求超时配置
    HTTP_REQUEST_TIMEOUT: float = Field(
        default=75.0,
        description="HTTP 请求超时时间（秒），用于 Telegram API 调用。默认 75 秒。"
        "该值在接口层的默认值为 5 秒，此处调高该值，支持机器人响应一些提及较大的全模态媒体组，例如：文档和音视频",
    )

    ENABLE_DEV_MODE: bool = Field(
        default=False,
        description="""
        是否为开发模式，开发模式下会 MOCK 模型调用请求，立即响应模版信息。
        消息不会发送到 Dify，所有请求均在本地环回。一般在仅开发 Bot 端功能时按需启动。
        """,
    )

    ENABLE_TEST_MODE: bool = Field(
        default=False,
        description="""
        是否为测试模式，默认 False 也即关闭测试模式。
        测试模式下消息会发送到 Dify 但会触发 forced_command 协议标准，立即返回一个提前设定好的段落结果。
        例如：直接假设一大段文本是模型生成的，直接通过 结束 节点返回。
        可以方便测试接口协议标准以及协议边界值问题。
        """,
    )

    DEV_MODE_MOCKED_TEMPLATE: str = Field(
        default="<b>in the dev mode!</b>", description="当开发模式开启时，将返回该模版作为回复。"
    )

    # Telegraph 配置
    TELEGRAPH_SHORT_NAME: str | None = Field(
        default=None, description="Telegraph 账户的短名称，显示在编辑按钮上方"
    )

    TELEGRAPH_AUTHOR_NAME: str | None = Field(
        default=None, description="Telegraph 页面的默认作者名称"
    )

    TELEGRAPH_AUTHOR_URL: str | None = Field(
        default=None, description="Telegraph 页面的默认作者链接"
    )

    def model_post_init(self, context: Any, /) -> None:
        try:
            if not self.whitelist and self.TELEGRAM_CHAT_WHITELIST:
                self.whitelist = {
                    int(i.strip()) for i in filter(None, self.TELEGRAM_CHAT_WHITELIST.split(","))
                }
        except Exception as err:
            logger.warning(f"解析 TELEGRAM_CHAT_WHITELIST 失败 - {err}")

        # 防呆设置，假设 Linux 作为生产环境部署
        if "linux" in sys.platform:
            if self.ENABLE_DEV_MODE:
                logger.warning("开发模式已自动关闭，请勿在 Linux 上运行开发模式")
                self.ENABLE_DEV_MODE = False

            if self.ENABLE_TEST_MODE:
                logger.warning("测试模式已自动关闭，请勿在 Linux 上运行测试模式")
                self.ENABLE_TEST_MODE = False

        # 测试模式下自动关闭开发模式，并强制使用阻塞模式
        if self.ENABLE_TEST_MODE:
            if self.ENABLE_DEV_MODE:
                logger.warning("开发模式已自动关闭，开发模式和测试模式不能同时开启")
            self.ENABLE_DEV_MODE = False
            # self.RESPONSE_MODE = "blocking"

        # 开发环境下默认使用阻塞模式
        if self.ENABLE_DEV_MODE:
            self.RESPONSE_MODE = "blocking"

        if not self.TELEGRAPH_SHORT_NAME:
            self.TELEGRAPH_SHORT_NAME = f"{uuid4().hex[:8]}"

    def get_default_application(self) -> Application:
        _base_builder = (
            Application.builder()
            .token(self.TELEGRAM_BOT_API_TOKEN.get_secret_value())
            .connect_timeout(self.HTTP_REQUEST_TIMEOUT)
            .write_timeout(self.HTTP_REQUEST_TIMEOUT)
            .read_timeout(self.HTTP_REQUEST_TIMEOUT)
        )
        if proxy_url := getproxies().get("http"):
            logger.success(f"使用代理: {proxy_url}")
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
