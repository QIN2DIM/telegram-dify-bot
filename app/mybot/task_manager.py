# -*- coding: utf-8 -*-
"""
Centralized task management system for non-blocking bot operations
"""
import asyncio
import functools
from typing import Set, Callable
from contextlib import suppress

from loguru import logger


# Global task registry for all bot operations
_active_tasks: Set[asyncio.Task] = set()


def get_active_tasks_count() -> int:
    """Get the number of currently active background tasks"""
    return len(_active_tasks)


async def cleanup_completed_tasks():
    """Clean up completed tasks from the active tasks set"""
    completed_tasks = [task for task in _active_tasks if task.done()]
    for task in completed_tasks:
        _active_tasks.discard(task)
        # Log any exceptions that occurred in background tasks
        if not task.cancelled() and task.exception():
            logger.error(f"Background task failed: {task.exception()}")


def non_blocking_handler(handler_name: str = "unknown"):
    """
    Decorator to make any bot handler non-blocking by running it as a background task.

    Args:
        handler_name: Name of the handler for logging purposes

    Usage:
        @non_blocking_handler("search_command")
        async def search_command(update, context):
            # This will run in background without blocking other handlers
            pass
    """

    def decorator(handler_func: Callable):
        @functools.wraps(handler_func)
        async def wrapper(update, context):
            # Clean up completed tasks periodically
            await cleanup_completed_tasks()

            # Create background task for the handler
            task = asyncio.create_task(
                _execute_handler_task(handler_func, update, context, handler_name)
            )

            # Add task to set to prevent garbage collection
            _active_tasks.add(task)

            # Log task creation
            logger.info(
                f"Started non-blocking {handler_name} task (Active tasks: {len(_active_tasks)})"
            )

        return wrapper

    return decorator


async def _execute_handler_task(handler_func: Callable, update, context, handler_name: str):
    """Execute handler function as a background task with proper cleanup"""
    current_task = asyncio.current_task()
    try:
        # Execute the actual handler
        await handler_func(update, context)
        logger.debug(f"Completed {handler_name} task")

    except Exception as e:
        logger.exception(f"Error in {handler_name} handler: {e}")

        # Try to send error message to user if possible
        with suppress(Exception):
            if update and update.effective_chat:
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text="❌ 处理请求时发生错误，请稍后重试",
                    parse_mode='HTML',
                    reply_to_message_id=(
                        update.effective_message.message_id if update.effective_message else None
                    ),
                )

    finally:
        # Ensure task is removed from active set when done
        if current_task:
            _active_tasks.discard(current_task)


async def wait_for_all_tasks(timeout: float = 30.0) -> bool:
    """
    Wait for all active tasks to complete, with timeout.
    Useful for graceful shutdown.

    Returns:
        True if all tasks completed, False if timeout occurred
    """
    if not _active_tasks:
        return True

    logger.info(f"Waiting for {len(_active_tasks)} active tasks to complete...")

    try:
        await asyncio.wait_for(
            asyncio.gather(*_active_tasks, return_exceptions=True), timeout=timeout
        )
        logger.info("All tasks completed successfully")
        return True

    except asyncio.TimeoutError:
        logger.warning(
            f"Timeout waiting for tasks to complete, {len(_active_tasks)} tasks still running"
        )
        return False


def cancel_all_tasks():
    """Cancel all active tasks. Use with caution."""
    if not _active_tasks:
        return

    logger.warning(f"Cancelling {len(_active_tasks)} active tasks...")

    for task in _active_tasks.copy():
        if not task.done():
            task.cancel()

    _active_tasks.clear()
    logger.info("All tasks cancelled")
