import importlib.util
from pathlib import Path
import sqlalchemy as sa
from sqlalchemy.orm import Session


def test_migrations_structure():
    """Verify all Alembic migration files are valid and export required variables."""
    versions_dir = Path("alembic") / "versions"
    migration_files = sorted(
        [f for f in versions_dir.glob("*.py") if not f.name.startswith("__")],
        key=lambda p: p.name,
    )
    assert len(migration_files) >= 9, "Expected at least 9 migrations in alembic/versions"

    for migration_file in migration_files:
        spec = importlib.util.spec_from_file_location("migration_module", migration_file)
        assert spec is not None and spec.loader is not None

        migration_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration_module)

        assert hasattr(migration_module, "revision")
        assert hasattr(migration_module, "upgrade")
        assert callable(migration_module.upgrade)
        assert hasattr(migration_module, "downgrade")
        assert callable(migration_module.downgrade)


def test_migration_0009_backfill_logic(db_session: Session):
    """Test migration 0009 backfill logic on SQLite test database."""
    # 1. Resolved ticket with history entry
    db_session.execute(
        sa.text(
            "INSERT INTO tickets (id, title, description, status, priority, category, requester_id, created_at, updated_at) "
            "VALUES (9001, 'Resolved With History', 'Desc', 'resolved', 'medium', 'other', 1, '2026-10-01 10:00:00', '2026-10-01 15:00:00')"
        )
    )
    db_session.execute(
        sa.text(
            "INSERT INTO ticket_status_history (id, ticket_id, changed_by_id, from_status, to_status, created_at) "
            "VALUES (9001, 9001, 1, 'in_progress', 'resolved', '2026-10-01 14:30:00')"
        )
    )

    # 2. Closed ticket without history (fallback to updated_at)
    db_session.execute(
        sa.text(
            "INSERT INTO tickets (id, title, description, status, priority, category, requester_id, created_at, updated_at) "
            "VALUES (9002, 'Closed No History', 'Desc', 'closed', 'medium', 'other', 1, '2026-10-02 10:00:00', '2026-10-02 16:00:00')"
        )
    )

    # 3. Open ticket (must stay NULL)
    db_session.execute(
        sa.text(
            "INSERT INTO tickets (id, title, description, status, priority, category, requester_id, created_at, updated_at) "
            "VALUES (9003, 'Open Ticket', 'Desc', 'open', 'medium', 'other', 1, '2026-10-03 10:00:00', '2026-10-03 10:00:00')"
        )
    )
    db_session.commit()

    # Execute backfill query from migration 0009
    db_session.execute(
        sa.text(
            """
            UPDATE tickets
            SET resolved_at = COALESCE(
                (
                    SELECT MAX(h.created_at)
                    FROM ticket_status_history h
                    WHERE h.ticket_id = tickets.id AND h.to_status = 'resolved'
                ),
                tickets.updated_at
            )
            WHERE tickets.status IN ('resolved', 'closed')
            """
        )
    )
    db_session.commit()

    # Verify backfill
    t1 = db_session.execute(sa.text("SELECT resolved_at FROM tickets WHERE id = 9001")).scalar()
    assert str(t1).startswith("2026-10-01 14:30:00")

    t2 = db_session.execute(sa.text("SELECT resolved_at FROM tickets WHERE id = 9002")).scalar()
    assert str(t2).startswith("2026-10-02 16:00:00")

    t3 = db_session.execute(sa.text("SELECT resolved_at FROM tickets WHERE id = 9003")).scalar()
    assert t3 is None
