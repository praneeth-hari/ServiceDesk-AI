from collections.abc import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

# Create the SQLAlchemy engine using DATABASE_URL from settings
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
)

# Factory for creating new database sessions
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency that yields a database session per request
    and ensures it is closed once the request is complete.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
