# -*- coding: utf-8 -*-
"""
Base command handler with access control
"""
from typing import Callable, Optional, Awaitable

from loguru import logger
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from mybot.services.access_control_service.access_control import access_control


class ACLCommandHandler(CommandHandler):
    """
    Command handler wrapper that enforces access control

    This handler checks user permissions before executing the actual command.
    All commands should use this handler instead of the default CommandHandler
    to ensure consistent access control.
    """

    def __init__(
        self,
        command: str | list[str],
        callback: Callable[[Update, ContextTypes.DEFAULT_TYPE], Awaitable[None]],
        filters=None,
        block: bool = True,
        has_args: Optional[bool | int] = None,
    ):
        """
        Initialize ACL command handler

        Args:
            command: Command or list of commands
            callback: Original callback function
            filters: Additional filters
            block: Whether to run blocking or non-blocking
            has_args: Whether command expects arguments
        """
        # Store original callback
        self._original_callback = callback

        # Initialize parent with our wrapped callback
        super().__init__(
            command=command,
            callback=self._acl_callback,
            filters=filters,
            block=block,
            has_args=has_args,
        )

    async def _acl_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Wrapped callback that checks access before executing original callback

        Args:
            update: Telegram update
            context: Bot context
        """
        # Extract command for logging
        message = update.effective_message
        command = message.text.split()[0] if message and message.text else "unknown"

        # Check user access
        user = update.effective_user
        user_id = user.id if user else "unknown"

        logger.debug(f"ACL check for command {command} from user {user_id}")

        # Perform access check
        if not await access_control.ensure_user_allowed(update, context):
            # Access denied - ensure_user_allowed already sent the denial message
            logger.info(f"Access denied for command {command} from user {user_id}")
            return

        # Access granted - execute original callback
        logger.debug(f"Access granted for command {command} from user {user_id}")
        await self._original_callback(update, context)
