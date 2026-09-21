"""
AI Workspace Platform - Database Base
SQLAlchemy base configuration and common utilities

Note: Database connection is not required for MVP demo.
These models provide structure for future database integration.
"""
from datetime import datetime
from typing import Any
from sqlalchemy import create_engine, MetaData
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Naming convention for constraints
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s"
}

metadata = MetaData(naming_convention=NAMING_CONVENTION)

# Base class for all models
Base = declarative_base(metadata=metadata)


class TimestampMixin:
    """Mixin that adds created_at and updated_at timestamps"""
    from sqlalchemy import Column, DateTime

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


# Database URL placeholder (will be configured via environment)
DATABASE_URL = "postgresql://user:password@localhost:5432/ai_workspace"

# Engine and session will be created when database is available
_engine = None
_SessionLocal = None


def get_engine(database_url: str = None):
    """Get or create database engine"""
    global _engine
    if _engine is None and database_url:
        _engine = create_engine(
            database_url,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10
        )
    return _engine


def get_session_factory(database_url: str = None):
    """Get or create session factory"""
    global _SessionLocal
    if _SessionLocal is None:
        engine = get_engine(database_url)
        if engine:
            _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return _SessionLocal


def create_all_tables(database_url: str):
    """Create all tables in the database"""
    engine = get_engine(database_url)
    if engine:
        Base.metadata.create_all(bind=engine)
