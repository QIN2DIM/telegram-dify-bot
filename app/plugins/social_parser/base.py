# -*- coding: utf-8 -*-
"""
@Time    : 2025/8/2 08:30
@Author  : QIN2DIM
@GitHub  : https://github.com/QIN2DIM
@Desc    : Base classes for social media parsers
"""
from abc import ABC, abstractmethod
from typing import TypeVar, Generic, List, Dict, Any, Optional

from loguru import logger
from pydantic import BaseModel, Field


class BaseSocialPost(BaseModel):
    """Minimal base model for social media posts - only download results field"""

    # Download results field (excluded from serialization by default)
    download_results: List[Dict[str, Any]] | None = Field(default=None, exclude=True)

    @property
    def platform_name(self) -> str:
        """Platform name - to be implemented by subclasses"""
        return "unknown"


# Generic type variable bound to BaseSocialPost
T = TypeVar('T', bound=BaseSocialPost)


class BaseSocialParser(ABC, Generic[T]):
    """Abstract base class for social media parsers"""

    # Trigger signals to identify link types - can be string or list of strings
    trigger_signal: str | List[str] = ""

    # Platform identifier for file organization
    platform_id: str = "unknown"

    def __init__(self):
        """Initialize the parser"""
        pass

    @abstractmethod
    async def _parse(self, share_link: str, **kwargs) -> T | None:
        """
        Parse a share link and return post details

        Args:
            share_link: The social media share link
            **kwargs: Additional parameters

        Returns:
            Parsed post object or None if parsing failed
        """
        pass

    async def invoke(self, link: str, download: bool = False, **kwargs) -> T | None:
        """
        Unified interface for parsing social media content

        Note: Download functionality should be implemented by individual parsers
        if needed, as different platforms may have different download requirements.

        Args:
            link: Social media share link
            download: Whether to download resources (implementation-dependent)
            **kwargs: Additional parameters

        Returns:
            Parsed post object
        """
        return await self._parse(link, **kwargs)


class SocialParserRegistry:
    """Registry for managing multiple social media parsers"""

    def __init__(self):
        self._parsers: List[BaseSocialParser] = []

    def register(self, parser: BaseSocialParser) -> None:
        """Register a new social media parser"""
        if not parser.trigger_signal:
            raise ValueError(f"Parser {parser.__class__.__name__} must define trigger_signal")

        self._parsers.append(parser)

        # Log registration with all trigger signals
        if isinstance(parser.trigger_signal, list):
            signals = ", ".join(parser.trigger_signal)
            logger.info(f"Registered {parser.__class__.__name__} with triggers: [{signals}]")
        else:
            logger.info(
                f"Registered {parser.__class__.__name__} with trigger: {parser.trigger_signal}"
            )

    def get_parser(self, link: str) -> Optional[BaseSocialParser]:
        """Get the appropriate parser for a given link using improved matching"""
        for parser in self._parsers:
            # Handle both single string and list of strings
            if isinstance(parser.trigger_signal, list):
                # Check if any of the trigger signals match
                if any(signal in link for signal in parser.trigger_signal):
                    return parser
            else:
                # Legacy single string matching
                if parser.trigger_signal in link:
                    return parser
        return None

    def get_supported_platforms(self) -> List[str]:
        """Get list of supported platform names"""
        return [parser.platform_id for parser in self._parsers]

    def get_trigger_signals(self) -> List[str]:
        """Get list of all trigger signals for debugging"""
        signals = []
        for parser in self._parsers:
            if isinstance(parser.trigger_signal, list):
                signals.extend(parser.trigger_signal)
            else:
                signals.append(parser.trigger_signal)
        return signals


# Global registry instance
parser_registry = SocialParserRegistry()
