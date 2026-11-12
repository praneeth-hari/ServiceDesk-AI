"""
Two admins demoting each other at the same instant must not leave the system with no admin.

Needs a real MySQL (the lock is SELECT ... FOR UPDATE, which SQLite does not have), so this runs
only when TEST_MYSQL_URL is set (it is in CI) and uses committed rows that it removes afterwards.
"""
import os
import threading
import time
import uuid
from unittest.mock import MagicMock

from fastapi import HTTPException
import pytest
import sqlalchemy as sa
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Session, sessionmaker

from app.core.security import hash_password
from app.models.enums import UserRole
from app.models.user import User
from app.services.users import _lock_active_admins, update_user_role

TEST_MYSQL_URL = os.getenv("TEST_MYSQL_URL")


def test_admin_lock_query_uses_for_update_on_mysql():
    """The helper locks the active admin rows (checked without needing a database)."""
    db = MagicMock()
    db.scalars.return_value.all.return_value = []
    _lock_active_admins(db)
    statement = db.scalars.call_args[0][0]
    assert "FOR UPDATE" in str(statement.compile(dialect=mysql.dialect()))


@pytest.mark.mysql
@pytest.mark.skipif(not TEST_MYSQL_URL, reason="TEST_MYSQL_URL is not set; skipping MySQL tests")
def test_two_admins_cannot_demote_each_other_concurrently():
    engine = sa.create_engine(TEST_MYSQL_URL)
    make_session = sessionmaker(bind=engine, autoflush=False)

    with make_session() as setup:
        if setup.scalar(sa.select(sa.func.count(User.id)).where(
            User.role == UserRole.ADMIN, User.is_active.is_(True)
        )):
            pytest.skip("the test database already has active admins")
        suffix = uuid.uuid4().hex[:8]
        admins = []
        for name in ("a", "b"):
            user = User(
                email=f"race-{name}-{suffix}@example.com",
                full_name=f"Race {name}",
                hashed_password=hash_password("password123"),
                role=UserRole.ADMIN,
                is_active=True,
            )
            setup.add(user)
            admins.append(user)
        setup.commit()
        id_a, id_b = admins[0].id, admins[1].id

    outcomes: dict[str, str] = {}

    def demote(label: str, target_id: int, actor_id: int, hold_before_commit: float):
        with make_session() as session:
            original_commit = session.commit

            def slow_commit():
                # Keep the first transaction open so the second one overlaps with it
                time.sleep(hold_before_commit)
                original_commit()

            session.commit = slow_commit
            try:
                update_user_role(session, user_id=target_id, new_role=UserRole.AGENT, actor_id=actor_id)
                outcomes[label] = "demoted"
            except HTTPException as exc:
                outcomes[label] = f"refused:{exc.status_code}"

    try:
        first = threading.Thread(target=demote, args=("first", id_b, id_a, 1.5))
        second = threading.Thread(target=demote, args=("second", id_a, id_b, 0.0))
        first.start()
        time.sleep(0.4)  # the first has locked the admin rows and is waiting to commit
        second.start()
        first.join(30)
        second.join(30)

        with make_session() as check:
            remaining = check.scalar(sa.select(sa.func.count(User.id)).where(
                User.id.in_([id_a, id_b]), User.role == UserRole.ADMIN, User.is_active.is_(True)
            ))
        assert remaining == 1, f"expected one admin to remain, got {remaining} ({outcomes})"
        assert sorted(outcomes.values()) == ["demoted", "refused:400"], outcomes
    finally:
        with make_session() as cleanup:
            cleanup.execute(sa.delete(User).where(User.id.in_([id_a, id_b])))
            cleanup.commit()
        engine.dispose()
