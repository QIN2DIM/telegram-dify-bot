# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Common Development Commands

### Package Management & Environment
- `uv sync` - Install dependencies using uv package manager
- `uv add <package>` - Add new dependency
- `uv remove <package>` - Remove dependency

## High-level Architecture

This is a sophisticated Telegram bot specifically designed for Dify Workflow integration. It serves as a "Swiss Army knife" bot optimized for group chat interactions with AI-powered capabilities.

### Core Components

**Main Application (`app/main.py`)**
- Entry point that initializes the Telegram bot using python-telegram-bot library
- Sets up command handlers, message handlers, and bot commands menu
- Implements non-blocking task management system for concurrent request handling
- Handles graceful shutdown with active task monitoring
- Periodic cleanup of temporary files (photos: 24h, social media downloads: 48h)

**Settings Management (`app/settings.py`)**
- Centralized configuration using Pydantic settings
- Supports environment variables and .env files
- Key configurations:
  - Telegram bot token and local API server URL
  - Dify Workflow API credentials (NOT Chatflow)
  - Database URL (PostgreSQL)
  - Chat whitelist for access control
  - Response mode switching (streaming/blocking)
  - Development/test mode toggles with automatic safeguards
  - Telegraph configuration for rich content
  - HTTP request timeout configuration (default: 3600s for large media)

**Task Manager (`app/mybot/task_manager.py`)**
- Implements non-blocking architecture using asyncio tasks
- Decorator-based system (`@non_blocking_handler`) for concurrent execution
- Global task registry with cleanup and monitoring
- Graceful shutdown support with configurable timeout
- Automatic error handling and user notification on failures

### Service Layer Architecture

**Core Services (`app/mybot/services/`)**
- `interaction_service.py` - Detects and classifies user interactions:
  - Direct mentions (@bot)
  - Reply to bot messages
  - Forward+mention (asking bot to comment on forwarded content)
  - Handles whitelist validation and access control
- `context_service.py` - Builds structured message context for Dify
  - Extracts user info, chat context, and media attachments
  - Formats context based on interaction type
  - Manages temporary file downloads
- `dify_service.py` - Core Dify Workflow integration
  - Supports both blocking and streaming invocation modes
  - Dev mode with mocked responses for testing
  - Handles file uploads for multi-modal inputs
- `response_service.py` - Manages bot responses
  - Streaming responses with real-time updates
  - Structured JSON parsing from Dify outputs
  - Type-based response routing (web search, translation, etc.)
  - Rate limiting for message edits to avoid Telegram flood limits
- `instant_view_service.py` - Telegraph integration
  - Creates rich Instant View articles for complex content
  - Handles HTML sanitization and Telegraph API
  - Automatic article management
- `telegram_media_service.py` - Media handling utilities
  - Downloads and manages various media types
  - File compression and optimization
  - Local file cleanup

### Dify Integration Layer (`app/dify/`)

**Core Components:**
- `dify_client.py` - Async HTTP client for Dify Workflow API
  - File upload support with proper MIME type handling
  - Streaming response parsing with SSE
  - Error handling and retry logic
- `models.py` - Comprehensive Pydantic models
  - Workflow input/output structures
  - Streaming event models (workflow_started, node_started, text_chunk, etc.)
  - Answer type enumeration for type-based routing
  - Forced command support for direct workflow branch selection
- `workflow_tool.py` - High-level workflow execution
  - Unified interface for blocking/streaming modes
  - Test mode support with forced command routing
  - Special handling for commit message generation

### Handler System (`app/mybot/handlers/`)

**Message Handler (`message_handler.py`)**
- Main orchestrator for all non-command messages
- Special handling for commands sent with media (routed here instead of CommandHandler)
- Implements the core workflow:
  1. Pre-interaction validation via interaction_service
  2. Context building via context_service
  3. Dify invocation via dify_service
  4. Response delivery via response_service

**Command Handlers (`command_handler/`)**
- `/zlib` - Z-Library search with direct link generation
- `/search` - Google search with media support
- `/parse` - Social media content parsing and downloading
- `/help` - Template-based help system
- `/start` - Welcome message

### Key Design Patterns

**Stateless Architecture**
- Each interaction is treated as a one-shot task
- No conversation memory to avoid context pollution in group chats
- User interactions are isolated from each other
- Eliminates the need for `/reset` commands

**Structured Output System**
- Dify Workflow returns JSON with standardized structure:
  - `type`: Task classification (web_search, translation, etc.)
  - `answer`: Main response content
  - `extras`: Additional metadata
- Enables type-based response customization on bot side

**Non-Blocking Concurrency**
- All handlers run as background tasks
- Multiple requests processed simultaneously
- No blocking between different users or commands
- Graceful error isolation

**Multi-Modal Intelligence**
- Supports text, images, documents, audio, video inputs
- Unified file processing pipeline
- Telegraph for rich output beyond Telegram's limits

### Data Storage & Management

**PostgreSQL Database**
- Plugin data persistence
- User access control
- Future extensibility for memory features

**File System Organization**
- `app/data/downloads/` - Temporary media downloads
- `app/data/group_messages/` - Message context storage
- `app/data/private_messages/` - Private chat storage
- `app/data/supergroup_messages/` - Supergroup storage
- Automatic cleanup with configurable retention

### Security & Access Control

**Whitelist System**
- Configurable via TELEGRAM_CHAT_WHITELIST
- Supports private chats, groups, supergroups
- Per-interaction validation
- Super admin commands for management

**Rate Limiting**
- Message edit throttling to avoid Telegram flood limits
- Configurable delays between streaming updates

### Development Features

**Dev Mode (ENABLE_DEV_MODE)**
- Returns mocked templates without Dify calls
- Forces blocking mode for easier debugging
- Auto-disabled on Linux (production)

**Test Mode (ENABLE_TEST_MODE)**
- Routes all requests to TEST branch in Dify
- Logs full Dify outputs for debugging
- Compatible with streaming mode

## Important Implementation Notes

- Bot is designed for Dify Workflow ONLY (not Chatflow) due to structured output requirements
- Each message is processed independently - no conversation state
- HTML parse mode for all responses (not Markdown)
- Comprehensive error handling with user-friendly fallbacks
- Local Telegram Bot API server support for large file handling
- No test files should be written
- No dependencies should be added/removed without permission
- Avoid over-engineering and redundant code

# important-instruction-reminders
Do what has been asked; nothing more, nothing less.
NEVER create files unless they're absolutely necessary for achieving your goal.
ALWAYS prefer editing an existing file to creating a new one.
NEVER proactively create documentation files (*.md) or README files. Only create documentation files if explicitly requested by the User.