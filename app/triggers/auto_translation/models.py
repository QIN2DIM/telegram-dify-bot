# -*- coding: utf-8 -*-
"""
@Time    : 2025/7/14 00:45
@Author  : QIN2DIM
@GitHub  : https://github.com/QIN2DIM
@Desc    : 自动翻译功能的数据库模型
"""

from datetime import datetime, UTC

from sqlalchemy import Column, Integer, String, DateTime, Boolean, BigInteger
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class AutoTranslationSettings(Base):
    __tablename__ = "auto_translation_settings"

    id = Column(Integer, primary_key=True, index=True)
    chat_id = Column(BigInteger, nullable=False, unique=True)
    enabled = Column(Boolean, default=False, nullable=False)
    source_languages = Column(String, default="vi,ru", nullable=False)  # 逗号分隔的语言代码
    target_languages = Column(String, default="en,zh", nullable=False)  # 逗号分隔的语言代码
    created_at = Column(DateTime, default=datetime.now(UTC), nullable=False)
    updated_at = Column(
        DateTime, default=datetime.now(UTC), onupdate=datetime.now(UTC), nullable=False
    )

    def __repr__(self):
        return f"<AutoTranslationSettings(chat_id={self.chat_id}, enabled={self.enabled}, source_languages='{self.source_languages}', target_languages='{self.target_languages}')>"
