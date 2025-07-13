# -*- coding: utf-8 -*-
"""
@Time    : 2025/7/9 17:38
@Author  : QIN2DIM
@GitHub  : https://github.com/QIN2DIM
@Desc    : 提示词模板
"""

# MENTION_WITH_REPLY 模式的提示词模板
MENTION_WITH_REPLY_PROMPT_TEMPLATE = """
<query>
{message_text}
</query>

<quote_content>
{reply_text}
</quote_content>
"""

REPLY_SINGLE_PROMPT_TEMPLATE = """
<query>
{user_query}
</query>

<quote_content>
{history_messages}
</quote_content>

**注意:** 
1. 区分 `quote_content` 中的用户名和需要编辑的消息。
2. `quote_content` 可能是用户期望处理的消息，也可能只是用户通过 reply 机器人发送的消息来触发机器人响应，你需要根据上下文判断用户的真实意图
"""

# REPLY 模式的提示词模板
REPLY_PROMPT_TEMPLATE = """
用户回复了你之前的消息，你需要根据对话上下文和用户的需求继续提供帮助。

<query>
{user_query}
</query>

以下是群聊中的相关消息记录，按时间从早到晚排列。这些消息包含了当前对话的上下文，可以帮助你理解话题的发展和用户的意图。

[history start]
{history_messages}
[history end]
"""

USER_PREFERENCES_TPL = """
以下是你和该用户之间的历史互动记录。这些记录反映了用户的语言偏好、交流风格和常见需求，请参考这些信息来提供更个性化的回应。

[user preferences start]
{user_preferences}
[user preferences end]
"""

# 消息格式化模板
MENTION_MESSAGE_FORMAT_TEMPLATE = """
<UserQuery username="{username}" date="{timestamp}">
{message}
</UserQuery>
"""

REPLAYED_FORMAT_TEMPLATE = "{username} [{timestamp}]\n{message}"


CONTEXT_PART = """
<context>
{context_part}
</context>
"""

# 自动翻译提示词模板
AUTO_TRANSLATION_PROMPT_TEMPLATE = """
请将以下{detected_language}文本翻译为{target_languages}：

<original_text>
{original_text}
</original_text>

<user_info>
用户: {username} (ID: {user_id})
时间: {timestamp}
</user_info>

要求：
1. 保持原文的语气和风格
2. 如果包含专业术语，请准确翻译
3. 对于俚语或习语，请提供合适的对应表达
4. 翻译结果请按以下格式输出：

**英文翻译：**
{english_translation}

**中文翻译：**
{chinese_translation}

注意：请直接回复翻译结果，不要添加其他说明。
"""
