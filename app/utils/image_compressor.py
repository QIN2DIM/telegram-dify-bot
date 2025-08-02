# -*- coding: utf-8 -*-
"""
@Time    : 2025/1/10
@Author  : Assistant
@Desc    : Image compression utility for Telegram Bot
"""

import os
import tempfile
from pathlib import Path
from typing import Optional, Tuple
from PIL import Image, ImageOps
from loguru import logger


class ImageCompressor:
    """High-quality image compressor for Telegram Bot media"""

    # Telegram limits
    TELEGRAM_PHOTO_SIZE_LIMIT = 10 * 1024 * 1024  # 10MB

    # Compression settings
    DEFAULT_QUALITY = 85
    MIN_QUALITY = 60
    MAX_DIMENSION = 2560  # Max width/height for high quality

    @staticmethod
    def get_file_size(file_path: str) -> int:
        """Get file size in bytes"""
        try:
            return os.path.getsize(file_path)
        except (OSError, FileNotFoundError):
            return 0

    @staticmethod
    def needs_compression(file_path: str) -> bool:
        """Check if image needs compression based on Telegram limits"""
        return ImageCompressor.get_file_size(file_path) > ImageCompressor.TELEGRAM_PHOTO_SIZE_LIMIT

    @staticmethod
    def get_optimal_dimensions(width: int, height: int, max_dimension: int) -> Tuple[int, int]:
        """Calculate optimal dimensions while maintaining aspect ratio"""
        if width <= max_dimension and height <= max_dimension:
            return width, height

        # Calculate scaling factor
        scale_factor = min(max_dimension / width, max_dimension / height)
        new_width = int(width * scale_factor)
        new_height = int(height * scale_factor)

        # Ensure dimensions are even numbers for better compatibility
        new_width = new_width if new_width % 2 == 0 else new_width - 1
        new_height = new_height if new_height % 2 == 0 else new_height - 1

        return max(new_width, 1), max(new_height, 1)

    @classmethod
    def compress_image(
        cls,
        input_path: str,
        output_path: Optional[str] = None,
        target_size: Optional[int] = None,
        preserve_transparency: bool = True,
    ) -> Optional[str]:
        """
        Compress image to meet Telegram size requirements while maintaining high quality

        Args:
            input_path: Path to input image
            output_path: Path for output image (if None, creates temp file)
            target_size: Target file size in bytes (default: TELEGRAM_PHOTO_SIZE_LIMIT)
            preserve_transparency: Whether to preserve transparency (convert to JPG if False)

        Returns:
            Path to compressed image or None if compression failed
        """
        try:
            input_path = Path(input_path)
            if not input_path.exists():
                logger.error(f"Input image file not found: {input_path}")
                return None

            # Set target size
            if target_size is None:
                target_size = cls.TELEGRAM_PHOTO_SIZE_LIMIT

            # Check if compression is needed
            if not cls.needs_compression(str(input_path)):
                logger.debug(f"Image {input_path.name} doesn't need compression")
                return str(input_path)

            # Open and process image
            with Image.open(input_path) as img:
                # Auto-rotate based on EXIF data
                img = ImageOps.exif_transpose(img)

                # Get image info
                original_format = img.format
                width, height = img.size
                has_transparency = img.mode in ('RGBA', 'LA') or 'transparency' in img.info

                logger.info(
                    f"Original image: {width}x{height}, format: {original_format}, "
                    f"size: {cls.get_file_size(str(input_path)) / 1024 / 1024:.1f}MB"
                )

                # Determine output format and setup
                if has_transparency and preserve_transparency:
                    output_format = 'PNG'
                    save_kwargs = {'optimize': True}
                    file_extension = '.png'
                else:
                    output_format = 'JPEG'
                    # Convert to RGB if necessary
                    if img.mode in ('RGBA', 'LA', 'P'):
                        # Create white background for transparent images
                        background = Image.new('RGB', img.size, (255, 255, 255))
                        if img.mode == 'P':
                            img = img.convert('RGBA')
                        background.paste(
                            img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None
                        )
                        img = background
                    elif img.mode != 'RGB':
                        img = img.convert('RGB')

                    save_kwargs = {'optimize': True, 'progressive': True}
                    file_extension = '.jpg'

                # Create output path
                if output_path is None:
                    temp_dir = tempfile.mkdtemp()
                    output_path = os.path.join(
                        temp_dir, f"compressed_{input_path.stem}{file_extension}"
                    )

                # Try different compression strategies
                compressed_path = cls._compress_with_strategies(
                    img, output_path, output_format, save_kwargs, target_size
                )

                if compressed_path:
                    final_size = cls.get_file_size(compressed_path)
                    compression_ratio = (1 - final_size / cls.get_file_size(str(input_path))) * 100
                    logger.info(
                        f"Compressed image: {Path(compressed_path).name}, "
                        f"size: {final_size / 1024 / 1024:.1f}MB "
                        f"({compression_ratio:.1f}% reduction)"
                    )
                    return compressed_path
                else:
                    logger.error("All compression strategies failed")
                    return None

        except Exception as e:
            logger.error(f"Image compression failed: {e}")
            return None

    @classmethod
    def _compress_with_strategies(
        cls,
        img: Image.Image,
        output_path: str,
        output_format: str,
        save_kwargs: dict,
        target_size: int,
    ) -> Optional[str]:
        """Try different compression strategies until target size is met"""

        strategies = [
            # Strategy 1: High quality with optimal dimensions
            {
                'max_dimension': cls.MAX_DIMENSION,
                'quality': cls.DEFAULT_QUALITY,
                'description': 'high quality with optimal dimensions',
            },
            # Strategy 2: Reduce dimensions more aggressively
            {
                'max_dimension': 1920,
                'quality': cls.DEFAULT_QUALITY,
                'description': 'reduced dimensions (1920px)',
            },
            # Strategy 3: Further reduce dimensions
            {
                'max_dimension': 1280,
                'quality': cls.DEFAULT_QUALITY,
                'description': 'smaller dimensions (1280px)',
            },
            # Strategy 4: Lower quality with medium dimensions
            {'max_dimension': 1920, 'quality': 75, 'description': 'medium quality'},
            # Strategy 5: Lower quality with small dimensions
            {'max_dimension': 1280, 'quality': 70, 'description': 'lower quality, smaller size'},
            # Strategy 6: Minimum acceptable quality
            {'max_dimension': 1024, 'quality': cls.MIN_QUALITY, 'description': 'minimum quality'},
        ]

        for i, strategy in enumerate(strategies, 1):
            try:
                # Calculate optimal dimensions
                width, height = img.size
                new_width, new_height = cls.get_optimal_dimensions(
                    width, height, strategy['max_dimension']
                )

                # Resize if needed
                if (new_width, new_height) != (width, height):
                    # Use high-quality resampling
                    resized_img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                else:
                    resized_img = img

                # Prepare save arguments
                current_save_kwargs = save_kwargs.copy()
                if output_format == 'JPEG':
                    current_save_kwargs['quality'] = strategy['quality']

                # Save with current strategy
                resized_img.save(output_path, format=output_format, **current_save_kwargs)

                # Check file size
                file_size = cls.get_file_size(output_path)

                logger.debug(
                    f"Strategy {i} ({strategy['description']}): "
                    f"{new_width}x{new_height}, "
                    f"size: {file_size / 1024 / 1024:.1f}MB"
                )

                if file_size <= target_size:
                    logger.info(
                        f"Compression successful with strategy {i}: {strategy['description']}"
                    )
                    return output_path

            except Exception as e:
                logger.warning(f"Compression strategy {i} failed: {e}")
                continue

        return None

    @classmethod
    def compress_image_smart(cls, file_path: str) -> str:
        """
        Smart compression that returns the best compressed version or original file

        Args:
            file_path: Path to image file

        Returns:
            Path to compressed image (or original if compression not needed/failed)
        """
        if not cls.needs_compression(file_path):
            return file_path

        compressed_path = cls.compress_image(file_path)
        return compressed_path if compressed_path else file_path


def compress_image_for_telegram(file_path: str) -> str:
    """
    Convenience function for compressing images for Telegram

    Args:
        file_path: Path to image file

    Returns:
        Path to compressed image (or original if compression not needed/failed)
    """
    return ImageCompressor.compress_image_smart(file_path)
