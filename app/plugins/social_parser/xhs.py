# -*- coding: utf-8 -*-
"""
@Time    : 2025/8/2 01:42
@Author  : QIN2DIM
@GitHub  : https://github.com/QIN2DIM
@Desc    : XHS (Xiaohongshu) social media parser implementation
"""
import uuid
from typing import List, Dict, Any

import httpx
from httpx import AsyncClient
from pydantic import Field
from loguru import logger

from settings import settings, DATA_DIR
from .base import BaseSocialPost, BaseSocialParser


class XhsNoteDetail(BaseSocialPost):
    """XHS (Xiaohongshu) note detail model"""

    # Core fields
    id: str | None = Field(default="")
    type: str | None = Field(default="")
    title: str | None = Field(default="")
    desc: str | None = Field(default="")
    user_nickname: str | None = Field(default="")
    user_id: str | None = Field(default="")
    url: str | None = Field(default="")
    published_time: str | None = Field(default="")
    resource_list: List[str] | None = Field(default_factory=list)

    # XHS-specific fields
    last_update_time: str | None = Field(default="")
    live_photo_list: List[str] | None = Field(default_factory=list)

    @property
    def user_link(self) -> str:
        """Return XHS user profile link"""
        return f"https://www.xiaohongshu.com/user/profile/{self.user_id}"

    @property
    def platform_name(self) -> str:
        """Platform identifier"""
        return "小红书"

    @classmethod
    def from_response_json(cls, response: httpx.Response):
        response.raise_for_status()
        result = response.json()
        data = result["data"]

        note_type = "video" if data.get("作品类型", "") == "视频" else "normal"

        return cls(
            id=data.get("作品ID", ""),
            type=note_type,
            title=data.get("作品标题", ""),
            last_update_time=data.get("最后更新时间", ""),
            desc=data.get("作品描述", ""),
            user_nickname=data.get("作者昵称", ""),
            user_id=data.get("作者ID", ""),
            url=data.get("作品链接", ""),
            published_time=data.get("发布时间", ""),
            resource_list=[i for i in filter(None, data.get("下载地址"))],
            live_photo_list=[i for i in filter(None, data.get("动图地址", []))],
        )


class XhsDownloader(BaseSocialParser[XhsNoteDetail]):
    """XHS (Xiaohongshu) content parser and downloader"""

    # Support multiple XHS link formats
    trigger_signal = [
        "https://www.xiaohongshu.com/",
        "https://xhslink.com/",
        "http://xhslink.com/",
        "xiaohongshu.com",
        "xhslink.com",
    ]
    platform_id = "xhs"

    def __init__(self):
        super().__init__()
        self._client = AsyncClient(
            base_url=settings.XHS_DOWNLOADER_BASE_URL, timeout=settings.XHS_CONNECTION_TIMEOUT
        )

    async def _parse(self, share_link: str, **kwargs) -> XhsNoteDetail | None:
        payload = {"url": share_link}
        response = await self._client.post("/xhs/detail", json=payload)
        return XhsNoteDetail.from_response_json(response)

    def _extract_resource_id(self, url: str) -> str:
        """
        Extract unique resource ID from XHS download URL

        Args:
            url: XHS resource download URL

        Returns:
            Unique resource identifier from URL path
        """
        try:
            # Extract the last part of the URL path as unique ID
            # Example: https://sns-video-bd.xhscdn.com/spectrum/1040g35031kffbsjs3q105n1klh0hq7js7mbn6io
            # Returns: 1040g35031kffbsjs3q105n1klh0hq7js7mbn6io
            from urllib.parse import urlparse

            parsed_url = urlparse(url)
            path_parts = parsed_url.path.strip('/').split('/')
            if path_parts:
                return path_parts[-1]
            else:
                # Fallback to last part of URL if no path
                return url.split('/')[-1] if '/' in url else url
        except Exception as e:
            logger.debug(f"Failed to extract resource ID from URL {url}: {e}")
            # Fallback to UUID if extraction fails
            return uuid.uuid4().hex[:16]

    def _get_file_extension(
        self, note_type: str, content_disposition: str | None = None, url: str = ""
    ) -> str:
        """
        Determine file extension based on note type and HTTP headers

        Args:
            note_type: Note type ("video" or "normal")
            content_disposition: Content-Disposition header from response
            url: The download URL as fallback

        Returns:
            File extension string
        """
        # Try to extract filename from Content-Disposition header first
        if content_disposition:
            try:
                # Parse Content-Disposition: attachment; filename="example.jpg"
                if 'filename=' in content_disposition:
                    filename_part = content_disposition.split('filename=')[1]
                    # Remove quotes if present
                    filename = filename_part.strip('"\'')
                    if '.' in filename:
                        return filename.split('.')[-1].lower()
            except Exception as e:
                logger.debug(f"Failed to parse Content-Disposition: {e}")

        # Fall back to note type-based extension
        if note_type == "video":
            return "mp4"
        else:
            return "jpg"  # Default for normal notes (images)

    async def _download_single_resource(
        self, download_url: str, post: XhsNoteDetail, index: int
    ) -> Dict[str, Any]:
        """
        Download a single resource from URL

        Args:
            download_url: The URL to download from
            post: The XHS note containing type information
            index: Resource index for file naming

        Returns:
            Dict containing download result info
        """
        try:
            # Create download directory
            post_id = post.id or uuid.uuid4().hex[:8]
            download_dir = DATA_DIR / "downloads" / self.platform_id / post_id
            download_dir.mkdir(parents=True, exist_ok=True)

            # Extract unique resource ID from URL
            resource_id = self._extract_resource_id(download_url)

            # Get file extension first to construct filename
            file_extension = self._get_file_extension(post.type or "normal", None, download_url)

            # Generate filename using resource ID instead of random UUID
            unique_filename = f"{index:03d}_{resource_id}.{file_extension}"
            local_path = download_dir / unique_filename

            # Check if file already exists to avoid re-downloading
            if local_path.exists():
                file_size = local_path.stat().st_size
                logger.info(
                    f"Resource already exists, skipping download: {local_path} ({file_size} bytes)"
                )
                return {
                    "success": True,
                    "url": download_url,
                    "local_path": str(local_path),
                    "file_size": file_size,
                    "index": index,
                    "error": None,
                    "skipped": True,  # Flag to indicate this was skipped
                }

            # Download the file and get headers
            async with httpx.AsyncClient(timeout=settings.XHS_CONNECTION_TIMEOUT) as client:
                response = await client.get(download_url)
                response.raise_for_status()

                # Update file extension based on actual response headers if available
                content_disposition = response.headers.get('content-disposition')
                actual_extension = self._get_file_extension(
                    post.type or "normal", content_disposition, download_url
                )

                # Update filename if extension changed
                if actual_extension != file_extension:
                    unique_filename = f"{index:03d}_{resource_id}.{actual_extension}"
                    local_path = download_dir / unique_filename

                # Write file to disk
                local_path.write_bytes(response.content)

                file_size = len(response.content)
                logger.info(
                    f"Downloaded {self.platform_id} resource: {local_path} ({file_size} bytes)"
                )

                return {
                    "success": True,
                    "url": download_url,
                    "local_path": str(local_path),
                    "file_size": file_size,
                    "index": index,
                    "error": None,
                    "skipped": False,  # This was actually downloaded
                }

        except Exception as e:
            logger.error(f"Failed to download resource {download_url}: {e}")
            return {
                "success": False,
                "url": download_url,
                "local_path": None,
                "file_size": 0,
                "index": index,
                "error": str(e),
                "skipped": False,
            }

    async def _download_resources(self, post: XhsNoteDetail) -> List[Dict[str, Any]]:
        """
        Download all resources from a XHS note concurrently

        Args:
            post: The XHS note containing resource URLs

        Returns:
            List of download results with success/failure info
        """
        if not post.resource_list:
            logger.debug(f"No resources to download for {self.platform_id}")
            return []

        import asyncio

        post_id = post.id or uuid.uuid4().hex[:8]
        logger.info(
            f"Starting download of {len(post.resource_list)} resources "
            f"for {self.platform_id} post {post_id}"
        )

        # Create download tasks for concurrent execution
        download_tasks = [
            self._download_single_resource(url, post, index)
            for index, url in enumerate(post.resource_list, 1)
        ]

        # Execute all downloads concurrently
        download_results = await asyncio.gather(*download_tasks, return_exceptions=True)

        # Process results and handle any exceptions
        processed_results = []
        for i, result in enumerate(download_results):
            if isinstance(result, Exception):
                logger.error(f"Download task {i+1} failed with exception: {result}")
                processed_results.append(
                    {
                        "success": False,
                        "url": post.resource_list[i] if i < len(post.resource_list) else "",
                        "local_path": None,
                        "file_size": 0,
                        "index": i + 1,
                        "error": str(result),
                        "skipped": False,
                    }
                )
            else:
                processed_results.append(result)

        # Log summary with detailed breakdown
        successful_downloads = sum(1 for r in processed_results if r["success"])
        new_downloads = sum(
            1 for r in processed_results if r["success"] and not r.get("skipped", False)
        )
        skipped_downloads = sum(
            1 for r in processed_results if r["success"] and r.get("skipped", False)
        )
        failed_downloads = sum(1 for r in processed_results if not r["success"])
        total_size = sum(r["file_size"] for r in processed_results if r["success"])

        logger.info(
            f"Download complete for {self.platform_id}: "
            f"{successful_downloads}/{len(post.resource_list)} successful "
            f"({new_downloads} new, {skipped_downloads} skipped, {failed_downloads} failed), "
            f"total size: {total_size} bytes"
        )

        return processed_results

    async def invoke(self, link: str, download: bool = False, **kwargs) -> XhsNoteDetail | None:
        """
        Unified interface for parsing and optionally downloading resources

        Args:
            link: XHS share link
            download: Whether to download resources automatically
            **kwargs: Additional parameters

        Returns:
            Parsed post object with optional download results
        """
        post = await self._parse(link, **kwargs)

        if post and download:
            # Download resources and add results to post
            download_results = await self._download_resources(post)
            post.download_results = download_results

        return post
