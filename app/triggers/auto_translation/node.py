# -*- coding: utf-8 -*-
"""
@Time    : 2025/7/14 00:45
@Author  : QIN2DIM
@GitHub  : https://github.com/QIN2DIM
@Desc    : 自动翻译功能的核心业务逻辑
"""

from typing import Optional, Dict, Any

from loguru import logger
from telegram import Update
from telegram.ext import ContextTypes

from models import TaskType, Interaction
from triggers.auto_translation.language_detector import (
    should_translate,
    get_language_display_name,
    format_language_list,
    detect_language,
)
from mybot.prompts import AUTO_TRANSLATION_PROMPT_TEMPLATE
from mybot.services import dify_service, response_service
from settings import settings
from triggers.auto_translation.crud import (
    init_database,
    set_auto_translation_enabled,
    is_auto_translation_enabled,
    get_auto_translation_config,
)


class AutoTranslationResult:
    """自动翻译结果"""

    def __init__(self, success: bool, message: str, data: Optional[Dict[str, Any]] = None):
        self.success = success
        self.message = message
        self.data = data or {}


async def enable_auto_translation(
    chat_id: int, user_id: int, username: str
) -> AutoTranslationResult:
    """开启自动翻译"""
    try:
        # 确保数据库已初始化
        init_database()

        # 设置自动翻译为开启状态
        set_auto_translation_enabled(chat_id, True)

        # 获取配置信息
        source_langs, target_langs = get_auto_translation_config(chat_id)
        source_lang_names = format_language_list(source_langs)
        target_lang_names = format_language_list(target_langs)

        message = (
            f"✅ 自动翻译已开启！\n\n"
            f"📋 配置信息：\n"
            f"• 源语言：{source_lang_names}\n"
            f"• 目标语言：{target_lang_names}\n\n"
            f"🤖 机器人将自动检测并翻译上述源语言的消息。"
        )

        logger.info(f"用户 {username}({user_id}) 在聊天 {chat_id} 中开启了自动翻译")

        return AutoTranslationResult(
            success=True,
            message=message,
            data={"source_languages": source_langs, "target_languages": target_langs},
        )

    except Exception as e:
        logger.error(f"开启自动翻译失败: {e}")
        return AutoTranslationResult(success=False, message="❌ 开启自动翻译失败，请稍后重试。")


async def disable_auto_translation(
    chat_id: int, user_id: int, username: str
) -> AutoTranslationResult:
    """关闭自动翻译"""
    try:
        # 设置自动翻译为关闭状态
        set_auto_translation_enabled(chat_id, False)

        message = "🔕 自动翻译已关闭。\n\n如需重新开启，请使用 `/auto_translation on` 命令。"

        logger.info(f"用户 {username}({user_id}) 在聊天 {chat_id} 中关闭了自动翻译")

        return AutoTranslationResult(success=True, message=message)

    except Exception as e:
        logger.error(f"关闭自动翻译失败: {e}")
        return AutoTranslationResult(success=False, message="❌ 关闭自动翻译失败，请稍后重试。")


async def get_auto_translation_status(chat_id: int) -> AutoTranslationResult:
    """获取自动翻译状态"""
    try:
        # 检查当前状态
        enabled = is_auto_translation_enabled(chat_id)
        source_langs, target_langs = get_auto_translation_config(chat_id)

        source_lang_names = format_language_list(source_langs)
        target_lang_names = format_language_list(target_langs)

        status_emoji = "✅" if enabled else "🔕"
        status_text = "已开启" if enabled else "已关闭"

        message = (
            f"🤖 **自动翻译状态**\n\n"
            f"状态：{status_emoji} {status_text}\n\n"
            f"📋 **配置信息：**\n"
            f"• 源语言：{source_lang_names}\n"
            f"• 目标语言：{target_lang_names}\n\n"
            f"💡 **使用说明：**\n"
            f"• `/auto_translation on` - 开启自动翻译\n"
            f"• `/auto_translation off` - 关闭自动翻译\n"
            f"• `/auto_translation status` - 查看状态\n\n"
            f"ℹ️ 当检测到源语言文本时，机器人会自动回复翻译结果。"
        )

        return AutoTranslationResult(
            success=True,
            message=message,
            data={
                "enabled": enabled,
                "source_languages": source_langs,
                "target_languages": target_langs,
            },
        )

    except Exception as e:
        logger.error(f"获取自动翻译状态失败: {e}")
        return AutoTranslationResult(success=False, message="❌ 获取自动翻译状态失败，请稍后重试。")


def check_should_auto_translate(chat_id: int, message_text: str) -> bool:
    """检查是否应该进行自动翻译"""
    # 检查是否启用了自动翻译
    if not is_auto_translation_enabled(chat_id):
        return False

    # 获取自动翻译配置
    source_langs, _ = get_auto_translation_config(chat_id)

    # 检查消息的语言是否需要翻译
    return should_translate(message_text, source_langs)


async def process_auto_translation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """处理自动翻译请求

    Returns:
        bool: 如果已处理自动翻译请求，返回 True；否则返回 False
    """
    chat_id = update.effective_chat.id
    message = update.effective_message

    # 跳过没有文本内容的消息
    if not message or not (message.text or message.caption):
        return False

    # 跳过机器人自己发送的消息
    if message.from_user and message.from_user.is_bot:
        return False

    # 跳过命令消息
    if message.text and message.text.startswith('/'):
        return False

    # 检查是否需要翻译
    message_text = message.text or message.caption or ""
    if not check_should_auto_translate(chat_id, message_text):
        return False

    # 执行翻译处理
    await _handle_auto_translation(update, context, message_text)
    return True


async def _handle_auto_translation(
    update: Update, context: ContextTypes.DEFAULT_TYPE, message_text: str
) -> None:
    """内部翻译处理逻辑"""
    message = update.effective_message
    user = update.effective_user
    chat_id = update.effective_chat.id

    try:
        # 检测语言
        detected_lang = detect_language(message_text)

        if not detected_lang:
            logger.warning("无法检测消息语言，跳过自动翻译")
            return

        # 获取配置
        _, target_langs = get_auto_translation_config(chat_id)

        # 构建翻译提示词
        detected_lang_name = get_language_display_name(detected_lang)
        target_lang_names = "、".join([get_language_display_name(lang) for lang in target_langs])

        username = user.username or user.first_name or "匿名用户"
        timestamp = message.date.strftime("%Y-%m-%d %H:%M:%S")

        translation_prompt = AUTO_TRANSLATION_PROMPT_TEMPLATE.format(
            detected_language=detected_lang_name,
            target_languages=target_lang_names,
            original_text=message_text,
            username=username,
            user_id=user.id,
            timestamp=timestamp,
            english_translation="[英文翻译结果]",
            chinese_translation="[中文翻译结果]",
        )

        # 调用 LLM 进行翻译
        bot_username = f"{context.bot.username.rstrip('@')}"
        response_mode = settings.RESPONSE_MODE.lower()

        if response_mode == "streaming":
            # 流式模式
            streaming_generator = dify_service.invoke_model_streaming(
                bot_username=bot_username,
                message_context=translation_prompt,
                from_user=f"{username}({user.id})",
                photo_paths=None,
            )

            # 创建一个模拟的 AUTO 任务类型的 interaction
            auto_interaction = Interaction(
                task_type=TaskType.AUTO, from_user_fmt=f"{username}({user.id})", photo_paths=None
            )

            await response_service.send_streaming_response(
                update, context, auto_interaction, streaming_generator
            )
        else:
            # 阻塞模式
            result_text = await dify_service.invoke_model_blocking(
                bot_username=bot_username,
                message_context=translation_prompt,
                from_user=f"{username}({user.id})",
                photo_paths=None,
            )

            if result_text:
                # 回复原消息
                await message.reply_text(result_text)

        logger.info(f"已为用户 {username}({user.id}) 的{detected_lang_name}消息执行自动翻译")

    except Exception as e:
        logger.error(f"自动翻译处理失败: {e}")
        # 不向用户显示错误，以免干扰正常聊天
