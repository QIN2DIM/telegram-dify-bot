# -*- coding: utf-8 -*-
"""
@Time    : 2025/7/14 00:45
@Author  : QIN2DIM
@GitHub  : https://github.com/QIN2DIM
@Desc    : 自动翻译功能的核心业务逻辑
"""

from typing import Optional, Dict, Any

from loguru import logger
from telegram import Update, User
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from models import TaskType, Interaction
from triggers.auto_translation.language_detector import (
    should_translate,
    get_language_display_name,
    format_language_list,
    detect_language,
    get_target_languages,
)
from mybot.prompts import AUTO_TRANSLATION_PROMPT_TEMPLATE
from mybot.services import dify_service, response_service
from settings import settings
from triggers.auto_translation.crud import (
    init_database,
    set_auto_translation_enabled,
    is_auto_translation_enabled,
    get_auto_translation_config,
    update_last_message_time,
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
        languages = get_auto_translation_config(chat_id)
        language_names = format_language_list(languages)

        message = (
            f"✅ 自动翻译已开启！\n\n"
            f"📋 配置信息：\n"
            f"• 支持语言：{language_names}\n\n"
            f"🤖 机器人将自动检测并翻译上述语言的消息。\n"
            f"💡 检测到其中一种语言时，会自动翻译为其他语言。"
        )

        logger.info(f"用户 {username}({user_id}) 在聊天 {chat_id} 中开启了自动翻译")

        return AutoTranslationResult(success=True, message=message, data={"languages": languages})

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
        languages = get_auto_translation_config(chat_id)

        language_names = format_language_list(languages)

        status_emoji = "✅" if enabled else "🔕"
        status_text = "已开启" if enabled else "已关闭"

        message = (
            f"🤖 **自动翻译状态**\n\n"
            f"状态：{status_emoji} {status_text}\n\n"
            f"📋 **配置信息：**\n"
            f"• 支持语言：{language_names}\n\n"
            f"💡 **使用说明：**\n"
            f"• `/auto_translation on` - 开启自动翻译\n"
            f"• `/auto_translation off` - 关闭自动翻译\n"
            f"• `/auto_translation status` - 查看状态\n\n"
            f"ℹ️ 检测到支持的语言时，机器人会自动翻译为其他语言。\n"
            f"⏰ 10分钟无消息时会自动关闭翻译功能。"
        )

        return AutoTranslationResult(
            success=True, message=message, data={"enabled": enabled, "languages": languages}
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
    languages = get_auto_translation_config(chat_id)

    # 检查消息的语言是否需要翻译
    return should_translate(message_text, languages)


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

    # 跳过真正的机器人发送的消息
    if message.from_user and is_real_bot(message.from_user):
        return False

    # 跳过命令消息
    if message.text and message.text.startswith('/'):
        return False

    # 检查是否需要翻译
    message_text = message.text or message.caption or ""
    if not check_should_auto_translate(chat_id, message_text):
        return False

    # 更新最后消息时间
    try:
        update_last_message_time(chat_id)
    except Exception as e:
        logger.error(f"更新最后消息时间失败: {e}")

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
        # 获取配置
        languages = get_auto_translation_config(chat_id)

        # 检测语言（限制在配置的语言范围内）
        detected_lang = detect_language(message_text, allowed_languages=languages)

        if not detected_lang:
            logger.warning("无法检测消息语言，跳过自动翻译")
            return

        # 获取目标语言（排除检测到的语言）
        target_langs = get_target_languages(detected_lang, languages)

        if not target_langs:
            logger.warning(
                f"没有找到目标语言，跳过翻译。检测语言：{detected_lang}，语言池：{languages}"
            )
            return

        # 构建翻译提示词
        detected_lang_name = get_language_display_name(detected_lang)
        target_lang_names = "、".join([get_language_display_name(lang) for lang in target_langs])

        username = user.username or user.first_name or "匿名用户"

        translation_prompt = AUTO_TRANSLATION_PROMPT_TEMPLATE.format(
            target_languages=target_lang_names, original_text=message_text
        )

        # 调用 LLM 进行翻译
        bot_username = f"{context.bot.username.rstrip('@')}"

        # 阻塞模式（自动翻译强制阻塞响应）
        result_answer = await dify_service.invoke_model_blocking(
            bot_username=bot_username,
            message_context=translation_prompt,
            from_user=f"{username}({user.id})",
            photo_paths=None,
            enable_auto_translation=True,
        )

        if result_answer:
            auto_translation = result_answer.get("auto_translation", [])
            lines = [
                f'<pre><code class="language-{output["language"]}">{output["text"]}</code></pre>'
                for output in auto_translation
            ]
            final_answer = "\n".join(lines)
            # 尝试回复原消息，失败时发送到群组
            try:
                await message.reply_html(final_answer)
            except Exception as reply_error:
                logger.warning(f"回复原消息失败: {reply_error}，尝试发送到群组")
                try:
                    await context.bot.send_message(
                        chat_id=chat_id, text=final_answer, parse_mode=ParseMode.HTML
                    )
                except Exception as send_error:
                    logger.error(f"发送消息到群组也失败: {send_error}")

        logger.info(f"已为用户 {username}({user.id}) 的{detected_lang_name}消息执行自动翻译")

    except Exception as e:
        logger.error(f"自动翻译处理失败: {e}")
        # 不向用户显示错误，以免干扰正常聊天


def is_real_bot(user: User) -> bool:
    """检测是否为真正的机器人用户

    Args:
        user: Telegram 用户对象

    Returns:
        bool: 如果是真正的机器人返回 True，否则返回 False
    """
    if not user:
        return False

    # 检查用户是否被标记为机器人
    if not user.is_bot:
        return False

    # 检查用户名是否以 'bot' 结尾（忽略大小写）
    if user.username and user.username.lower().endswith('bot'):
        return True

    # 对于没有用户名的机器人，仍然认为是真正的机器人
    if not user.username:
        return True

    # 其他情况，如果 is_bot 为 True 但用户名不以 bot 结尾，
    # 可能是频道或匿名管理员，不认为是真正的机器人
    return False


async def run_auto_shutdown_task():
    """运行自动关闭任务"""
    from triggers.auto_translation.crud import (
        get_chats_for_auto_shutdown,
        auto_disable_translation_for_chat,
    )

    try:
        # 获取需要关闭的聊天列表
        chats_to_shutdown = get_chats_for_auto_shutdown(timeout_minutes=10)

        if chats_to_shutdown:
            logger.info(f"发现 {len(chats_to_shutdown)} 个聊天需要自动关闭翻译功能")

            for chat_id in chats_to_shutdown:
                success = auto_disable_translation_for_chat(chat_id)
                if success:
                    logger.info(f"已自动关闭聊天 {chat_id} 的翻译功能")
                else:
                    logger.error(f"自动关闭聊天 {chat_id} 的翻译功能失败")
        else:
            logger.debug("没有需要自动关闭的聊天")

    except Exception as e:
        logger.error(f"自动关闭任务执行失败: {e}")


def start_auto_shutdown_task():
    """启动自动关闭任务"""
    import asyncio

    async def periodic_task():
        while True:
            await asyncio.sleep(300)  # 每5分钟检查一次
            await run_auto_shutdown_task()

    # 在后台启动任务
    asyncio.create_task(periodic_task())
    logger.info("自动关闭任务已启动，每5分钟检查一次")
