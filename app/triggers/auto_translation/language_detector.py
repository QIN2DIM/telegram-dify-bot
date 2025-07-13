# -*- coding: utf-8 -*-
"""
@Time    : 2025/7/14 00:15
@Author  : QIN2DIM
@GitHub  : https://github.com/QIN2DIM
@Desc    : 语言检测模块
"""

import re
from typing import Optional

from langdetect import DetectorFactory
from langdetect.lang_detect_exception import LangDetectException
from loguru import logger

# 设置随机种子以确保检测结果的一致性
DetectorFactory.seed = 0

# 语言代码映射表
LANGUAGE_MAPPING = {
    "vi": "越南语",
    "ru": "俄语",
    "en": "英语",
    "zh": "中文",
    "zh-cn": "中文",
    "ko": "韩语",
    "ja": "日语",
    "th": "泰语",
    "ar": "阿拉伯语",
    "de": "德语",
    "fr": "法语",
    "es": "西班牙语",
    "it": "意大利语",
    "pt": "葡萄牙语",
    "nl": "荷兰语",
    "tr": "土耳其语",
}


def clean_text_for_detection(text: str) -> str:
    """清理文本以便进行语言检测"""
    if not text:
        return ""

    # 移除 URL
    text = re.sub(r'https?://[^\s]+', '', text)

    # 移除邮箱地址
    text = re.sub(r'\S+@\S+', '', text)

    # 移除用户名提及（@username）
    text = re.sub(r'@\w+', '', text)

    # 移除 hashtag
    text = re.sub(r'#\w+', '', text)

    # 移除特殊字符和数字，保留字母和基本标点
    text = re.sub(
        r'[^\w\s\.,!?;:\'\"()\-\u4e00-\u9fff\u0400-\u04ff\u00c0-\u017f\u1ea0-\u1ef9]', '', text
    )

    # 移除多余的空格
    text = re.sub(r'\s+', ' ', text).strip()

    return text


def detect_language(text: str, allowed_languages: list[str] = None) -> Optional[str]:
    """检测文本的主要语言

    Args:
        text: 待检测的文本
        allowed_languages: 允许的语言列表，如果提供则只在这些语言中选择

    Returns:
        语言代码（如 'vi', 'ru', 'en'）或 None
    """
    if not text or len(text.strip()) < 3:
        return None

    # 默认支持的语言：越语、英语、中文、日语、俄语
    if allowed_languages is None:
        allowed_languages = ["vi", "en", "zh", "ja", "ru"]

    try:
        # 清理文本
        cleaned_text = clean_text_for_detection(text)

        if not cleaned_text or len(cleaned_text.strip()) < 3:
            return None

        # 进行多次检测以提高准确性
        from langdetect import detect_langs

        # 首先尝试获取概率分布
        lang_probs = detect_langs(cleaned_text)

        if not lang_probs:
            logger.debug("语言检测未返回结果")
            return None

        # 寻找第一个在允许列表中的语言
        detected_lang = None
        for lang_prob in lang_probs:
            candidate_lang = lang_prob.lang

            # 标准化语言代码
            if candidate_lang == "zh-cn":
                candidate_lang = "zh"

            # 特殊处理一些容易混淆的语言
            if candidate_lang in ["mk", "bg"] and _contains_cyrillic(cleaned_text):
                # 马其顿语或保加利亚语可能实际是俄语
                if _is_likely_russian(cleaned_text):
                    candidate_lang = "ru"

            # 检查是否在允许的语言列表中
            if candidate_lang in allowed_languages:
                # 检查置信度是否足够
                if lang_prob.prob >= 0.6:  # 稍微降低置信度要求
                    detected_lang = candidate_lang
                    logger.debug(
                        f"检测到语言: {detected_lang} (置信度: {lang_prob.prob:.3f}) (原文: {text[:30]}...)"
                    )
                    break

        # 如果没有找到合适的语言，但有高置信度的中文检测，进行额外检查
        if not detected_lang and lang_probs:
            top_lang = lang_probs[0]
            if top_lang.lang == "ko" and top_lang.prob > 0.8:
                # 韩语被误检测为中文的情况，检查是否真的是中文
                if _is_likely_chinese(cleaned_text):
                    detected_lang = "zh"
                    logger.debug(
                        f"韩语误检测修正为中文 (置信度: {top_lang.prob:.3f}) (原文: {text[:30]}...)"
                    )

        if not detected_lang:
            logger.debug(f"未在允许的语言列表 {allowed_languages} 中找到合适的语言")

        return detected_lang

    except LangDetectException as e:
        logger.debug(f"语言检测失败: {e}")
        return None
    except Exception as e:
        logger.warning(f"语言检测异常: {e}")
        return None


def _contains_cyrillic(text: str) -> bool:
    """检查文本是否包含西里尔字母"""
    return bool(re.search(r'[\u0400-\u04FF]', text))


def _is_likely_russian(text: str) -> bool:
    """检查文本是否可能是俄语"""
    # 一些常见的俄语单词
    russian_words = [
        'привет',
        'как',
        'дела',
        'что',
        'это',
        'да',
        'нет',
        'хорошо',
        'плохо',
        'спасибо',
    ]
    text_lower = text.lower()

    for word in russian_words:
        if word in text_lower:
            return True

    # 检查是否包含俄语特有的字母组合
    russian_patterns = [r'ё', r'ъ', r'ь', r'щ', r'ж', r'ч', r'ш', r'ц', r'ы', r'э', r'ю', r'я']
    for pattern in russian_patterns:
        if re.search(pattern, text_lower):
            return True

    return False


def _is_likely_chinese(text: str) -> bool:
    """检查文本是否可能是中文"""
    # 检查是否包含中文字符
    chinese_char_count = len(re.findall(r'[\u4e00-\u9fff]', text))
    total_char_count = len(re.findall(r'[^\s\.,!?;:\'\"()\-]', text))

    if total_char_count == 0:
        return False

    # 如果中文字符占比超过30%，认为是中文
    chinese_ratio = chinese_char_count / total_char_count
    if chinese_ratio > 0.3:
        return True

    # 检查常见的中文词汇
    chinese_words = [
        '你好',
        '谢谢',
        '请问',
        '不是',
        '可以',
        '什么',
        '怎么',
        '为什么',
        '哪里',
        '时候',
        '这个',
        '那个',
        '现在',
        '以后',
        '之前',
        '一直',
        '已经',
        '还是',
        '或者',
        '如果',
        '所以',
        '因为',
        '但是',
        '然后',
        '虽然',
        '虽然',
        '不过',
        '除了',
        '关于',
        '对于',
    ]

    for word in chinese_words:
        if word in text:
            return True

    return False


def should_translate(text: str, language_pool: list[str]) -> bool:
    """判断是否应该翻译该文本

    Args:
        text: 待检测的文本
        language_pool: 语言池，包含支持的语言列表

    Returns:
        是否应该翻译
    """
    if not text or not language_pool:
        return False

    # 使用语言池作为允许的语言列表来进行检测
    detected_lang = detect_language(text, allowed_languages=language_pool)

    if not detected_lang:
        return False

    # 检查是否在语言池中（应该总是True，因为我们已经限制了检测范围）
    should_translate_flag = detected_lang in language_pool

    if should_translate_flag:
        lang_name = LANGUAGE_MAPPING.get(detected_lang, detected_lang)
        logger.info(f"检测到{lang_name}文本，将触发自动翻译")

    return should_translate_flag


def get_language_display_name(lang_code: str) -> str:
    """获取语言的显示名称"""
    return LANGUAGE_MAPPING.get(lang_code, lang_code)


def format_language_list(lang_codes: list[str]) -> str:
    """格式化语言列表为显示文本"""
    if not lang_codes:
        return ""

    lang_names = [get_language_display_name(code) for code in lang_codes]
    return "、".join(lang_names)


def get_target_languages(detected_lang: str, language_pool: list[str]) -> list[str]:
    """获取目标语言列表（从语言池中排除检测到的语言）

    Args:
        detected_lang: 检测到的语言代码
        language_pool: 语言池

    Returns:
        list[str]: 目标语言代码列表
    """
    if not detected_lang or not language_pool:
        return []

    # 从语言池中排除检测到的语言
    target_languages = [lang for lang in language_pool if lang != detected_lang]

    return target_languages
