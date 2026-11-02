from unittest.mock import MagicMock, patch

from app.db.session import get_db


def test_get_db_yields_and_closes():
    """Test get_db yields session and closes it in finally block."""
    mock_session = MagicMock()
    with patch("app.db.session.SessionLocal", return_value=mock_session):
        generator = get_db()
        session = next(generator)
        assert session == mock_session
        assert mock_session.close.call_count == 0

        # Generator finishes
        try:
            next(generator)
        except StopIteration:
            pass

        assert mock_session.close.call_count == 1
