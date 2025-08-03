# -*- coding: utf-8 -*-
"""
@Time    : 2025/8/2 01:42
@Author  : QIN2DIM
@GitHub  : https://github.com/QIN2DIM
@Desc    : Social media parser registry and auto-registration
"""

from .base import parser_registry, BaseSocialParser, BaseSocialPost
from .xhs_parser import XhsDownloader, XhsNoteDetail
from .fallback_parser import YtDlpParser, YtDlpPostDetail


# Auto-register all available parsers
def _register_parsers():
    """Register all available social media parsers"""
    # Specific parsers first (higher priority)
    specific_parsers = [
        XhsDownloader(),
        # Add more specific parsers here as they are implemented
        # TikTokDownloader(),
        # WeiboDownloader(),
        # etc.
    ]

    # Fallback parsers last (lower priority)
    fallback_parsers = [YtDlpParser()]  # Universal fallback using yt-dlp

    # Register specific parsers first
    for parser in specific_parsers:
        parser_registry.register(parser, is_fallback=False)

    # Register fallback parsers last
    for parser in fallback_parsers:
        parser_registry.register(parser, is_fallback=True)


# Initialize parsers on module import
_register_parsers()

# Export public API
__all__ = [
    "parser_registry",
    "BaseSocialParser",
    "BaseSocialPost",
    "XhsDownloader",
    "XhsNoteDetail",
    "YtDlpParser",
    "YtDlpPostDetail",
]
