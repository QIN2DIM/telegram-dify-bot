# -*- coding: utf-8 -*-
"""
Hidden ACL management commands for super admin
"""
from telegram import Update
from telegram.ext import ContextTypes

from mybot.services.access_control_service.database import UserCRUD
from mybot.services.access_control_service.access_control import access_control
from mybot.services.access_control_service.binders import binder_service
from settings import settings


async def acl_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Hidden command for super admin to manage access control

    Usage:
        /__acl_sync list - Show access statistics
        /__acl_sync renew <user_id> - Manually check and update user access
        /__acl_sync check <user_id> - Check user's current access status
        /__acl_sync invalidate <user_id> - Manually invalidate user access
    """
    user = update.effective_user
    if not user or user.id != settings.SUPER_ADMIN_ID:
        # Not super admin, ignore command silently
        return

    message = update.effective_message
    if not message or not context.args:
        await message.reply_html(
            "<b>ACL Admin Commands:</b>\n\n"
            "<code>/__acl_sync list</code> - Show access statistics\n"
            "<code>/__acl_sync renew &lt;user_id&gt;</code> - Check and update user access\n"
            "<code>/__acl_sync check &lt;user_id&gt;</code> - Check user access status\n"
            "<code>/__acl_sync invalidate &lt;user_id&gt;</code> - Invalidate user access"
        )
        return

    subcommand = context.args[0].lower()

    if subcommand == "list":
        # Show access statistics
        valid_count = UserCRUD.get_valid_user_count()
        invalid_count = UserCRUD.get_invalid_user_count()
        total_count = valid_count + invalid_count

        binders = binder_service.get_binders()
        binder_info = "\n".join([f"• {b.title} (ID: <code>{b.id}</code>)" for b in binders])

        await message.reply_html(
            f"<b>📊 Access Control Statistics</b>\n\n"
            f"<b>Users:</b>\n"
            f"✅ Valid: {valid_count}\n"
            f"❌ Invalid: {invalid_count}\n"
            f"📊 Total: {total_count}\n\n"
            f"<b>Required Binders ({len(binders)}):</b>\n"
            f"{binder_info if binder_info else '<i>No binders configured</i>'}"
        )

    elif subcommand == "renew" and len(context.args) > 1:
        # Manually check and update user access
        try:
            target_user_id = int(context.args[1])
        except ValueError:
            await message.reply_text("❌ Invalid user ID format")
            return

        # Check membership
        has_access = await access_control.check_user_access_silent(target_user_id, context.bot)

        if has_access:
            UserCRUD.validate_user(target_user_id)
            await message.reply_html(
                f"✅ User <code>{target_user_id}</code> has been validated.\n"
                f"They are member of all required binders."
            )
        else:
            UserCRUD.invalidate_user(target_user_id)

            # Get missing binders
            missing = await binder_service.get_user_missing_binders(context.bot, target_user_id)
            missing_info = "\n".join([f"• {b.title}" for b in missing])

            await message.reply_html(
                f"❌ User <code>{target_user_id}</code> has been invalidated.\n\n"
                f"<b>Missing binders:</b>\n{missing_info if missing_info else '<i>Unable to check</i>'}"
            )

    elif subcommand == "check" and len(context.args) > 1:
        # Check user's current access status
        try:
            target_user_id = int(context.args[1])
        except ValueError:
            await message.reply_text("❌ Invalid user ID format")
            return

        # Check database
        db_valid = UserCRUD.is_valid(target_user_id)

        # Check actual membership
        actual_valid = await access_control.check_user_access_silent(target_user_id, context.bot)

        # Get user hash for display
        user_hash = UserCRUD.hash_user_id(target_user_id)

        await message.reply_html(
            f"<b>User Access Status</b>\n\n"
            f"User ID: <code>{target_user_id}</code>\n"
            f"Hash: <code>{user_hash[:16]}...</code>\n\n"
            f"Database status: {'✅ Valid' if db_valid else '❌ Invalid'}\n"
            f"Actual membership: {'✅ Valid' if actual_valid else '❌ Invalid'}\n\n"
            f"<i>Note: Actual membership check may fail if bot is not in all binder groups.</i>"
        )

    elif subcommand == "invalidate" and len(context.args) > 1:
        # Manually invalidate user access
        try:
            target_user_id = int(context.args[1])
        except ValueError:
            await message.reply_text("❌ Invalid user ID format")
            return

        UserCRUD.invalidate_user(target_user_id)
        await message.reply_html(
            f"✅ User <code>{target_user_id}</code> has been invalidated.\n"
            f"They will need to rejoin all required binders to regain access."
        )

    else:
        await message.reply_text("❌ Unknown subcommand or missing parameters")
