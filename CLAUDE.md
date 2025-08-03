# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Common Development Commands

### Package Management & Environment
- `uv sync` - Install dependencies using uv package manager
- `uv add <package>` - Add new dependency
- `uv remove <package>` - Remove dependency

### Code Quality & Testing
- `black app/ -C -l 100` - Format code using Black formatter
- `ruff check app/ --fix` - Run linting with Ruff
- `uv run app/main.py` - Run the main Telegram bot application

## High-level Architecture

This is a sophisticated Telegram bot that integrates with Dify Workflow for AI-powered responses. The architecture follows a modular service-oriented design:

### Core Components

**Main Application (`app/main.py`)**
- Entry point that initializes the Telegram bot using python-telegram-bot library
- Sets up command handlers, message handlers, and bot commands menu
- Handles graceful shutdown and periodic cleanup of temporary files

**Settings Management (`app/settings.py`)**
- Centralized configuration using Pydantic settings
- Supports environment variables and .env files
- Key configurations: Telegram bot token, Dify API credentials, database URL, chat whitelist
- Development/test mode switches for easier debugging

**Service Layer Architecture (`app/mybot/services/`)**
- `context_service.py` - Manages conversation context and user interaction history
- `dify_service.py` - Core integration with Dify Workflow API
- `instant_view_service.py` - Telegraph integration for rich content display
- `interaction_service.py` - Handles different types of user interactions (mentions, replies, etc.)
- `response_service.py` - Manages bot response formatting and delivery

**Dify Integration (`app/dify/`)**
- `dify_client.py` - HTTP client for Dify Workflow API with file upload support
- `models.py` - Pydantic models for Dify API request/response structures
- `workflow_tool.py` - High-level workflow execution interface
- Supports both streaming and blocking response modes

**Handler System (`app/mybot/handlers/`)**
- `message_handler.py` - Processes all non-command messages, handles context detection
- `command_handler/` - Individual command implementations:
  - `zlib_command.py` - Z-Library book search functionality
  - `search_command.py` - Google search integration
  - `parse_command.py` - Social media content parsing and downloading
  - `help_command.py` - Dynamic help system with template support

### Key Design Patterns

**Workflow-First Architecture**
- Built specifically for Dify Workflow (not Chatflow) to enable structured JSON outputs
- Intent classification system routes different user inputs to appropriate workflow branches
- Supports both streaming responses for long operations and blocking for quick tasks

**Context-Aware Interactions**  
- Differentiates between mentions, replies, and forward+mention scenarios
- Maintains separate conversation contexts per user to avoid cross-contamination
- Implements "stateless by design" philosophy - each interaction is treated as independent

**Multi-Modal Content Support**

- Handles text, images, documents, audio, and video through unified file processing
- Telegraph integration for rich content display beyond Telegram's formatting limits
- Automatic file compression and cleanup with configurable retention periods

**Access Control & Security**

- Chat whitelist system supporting private chats, groups, and supergroups

### Database & Storage
- PostgreSQL database for persistent storage (plugins, user data)
- Organized data directories: `app/data/downloads/`, `app/data/group_messages/`, etc.

### Plugin System
- Extensible plugin architecture (`app/plugins/`)

## Important Implementation Notes

- The bot is designed to work WITHOUT traditional conversation memory - each interaction is treated as a one-shot task to avoid context pollution in group chats
- Rich text output uses HTML formatting (not Markdown) for better Telegram compatibility
- Error handling is comprehensive with graceful fallbacks to prevent bot crashes
- No one is allowed to write test files and execute tests
- No one can add or remove project dependencies without permission
- No one should over-design a system or add redundant code