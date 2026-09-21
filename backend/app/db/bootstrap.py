"""Explicit database bootstrap helpers for local development and tests."""
import logging

from app.core.config import settings
from app.db.base import Base
from app.db.session import engine

_log = logging.getLogger(__name__)


def should_bootstrap_dev_schema() -> bool:
    """Return whether local startup should create missing tables."""
    if not settings.AUTO_CREATE_DB_TABLES:
        return False
    return settings.ENVIRONMENT.lower() not in {"production", "prod"}


def bootstrap_dev_schema() -> None:
    """Create tables only for explicit non-production bootstrap flows."""
    if not should_bootstrap_dev_schema():
        _log.info(
            "Skipping startup DB bootstrap; environment=%s auto_create=%s",
            settings.ENVIRONMENT,
            settings.AUTO_CREATE_DB_TABLES,
        )
        return

    Base.metadata.create_all(bind=engine)
    _log.info("Dev schema bootstrap completed via Base.metadata.create_all")
