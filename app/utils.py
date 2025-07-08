# -*- coding: utf-8 -*-
# Time       : 2023/8/19 17:19
# Author     : QIN2DIM
# GitHub     : https://github.com/QIN2DIM
# Description:
from __future__ import annotations

import os
import sys
import random
from typing import List
from zoneinfo import ZoneInfo

from loguru import logger


def timezone_filter(record):
    """为日志记录添加东八区时区信息"""
    record["time"] = record["time"].astimezone(ZoneInfo("Asia/Shanghai"))
    return record


def init_log(**sink_channel):
    # 从环境变量中读取日志级别，默认值为 "DEBUG"
    log_level = os.getenv("LOG_LEVEL", "DEBUG").upper()

    persistent_format = (
        "<g>{time:YYYY-MM-DD HH:mm:ss}</g> | "
        "<lvl>{level}</lvl>    | "
        "<c><u>{name}</u></c>:{function}:{line} | "
        "{message} - "
        "{extra}"
    )
    stdout_format = (
        "<g>{time:YYYY-MM-DD HH:mm:ss}</g> | "
        "<lvl>{level:<8}</lvl>    | "
        "<c>{name}</c>:<c>{function}</c>:<c>{line}</c> | "
        "<n>{message}</n>"
    )

    # 配置 loguru 日志记录器
    logger.remove()
    logger.add(
        sink=sys.stdout,
        colorize=True,
        level=log_level,
        format=stdout_format,
        diagnose=False,
        filter=timezone_filter,
    )
    if sink_channel.get("error"):
        logger.add(
            sink=sink_channel.get("error"),
            level="ERROR",
            rotation="5 MB",
            retention="7 days",
            encoding="utf8",
            diagnose=False,
            filter=timezone_filter,
        )
    if sink_channel.get("runtime"):
        logger.add(
            sink=sink_channel.get("runtime"),
            level="TRACE",
            rotation="5 MB",
            retention="7 days",
            encoding="utf8",
            diagnose=False,
            filter=timezone_filter,
        )
    if sink_channel.get("serialize"):
        logger.add(
            sink=sink_channel.get("serialize"),
            level="DEBUG",
            format=persistent_format,
            encoding="utf8",
            diagnose=False,
            serialize=True,
            filter=timezone_filter,
        )
    return logger


hello_replies: List[str] = [
    "Hey! 👋 Welcome—I'm here to help. 😊\nWhat can I do for you today? Whether it’s a question, an idea, or you just want to chat, I’m all ears! 💬❤️‍🔥",
    "Hi there!",
    "Hey! 👋",
    "Hi! 😊",
    "What's up?",
    "Good to see you!",
    "Hey there!",
    "Howdy!",
    "Hi! 👀",
    "Hello hello!",
    "Yo! (^_^)",
    "你好！",
    "嗨！✨",
    "Hello! 🌟",
    "Hey hey!",
    "Hi friend!",
    "Greetings!",
    "Hiya!",
    "Well hello!",
    "Hey you! 😄",
    "Hi hi!",
    "Hello world!",
    "嗨呀！",
    "Sup!",
    "Oh hi!",
    "Hello beautiful!",
    "Hey buddy!",
    "Hi stranger!",
    "Hello sunshine! ☀️",
    "Hellow~ 🎵",
    "Hey! Nice to meet you! 🤝",
]


def get_hello_reply():
    return random.choice(hello_replies)
