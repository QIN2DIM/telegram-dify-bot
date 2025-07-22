# -*- coding: utf-8 -*-
"""
Binder service for managing group/channel requirements
"""
import asyncio
from typing import List, Optional

import yaml
from loguru import logger
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import TelegramError, BadRequest

from mybot.services.access_control_service.binders_model import BindersConfig, Binder
from settings import settings


class BinderService:
    """Service for managing binder configurations and membership checks"""

    def __init__(self):
        self._config: Optional[BindersConfig] = None
        self._config_path = settings.BINDERS_YAML_PATH

    def load_config(self) -> BindersConfig:
        """
        Load binders configuration from YAML file

        Returns:
            BindersConfig object
        """
        if self._config is not None:
            return self._config

        try:
            if not self._config_path.exists():
                logger.warning(
                    f"Binders config not found at {self._config_path}, using empty config"
                )
                self._config = BindersConfig()
                return self._config

            with open(self._config_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f) or {}

            self._config = BindersConfig(**data)
            logger.info(f"Loaded {len(self._config.binders)} binders from config")
            return self._config

        except Exception as e:
            logger.error(f"Failed to load binders config: {e}")
            self._config = BindersConfig()
            return self._config

    def get_binders(self) -> List[Binder]:
        """Get list of configured binders"""
        config = self.load_config()
        return config.binders

    def build_invite_buttons(self) -> Optional[InlineKeyboardMarkup]:
        """
        Build inline keyboard with invite links for all binders

        Returns:
            InlineKeyboardMarkup with buttons, or None if no binders configured
        """
        binders = self.get_binders()
        if not binders:
            return None

        buttons = []
        for binder in binders:
            # Use invite link if provided, otherwise generate telegram link
            if binder.invite_link:
                url = binder.invite_link
            else:
                # For public channels, use t.me/channelname format
                # This is a fallback - private channels must provide invite_link
                url = f"https://t.me/c/{str(binder.id).lstrip('-')}"

            button = InlineKeyboardButton(text=f"➕ {binder.title}", url=url)
            buttons.append([button])  # One button per row

        return InlineKeyboardMarkup(buttons)

    async def check_membership(self, bot: Bot, user_id: int) -> bool:
        """
        Check if user is member of ALL required binders

        Args:
            bot: Telegram bot instance
            user_id: User ID to check

        Returns:
            True if user is member of all binders, False otherwise
        """
        binders = self.get_binders()
        if not binders:
            # No binders configured = no restrictions
            return True

        for binder in binders:
            try:
                # Add small delay to avoid rate limiting
                await asyncio.sleep(0.1)

                # Get chat member status
                member = await bot.get_chat_member(chat_id=binder.id, user_id=user_id)

                # Check if user is active member
                if member.status not in ['member', 'administrator', 'creator']:
                    logger.debug(
                        f"User {user_id} not in binder {binder.title} (status: {member.status})"
                    )
                    return False

            except BadRequest as e:
                # Bot not in chat or chat doesn't exist
                logger.warning(f"Cannot check membership for binder {binder.title}: {e}")
                # If we can't check, assume user doesn't have access
                return False
            except TelegramError as e:
                logger.error(f"Telegram error checking membership: {e}")
                # On error, deny access for safety
                return False
            except Exception as e:
                logger.error(f"Unexpected error checking membership: {e}")
                return False

        # User is member of all binders
        logger.debug(f"User {user_id} is member of all {len(binders)} binders")
        return True

    async def get_user_missing_binders(self, bot: Bot, user_id: int) -> List[Binder]:
        """
        Get list of binders that user is not member of

        Args:
            bot: Telegram bot instance
            user_id: User ID to check

        Returns:
            List of Binder objects that user needs to join
        """
        binders = self.get_binders()
        missing = []

        for binder in binders:
            try:
                await asyncio.sleep(0.1)
                member = await bot.get_chat_member(chat_id=binder.id, user_id=user_id)

                if member.status not in ['member', 'administrator', 'creator']:
                    missing.append(binder)

            except Exception:
                # If we can't check, assume user needs to join
                missing.append(binder)

        return missing


# Global instance
binder_service = BinderService()
