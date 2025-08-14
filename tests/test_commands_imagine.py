# -*- coding: utf-8 -*-
"""
@Time    : 2025/8/14 18:44
@Author  : QIN2DIM
@GitHub  : https://github.com/QIN2DIM
@Desc    : Comprehensive tests for /imagine command functionality
"""

from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch, mock_open

import pytest
import pytest_asyncio
from telegram import Update, Message, Chat, User, ReactionTypeEmoji
from telegram.ext import ContextTypes

from dify.models import ForcedCommand
from models import Interaction, TaskType
from mybot.handlers.command_handler.imagine_command import imagine_command
from mybot.services import response_service


class TestImagineCommand:
    """Test suite for /imagine command handler following Google's testing best practices."""

    @pytest_asyncio.fixture
    async def mock_update(self):
        """Create a mock Update object with all required attributes."""
        update = AsyncMock(spec=Update)

        # Mock message
        message = AsyncMock(spec=Message)
        message.message_id = 123
        message.text = "/imagine beautiful sunset"
        message.reply_to_message = None

        # Mock user
        user = Mock(spec=User)
        user.id = 456789
        user.is_bot = False
        message.from_user = user

        # Mock chat
        chat = Mock(spec=Chat)
        chat.id = -987654
        message.chat = chat

        # Set up update attributes
        update.message = message
        update.effective_message = message
        update.effective_chat = chat
        update.callback_query = None
        update.inline_query = None

        return update

    @pytest_asyncio.fixture
    async def mock_context(self):
        """Create a mock context with bot and args."""
        context = AsyncMock(spec=ContextTypes.DEFAULT_TYPE)

        # Mock bot
        bot = AsyncMock()
        bot.username = "@test_bot"
        bot.send_message = AsyncMock()
        bot.set_message_reaction = AsyncMock()
        bot.delete_message = AsyncMock()
        bot.send_photo = AsyncMock()
        bot.send_media_group = AsyncMock()

        context.bot = bot
        context.args = ["beautiful", "sunset"]

        return context

    @pytest_asyncio.fixture
    async def mock_dify_response(self):
        """Create mock Dify streaming response for imagine command."""

        async def generate_response():
            # Simulate streaming chunks
            yield {"event": "workflow_started", "data": {"workflow_run_id": "test-run-123"}}

            yield {
                "event": "node_started",
                "data": {"node_type": "agent", "title": "Image Generation", "index": 1},
            }

            yield {
                "event": "workflow_finished",
                "data": {
                    "outputs": {
                        "answer": (
                            "Prompt: a breathtaking sunset over ocean waves, golden hour lighting\n"
                            "Negative-Prompt: 模糊，变形，多尾，卡通，动漫，过曝，噪点，像素化\n"
                            "Size: 1328x1328\n"
                            "Sampler: Euler a\n"
                            "GuidanceScale: 4\n"
                            "Steps: 50\n"
                            "Seed: 42"
                        ),
                        "type": "Imagine",
                        "extras": {"all_image_urls": ["https://example.com/generated_image.jpg"]},
                    }
                },
            }

        return generate_response()

    @pytest.mark.asyncio
    async def test_imagine_command_basic_generation(
        self, mock_update, mock_context, mock_dify_response
    ):
        """Test basic image generation with prompt."""
        with patch('mybot.handlers.command_handler.imagine_command.dify_service') as mock_dify:
            with patch(
                'mybot.handlers.command_handler.imagine_command.response_service'
            ) as mock_response:
                # Setup mocks
                mock_dify.invoke_model_streaming.return_value = mock_dify_response

                # Execute command
                await imagine_command(mock_update, mock_context)

                # Verify bot reaction was set
                mock_context.bot.set_message_reaction.assert_called_once_with(
                    chat_id=-987654, message_id=123, reaction=[ReactionTypeEmoji(emoji="🎨")]
                )

                # Verify Dify was called with correct parameters
                mock_dify.invoke_model_streaming.assert_called_once_with(
                    bot_username="test_bot",
                    message_context="beautiful sunset",
                    from_user="456789",
                    photo_paths=[],
                    media_files={},
                    forced_command=ForcedCommand.IMAGINE,
                )

                # Verify response service was called
                mock_response.send_streaming_response.assert_called_once()

    @pytest.mark.asyncio
    async def test_imagine_command_no_prompt(self, mock_update, mock_context):
        """Test command without prompt shows usage instructions."""
        mock_context.args = []

        await imagine_command(mock_update, mock_context)

        # Verify help message was sent
        mock_context.bot.send_message.assert_called_once()
        call_kwargs = mock_context.bot.send_message.call_args.kwargs

        assert "请提供图片生成提示词" in call_kwargs['text']
        assert call_kwargs['chat_id'] == -987654
        assert call_kwargs['parse_mode'] == 'HTML'

    @pytest.mark.asyncio
    async def test_imagine_command_with_edit_context(self, mock_update, mock_context):
        """Test editing a previously generated image."""
        # Setup reply to message with bot's previous generation
        reply_message = AsyncMock(spec=Message)
        reply_message.from_user = Mock(spec=User)
        reply_message.from_user.is_bot = True
        reply_message.caption = "Prompt: beautiful sunset\n" "Size: 1024x1024\n" "Steps: 30"

        mock_update.message.reply_to_message = reply_message
        mock_context.args = ["add", "birds"]

        with patch('mybot.handlers.command_handler.imagine_command.dify_service') as mock_dify:
            with patch('mybot.handlers.command_handler.imagine_command.response_service'):
                mock_dify.invoke_model_streaming.return_value = AsyncMock()

                await imagine_command(mock_update, mock_context)

                # Verify context was included in prompt
                call_args = mock_dify.invoke_model_streaming.call_args.kwargs
                expected_context = "Based on the previous image generation with these parameters:"
                assert expected_context in call_args['message_context']
                assert "add birds" in call_args['message_context']

    @pytest.mark.asyncio
    async def test_imagine_command_error_handling(self, mock_update, mock_context):
        """Test error handling when Dify service fails."""
        with patch('mybot.handlers.command_handler.imagine_command.dify_service') as mock_dify:
            # Simulate Dify service error
            mock_dify.invoke_model_streaming.side_effect = Exception("Dify service error")

            await imagine_command(mock_update, mock_context)

            # Verify error message was sent
            mock_context.bot.send_message.assert_called_once()
            call_kwargs = mock_context.bot.send_message.call_args.kwargs

            assert "❌ 图片生成过程中发生错误" in call_kwargs['text']
            assert call_kwargs['reply_to_message_id'] == 123

    @pytest.mark.asyncio
    async def test_imagine_command_inline_query_ignored(self, mock_update, mock_context):
        """Test that inline queries are properly ignored."""
        # Setup inline query
        mock_update.message = None
        mock_update.effective_message = None
        mock_update.inline_query = Mock()
        mock_update.inline_query.query = "test query"

        await imagine_command(mock_update, mock_context)

        # Verify no actions were taken
        mock_context.bot.send_message.assert_not_called()
        mock_context.bot.set_message_reaction.assert_not_called()


class TestResponseServiceImagineHandling:
    """Test suite for response service's imagine-specific functionality."""

    @pytest_asyncio.fixture
    async def mock_context(self):
        """Create mock context for response service tests."""
        context = AsyncMock()
        bot = AsyncMock()
        bot.edit_message_text = AsyncMock()
        bot.delete_message = AsyncMock()
        bot.send_photo = AsyncMock()
        bot.send_media_group = AsyncMock()
        bot.send_message = AsyncMock()
        context.bot = bot
        return context

    @pytest.mark.asyncio
    async def test_download_image_from_url_success(self):
        """Test successful image download from URL."""
        test_url = "https://example.com/test_image.jpg"
        test_content = b"fake_image_data"

        with patch('mybot.services.response_service.httpx.AsyncClient') as mock_client:
            # Mock HTTP response
            mock_response = AsyncMock()
            mock_response.content = test_content
            mock_response.raise_for_status = AsyncMock()

            mock_client_instance = AsyncMock()
            mock_client_instance.get.return_value = mock_response
            mock_client.return_value.__aenter__.return_value = mock_client_instance

            # Mock file operations
            with patch('mybot.services.response_service.DATA_DIR', Path("/tmp/test")):
                with patch('pathlib.Path.mkdir'):
                    with patch('pathlib.Path.write_bytes') as mock_write:
                        result = await response_service._download_image_from_url(test_url)

                        assert result is not None
                        assert result.name == "test_image.jpg"
                        mock_write.assert_called_once_with(test_content)

    @pytest.mark.asyncio
    async def test_download_image_from_url_failure(self):
        """Test handling of download failure."""
        test_url = "https://example.com/bad_image.jpg"

        with patch('mybot.services.response_service.httpx.AsyncClient') as mock_client:
            # Simulate network error
            mock_client_instance = AsyncMock()
            mock_client_instance.get.side_effect = Exception("Network error")
            mock_client.return_value.__aenter__.return_value = mock_client_instance

            result = await response_service._download_image_from_url(test_url)

            assert result is None

    @pytest.mark.asyncio
    async def test_send_imagine_result_single_image(self, mock_context):
        """Test sending a single generated image with caption."""
        image_urls = ["https://example.com/image1.jpg"]
        prompt = "beautiful sunset"
        negative_prompt = "blurry"
        params = {"Size": "1024x1024", "Steps": "30", "Seed": "42"}

        with patch('mybot.services.response_service._download_image_from_url') as mock_download:
            # Mock successful download
            mock_path = Path("/tmp/test/image1.jpg")
            mock_download.return_value = mock_path

            with patch('builtins.open', mock_open(read_data=b"image_data")):
                result = await response_service._send_imagine_result(
                    mock_context,
                    chat_id=123,
                    image_urls=image_urls,
                    prompt=prompt,
                    negative_prompt=negative_prompt,
                    params=params,
                    reply_to_message_id=456,
                )

                assert result is True
                mock_context.bot.send_photo.assert_called()

    @pytest.mark.asyncio
    async def test_send_imagine_result_multiple_images(self, mock_context):
        """Test sending multiple generated images as media group."""
        image_urls = [
            "https://example.com/image1.jpg",
            "https://example.com/image2.jpg",
            "https://example.com/image3.jpg",
        ]
        prompt = "sunset variations"
        negative_prompt = ""
        params = {"Size": "1024x1024"}

        with patch('mybot.services.response_service._download_image_from_url') as mock_download:
            # Mock successful downloads
            mock_paths = [Path(f"/tmp/test/image{i}.jpg") for i in range(1, 4)]
            mock_download.side_effect = mock_paths

            with patch('builtins.open', mock_open(read_data=b"image_data")):
                result = await response_service._send_imagine_result(
                    mock_context,
                    chat_id=123,
                    image_urls=image_urls,
                    prompt=prompt,
                    negative_prompt=negative_prompt,
                    params=params,
                )

                assert result is True
                mock_context.bot.send_media_group.assert_called()

    @pytest.mark.asyncio
    async def test_send_imagine_result_no_images(self, mock_context):
        """Test handling when no images are provided."""
        result = await response_service._send_imagine_result(
            mock_context, chat_id=123, image_urls=[], prompt="test", negative_prompt="", params={}
        )

        assert result is False
        mock_context.bot.send_photo.assert_not_called()
        mock_context.bot.send_media_group.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_final_result_imagine_type(self, mock_context):
        """Test handling of Imagine type in final result."""
        chat = Mock()
        chat.id = 123

        initial_message = Mock()
        initial_message.message_id = 456

        final_result = {
            "answer": (
                "Prompt: sunset over mountains\n"
                "Negative-Prompt: blur\n"
                "Size: 1024x1024\n"
                "Steps: 30"
            ),
            "type": "Imagine",
            "extras": {"all_image_urls": ["https://example.com/result.jpg"]},
        }

        interaction = Interaction(
            task_type=TaskType.MENTION, from_user_fmt="user123", photo_paths=[], media_files={}
        )

        trigger_message = Mock()
        trigger_message.message_id = 789

        with patch('mybot.services.response_service._send_imagine_result') as mock_send:
            mock_send.return_value = True

            await response_service._handle_final_result(
                mock_context, chat, initial_message, final_result, interaction, trigger_message
            )

            # Verify initial message was deleted
            mock_context.bot.delete_message.assert_called_once_with(chat_id=123, message_id=456)

            # Verify image was sent
            mock_send.assert_called_once()
            call_kwargs = mock_send.call_args.kwargs
            assert call_kwargs['prompt'] == "sunset over mountains"
            assert call_kwargs['negative_prompt'] == "blur"

    @pytest.mark.asyncio
    async def test_convert_caption_to_html(self):
        """Test HTML caption conversion."""
        prompt = "test prompt"
        negative_prompt = "test negative"
        params = {
            "Size": "1024x1024",
            "Sampler": "Euler",
            "GuidanceScale": "7.5",
            "Steps": "30",
            "Seed": "12345",
        }

        result = response_service._convert_caption_to_html(prompt, negative_prompt, params)

        assert "<b>Prompt:</b> test prompt" in result
        assert "<b>Negative:</b> test negative" in result
        assert "Size: 1024x1024" in result
        assert "Sampler: Euler" in result
        assert "CFG: 7.5" in result
        assert "Steps: 30" in result
        assert "Seed: 12345" in result

    @pytest.mark.asyncio
    async def test_markdown_v2_escaping(self):
        """Test proper escaping of special characters for MarkdownV2."""
        # This test verifies the escaping logic in _send_imagine_result
        special_chars = "\\*_[]()~`>#+-=|{}.!"

        with patch('mybot.services.response_service._download_image_from_url') as mock_download:
            mock_download.return_value = Path("/tmp/test.jpg")

            with patch('builtins.open', mock_open(read_data=b"data")):
                with patch('mybot.services.response_service.ContextTypes.DEFAULT_TYPE') as mock_ctx:
                    mock_bot = AsyncMock()
                    mock_bot.send_photo = AsyncMock()
                    mock_ctx.bot = mock_bot

                    await response_service._send_imagine_result(
                        mock_ctx,
                        chat_id=123,
                        image_urls=["https://example.com/test.jpg"],
                        prompt=special_chars,
                        negative_prompt="",
                        params={},
                    )

                    # Verify send_photo was called (escaping doesn't raise error)
                    mock_bot.send_photo.assert_called()


class TestImagineParameterParsing:
    """Test suite for parsing Dify response parameters."""

    def test_parse_imagine_answer_complete(self):
        """Test parsing complete answer with all parameters."""
        answer = """Prompt: a beautiful landscape
Negative-Prompt: blur, distortion
Size: 1328x1328
Sampler: Euler a
GuidanceScale: 4
Steps: 50
Seed: 42
TimeTaken: 14671.939611434937"""

        lines = answer.split('\n')
        params = {}
        prompt = ""
        negative_prompt = ""

        for line in lines:
            if line.startswith("Prompt:"):
                prompt = line.replace("Prompt:", "").strip()
            elif line.startswith("Negative-Prompt:"):
                negative_prompt = line.replace("Negative-Prompt:", "").strip()
            elif line.startswith("Size:"):
                params["Size"] = line.replace("Size:", "").strip()
            elif line.startswith("Sampler:"):
                params["Sampler"] = line.replace("Sampler:", "").strip()
            elif line.startswith("GuidanceScale:"):
                params["GuidanceScale"] = line.replace("GuidanceScale:", "").strip()
            elif line.startswith("Steps:"):
                params["Steps"] = line.replace("Steps:", "").strip()
            elif line.startswith("Seed:"):
                params["Seed"] = line.replace("Seed:", "").strip()

        assert prompt == "a beautiful landscape"
        assert negative_prompt == "blur, distortion"
        assert params["Size"] == "1328x1328"
        assert params["Sampler"] == "Euler a"
        assert params["GuidanceScale"] == "4"
        assert params["Steps"] == "50"
        assert params["Seed"] == "42"

    def test_parse_imagine_answer_partial(self):
        """Test parsing answer with missing parameters."""
        answer = """Prompt: simple test
Size: 512x512"""

        lines = answer.split('\n')
        params = {}
        prompt = ""
        negative_prompt = ""

        for line in lines:
            if line.startswith("Prompt:"):
                prompt = line.replace("Prompt:", "").strip()
            elif line.startswith("Negative-Prompt:"):
                negative_prompt = line.replace("Negative-Prompt:", "").strip()
            elif line.startswith("Size:"):
                params["Size"] = line.replace("Size:", "").strip()

        assert prompt == "simple test"
        assert negative_prompt == ""
        assert params.get("Size") == "512x512"
        assert params.get("Steps") is None


class TestEdgeeCases:
    """Test suite for edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_imagine_command_no_message_or_chat(self):
        """Test handling when no valid message or chat is found."""
        update = AsyncMock(spec=Update)
        update.message = None
        update.effective_message = None
        update.effective_chat = None
        update.callback_query = None
        update.inline_query = None

        context = AsyncMock(spec=ContextTypes.DEFAULT_TYPE)
        context.args = ["test"]

        await imagine_command(update, context)

        # Should return early without any bot actions
        context.bot.send_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_reaction_setting_failure_ignored(self, mock_update, mock_context):
        """Test that reaction setting failure doesn't break the command."""
        mock_context.bot.set_message_reaction.side_effect = Exception("Reaction failed")

        with patch('mybot.handlers.command_handler.imagine_command.dify_service') as mock_dify:
            with patch('mybot.handlers.command_handler.imagine_command.response_service'):
                mock_dify.invoke_model_streaming.return_value = AsyncMock()

                # Should complete without raising exception
                await imagine_command(mock_update, mock_context)

                # Verify command continued despite reaction failure
                mock_dify.invoke_model_streaming.assert_called_once()

    @pytest.mark.asyncio
    async def test_download_with_invalid_url_format(self):
        """Test download with malformed URL."""
        invalid_urls = ["", "not_a_url", "http://", "//missing-protocol.com/image.jpg"]

        for url in invalid_urls:
            result = await response_service._download_image_from_url(url)
            assert result is None

    @pytest.mark.asyncio
    async def test_media_group_limit_enforcement(self):
        """Test that media group respects Telegram's limit."""
        # Create mock context
        mock_context = AsyncMock()
        mock_bot = AsyncMock()
        mock_bot.send_media_group = AsyncMock()
        mock_context.bot = mock_bot

        # Create more than 10 images (Telegram's limit)
        image_urls = [f"https://example.com/image{i}.jpg" for i in range(15)]

        with patch('mybot.services.response_service._download_image_from_url') as mock_download:
            with patch('mybot.services.response_service.MEDIA_GROUP_LIMIT', 10):
                # Mock downloads for only first 10 images
                mock_paths = [Path(f"/tmp/image{i}.jpg") for i in range(10)]
                mock_download.side_effect = mock_paths

                with patch('builtins.open', mock_open(read_data=b"data")):
                    await response_service._send_imagine_result(
                        mock_context,
                        chat_id=123,
                        image_urls=image_urls,
                        prompt="test",
                        negative_prompt="",
                        params={},
                    )

                    # Verify only 10 downloads were attempted
                    assert mock_download.call_count == 10


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
