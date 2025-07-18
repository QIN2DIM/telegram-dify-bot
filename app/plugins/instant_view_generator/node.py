# -*- coding: utf-8 -*-
"""
@Time    : 2025/7/18 23:08
@Author  : QIN2DIM
@GitHub  : https://github.com/QIN2DIM
@Desc    : Telegraph Instant View Generator based on telegraph[aio]
"""
import asyncio
import re
from pathlib import Path
from typing import Union, List, Dict, Any, Optional, Literal

import markdown
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field, ConfigDict
from telegraph.aio import Telegraph

from settings import settings


class TelegraphPageResult(BaseModel):
    """Telegraph page creation result"""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    path: str = Field(description="Path to the Telegraph page")
    url: str = Field(description="Full URL to the Telegraph page")
    title: str = Field(description="Page title")
    description: str = Field(description="Page description")
    author_name: Optional[str] = Field(default=None, description="Author name")
    author_url: Optional[str] = Field(default=None, description="Author URL")
    image_url: Optional[str] = Field(default=None, description="Page image URL")
    views: int = Field(default=0, description="Page view count")
    can_edit: Optional[bool] = Field(default=None, description="Whether the page can be edited")


class InstantViewRequest(BaseModel):
    """Input model for instant view generation"""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    content: Union[str, bytes, Path] = Field(
        description="Content to convert - file path, bytes, or string"
    )
    input_format: Literal["HTML", "Markdown"] = Field(description="Input content format")
    title: str = Field(description="Page title (1-256 characters)")
    author_name: Optional[str] = Field(default=None, description="Author name (0-128 characters)")
    author_url: Optional[str] = Field(default=None, description="Author URL (0-512 characters)")
    return_content: bool = Field(default=True, description="Whether to return the page content")


class InstantViewResponse(BaseModel):
    """Output model for instant view generation"""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    success: bool = Field(description="Whether the operation was successful")
    page: Optional[TelegraphPageResult] = Field(
        default=None, description="Telegraph page information"
    )
    content: Optional[List[Dict[str, Any]]] = Field(
        default=None, description="Telegraph page content nodes"
    )
    error: Optional[str] = Field(default=None, description="Error message if failed")


class TelegraphInstantViewGenerator:
    """Telegraph-based instant view generator"""

    def __init__(self):
        self._telegraph: Optional[Telegraph] = None
        self._account_created = False

    async def _ensure_telegraph_account(self) -> Telegraph:
        """Ensure Telegraph account is created and ready"""
        if self._telegraph is None:
            self._telegraph = Telegraph()

        if not self._account_created:
            await self._telegraph.create_account(
                short_name=settings.TELEGRAPH_SHORT_NAME,
                author_name=settings.TELEGRAPH_AUTHOR_NAME,
                author_url=settings.TELEGRAPH_AUTHOR_URL,
            )
            self._account_created = True

        return self._telegraph

    @staticmethod
    def _read_content(content: Union[str, bytes, Path]) -> str:
        """Read content from various input types"""
        if isinstance(content, Path):
            return content.read_text(encoding='utf-8')
        elif isinstance(content, bytes):
            return content.decode('utf-8')
        elif isinstance(content, str):
            return content
        else:
            raise ValueError(f"Unsupported content type: {type(content)}")

    def _html_to_telegraph_nodes(self, html_content: str) -> List[Dict[str, Any]]:
        """Convert HTML content to Telegraph Node format"""
        # Remove or convert unsupported HTML tags to Telegraph-compatible ones
        # Telegraph supports: a, aside, b, blockquote, br, code, em, figcaption, figure, h3, h4, hr, i, iframe, img, li, ol, p, pre, s, strong, u, ul, video

        # Clean up the HTML first
        cleaned_html = self._clean_html_for_telegraph(html_content)

        soup = BeautifulSoup(cleaned_html, 'html.parser')

        # Convert the parsed HTML to Telegraph nodes
        nodes = []
        # Track if we're between list elements to handle text nodes properly
        last_was_list = False

        for element in soup.children:
            if hasattr(element, 'name'):  # Element node
                node = self._element_to_telegraph_node(element)
                if node:
                    nodes.append(node)
                    # Check if this is a list element
                    last_was_list = isinstance(node, dict) and node.get('tag') in ['ul', 'ol']
            elif isinstance(element, str):
                text = str(element)
                if text.strip():
                    # Only wrap in <p> if it's substantial text and not between lists
                    # This helps preserve list structure
                    if not last_was_list and len(text.strip()) > 1:
                        nodes.append({"tag": "p", "children": [text]})
                    # For whitespace or small text between lists, skip it
                    elif not last_was_list:
                        # Still add single characters or important punctuation
                        nodes.append({"tag": "p", "children": [text]})

        return nodes

    def _clean_html_for_telegraph(self, html_content: str) -> str:
        """Clean HTML content to be Telegraph-compatible"""
        # Map unsupported tags to supported ones
        tag_mapping = {
            'h1': 'h3',
            'h2': 'h3',
            'h5': 'h4',
            'h6': 'h4',
            'span': '',
            'div': '',  # Don't convert div to p - let element handler decide
            'section': 'aside',
            'article': 'aside',
            'header': 'aside',
            'footer': 'aside',
            'bold': 'b',
            'italic': 'i',
            'emphasis': 'em',
            'strike': 's',
            'underline': 'u',
            'del': 's',
            'ins': 'u',
            'mark': 'strong',
            'small': '',
            'sub': '',
            'sup': '',
            'tt': 'code',
            'var': 'code',
            'kbd': 'code',
            'samp': 'code',
            'nav': '',  # Navigation elements
            'main': '',  # Main content container
        }

        # Replace unsupported tags - be careful with nested structures
        for old_tag, new_tag in tag_mapping.items():
            if new_tag:
                html_content = re.sub(
                    f'<{old_tag}([^>]*)>', f'<{new_tag}\\1>', html_content, flags=re.IGNORECASE
                )
                html_content = re.sub(
                    f'</{old_tag}>', f'</{new_tag}>', html_content, flags=re.IGNORECASE
                )
            else:
                # Remove the tag but keep content
                html_content = re.sub(f'<{old_tag}[^>]*>', '', html_content, flags=re.IGNORECASE)
                html_content = re.sub(f'</{old_tag}>', '', html_content, flags=re.IGNORECASE)

        # Remove all attributes except href and src
        html_content = re.sub(r'<(\w+)([^>]*?)>', self._clean_attributes, html_content)

        return html_content

    @staticmethod
    def _clean_attributes(match) -> str:
        """Clean HTML tag attributes, keeping only href and src"""
        tag = match.group(1)
        attrs = match.group(2)

        # Extract href and src attributes
        href_match = re.search(r'href=["\']([^"\']*)["\']', attrs, re.IGNORECASE)
        src_match = re.search(r'src=["\']([^"\']*)["\']', attrs, re.IGNORECASE)

        new_attrs = []
        if href_match:
            new_attrs.append(f'href="{href_match.group(1)}"')
        if src_match:
            new_attrs.append(f'src="{src_match.group(1)}"')

        attr_str = ' ' + ' '.join(new_attrs) if new_attrs else ''
        return f'<{tag}{attr_str}>'

    def _element_to_telegraph_node(self, element) -> Optional[Dict[str, Any]]:
        """Convert BeautifulSoup element to Telegraph node"""
        if element.name is None:
            # Text node - preserve whitespace to avoid text merging issues
            text = str(element)
            # Only return if there's actual content (not just whitespace)
            return text if text.strip() else None

        # Skip unsupported tags
        supported_tags = {
            'a',
            'aside',
            'b',
            'blockquote',
            'br',
            'code',
            'em',
            'figcaption',
            'figure',
            'h3',
            'h4',
            'hr',
            'i',
            'iframe',
            'img',
            'li',
            'ol',
            'p',
            'pre',
            's',
            'strong',
            'u',
            'ul',
            'video',
        }

        if element.name not in supported_tags:
            # For unsupported tags, try to preserve structure for certain cases
            # If it's a container element (like div) that might contain lists,
            # wrap its children in a supported container
            children = []
            for child in element.children:
                if hasattr(child, 'name'):
                    node = self._element_to_telegraph_node(child)
                    if node:
                        children.append(node)
                elif isinstance(child, str):
                    text = str(child)
                    if text.strip():  # Only add if there's actual content
                        children.append(text)

            # If there are multiple children or complex nodes, preserve the structure
            if len(children) > 1 or (len(children) == 1 and isinstance(children[0], dict)):
                # Check if all children are list items, if so, wrap in ul
                all_list_items = all(
                    isinstance(child, dict) and child.get('tag') == 'li'
                    for child in children
                    if isinstance(child, dict)
                )
                if all_list_items and children:
                    return {"tag": "ul", "children": children}
                # Otherwise, wrap in a paragraph or aside for complex content
                elif any(isinstance(child, dict) for child in children):
                    return {"tag": "aside", "children": children}

            return (
                children[0]
                if len(children) == 1 and isinstance(children[0], str)
                else {"children": children} if children else None
            )

        node = {"tag": element.name}

        # Handle attributes
        attrs = {}
        if element.get('href'):
            attrs['href'] = element.get('href')
        if element.get('src'):
            attrs['src'] = element.get('src')

        if attrs:
            node['attrs'] = attrs

        # Handle children
        children = []
        for child in element.children:
            if hasattr(child, 'name'):
                child_node = self._element_to_telegraph_node(child)
                if child_node:
                    children.append(child_node)
            elif isinstance(child, str):
                text = str(child)
                if text.strip():  # Only add if there's actual content
                    children.append(text)

        if children:
            node['children'] = children

        return node

    def _markdown_to_telegraph_nodes(self, markdown_content: str) -> List[Dict[str, Any]]:
        """Convert Markdown content to Telegraph Node format"""
        # Convert markdown to HTML first with additional extensions for better list handling
        # Using 'extra' extension which includes:
        # - Abbreviations
        # - Attribute Lists
        # - Definition Lists
        # - Fenced Code Blocks
        # - Footnotes
        # - Tables
        # - Smart Strong/Emphasis
        html_content = markdown.markdown(
            markdown_content,
            extensions=[
                'extra',  # Includes many useful features
                'codehilite',  # Code syntax highlighting
                'toc',  # Table of contents
                'sane_lists',  # Better list handling with proper nesting
            ],
        )

        # Then convert HTML to Telegraph nodes
        return self._html_to_telegraph_nodes(html_content)

    def _telegram_html_to_telegraph_nodes(self, telegram_html: str) -> List[Dict[str, Any]]:
        """Convert Telegram-compatible HTML to Telegraph Node format"""
        # Telegram HTML uses: b, strong, i, em, u, ins, s, strike, del, tg-spoiler, a, code, pre, blockquote
        # Map Telegram tags to Telegraph tags

        telegram_to_telegraph = {
            'strong': 'b',
            'ins': 'u',
            'strike': 's',
            'del': 's',
            'tg-spoiler': 's',  # Telegraph doesn't have spoiler, use strikethrough
        }

        # Replace Telegram-specific tags
        converted_html = telegram_html
        for tg_tag, tel_tag in telegram_to_telegraph.items():
            converted_html = re.sub(
                f'<{tg_tag}([^>]*)>', f'<{tel_tag}\\1>', converted_html, flags=re.IGNORECASE
            )
            converted_html = re.sub(
                f'</{tg_tag}>', f'</{tel_tag}>', converted_html, flags=re.IGNORECASE
            )

        # Handle <pre> with language attribute - Telegraph <pre> doesn't support language
        converted_html = re.sub(r'<pre[^>]*>', '<pre>', converted_html, flags=re.IGNORECASE)

        return self._html_to_telegraph_nodes(converted_html)

    async def generate_instant_view(self, request: InstantViewRequest) -> InstantViewResponse:
        """Generate Telegraph instant view from input content"""
        try:
            # Read content
            content_str = self._read_content(request.content)

            # Convert to Telegraph nodes based on input format
            if request.input_format == "HTML":
                # Check if it's Telegram-compatible HTML or regular HTML
                # Telegram HTML typically uses specific tags like <b>, <i>, <code>, etc.
                if self._is_telegram_html(content_str):
                    nodes = self._telegram_html_to_telegraph_nodes(content_str)
                else:
                    nodes = self._html_to_telegraph_nodes(content_str)
            elif request.input_format == "Markdown":
                nodes = self._markdown_to_telegraph_nodes(content_str)
            else:
                raise ValueError(f"Unsupported input format: {request.input_format}")

            # Create Telegraph account if needed
            telegraph = await self._ensure_telegraph_account()

            # Create page
            page_response = await telegraph.create_page(
                title=request.title,
                content=nodes,
                author_name=request.author_name,
                author_url=request.author_url,
                return_content=request.return_content,
            )

            # Convert response to our model
            page_result = TelegraphPageResult(
                path=page_response['path'],
                url=page_response['url'],
                title=page_response['title'],
                description=page_response.get('description', ''),
                author_name=page_response.get('author_name'),
                author_url=page_response.get('author_url'),
                image_url=page_response.get('image_url'),
                views=page_response.get('views', 0),
                can_edit=page_response.get('can_edit'),
            )

            return InstantViewResponse(
                success=True,
                page=page_result,
                content=page_response.get('content') if request.return_content else None,
            )

        except Exception as e:
            return InstantViewResponse(success=False, error=str(e))

    @staticmethod
    def _is_telegram_html(html_content: str) -> bool:
        """Check if HTML content uses Telegram-specific formatting"""
        telegram_tags = ['tg-spoiler', 'tg-emoji']
        telegram_patterns = ['<b>', '<i>', '<code>', '<pre>', '<a href=']

        # Check for Telegram-specific tags
        for tag in telegram_tags:
            if f'<{tag}' in html_content.lower():
                return True

        # Check if it's simple HTML with only Telegram-supported tags
        has_telegram_pattern = any(pattern in html_content.lower() for pattern in telegram_patterns)
        has_complex_html = any(
            tag in html_content.lower() for tag in ['<div', '<span', '<h1', '<h2']
        )

        return has_telegram_pattern and not has_complex_html


# Convenience function for easy usage
async def create_instant_view(
    content: Union[str, bytes, Path],
    input_format: Literal["HTML", "Markdown"],
    title: str,
    author_name: Optional[str] = None,
    author_url: Optional[str] = None,
    return_content: bool = True,
) -> InstantViewResponse:
    """
    Convenience function to create a Telegraph instant view

    Args:
        content: Content to convert (file path, bytes, or string)
        input_format: Input format ("HTML" or "Markdown")
        title: Page title
        author_name: Optional author name
        author_url: Optional author URL
        return_content: Whether to return page content

    Returns:
        InstantViewResponse with page information
    """
    generator = TelegraphInstantViewGenerator()
    request = InstantViewRequest(
        content=content,
        input_format=input_format,
        title=title,
        author_name=author_name,
        author_url=author_url,
        return_content=return_content,
    )

    return await generator.generate_instant_view(request)


# Example usage
async def main():
    """Example usage of the Telegraph instant view generator"""

    # Example with HTML content
    html_content = """
    <h1>Hello World</h1>
    <p>This is a <b>bold</b> text and <i>italic</i> text.</p>
    <p>Here's a <a href="https://example.com">link</a>.</p>
    <blockquote>This is a quote</blockquote>
    <pre><code>print("Hello, World!")</code></pre>
    """

    response = await create_instant_view(
        content=html_content,
        input_format="HTML",
        title="Example Telegraph Page",
        author_name="QIN2DIM Bot",
        author_url="https://github.com/QIN2DIM",
    )

    if response.success:
        print(f"Page created: {response.page.url}")
        print(f"Page path: {response.page.path}")
    else:
        print(f"Error: {response.error}")


if __name__ == '__main__':
    asyncio.run(main())
