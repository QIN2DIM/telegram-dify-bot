# -*- coding: utf-8 -*-
"""
@Time    : 2025/8/2 01:42
@Author  : QIN2DIM
@GitHub  : https://github.com/QIN2DIM
@Desc    : Social media parser registry and auto-registration
"""

from .base import parser_registry, BaseSocialParser, BaseSocialPost
from .xhs import XhsDownloader, XhsNoteDetail


# Auto-register all available parsers
def _register_parsers():
    """Register all available social media parsers"""
    parsers = [
        XhsDownloader(),
        # Add more parsers here as they are implemented
        # TikTokDownloader(),
        # WeiboDownloader(),
        # etc.
    ]

    for parser in parsers:
        parser_registry.register(parser)


# Initialize parsers on module import
_register_parsers()

# Export public API
__all__ = [
    "parser_registry",
    "BaseSocialParser",
    "BaseSocialPost",
    "XhsDownloader",
    "XhsNoteDetail",
]
