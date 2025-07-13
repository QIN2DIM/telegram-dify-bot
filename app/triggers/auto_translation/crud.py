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
                chat_id=chat_id, enabled=enabled, source_languages="vi,ru", target_languages="en,zh"
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


def get_auto_translation_config(chat_id: int) -> tuple[list[str], list[str]]:
    """获取聊天的自动翻译配置

    Returns:
        tuple: (source_languages, target_languages) 语言代码列表
    """
    settings_obj = get_auto_translation_settings(chat_id)
    if settings_obj:
        source_langs = [lang.strip() for lang in settings_obj.source_languages.split(",")]
        target_langs = [lang.strip() for lang in settings_obj.target_languages.split(",")]
        return source_langs, target_langs

    # 默认配置
    return ["vi", "ru"], ["en", "zh"]
