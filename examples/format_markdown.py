# -*- coding: utf-8 -*-
"""
@Time    : 2025/7/11 07:45
@Author  : QIN2DIM
@GitHub  : https://github.com/QIN2DIM
@Desc    :
"""
from markdown_it import MarkdownIt

test_md_text = """
好的，这是一个专门设计的 Markdown 文本，它包含了几乎所有 Telegram 支持的格式。你可以将这段文本直接喂给你上面创建的 `markdown_to_html_for_telegram` 函数，来全面测试其转换效果。

这个测试文本也包括了一些边缘情况，比如嵌套格式和需要转义的特殊字符。

**加粗文本**

*斜体文本*

***加粗并斜体***

~~删除线文本~~

`行内代码`

**`加粗的行内代码`**

> 这是一个引用块。
> 它可以是多行的。
> > 甚至可以嵌套引用！

这是一个链接到 [Telegram Bot API 文档](https://core.telegram.org/bots/api)。

这是一个剧透内容: ||点我查看秘密！||

""".strip()


def markdown_to_html_for_telegram(md_text: str) -> str:
    """
    将标准的 Markdown 文本转换为 Telegram `parse_mode=HTML` 支持的格式。

    这个函数会处理：
    - 加粗: **text** -> <b>text</b>
    - 斜体: *text* -> <i>text</i>
    - 删除线: ~~text~~ -> <s>text</s>
    - 行内代码: `code` -> <code>code</code>
    - 代码块: ```python...``` -> <pre><code class="language-python">...</code></pre>
    - 引用: > text -> <blockquote>text</blockquote>
    - 链接: [text](url) -> <a href="url">text</a>
    - 剧透 (自定义语法): ||spoiler|| -> <tg-spoiler>spoiler</tg-spoiler>
    - HTML 特殊字符转义。
    """

    # 初始化 markdown-it-py 并只启用 Telegram 支持的规则
    # 这可以防止生成 <ul>, <li>, <h1> 等不支持的标签
    md = (
        MarkdownIt()
        # .enable('strong')  # **bold**
        .enable('emphasis')  # *italic*
        .enable('strikethrough')  # ~~strikethrough~~
        # .enable('code_inline')  # `code`
        .enable('fence')  # ```code block```
        .enable('blockquote')  # > quote
        .enable('link')  # [text](url)
        .enable('escape')  # 自动处理转义
    )

    # 渲染 Markdown 到 HTML
    # markdown-it-py 会自动处理 <pre><code> 内部的 HTML 字符转义，非常安全
    html_text = md.render(md_text)

    # 手动处理 Telegram 的剧透格式 (Spoiler)
    # 我们自定义一种类似 Discord 的语法: ||spoiler text||
    # 注意：这里使用简单的 replace，如果内容复杂可能需要更健壮的正则
    # 重要的是，这个替换要在 markdown 渲染之后进行
    html_text = html_text.replace('||', '<tg-spoiler>', 1)
    html_text = html_text.replace('||', '</tg-spoiler>', 1)

    # markdown-it-py 可能会在段落外层包裹 <p> 标签，Telegram 会忽略它们，
    # 但为了更干净，我们可以选择性地移除它们。
    # 不过，通常保留也无妨，Telegram 的容错性很好。
    # 下面的替换可以将段落间的 <p> 标签转换成换行，更符合预期
    html_text = html_text.replace("</p><p>", "\n\n")
    html_text = html_text.strip()

    # 移除首尾的 <p>
    if html_text.startswith("<p>"):
        html_text = html_text[3:]
    if html_text.endswith("</p>"):
        html_text = html_text[:-4]

    return html_text.strip()


if __name__ == '__main__':
    print(markdown_to_html_for_telegram(test_md_text))
