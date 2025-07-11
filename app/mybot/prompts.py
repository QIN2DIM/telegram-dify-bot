# -*- coding: utf-8 -*-
"""
@Time    : 2025/7/9 17:38
@Author  : QIN2DIM
@GitHub  : https://github.com/QIN2DIM
@Desc    : 提示词模板
"""

# MENTION 模式的提示词模板
MENTION_PROMPT_TEMPLATE = """
用户向你提出了一个文本生成需求，你需要根据用户的要求进行具体的消息处理任务。

<query>
{user_query}
</query>

以下是群聊的历史消息记录，按时间从早到晚排列。这些消息可以帮助你理解当前对话的上下文和背景信息。请合理利用这些信息来更好地理解和响应用户的需求。

[history start]
{history_messages}
[history end]
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
以下是指令输入:
<query>
{user_query}
</query>

以下是引用的的消息：
<quote_content>
{history_messages}
</quote_content>

**注意:** 
1. 区分 quote_content 中的用户名和需要编辑的消息。
2. quote_content 可能是用户期望处理的消息，也可能只是用户通过 reply 机器人发送的消息来触发机器人响应，你需要根据上下文判断用户的真实意图
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
MESSAGE_FORMAT_TEMPLATE = "{username}({user_id}) [{timestamp}]\n{message}"

# 消息分隔符
MESSAGE_SEPARATOR = "\n---\n"

# https://core.telegram.org/bots/api#html-style
HTML_STYLE_TPL = """
Please use Telegram-compatible HTML for rich text formatting, instead of Markdown. 

**The following tags are currently supported:**
[example start]
<b>bold</b>
<i>italic</i>
<u>underline</u>
<s>strikethrough</s>
<tg-spoiler>spoiler</tg-spoiler>
<b>bold <i>italic bold <s>italic bold strikethrough <span class="tg-spoiler">italic bold strikethrough spoiler</span></s> <u>underline italic bold</u></i> bold</b>
<a href="http://www.example.com/">inline URL</a>
<a href="tg://user?id=123456789">inline mention of a user</a>
<code>inline fixed-width code</code>
<pre>pre-formatted fixed-width code block</pre>
<pre><code class="language-python">pre-formatted fixed-width code block written in the Python programming language</code></pre>
<blockquote>Block quotation started\nBlock quotation continued\nThe last line of the block quotation</blockquote>
<blockquote expandable>Expandable block quotation started\nExpandable block quotation continued\nExpandable block quotation continued\nHidden by default part of the block quotation started\nExpandable block quotation continued\nThe last line of the block quotation</blockquote>
[example end]

Please note:
- You MUST NOT use emoji in your answers.
- Only the tags mentioned above are currently supported.
- All `<`, `>` and `&` symbols that are not a part of a tag or an HTML entity must be replaced with the corresponding HTML entities (`<` with `<`, `>` with `>` and `&` with `&`).
- All numerical HTML entities are supported.
- The API currently supports only the following named HTML entities: `<`, `>`, `&` and `"`.
- Use nested `pre` and `code` tags, to define programming language for `pre` entity.
- Programming language can't be specified for standalone `code` tags.
"""
