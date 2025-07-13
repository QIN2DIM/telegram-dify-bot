# -*- coding: utf-8 -*-
"""
@Time    : 2025/7/13 12:25
@Author  : QIN2DIM
@GitHub  : https://github.com/QIN2DIM
@Desc    : 数据库模型和初始化
"""
from datetime import datetime
from typing import Optional

from loguru import logger
from sqlalchemy import create_engine, Column, Integer, String, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

from settings import settings

Base = declarative_base()


class ZlibAccessPoint(Base):
    __tablename__ = "zlib_access_points"

    id = Column(Integer, primary_key=True, index=True)
    useful_link = Column(String, nullable=False)
    update_time = Column(DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<ZlibAccessPoint(id={self.id}, useful_link='{self.useful_link}', update_time='{self.update_time}')>"


# 创建数据库引擎
engine = create_engine(settings.DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_database():
    """初始化数据库表"""
    try:
        Base.metadata.create_all(bind=engine)
        logger.success("数据库表初始化成功")
    except Exception as e:
        logger.error(f"数据库表初始化失败: {e}")
        raise


def get_db_session() -> Session:
    """获取数据库会话"""
    return SessionLocal()


def get_latest_zlib_access_point() -> Optional[ZlibAccessPoint]:
    """获取最新的 zlib 访问点"""
    session = get_db_session()
    try:
        return session.query(ZlibAccessPoint).order_by(ZlibAccessPoint.update_time.desc()).first()
    finally:
        session.close()


def save_zlib_access_point(useful_link: str) -> ZlibAccessPoint:
    """保存新的 zlib 访问点"""
    session = get_db_session()
    try:
        # 创建新记录
        new_access_point = ZlibAccessPoint(useful_link=useful_link, update_time=datetime.utcnow())
        session.add(new_access_point)
        session.commit()
        session.refresh(new_access_point)
        logger.info(f"已保存新的 zlib 访问点: {useful_link}")
        return new_access_point
    except Exception as e:
        session.rollback()
        logger.error(f"保存 zlib 访问点失败: {e}")
        raise
    finally:
        session.close()
