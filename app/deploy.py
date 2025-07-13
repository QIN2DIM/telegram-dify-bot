# -*- coding: utf-8 -*-
"""
@Time    : 2025/7/13 12:19
@Author  : QIN2DIM
@GitHub  : https://github.com/QIN2DIM
@Desc    : 部署定时任务
"""
import asyncio
import signal
import sys

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from loguru import logger

from settings import LOG_DIR
from triggers.zlib_access_points import update_zlib_links
from triggers.zlib_access_points.crud import init_database
from utils import init_log

init_log(
    runtime=LOG_DIR.joinpath("runtime.log"),
    error=LOG_DIR.joinpath("error.log"),
    serialize=LOG_DIR.joinpath("serialize.log"),
)


async def run_zlib_update_job():
    """运行 zlib 更新任务"""
    try:
        logger.info("开始运行 zlib 更新任务")
        success = update_zlib_links(should_update_db=True)
        if success:
            logger.success("zlib 更新任务完成")
        else:
            logger.warning("zlib 更新任务失败")
    except Exception as e:
        logger.error(f"运行 zlib 更新任务时发生错误: {e}")


async def main():
    """主函数 - 初始化并启动定时任务调度器"""
    logger.info("正在启动定时任务...")

    # 初始化数据库
    try:
        init_database()
    except Exception as e:
        logger.error(f"初始化数据库失败: {e}")
        return

    # 创建异步调度器
    scheduler = AsyncIOScheduler(timezone='Asia/Shanghai')

    # 添加定时任务：每天凌晨04:00运行
    scheduler.add_job(
        run_zlib_update_job,
        trigger=CronTrigger(hour=4, minute=0, timezone='Asia/Shanghai'),
        id='zlib_update_job',
        name='ZLib 更新任务',
        max_instances=1,  # 防止任务重叠
        replace_existing=True,
    )

    # 启动调度器
    scheduler.start()
    logger.success("定时任务调度器已启动，将在每天凌晨04:00（东八区）运行")

    # 立即运行一次任务
    logger.info("首次运行 zlib 更新任务")
    await run_zlib_update_job()

    # 设置优雅关闭
    def shutdown_handler(signum, frame):
        logger.info("接收到关闭信号，正在停止调度器...")
        scheduler.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    try:
        # 保持程序运行
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        logger.info("收到键盘中断信号，正在停止调度器...")
        scheduler.shutdown()
    except Exception as e:
        logger.error(f"程序运行时发生错误: {e}")
        scheduler.shutdown()
        raise


if __name__ == '__main__':
    asyncio.run(main())
