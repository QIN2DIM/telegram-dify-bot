# -*- coding: utf-8 -*-
"""
@Time    : 2025/8/2 01:42
@Author  : QIN2DIM
@GitHub  : https://github.com/QIN2DIM
@Desc    : yt-dlp universal fallback downloader for social media content
"""
import asyncio
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from pathlib import Path
from typing import List, Dict, Any, Optional
from urllib.parse import urlparse

from loguru import logger
from pydantic import Field
from yt_dlp import YoutubeDL

from plugins.social_parser.base import BaseSocialPost, BaseSocialParser
from settings import DATA_DIR, YT_DLP_COOKIES


class YtDlpPostDetail(BaseSocialPost):
    """Universal post detail model for yt-dlp supported content"""

    # Core fields
    id: str | None = Field(default="")
    title: str | None = Field(default="")
    desc: str | None = Field(default="")
    user_nickname: str | None = Field(default="")
    user_id: str | None = Field(default="")
    url: str | None = Field(default="")
    published_time: str | None = Field(default="")
    duration: int | float | None = Field(default=0)

    # yt-dlp specific fields
    extractor: str | None = Field(default="")
    format_id: str | None = Field(default="")
    width: int | None = Field(default=0)
    height: int | None = Field(default=0)
    filesize: int | None = Field(default=0)
    view_count: int | None = Field(default=0)
    like_count: int | None = Field(default=0)

    @property
    def platform_name(self) -> str:
        """Platform identifier based on extractor"""
        return self.extractor or "unknown"

    @classmethod
    def from_yt_dlp_info(cls, info_dict: Dict[str, Any]):
        """Create post-detail from yt-dlp info dictionary"""
        return cls(
            id=info_dict.get("id", ""),
            title=info_dict.get("title", ""),
            desc=info_dict.get("description", ""),
            user_nickname=info_dict.get("uploader", ""),
            user_id=info_dict.get("uploader_id", ""),
            url=info_dict.get("webpage_url", ""),
            published_time=info_dict.get("upload_date", ""),
            duration=info_dict.get("duration", 0),
            extractor=info_dict.get("extractor", ""),
            format_id=info_dict.get("format_id", ""),
            width=info_dict.get("width", 0),
            height=info_dict.get("height", 0),
            filesize=info_dict.get("filesize", 0),
            view_count=info_dict.get("view_count", 0),
            like_count=info_dict.get("like_count", 0),
        )


class YtDlpParser(BaseSocialParser[YtDlpPostDetail]):
    """Universal fallback parser using yt-dlp for any supported URL"""

    # As a fallback parser, it should match any URL that looks like a social media link
    trigger_signal = ["http://", "https://", "www.", ".com", ".net", ".org", ".tv", ".co"]
    platform_id = "yt-dlp"

    def __init__(self):
        super().__init__()
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="yt-dlp")

    @staticmethod
    def _extract_domain_from_url(url: str) -> Optional[str]:
        """Extract domain from URL for cookie file matching"""
        with suppress(Exception):
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            # Remove www. prefix if present
            if domain.startswith('www.'):
                domain = domain[4:]
            return domain

    @staticmethod
    def _find_cookie_file(url: str) -> Optional[Path]:
        """Find the appropriate cookie file based on URL domain"""
        domain = YtDlpParser._extract_domain_from_url(url)
        logger.debug(f"{domain=}")

        if not domain:
            return None

        # Define priority order for cookie file lookup
        # 1. Full domain match (e.g., twitter.com.cookie)
        # 2. Main domain match (e.g., twitter.cookie for twitter.com)
        # 3. Special cases (youtube.com -> youtube.cookie, youtu.be -> youtube.cookie)

        cookie_candidates = [YT_DLP_COOKIES / f"{domain}.cookie"]

        # Full domain match

        # Extract the main domain (without TLD) for simplified matching
        main_domain = domain.split('.')[0]
        if main_domain != domain:
            cookie_candidates.append(YT_DLP_COOKIES / f"{main_domain}.cookie")

        # Special cases mapping
        domain_mapping = {
            'youtu.be': 'youtube',
            'youtube.com': 'youtube',
            'bilibili.com': 'bilibili',
            'b23.tv': 'bilibili',  # Bilibili short link
            'twitter.com': 'twitter',
            'x.com': 'twitter',  # X (formerly Twitter)
            'instagram.com': 'instagram',
            'tiktok.com': 'tiktok',
        }

        if domain in domain_mapping:
            mapped_name = domain_mapping[domain]
            cookie_candidates.append(YT_DLP_COOKIES / f"{mapped_name}.cookie")

        # Check each candidate in order
        for cookie_path in cookie_candidates:
            if cookie_path.exists() and cookie_path.stat().st_size > 0:
                logger.info(f"Found cookie file for {domain}: {cookie_path.name}")
                return cookie_path

        return None

    @staticmethod
    def _get_yt_dlp_opts(
        download_dir: Path, extract_only: bool = False, url: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get yt-dlp configuration options with flexible cookie support"""
        opts = {}

        # Always try to load the appropriate cookie file when URL is provided
        # Some sites (like YouTube) require cookies even for info extraction
        if url:
            cookie_file = YtDlpParser._find_cookie_file(url)
            if cookie_file:
                opts['cookiefile'] = str(cookie_file)
                logger.info(f"Using cookie file: {cookie_file.name}")

        # Only add necessary options for a download path when actually downloading
        if not extract_only:
            opts['outtmpl'] = str(download_dir / '%(title)s-%(id)s.%(ext)s')

            # Prioritize a high-quality MP4 format for better Telegram compatibility
            # First try: Download the best MP4 video with best M4A audio
            # Fallback: Download best quality and convert to MP4
            opts['format'] = (
                'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/bestvideo+bestaudio/best'
            )
            opts['merge_output_format'] = 'mp4'

        return opts

    def _extract_info_sync(
        self, url: str, download_dir: Path, extract_only: bool = False
    ) -> Optional[Dict[str, Any]]:
        """Synchronous yt-dlp info extraction/download (runs in thread)"""
        # Pass URL to opt for cookie loading during download
        opts = self._get_yt_dlp_opts(download_dir, extract_only, url)

        try:
            with YoutubeDL(opts) as ydl:
                if extract_only:
                    info = ydl.extract_info(url, download=False)
                else:
                    info = ydl.extract_info(url, download=False)
                    ydl.download([url])
                return info
        except Exception as e:
            logger.error(f"yt-dlp failed to process {url}: {e}")
            return None

    async def _extract_info_async(
        self, url: str, download_dir: Path, extract_only: bool = False
    ) -> Optional[Dict[str, Any]]:
        """Async wrapper for yt-dlp operations"""
        loop = asyncio.get_event_loop()
        try:
            info = await loop.run_in_executor(
                self._executor, self._extract_info_sync, url, download_dir, extract_only
            )
            return info
        except Exception as e:
            logger.error(f"Async yt-dlp operation failed for {url}: {e}")
            return None

    def _collect_downloaded_files(
        self, download_dir: Path, info_dict: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Collect information about downloaded files"""
        results = []

        # Handle single file or playlist
        if 'entries' in info_dict:
            # Playlist
            for i, entry in enumerate(info_dict['entries']):
                if entry:
                    results.extend(self._collect_single_file_info(download_dir, entry, i))
        else:
            # Single file
            results.extend(self._collect_single_file_info(download_dir, info_dict, 0))

        return results

    @staticmethod
    def _collect_single_file_info(
        download_dir: Path, info_dict: Dict[str, Any], index: int
    ) -> List[Dict[str, Any]]:
        """Collect info for a single downloaded file"""
        results = []

        # Try to find the downloaded file
        video_id = info_dict.get('id', 'unknown')
        title = info_dict.get('title', 'untitled')

        # yt-dlp creates files with the pattern we specified in outtmpl
        # First try exact pattern match
        pattern_exact = f"{title}-{video_id}.*"
        matching_files = list(download_dir.glob(pattern_exact))

        # If no exact match, try with video_id only
        if not matching_files:
            pattern_id = f"*{video_id}*"
            matching_files = list(download_dir.glob(pattern_id))

        # If still no match, look for any video/audio files in the directory
        if not matching_files:
            video_extensions = ['.mp4', '.webm', '.mkv', '.avi', '.mov', '.flv', '.m4v']
            audio_extensions = ['.mp3', '.m4a', '.wav', '.flac', '.opus', '.ogg']
            all_extensions = video_extensions + audio_extensions

            for ext in all_extensions:
                matching_files.extend(download_dir.glob(f"*{ext}"))

        for file_path in matching_files:
            if file_path.suffix in ['.json', '.info', '.part']:
                continue  # Skip metadata and partial files

            file_size = file_path.stat().st_size if file_path.exists() else 0

            results.append(
                {
                    "success": True,
                    "url": info_dict.get('webpage_url', ''),
                    "local_path": str(file_path),
                    "file_size": file_size,
                    "index": index,
                    "error": None,
                    "skipped": False,
                    "title": title,
                    "format_id": info_dict.get('format_id', ''),
                }
            )

        # If no files found, mark as failed
        if not results:
            results.append(
                {
                    "success": False,
                    "url": info_dict.get('webpage_url', ''),
                    "local_path": None,
                    "file_size": 0,
                    "index": index,
                    "error": "Downloaded file not found",
                    "skipped": False,
                    "title": title,
                    "format_id": info_dict.get('format_id', ''),
                }
            )

        return results

    async def _parse(self, share_link: str, **kwargs) -> YtDlpPostDetail | None:
        """Parse URL and extract information without downloading"""
        # Create temporary directory for info extraction
        temp_dir = DATA_DIR / "temp" / "yt-dlp-info" / uuid.uuid4().hex[:8]
        temp_dir.mkdir(parents=True, exist_ok=True)

        try:
            # Extract info only (no download)
            info_dict = await self._extract_info_async(share_link, temp_dir, extract_only=True)

            if not info_dict:
                return None

            # Handle playlist case - use first entry for post-details
            if 'entries' in info_dict and info_dict['entries']:
                first_entry = next((entry for entry in info_dict['entries'] if entry), None)
                if first_entry:
                    return YtDlpPostDetail.from_yt_dlp_info(first_entry)
            else:
                return YtDlpPostDetail.from_yt_dlp_info(info_dict)

        except Exception as e:
            logger.error(f"Failed to parse URL with yt-dlp: {e}")
            return None
        finally:
            # Clean up temp directory
            with suppress(Exception):
                if temp_dir.exists():
                    import shutil

                    shutil.rmtree(temp_dir)

    async def _download_resources(self, post: YtDlpPostDetail, url: str) -> List[Dict[str, Any]]:
        """Download resources using yt-dlp"""
        try:
            # Create download directory
            post_id = post.id or uuid.uuid4().hex[:8]
            download_dir = DATA_DIR / "downloads" / self.platform_id / post_id
            download_dir.mkdir(parents=True, exist_ok=True)

            logger.info(f"Starting yt-dlp download for: {url}")

            # Extract and download
            info_dict = await self._extract_info_async(url, download_dir, extract_only=False)

            if not info_dict:
                return [
                    {
                        "success": False,
                        "url": url,
                        "local_path": None,
                        "file_size": 0,
                        "index": 0,
                        "error": "yt-dlp extraction failed",
                        "skipped": False,
                    }
                ]

            # Collect downloaded file information
            download_results = self._collect_downloaded_files(download_dir, info_dict)

            # Log summary
            successful_downloads = sum(1 for r in download_results if r["success"])
            total_size = sum(r["file_size"] for r in download_results if r["success"])

            total_size_mib = total_size / (1024 * 1024)
            logger.info(
                f"yt-dlp download complete: {successful_downloads}/{len(download_results)} successful, "
                f"total size: {total_size_mib:.2f} MiB"
            )

            return download_results

        except Exception as e:
            logger.error(f"yt-dlp download failed for {url}: {e}")
            return [
                {
                    "success": False,
                    "url": url,
                    "local_path": None,
                    "file_size": 0,
                    "index": 0,
                    "error": str(e),
                    "skipped": False,
                }
            ]

    async def invoke(self, link: str, download: bool = False, **kwargs) -> YtDlpPostDetail | None:
        """
        Unified interface for parsing and optionally downloading resources

        Args:
            link: URL to process
            download: Whether to download resources automatically
            **kwargs: Additional parameters

        Returns:
            Parsed post object with optional download results
        """
        post = await self._parse(link, **kwargs)

        if post and download:
            # Download resources and add results to post
            download_results = await self._download_resources(post, link)
            post.download_results = download_results

        return post

    def __del__(self):
        """Cleanup thread pool executor"""
        if hasattr(self, '_executor'):
            self._executor.shutdown(wait=False)
