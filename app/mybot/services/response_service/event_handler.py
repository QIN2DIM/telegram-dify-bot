# -*- coding: utf-8 -*-
"""
@Time    : 2025/8/14 22:03
@Author  : QIN2DIM
@GitHub  : https://github.com/QIN2DIM
@Desc    :
"""
from dataclasses import dataclass, field
from typing import Dict, Any

from loguru import logger
from telegram.constants import ParseMode
from telegram.ext import ContextTypes


# Constants
AGENT_LOG_UPDATE_INTERVAL = 1.5


@dataclass
class LazyData:
    agent_strategy_name: str | None = ""
    imagine_optimized_output: Dict[str, Any] | None = field(default_factory=dict)


class EventHandler:
    def __init__(self, context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: int):
        self.lazy_data: LazyData = LazyData()
        self._ctx = context
        self._chat_id = chat_id
        self._message_id = message_id

    async def update_progress_message(self, text: str) -> None:
        """Update progress message with error handling"""
        if not text:
            return

        try:
            await self._ctx.bot.edit_message_text(
                chat_id=self._chat_id,
                message_id=self._message_id,
                text=text,
                parse_mode=ParseMode.HTML,
            )
        except Exception as err:
            logger.error(f"Failed to update progress message: {err}")
