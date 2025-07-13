# -*- coding: utf-8 -*-
"""
@Time    : 2025/7/14 00:45
@Author  : QIN2DIM
@GitHub  : https://github.com/QIN2DIM
@Desc    : 自动翻译功能模块
"""

from .node import (
    enable_auto_translation,
    disable_auto_translation,
    get_auto_translation_status,
    process_auto_translation,
    check_should_auto_translate,
    start_auto_shutdown_task,
)

__all__ = [
    "enable_auto_translation",
    "disable_auto_translation",
    "get_auto_translation_status",
    "process_auto_translation",
    "check_should_auto_translate",
    "start_auto_shutdown_task",
]
