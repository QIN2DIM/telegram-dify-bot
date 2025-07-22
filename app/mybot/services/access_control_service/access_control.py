# -*- coding: utf-8 -*-
"""
Access control service for managing user permissions
"""
from typing import Optional

from loguru import logger
from telegram import Update, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from mybot.services.access_control_service.database import UserCRUD
from mybot.services.access_control_service.binders import binder_service
from settings import settings


# Template message for users without access
ACCESS_DENIED_TEMPLATE = """
🔒 <b>访问受限</b>

要使用此机器人，您需要加入以下所有官方频道/群组：

请点击下方按钮加入，然后再试一次。

<i>提示：加入所有频道后，您的访问权限将自动激活。</i>
"""


class AccessControlService:
    """Service for checking and enforcing user access permissions"""

    @staticmethod
    async def reply_join_prompt(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        buttons: Optional[InlineKeyboardMarkup] = None,
    ) -> None:
        """
        Send access denied message with join buttons

        Args:
            update: Telegram update
            context: Bot context
            buttons: Optional inline keyboard with join buttons
        """
        message = update.effective_message
        if not message:
            return

        try:
            await message.reply_html(text=ACCESS_DENIED_TEMPLATE.strip(), reply_markup=buttons)
        except Exception as e:
            logger.error(f"Failed to send access denied message: {e}")

    @classmethod
    async def ensure_user_allowed(cls, update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
        """
        Check if user is allowed to use the bot

        This is the main access control function that should be called
        before processing any user request.

        Args:
            update: Telegram update
            context: Bot context

        Returns:
            True if user is allowed, False otherwise (and sends denial message)
        """
        # Get effective user
        user = update.effective_user
        if not user:
            logger.warning("No effective user in update")
            return False

        user_id = user.id

        # Super admin always has access
        if user_id == settings.SUPER_ADMIN_ID:
            logger.debug(f"Super admin {user_id} granted access")
            return True

        # Check if user is in the database with valid access
        if UserCRUD.is_valid(user_id):
            logger.debug(f"User {user_id} has valid database record")
            return True

        # Check membership in all required binders
        try:
            is_member = await binder_service.check_membership(context.bot, user_id)

            if is_member:
                # User is member of all binders, grant access and save to database
                UserCRUD.validate_user(user_id)
                logger.info(f"User {user_id} validated through membership check")
                return True
            else:
                # User is not member of all binders
                logger.debug(f"User {user_id} failed membership check")

                # Build invite buttons
                buttons = binder_service.build_invite_buttons()

                # Send denial message with buttons
                await cls.reply_join_prompt(update, context, buttons)

                # Mark user as invalid in database (if they were previously valid)
                UserCRUD.invalidate_user(user_id)

                return False

        except Exception as e:
            logger.error(f"Error checking user {user_id} access: {e}")
            # On error, deny access for safety
            await cls.reply_join_prompt(update, context)
            return False

    @staticmethod
    async def check_user_access_silent(user_id: int, bot) -> bool:
        """
        Check user access without sending messages (for background checks)

        Args:
            user_id: Telegram user ID
            bot: Bot instance

        Returns:
            True if user has access, False otherwise
        """
        # Super admin always has access
        if user_id == settings.SUPER_ADMIN_ID:
            return True

        # Check database first
        if UserCRUD.is_valid(user_id):
            return True

        # Check membership
        try:
            return await binder_service.check_membership(bot, user_id)
        except Exception as e:
            logger.error(f"Error in silent access check for user {user_id}: {e}")
            return False


# Global instance
access_control = AccessControlService()
