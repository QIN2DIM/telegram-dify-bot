# -*- coding: utf-8 -*-
"""
@Time    : 2025/7/9 00:44
@Author  : QIN2DIM
@GitHub  : https://github.com/QIN2DIM
@Desc    :
"""
from telegram import Update, ForceReply
from telegram.ext import ContextTypes

# 自动翻译模式状态管理（简单实现，生产环境应使用数据库）
auto_translation_enabled_chats = set()

START_TPL = """
你好，我是 @{username}，一个部署在 Telegram 群聊中的 AI 助手。

我的主要任务是回答群组成员提出的通用知识问题。你可以通过 @{username} 提及我，或者直接回复我的消息来向我提问。我会尽力提供准确、简洁、中立的答案，并使用你提问的相同语言进行回复。
"""


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued."""
    bot_username = context.bot.username
    answer_text = START_TPL.format(username=bot_username).strip()
    await update.message.reply_html(rf"{answer_text}", reply_markup=ForceReply(selective=True))


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /help is issued."""
    test_html = """
下面我将逐一列出所有支持的标签，并附上 <a href="https://python-telegram-bot.org/">python-telegram-bot</a> 的代码示例。

<b>加粗字体</b> 或 <strong>加粗字体</strong>

<i>斜体</i> 或 <em>斜体</em>

<u>下划线</u> 或 <ins>划线</ins>

<s>删除线</s> 或 <strike>删除线</strike> 或 <del>删除线</del>

剧透：<tg-spoiler>剧透</tg-spoiler>

<a href="https://blog.echosec.top/">超链接</a>

<code>以等宽字体显示一小段文本，通常用于代码变量、命令等。</code>

<pre>创建一个预格式化的多行代码块，保留所有空格和换行符，并以等宽字体显示。</pre>

<pre><code class="language-python">import httpx\nresponse = httpx.get("url")</code></pre>

<blockquote>创建一个引用块，通常带有垂直线标识。</blockquote>
"""
    await update.message.reply_html(test_html)


async def auto(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """开启自动翻译模式"""
    chat_id = update.effective_chat.id
    auto_translation_enabled_chats.add(chat_id)
    await update.message.reply_text("已开启自动翻译模式")


async def pause(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """暂停自动翻译模式"""
    chat_id = update.effective_chat.id
    auto_translation_enabled_chats.discard(chat_id)
    await update.message.reply_text("已暂停自动翻译模式")
