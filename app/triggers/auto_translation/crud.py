# -*- coding: utf-8 -*-
"""
@Time    : 2025/7/14 00:45
@Author  : QIN2DIM
@GitHub  : https://github.com/QIN2DIM
@Desc    : 自动翻译功能的数据库操作
"""

from datetime import datetime, UTC
from typing import Optional

from loguru import logger
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from settings import settings
from .models import Base, AutoTranslationSettings

# 创建数据库引擎
engine = create_engine(settings.DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_database():
    """初始化数据库表"""
    try:
        Base.metadata.create_all(bind=engine)
        logger.success("自动翻译数据库表初始化成功")
    except Exception as e:
        logger.error(f"自动翻译数据库表初始化失败: {e}")
        raise


def get_db_session() -> Session:
    """获取数据库会话"""
    return SessionLocal()


def get_auto_translation_settings(chat_id: int) -> Optional[AutoTranslationSettings]:
    """获取聊天的自动翻译设置"""
    session = get_db_session()
    try:
        return (
            session.query(AutoTranslationSettings)
            .filter(AutoTranslationSettings.chat_id == chat_id)
            .first()
        )
    finally:
        session.close()


def set_auto_translation_enabled(chat_id: int, enabled: bool) -> AutoTranslationSettings:
    """设置聊天的自动翻译开关"""
    session = get_db_session()
    try:
        # 查找已有设置
        settings_obj = (
            session.query(AutoTranslationSettings)
            .filter(AutoTranslationSettings.chat_id == chat_id)
            .first()
        )

        if settings_obj:
            # 更新现有设置
            settings_obj.enabled = enabled
            settings_obj.updated_at = datetime.now(UTC)
        else:
            # 创建新设置
            settings_obj = AutoTranslationSettings(
                chat_id=chat_id, enabled=enabled, languages="zh,en,ru"
            )
            session.add(settings_obj)

        session.commit()
        session.refresh(settings_obj)
        logger.info(f"已设置聊天 {chat_id} 的自动翻译状态: {enabled}")
        return settings_obj
    except Exception as e:
        session.rollback()
        logger.error(f"设置自动翻译状态失败: {e}")
        raise
    finally:
        session.close()


def is_auto_translation_enabled(chat_id: int) -> bool:
    """检查聊天是否启用了自动翻译"""
    settings_obj = get_auto_translation_settings(chat_id)
    return settings_obj.enabled if settings_obj else False


def get_auto_translation_config(chat_id: int) -> list[str]:
    """获取聊天的自动翻译语言池配置

    Returns:
        list[str]: 语言代码列表
    """
    settings_obj = get_auto_translation_settings(chat_id)
    if settings_obj:
        languages = [lang.strip() for lang in settings_obj.languages.split(",")]
        return languages

    # 默认配置：简体中文、英文、俄语
    return ["zh", "en", "ru"]


def update_last_message_time(chat_id: int) -> None:
    """更新聊天的最后消息时间"""
    session = get_db_session()
    try:
        settings_obj = (
            session.query(AutoTranslationSettings)
            .filter(AutoTranslationSettings.chat_id == chat_id)
            .first()
        )

        if settings_obj:
            settings_obj.last_message_time = datetime.now(UTC)
            settings_obj.updated_at = datetime.now(UTC)
            session.commit()
            logger.debug(f"已更新聊天 {chat_id} 的最后消息时间")
    except Exception as e:
        session.rollback()
        logger.error(f"更新最后消息时间失败: {e}")
        raise
    finally:
        session.close()


def get_chats_for_auto_shutdown(timeout_minutes: int = 10) -> list[int]:
    """获取需要自动关闭的聊天列表

    Args:
        timeout_minutes: 超时时间（分钟）

    Returns:
        list[int]: 需要关闭的聊天ID列表
    """
    session = get_db_session()
    try:
        from datetime import timedelta

        cutoff_time = datetime.now(UTC) - timedelta(minutes=timeout_minutes)

        # 查找启用了自动翻译且最后消息时间超过超时时间的聊天
        settings_list = (
            session.query(AutoTranslationSettings)
            .filter(
                AutoTranslationSettings.enabled is True,
                AutoTranslationSettings.last_message_time < cutoff_time,
            )
            .all()
        )

        return [settings.chat_id for settings in settings_list]
    finally:
        session.close()


def auto_disable_translation_for_chat(chat_id: int) -> bool:
    """自动关闭指定聊天的翻译功能

    Args:
        chat_id: 聊天ID

    Returns:
        bool: 是否成功关闭
    """
    try:
        set_auto_translation_enabled(chat_id, False)
        logger.info(f"已自动关闭聊天 {chat_id} 的翻译功能（超时无消息）")
        return True
    except Exception as e:
        logger.error(f"自动关闭聊天 {chat_id} 的翻译功能失败: {e}")
        return False
