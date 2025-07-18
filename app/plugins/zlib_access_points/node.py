# -*- coding: utf-8 -*-
"""
@Time    : 2025/7/13 12:20
@Author  : QIN2DIM
@GitHub  : https://github.com/QIN2DIM
@Desc    : 更新最新的 zlib 访问链接
"""
from urllib.parse import urlparse, quote

import httpx
from bs4 import BeautifulSoup
from loguru import logger

from settings import settings
from plugins.zlib_access_points.crud import get_latest_zlib_access_point, save_zlib_access_point


def get_zlib_useful_links():
    """从 Wikipedia 获取 zlib 有用链接"""
    response = httpx.get(settings.SAFE_ZLIBRARY_WIKI_URL)
    response.raise_for_status()
    useful_links = []

    # //table[@class='infobox vcard']//a[@rel='nofollow']
    soup = BeautifulSoup(response.text, "html.parser")
    if infobox := soup.find("table", class_="infobox vcard"):
        if rels := infobox.find_all("a", attrs={"rel": "nofollow"}):
            urls = [rel.get("href", "").strip() for rel in rels]
            useful_links = [url for url in filter(None, urls) if url.startswith("https://")]

    return useful_links


def parse_input_params(best_link: str, k: str | None = ""):
    """解析输入参数并构造搜索链接"""
    u = urlparse(best_link)
    return f"{u.scheme}://{u.netloc}/s/{quote(k.strip())}" if k else best_link


def get_latest_zlib_link_from_db() -> str | None:
    """从数据库获取最新的 zlib 链接"""
    try:
        access_point = get_latest_zlib_access_point()
        if access_point:
            return access_point.useful_link
        return None
    except Exception as e:
        logger.error(f"从数据库获取 zlib 链接失败: {e}")
        return None


def get_latest_zlib_access_point_info() -> dict | None:
    """从数据库获取最新的 zlib 访问点信息（包含链接和更新时间）"""
    try:
        access_point = get_latest_zlib_access_point()
        if access_point:
            return {"link": access_point.useful_link, "update_time": access_point.update_time}
        return None
    except Exception as e:
        logger.error(f"从数据库获取 zlib 访问点信息失败: {e}")
        return None


@logger.catch
def update_zlib_links(should_update_db: bool = False) -> bool:
    """更新 zlib 链接到数据库

    Args:
        should_update_db: 是否更新数据库，仅在定时任务触发时为 True

    Returns:
        是否成功更新
    """
    if not should_update_db:
        logger.debug("参数设置为不更新数据库，跳过更新")
        return True

    try:
        links = get_zlib_useful_links()
        if not links:
            logger.warning("未获取到有效的 zlib 链接")
            return False

        # 获取最新链接
        best_link = links[0]

        # 检查是否与数据库中的最新链接相同
        latest_db_link = get_latest_zlib_link_from_db()
        if latest_db_link == best_link:
            logger.info("zlib 链接未发生变化，无需更新")
            return True

        # 保存到数据库
        save_zlib_access_point(best_link)
        logger.success(f"已更新 zlib 链接: {best_link}")
        return True

    except Exception as e:
        logger.error(f"更新 zlib 链接失败: {e}")
        return False


@logger.catch
def get_zlib_search_url(query: str | None = "") -> str | None:
    """获取 zlib 搜索链接（仅从数据库读取）

    Args:
        query: 搜索查询字符串

    Returns:
        构造的搜索链接或 None
    """
    best_link = get_latest_zlib_link_from_db()
    if best_link:
        return parse_input_params(best_link, query)
    return None


@logger.catch
def get_zlib_search_url_with_info(query: str | None = "") -> dict | None:
    """获取 zlib 搜索链接和更新时间信息（仅从数据库读取）

    Args:
        query: 搜索查询字符串

    Returns:
        包含链接和更新时间的字典或 None
        格式: {"url": "链接", "update_time": "更新时间"}
    """
    access_point_info = get_latest_zlib_access_point_info()
    if access_point_info:
        search_url = parse_input_params(access_point_info["link"], query)
        return {"url": search_url, "update_time": access_point_info["update_time"]}
    return None
