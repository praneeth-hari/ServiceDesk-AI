from sqlalchemy import text
from sqlalchemy.orm import Session


def check_database_health(db: Session) -> tuple[bool, str]:
    """
    Executes a simple query to confirm the database connection is operational.
    
    Returns:
        tuple[bool, str]: (True, message) if connected, (False, error_message) otherwise.
    """
    try:
        db.execute(text("SELECT 1"))
        return True, "Database connection healthy"
    except Exception as exc:
        return False, f"Database connection failed: {exc}"
