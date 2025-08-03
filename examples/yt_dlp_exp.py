# -*- coding: utf-8 -*-
"""
@Time    : 2025/8/3 23:52
@Author  : QIN2DIM
@GitHub  : https://github.com/QIN2DIM
@Desc    :
"""
from yt_dlp import YoutubeDL

from settings import settings

yt_opts = {"verbose": True, "cookiefile": str(settings.YT_DLP_COOKIES_BILIBILI.resolve())}

with YoutubeDL(yt_opts) as ydl:
    ydl.download("https://www.bilibili.com/bangumi/play/ep1633654")
