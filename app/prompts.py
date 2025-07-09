# -*- coding: utf-8 -*-
"""
@Time    : 2025/7/9 17:38
@Author  : QIN2DIM
@GitHub  : https://github.com/QIN2DIM
@Desc    : 提示词模板
"""

# MENTION 模式的提示词模板
MENTION_PROMPT_TEMPLATE = """你是一个智能文本处理助手。用户向你提出了一个文本生成需求，你需要根据用户的要求进行翻译、总结、润色、风格转写或其他文本处理任务。

<query>
{user_query}
</query>

以下是群聊的历史消息记录，按时间从早到晚排列。这些消息可以帮助你理解当前对话的上下文和背景信息。请合理利用这些信息来更好地理解和响应用户的需求。

[history start]
{history_messages}
[history end]"""

# MENTION_WITH_REPLY 模式的提示词模板
MENTION_WITH_REPLY_PROMPT_TEMPLATE = """<query>
{message_text}
</query>

<quote_content>
{reply_text}
</quote_content>"""

# REPLY 模式的提示词模板
REPLY_PROMPT_TEMPLATE = """你是一个智能文本处理助手。用户回复了你之前的消息，你需要根据对话上下文和用户的需求继续提供帮助。

<query>
{user_query}
</query>

以下是群聊中的相关消息记录，按时间从早到晚排列。这些消息包含了当前对话的上下文，可以帮助你理解话题的发展和用户的意图。

[history start]
{history_messages}
[history end]

以下是你和该用户之间的历史互动记录。这些记录反映了用户的语言偏好、交流风格和常见需求，请参考这些信息来提供更个性化的回应。

[user preferences start]
{user_preferences}
[user preferences end]"""

# 消息格式化模板
MESSAGE_FORMAT_TEMPLATE = "{username}({user_id}) [{timestamp}]\n{message}"

# 消息分隔符
MESSAGE_SEPARATOR = "\n---\n"
