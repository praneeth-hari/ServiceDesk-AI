from unittest.mock import MagicMock
from sqlalchemy.orm import Session

from app.services.health import check_database_health


def test_check_database_health_success(db_session: Session):
    """Test health check returns True when database executes successfully."""
    is_healthy, message = check_database_health(db_session)
    assert is_healthy is True
    assert "healthy" in message


def test_check_database_health_failure():
    """Test health check returns False and error message when query fails."""
    mock_session = MagicMock(spec=Session)
    mock_session.execute.side_effect = RuntimeError("Database unreachable")

    is_healthy, message = check_database_health(mock_session)
    assert is_healthy is False
    assert "Database connection failed" in message
