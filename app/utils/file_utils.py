# -*- coding: utf-8 -*-
"""
File utility functions for handling file sizes and media types
"""
from pathlib import Path
from typing import Literal

# Media type constants
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tiff'}
VIDEO_EXTENSIONS = {'.mp4', '.avi', '.mov', '.mkv', '.webm', '.m4v', '.3gp', '.flv'}

MediaType = Literal['photo', 'video', 'document']


def format_file_size(size_bytes: int) -> str:
    """Format file size in bytes to human-readable string"""
    if size_bytes >= 1024 * 1024 * 1024:  # >= 1GB
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GiB"
    elif size_bytes >= 1024 * 1024:  # >= 1MB
        return f"{size_bytes / (1024 * 1024):.2f} MiB"
    elif size_bytes >= 1024:  # >= 1KB
        return f"{size_bytes / 1024:.2f} KiB"
    else:
        return f"{size_bytes} B"


def get_media_type(file_path: str) -> MediaType:
    """Determine media type from file extension"""
    extension = Path(file_path).suffix.lower()

    if extension in IMAGE_EXTENSIONS:
        return 'photo'
    elif extension in VIDEO_EXTENSIONS:
        return 'video'
    else:
        return 'document'


def get_file_extension_display(file_path: str) -> str:
    """Get file extension in uppercase for display"""
    extension = Path(file_path).suffix.upper().lstrip('.')
    return extension or 'FILE'
