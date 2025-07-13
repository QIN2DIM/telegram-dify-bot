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


def detect_language(text: str) -> Optional[str]:
    """检测文本的主要语言

    Args:
        text: 待检测的文本

    Returns:
        语言代码（如 'vi', 'ru', 'en'）或 None
    """
    if not text or len(text.strip()) < 3:
        return None

    try:
        # 清理文本
        cleaned_text = clean_text_for_detection(text)

        if not cleaned_text or len(cleaned_text.strip()) < 3:
            return None

        # 进行多次检测以提高准确性
        from langdetect import detect_langs

        # 首先尝试获取概率分布
        lang_probs = detect_langs(cleaned_text)

        # 如果最高概率的语言置信度太低，返回 None
        if not lang_probs or lang_probs[0].prob < 0.7:
            logger.debug(f"语言检测置信度过低: {lang_probs[0].prob if lang_probs else 'N/A'}")
            return None

        detected_lang = lang_probs[0].lang

        # 标准化语言代码
        if detected_lang == "zh-cn":
            detected_lang = "zh"

        # 特殊处理一些容易混淆的语言
        if detected_lang in ["mk", "bg"] and _contains_cyrillic(cleaned_text):
            # 马其顿语或保加利亚语可能实际是俄语
            if _is_likely_russian(cleaned_text):
                detected_lang = "ru"

        logger.debug(
            f"检测到语言: {detected_lang} (置信度: {lang_probs[0].prob:.3f}) (原文: {text[:30]}...)"
        )
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


def should_translate(text: str, source_languages: list[str]) -> bool:
    """判断是否应该翻译该文本

    Args:
        text: 待检测的文本
        source_languages: 需要翻译的源语言列表

    Returns:
        是否应该翻译
    """
    if not text or not source_languages:
        return False

    detected_lang = detect_language(text)

    if not detected_lang:
        return False

    # 检查是否在需要翻译的语言列表中
    should_translate_flag = detected_lang in source_languages

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
