# -*- coding: utf-8 -*-
"""
SQLAlchemy database models
"""
from datetime import datetime

from sqlalchemy import create_engine, Column, String, Boolean, DateTime, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from settings import settings

# Create database engine
engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for models
Base = declarative_base()


class UserRecord(Base):
    """
    User access record table
    Stores hashed user IDs and their access validity status
    """

    __tablename__ = "user_records"

    # SHA256 hash of user ID (primary key)
    id_sha256 = Column(String(64), primary_key=True, index=True)

    # Whether the user currently has valid access
    is_valid = Column(Boolean, default=True, nullable=False, index=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Create composite index for efficient querying
    __table_args__ = (Index('idx_valid_users', 'is_valid', 'id_sha256'),)

    def __repr__(self):
        return f"<UserRecord(id_sha256={self.id_sha256[:8]}..., is_valid={self.is_valid})>"
