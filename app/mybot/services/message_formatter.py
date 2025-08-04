# -*- coding: utf-8 -*-
"""
Message formatting service for social media parsing responses
"""
from pathlib import Path
from typing import List, Dict, Any

from utils.file_utils import format_file_size, get_file_extension_display

# Telegram text limits
MAX_MESSAGE_LENGTH = int(4096 * 0.9)  # 3686 characters (90% of 4096 for safety)


class MessageFormatter:
    """Service for formatting messages and download summaries"""

    @staticmethod
    def format_download_summary(download_results: List[Dict[str, Any]]) -> str:
        """Format download summary with file information"""
        successful_downloads = [
            r for r in download_results if r.get('success') and r.get('local_path')
        ]

        if not successful_downloads:
            return "📥 没有成功下载的文件"

        lines = ["📥 已下载的文件：\n"]

        # Format each file
        for i, result in enumerate(successful_downloads, 1):
            file_path = Path(result['local_path'])
            if not file_path.exists():
                continue

            file_size = file_path.stat().st_size
            extension = get_file_extension_display(str(file_path))
            size_str = format_file_size(file_size)

            lines.append(f"{i}. {extension} - {size_str}")

        # Add total summary
        total_size = sum(
            Path(r['local_path']).stat().st_size
            for r in successful_downloads
            if r.get('local_path') and Path(r['local_path']).exists()
        )

        total_size_str = format_file_size(total_size)
        lines.append(f"\n📊 总计: {len(successful_downloads)} 个文件, {total_size_str}")

        return "\n".join(lines)

    @staticmethod
    def format_social_post(post: Any) -> str:
        """Format social media post data into telegram message"""
        if not post:
            return "无法解析链接内容"

        response_parts = []

        # Title and author
        title = getattr(post, 'title', '')
        author = getattr(post, 'user_nickname', '')

        if title and author:
            response_parts.append(f"<b>{title}</b> - {author}")
        elif title:
            response_parts.append(f"<b>{title}</b>")
        elif author:
            response_parts.append(author)

        # Published time
        if hasattr(post, 'published_time') and post.published_time:
            response_parts.append(post.published_time)

        # Description
        if hasattr(post, 'desc') and post.desc:
            desc = post.desc.replace("[话题]", "")
            desc = f"<blockquote>{desc}</blockquote>"
            response_parts.append(desc)

        # Join and check length
        final_message = "\n\n".join(response_parts)

        # Truncate if too long
        if len(final_message) > MAX_MESSAGE_LENGTH:
            final_message = MessageFormatter._truncate_message(response_parts)

        return final_message

    @staticmethod
    def _truncate_message(response_parts: List[str]) -> str:
        """Truncate message to fit Telegram limits"""
        # Find description to truncate (usually the longest part)
        for i, part in enumerate(response_parts):
            if part.startswith("<blockquote>") and part.endswith("</blockquote>"):
                # Calculate available space
                other_parts_length = sum(len(p) + 2 for j, p in enumerate(response_parts) if j != i)
                available_length = MAX_MESSAGE_LENGTH - other_parts_length

                # Keep space for tags and ellipsis
                blockquote_overhead = len("<blockquote></blockquote>") + 3
                max_desc_length = available_length - blockquote_overhead

                if max_desc_length > 50:
                    original_desc = part[12:-13]  # Remove tags
                    truncated_desc = original_desc[:max_desc_length] + "..."
                    response_parts[i] = f"<blockquote>{truncated_desc}</blockquote>"
                    break

        return "\n\n".join(response_parts)

    @staticmethod
    def format_media_sending_info(photos: List, videos: List, documents: List) -> str:
        """Format media sending progress information"""
        total_files = len(photos) + len(videos) + len(documents)

        if total_files == 0:
            return "📤 没有媒体文件需要发送"

        info_parts = ["📤 正在发送媒体文件：\n"]

        if photos:
            info_parts.append(f"🖼️ 图片: {len(photos)} 个")
        if videos:
            info_parts.append(f"🎥 视频: {len(videos)} 个")
        if documents:
            info_parts.append(f"📄 文档: {len(documents)} 个")

        info_parts.append(f"\n📊 总计: {total_files} 个文件")

        return "\n".join(info_parts)
