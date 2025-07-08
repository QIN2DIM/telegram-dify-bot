#!/usr/bin/env python
# pylint: disable=unused-argument
# This program is dedicated to the public domain under the CC0 license.

"""
Simple Bot to reply to Telegram messages.

First, a few handler functions are defined. Then, those functions are passed to
the Application and registered at their respective places.
Then, the bot is started and runs until we press Ctrl-C on the command line.

Usage:
Basic Echobot example, repeats messages.
Press Ctrl-C on the command line or send a signal to the process to stop the
bot.
"""
import asyncio
import json
import time
import uuid
from contextlib import suppress
from pathlib import Path
from typing import List

from loguru import logger
from telegram import Chat, PhotoSize
from telegram import ForceReply, Update, Message, Bot
from telegram.ext import CommandHandler, ContextTypes, MessageHandler, filters

from dify.workflow_tool import direct_translation_tool
from models import TaskType
from settings import settings, LOG_DIR
from utils import init_log, get_hello_reply

init_log(
    runtime=LOG_DIR.joinpath("runtime.log"),
    error=LOG_DIR.joinpath("error.log"),
    serialize=LOG_DIR.joinpath("serialize.log"),
)


data_dir = Path(__file__).parent / "data"
data_dir.mkdir(parents=True, exist_ok=True)

# 自动翻译模式状态管理（简单实现，生产环境应使用数据库）
auto_translation_enabled_chats = set()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued."""
    user = update.effective_user
    await update.message.reply_html(
        rf"Hi {user.mention_html()}!", reply_markup=ForceReply(selective=True)
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /help is issued."""
    await update.message.reply_text("Help!")


async def auto(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """开启自动翻译模式"""
    chat_id = update.effective_chat.id
    auto_translation_enabled_chats.add(chat_id)
    await update.message.reply_text("已开启自动翻译模式")


async def pause(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """暂停自动翻译模式"""
    chat_id = update.effective_chat.id
    auto_translation_enabled_chats.discard(chat_id)
    await update.message.reply_text("已暂停自动翻译模式")


def storage_messages_dataset(chat_type: str, effective_message: Message) -> None:
    """仅用于开发测试，程序运行稳定后移除"""

    preview_text = json.dumps(effective_message.to_dict(), indent=2, ensure_ascii=False)

    fp = data_dir.joinpath(f"{chat_type}_messages/{int(time.time())}.json")
    fp.parent.mkdir(parents=True, exist_ok=True)

    fp.write_text(preview_text, encoding="utf-8")
    logger.debug(f"echo message - {preview_text}")


def _is_available_direct_translation(
    chat: Chat, message: Message, bot: Bot, is_auto_trigger: bool = False
) -> TaskType | None:
    """
    判断是否需要进行直接翻译及翻译类型

    Args:
        chat: Telegram聊天对象
        message: 触发消息对象
        bot: 机器人对象
        is_auto_trigger: 是否为自动触发模式

    Returns:
        TaskType: 翻译任务类型，如果不需要翻译则返回None
    """
    # 1. 检查聊天是否在白名单中
    if chat.id not in settings.whitelist:
        return None

    # 2. 过滤机器人消息（如果需要的话）
    if message.from_user.is_bot:
        # 这里可以根据需要添加特殊逻辑
        # 比如频道消息等特殊情况的处理
        pass

    # 3. 检查是否为回复消息的情况
    if message.reply_to_message:
        reply_user = message.reply_to_message.from_user

        # 用户回复机器人消息，提出新的编辑需求
        if reply_user.is_bot and reply_user.username == bot.username:
            return TaskType.REPLAY

        # 用户在回复其他消息时提及机器人
        if _is_mention_bot(message, bot.username):
            return TaskType.MENTION_WITH_REPLY

    # 4. 非自动模式下，没有提及机器人且没有实体则不触发翻译
    if not is_auto_trigger and not message.entities:
        return None

    # 5. 检查是否直接提及机器人
    if _is_mention_bot(message, bot.username):
        return TaskType.MENTION

    # 6. 自动模式下，有文本内容或图片就可以翻译
    if is_auto_trigger and (message.text or message.photo or message.caption):
        return TaskType.AUTO

    return None


async def _download_photos_from_message(message: Message, bot: Bot) -> List[Path] | None:
    """
    从Telegram消息中下载照片到本地
    
    特性：
    - 自动选择最高质量的图片版本（最大file_size）
    - 生成唯一文件名避免冲突
    - 保持原始文件扩展名
    - 错误处理和日志记录
    
    Args:
        message: Telegram消息对象
        bot: 机器人对象
    
    Returns:
        List[Path]: 下载的图片文件路径列表，如果没有图片则返回None
    """
    if not message.photo:
        return None
    
    # 创建下载目录
    download_dir = data_dir / "downloads" / "photos"
    download_dir.mkdir(parents=True, exist_ok=True)
    
    downloaded_files = []
    
    # Telegram的photo字段是PhotoSize列表，包含不同尺寸的同一张图片
    # 我们选择最大尺寸的版本（file_size最大的）
    largest_photo = max(message.photo, key=lambda x: x.file_size or 0)
    
    try:
        # 获取文件对象
        file = await bot.get_file(largest_photo.file_id)
        
        # 生成唯一文件名
        file_extension = file.file_path.split('.')[-1] if file.file_path else 'jpg'
        unique_filename = f"{uuid.uuid4()}.{file_extension}"
        local_path = download_dir / unique_filename
        
        # 下载文件
        await file.download_to_drive(local_path)
        downloaded_files.append(local_path)
        
        logger.info(f"Downloaded photo: {local_path}")
        
    except Exception as e:
        logger.error(f"Failed to download photo {largest_photo.file_id}: {e}")
        
    return downloaded_files if downloaded_files else None


async def _download_multiple_photos_from_message(message: Message, bot: Bot) -> List[Path] | None:
    """
    处理包含多张图片的消息（如果消息包含多个媒体组）
    注意：单个消息的photo字段只包含一张图片的多个尺寸版本
    如果要处理真正的多张图片，需要处理media_group_id相同的多条消息
    
    Args:
        message: Telegram消息对象
        bot: 机器人对象
    
    Returns:
        List[Path]: 下载的图片文件路径列表
    """
    # 对于单条消息，直接调用单张图片下载函数
    return await _download_photos_from_message(message, bot)


def _is_mention_bot(message: Message, bot_username: str) -> bool:
    """
    检查消息是否提及了指定的机器人

    Args:
        message: Telegram消息对象
        bot_username: 机器人用户名

    Returns:
        bool: 如果提及了机器人则返回True
    """
    if not message.entities or not message.text:
        return False

    for entity in message.entities:
        if entity.type == "mention":
            # 提取@后的用户名
            mentioned_username = message.text[entity.offset + 1 : entity.offset + entity.length]
            if mentioned_username == bot_username:
                return True

    return False


async def _cleanup_old_photos(max_age_hours: int = 24) -> None:
    """
    清理超过指定时间的下载图片文件
    
    Args:
        max_age_hours: 文件最大保留时间（小时）
    """
    download_dir = data_dir / "downloads" / "photos"
    if not download_dir.exists():
        return
    
    current_time = time.time()
    max_age_seconds = max_age_hours * 3600
    
    cleaned_count = 0
    try:
        for photo_file in download_dir.iterdir():
            if photo_file.is_file():
                file_age = current_time - photo_file.stat().st_mtime
                if file_age > max_age_seconds:
                    photo_file.unlink()
                    cleaned_count += 1
        
        if cleaned_count > 0:
            logger.info(f"Cleaned up {cleaned_count} old photo files")
            
    except Exception as e:
        logger.error(f"Failed to cleanup old photos: {e}")


async def translation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    处理翻译请求，支持文本和图片
    
    功能特性：
    - 支持四种任务类型：MENTION, MENTION_WITH_REPLY, REPLAY, AUTO
    - 自动下载并处理图片（选择最高质量版本）
    - 处理引用消息中的文本和图片内容
    - 根据任务类型采用不同的回复策略
    - 自动清理过期的临时图片文件
    - 完整的错误处理和日志记录
    """
    chat = update.effective_chat
    trigger_message = update.effective_message

    # 定期清理旧的下载图片（每次处理时都尝试清理）
    with suppress(Exception):
        await _cleanup_old_photos(max_age_hours=24)

    # todo: remove
    with suppress(Exception):
        storage_messages_dataset(chat.type, trigger_message)

    # 检查当前聊天是否启用了自动翻译模式
    is_auto_mode = chat.id in auto_translation_enabled_chats

    task_type = _is_available_direct_translation(
        chat, trigger_message, context.bot, is_auto_trigger=is_auto_mode
    )
    if not task_type or not isinstance(task_type, TaskType):
        return

    placeholder_message = None

    if task_type == TaskType.MENTION:
        # 提及我，但没有输入任何内容且没有图片
        real_text = (trigger_message.text or "").replace(f"@{context.bot.username}", "")
        if not real_text.strip() and not trigger_message.photo and not trigger_message.caption:
            await trigger_message.reply_text(get_hello_reply())
            return
        # MENTION: 回复被@的消息
        placeholder_message = await trigger_message.reply_text("> 正在处理...")
    elif task_type == TaskType.MENTION_WITH_REPLY:
        # MENTION_WITH_REPLY: 回复被@的消息（用户引用材料并@机器人）
        placeholder_message = await trigger_message.reply_text("> 正在分析并处理...")
    elif task_type == TaskType.REPLAY:
        # REPLAY: 不回复消息，而是mention用户
        placeholder_message = await context.bot.send_message(
            chat_id=chat.id,
            text=f"@{trigger_message.from_user.username or trigger_message.from_user.first_name} 正在处理您的新需求...",
        )
    elif task_type == TaskType.AUTO:
        # AUTO: 直接发在群里，不打扰任何人，不使用placeholder
        pass

    # AUTO模式下不需要placeholder，直接处理
    if task_type != TaskType.AUTO and not placeholder_message:
        return

    # 准备用户信息
    from_user_fmt = "Anonymous"
    if trigger_message.sender_chat:
        _user = trigger_message.sender_chat
        from_user_fmt = f"{_user.username}({_user.id})"
    elif trigger_message.from_user:
        _user = trigger_message.from_user
        from_user_fmt = f"{_user.username}({_user.id})"

    # 处理消息内容和图片
    message_text = trigger_message.text or trigger_message.caption or ""
    
    # 处理引用消息的内容（MENTION_WITH_REPLY情况）
    if task_type == TaskType.MENTION_WITH_REPLY and trigger_message.reply_to_message:
        reply_text = trigger_message.reply_to_message.text or trigger_message.reply_to_message.caption or ""
        if reply_text:
            # 将引用消息的内容添加到上下文中
            message_text = f"用户消息: {message_text}\n\n引用的内容: {reply_text}" if message_text else f"引用的内容: {reply_text}"
    
    # 下载图片（如果有的话）
    photo_paths = None
    if trigger_message.photo:
        try:
            photo_paths = await _download_photos_from_message(trigger_message, context.bot)
            if photo_paths:
                logger.info(f"Downloaded {len(photo_paths)} photos for translation")
        except Exception as e:
            logger.error(f"Failed to download photos: {e}")

    # 处理引用消息中的图片（MENTION_WITH_REPLY情况）
    if task_type == TaskType.MENTION_WITH_REPLY and trigger_message.reply_to_message:
        if trigger_message.reply_to_message.photo:
            try:
                reply_photo_paths = await _download_photos_from_message(trigger_message.reply_to_message, context.bot)
                if reply_photo_paths:
                    photo_paths = (photo_paths or []) + reply_photo_paths
                    logger.info(f"Downloaded {len(reply_photo_paths)} photos from replied message")
            except Exception as e:
                logger.error(f"Failed to download photos from replied message: {e}")

    result = await direct_translation_tool(
        message_context=message_text or "请分析这张图片",
        from_user=from_user_fmt,
        with_files=photo_paths
    )
    outputs_json = json.dumps(
        result.data.outputs.model_dump(mode="json"), ensure_ascii=False, indent=2
    )
    result_text = f"```json\n{outputs_json}\n```"

    # 根据不同的task_type采用不同的回复方式
    if task_type == TaskType.MENTION or task_type == TaskType.MENTION_WITH_REPLY:
        # MENTION 和 MENTION_WITH_REPLY: 删除placeholder并回复原消息
        if placeholder_message:
            await placeholder_message.delete()
        await trigger_message.reply_text(result_text, parse_mode="Markdown")

    elif task_type == TaskType.REPLAY:
        # REPLAY: 删除placeholder并mention用户回复
        if placeholder_message:
            await placeholder_message.delete()
        user_mention = (
            f"@{trigger_message.from_user.username}"
            if trigger_message.from_user.username
            else trigger_message.from_user.mention_markdown_v2()
        )
        final_text = f"{user_mention}\n\n{result_text}"
        await context.bot.send_message(chat_id=chat.id, text=final_text, parse_mode="Markdown")

    elif task_type == TaskType.AUTO:
        # AUTO: 直接发在群里，不打扰任何人
        await context.bot.send_message(chat_id=chat.id, text=result_text, parse_mode="Markdown")


def main() -> None:
    """Start the bot."""
    sp = settings.model_dump(mode='json')

    s = json.dumps(sp, indent=2, ensure_ascii=False)
    logger.success(f"Loading settings: {s}")

    # Create the Application and pass it your bot's token.
    application = settings.get_default_application()

    # on different commands - answer in Telegram
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("auto", auto))
    application.add_handler(CommandHandler("pause", pause))

    # on non command i.e message - echo the message on Telegram
    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, translation))

    # Run the bot until the user presses Ctrl-C
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
