# -*- coding: utf-8 -*-
"""
@Time    : 2025/7/9 00:44
@Author  : QIN2DIM
@GitHub  : https://github.com/QIN2DIM
@Desc    :
"""
import json
import time
import uuid
from pathlib import Path
from typing import List

from loguru import logger
from telegram import Message, Chat, Bot

from models import TaskType
from settings import DATA_DIR, settings


def storage_messages_dataset(chat_type: str, effective_message: Message) -> None:
    """仅用于开发测试，程序运行稳定后移除"""

    preview_text = json.dumps(effective_message.to_dict(), indent=2, ensure_ascii=False)

    fp = DATA_DIR.joinpath(f"{chat_type}_messages/{int(time.time())}.json")
    fp.parent.mkdir(parents=True, exist_ok=True)

    fp.write_text(preview_text, encoding="utf-8")
    # logger.debug(f"echo message - {preview_text}")


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
    download_dir = DATA_DIR / "downloads" / "photos"
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
    # 提取@后的用户名
    for entity in message.entities:
        if entity.type == "mention":
            mentioned_username = message.text[entity.offset + 1 : entity.offset + entity.length]
            if mentioned_username == bot_username:
                return True

    for entity in message.caption_entities:
        if entity.type == "mention":
            mentioned_username = message.caption[entity.offset + 1 : entity.offset + entity.length]
            if mentioned_username == bot_username:
                return True

    return False


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
    if not is_auto_trigger and not message.entities and not message.caption_entities:
        logger.debug("[IGNORE] 非自动模式下，没有提及机器人且没有实体则不触发翻译")
        return None

    # 5. 检查是否直接提及机器人
    if _is_mention_bot(message, bot.username):
        return TaskType.MENTION

    # 6. 自动模式下，有文本内容或图片就可以翻译
    if is_auto_trigger and (message.text or message.photo or message.caption):
        return TaskType.AUTO

    logger.debug("[IGNORE] unknown type message")
    return None


def _cleanup_old_photos(max_age_hours: int = 24) -> None:
    """
    清理超过指定时间的下载图片文件

    Args:
        max_age_hours: 文件最大保留时间（小时）
    """
    download_dir = DATA_DIR / "downloads" / "photos"
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
