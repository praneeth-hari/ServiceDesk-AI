from collections.abc import Generator
import tempfile
from typing import Any
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings


def get_database_connect_args(
    url: str | None = None,
    ssl_ca: str | None = None,
    ssl_ca_pem: str | None = None,
) -> dict[str, Any]:
    """
    Generate SQLAlchemy connect_args dictionary for database connections.
    Applies TLS/SSL CA verification only for MySQL database URLs.
    SQLite or other engines return an empty connect_args dict so they are never broken.
    """
    target_url = (url if url is not None else settings.DATABASE_URL).strip()

    try:
        parsed_url = make_url(target_url)
        is_mysql = parsed_url.drivername.startswith("mysql")
    except Exception:
        is_mysql = target_url.startswith("mysql://") or target_url.startswith("mysql+")

    if not is_mysql:
        return {}

    ca_path: str | None = None
    if ssl_ca:
        ca_path = ssl_ca
    elif ssl_ca_pem:
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".pem", encoding="utf-8") as f:
            f.write(ssl_ca_pem)
            ca_path = f.name
    elif settings.DATABASE_SSL_CA:
        ca_path = settings.DATABASE_SSL_CA
    elif settings.DATABASE_SSL_CA_PEM:
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".pem", encoding="utf-8") as f:
            f.write(settings.DATABASE_SSL_CA_PEM)
            ca_path = f.name

    if ca_path:
        return {"ssl": {"ca": ca_path}}

    return {}


# Create the SQLAlchemy engine using DATABASE_URL from settings and SSL connect_args if configured
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    connect_args=get_database_connect_args(),
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
