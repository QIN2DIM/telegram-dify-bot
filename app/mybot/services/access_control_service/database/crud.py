# -*- coding: utf-8 -*-
"""
CRUD operations for user access control
"""
import hashlib
from datetime import datetime

from sqlalchemy.orm import Session
from loguru import logger

from settings import settings
from .models import UserRecord, SessionLocal


class UserCRUD:
    """CRUD operations for UserRecord table"""

    @staticmethod
    def hash_user_id(user_id: int) -> str:
        """
        Hash user ID with SHA256 and salt

        Args:
            user_id: Telegram user ID

        Returns:
            SHA256 hash string (64 characters)
        """
        salted = f"{settings.SHA256_SALT}{user_id}"
        return hashlib.sha256(salted.encode()).hexdigest()

    @staticmethod
    def get_db() -> Session:
        """Get database session"""
        db = SessionLocal()
        try:
            return db
        except Exception:
            db.close()
            raise

    @classmethod
    def upsert(cls, user_id: int, is_valid: bool = True) -> bool:
        """
        Insert or update user record

        Args:
            user_id: Telegram user ID
            is_valid: Whether the user has valid access

        Returns:
            Success status
        """
        db = cls.get_db()
        try:
            id_hash = cls.hash_user_id(user_id)

            # Check if record exists
            record = db.query(UserRecord).filter(UserRecord.id_sha256 == id_hash).first()

            if record:
                # Update existing record
                record.is_valid = is_valid
                record.updated_at = datetime.utcnow()
                logger.debug(f"Updated user record: {id_hash[:8]}... is_valid={is_valid}")
            else:
                # Create new record
                record = UserRecord(id_sha256=id_hash, is_valid=is_valid)
                db.add(record)
                logger.debug(f"Created user record: {id_hash[:8]}... is_valid={is_valid}")

            db.commit()
            return True

        except Exception as e:
            logger.error(f"Failed to upsert user record: {e}")
            db.rollback()
            return False
        finally:
            db.close()

    @classmethod
    def is_valid(cls, user_id: int) -> bool:
        """
        Check if user has valid access

        Args:
            user_id: Telegram user ID

        Returns:
            True if user has valid access, False otherwise
        """
        db = cls.get_db()
        try:
            id_hash = cls.hash_user_id(user_id)
            record = (
                db.query(UserRecord)
                .filter(UserRecord.id_sha256 == id_hash, UserRecord.is_valid is True)
                .first()
            )

            return record is not None

        except Exception as e:
            logger.error(f"Failed to check user validity: {e}")
            return False
        finally:
            db.close()

    @classmethod
    def get_valid_user_count(cls) -> int:
        """
        Get count of valid users

        Returns:
            Number of users with valid access
        """
        db = cls.get_db()
        try:
            count = db.query(UserRecord).filter(UserRecord.is_valid is True).count()
            return count
        except Exception as e:
            logger.error(f"Failed to count valid users: {e}")
            return 0
        finally:
            db.close()

    @classmethod
    def get_invalid_user_count(cls) -> int:
        """
        Get count of invalid users

        Returns:
            Number of users without valid access
        """
        db = cls.get_db()
        try:
            count = db.query(UserRecord).filter(UserRecord.is_valid is False).count()
            return count
        except Exception as e:
            logger.error(f"Failed to count invalid users: {e}")
            return 0
        finally:
            db.close()

    @classmethod
    def invalidate_user(cls, user_id: int) -> bool:
        """
        Mark user as invalid (used when user leaves a required group)

        Args:
            user_id: Telegram user ID

        Returns:
            Success status
        """
        return cls.upsert(user_id, is_valid=False)

    @classmethod
    def validate_user(cls, user_id: int) -> bool:
        """
        Mark user as valid (used when user joins all required groups)

        Args:
            user_id: Telegram user ID

        Returns:
            Success status
        """
        return cls.upsert(user_id, is_valid=True)
