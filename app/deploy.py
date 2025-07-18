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
from plugins.zlib_access_points import update_zlib_links
from plugins.zlib_access_points.crud import init_database
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


async def run_zlib_update_job_with_scheduler(scheduler):
    """运行 zlib 更新任务并显示下次运行时间"""
    await run_zlib_update_job()

    # 获取下次运行时间
    job = scheduler.get_job('zlib_update_job')
    if job and job.next_run_time:
        next_run_time = job.next_run_time.strftime('%Y-%m-%d %H:%M:%S')
        logger.info(f"下次运行时间: {next_run_time}")
    else:
        logger.info("无法获取下次运行时间")


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

    # 创建包装函数，用于在任务完成后显示下次运行时间
    async def scheduled_zlib_update_job():
        await run_zlib_update_job_with_scheduler(scheduler)

    # 添加定时任务：每小时运行1次
    scheduler.add_job(
        scheduled_zlib_update_job,
        trigger=CronTrigger(minute=0, timezone='Asia/Shanghai'),
        id='zlib_update_job',
        name='ZLib 更新任务',
        max_instances=1,  # 防止任务重叠
        replace_existing=True,
    )

    # 启动调度器
    scheduler.start()

    # 获取任务的下次运行时间
    job = scheduler.get_job('zlib_update_job')
    if job and job.next_run_time:
        next_run_time = job.next_run_time.strftime('%Y-%m-%d %H:%M:%S')
        logger.success(f"定时任务调度器已启动，下次运行时间: {next_run_time}")
    else:
        logger.success("定时任务调度器已启动")

    # 立即运行一次任务
    logger.info("首次运行 zlib 更新任务")
    await run_zlib_update_job_with_scheduler(scheduler)

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
