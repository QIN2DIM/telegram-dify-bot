# -*- coding: utf-8 -*-
"""
Chat member update handler for tracking user join/leave events
"""
from loguru import logger
from telegram import Update
from telegram.ext import ContextTypes

from mybot.services.access_control_service.database import UserCRUD
from mybot.services.access_control_service.binders import binder_service
from mybot.services.access_control_service.access_control import access_control


async def handle_chat_member_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle chat member updates (join/leave events)

    This handler tracks when users join or leave binder groups
    and updates their access status accordingly.
    """
    # Get the chat member update
    chat_member_update = update.chat_member or update.my_chat_member
    if not chat_member_update:
        return

    # Extract user and chat info
    user = chat_member_update.new_chat_member.user
    chat_id = chat_member_update.chat.id
    old_status = chat_member_update.old_chat_member.status
    new_status = chat_member_update.new_chat_member.status

    # Check if this chat is one of our binders
    binders = binder_service.get_binders()
    binder_ids = {binder.id for binder in binders}

    if chat_id not in binder_ids:
        # Not a binder chat, ignore
        return

    logger.debug(
        f"Chat member update in binder {chat_id}: "
        f"User {user.id} status changed from {old_status} to {new_status}"
    )

    # Determine if user joined or left
    active_statuses = {'member', 'administrator', 'creator'}
    # inactive_statuses = {'left', 'kicked', 'restricted'}

    was_active = old_status in active_statuses
    is_active = new_status in active_statuses

    if not was_active and is_active:
        # User joined the group
        logger.info(f"User {user.id} joined binder chat {chat_id}")

        # Check if user now has access to all binders
        has_full_access = await access_control.check_user_access_silent(user.id, context.bot)

        if has_full_access:
            # User now has access to all binders
            UserCRUD.validate_user(user.id)
            logger.info(f"User {user.id} now has full access after joining binder {chat_id}")

    elif was_active and not is_active:
        # User left or was removed from the group
        logger.info(f"User {user.id} left/removed from binder chat {chat_id}")

        # Mark user as invalid since they no longer have access to all binders
        UserCRUD.invalidate_user(user.id)
        logger.info(f"User {user.id} access invalidated after leaving binder {chat_id}")


async def handle_my_chat_member_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle updates about the bot's own membership status

    This is useful for tracking when the bot is added to or removed from groups.
    """
    if not update.my_chat_member:
        return

    chat = update.my_chat_member.chat
    old_status = update.my_chat_member.old_chat_member.status
    new_status = update.my_chat_member.new_chat_member.status

    if old_status != new_status:
        logger.info(
            f"Bot membership changed in {chat.type} '{chat.title or chat.id}': "
            f"{old_status} -> {new_status}"
        )

        # Check if this is a binder chat
        binders = binder_service.get_binders()
        binder_ids = {binder.id for binder in binders}

        if chat.id in binder_ids and new_status not in ['member', 'administrator']:
            logger.warning(
                f"Bot was removed from binder chat {chat.id} ({chat.title}). "
                f"This will prevent membership verification for this binder!"
            )
