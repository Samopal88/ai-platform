"""
Database initializer — quick dev alternative to running alembic migrations.

Usage:
    cd backend
    python scripts/init_db.py

Creates all tables defined by SQLAlchemy models and prints each table name.
"""
import os
import sys

# Allow imports from backend/ root when run as a script
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import create_engine

from app.db.base import Base

# Import all models so their tables are registered on Base.metadata
import app.models.user       # noqa: F401
import app.models.project    # noqa: F401
import app.models.chat       # noqa: F401
import app.models.message    # noqa: F401
import app.models.file       # noqa: F401
import app.models.job        # noqa: F401


def init_db(database_url: str | None = None) -> None:
    url = database_url or os.environ.get("DATABASE_URL", "sqlite:///./storage/app.db")
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}

    # Ensure parent directory exists for SQLite file paths
    if url.startswith("sqlite:///"):
        db_path = url[len("sqlite:///"):]
        if db_path and not db_path.startswith(":"):
            os.makedirs(os.path.dirname(os.path.abspath(db_path)) if os.path.dirname(db_path) else ".", exist_ok=True)
    engine = create_engine(url, connect_args=connect_args)

    Base.metadata.create_all(bind=engine)

    tables = sorted(Base.metadata.tables.keys())
    for table in tables:
        print(f"  created table: {table}")
    print(f"done — {len(tables)} table(s) in {url}")


if __name__ == "__main__":
    init_db()
