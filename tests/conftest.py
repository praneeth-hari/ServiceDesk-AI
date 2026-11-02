from collections.abc import Generator
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import create_access_token, hash_password
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.enums import UserRole
from app.models.user import User

# In-memory SQLite engine for fast, isolated tests
TEST_DATABASE_URL = "sqlite:///:memory:"

test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

TestingSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=test_engine,
)


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    """Create all database tables before test session and drop after."""
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    """Provide a clean transactional session for a test."""
    connection = test_engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def client(db_session: Session) -> Generator[TestClient, None, None]:
    """Provide a TestClient with get_db overridden to use test database session."""
    def override_get_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def requester_user(db_session: Session) -> User:
    """Create and return a user with REQUESTER role."""
    user = User(
        email="requester@example.com",
        full_name="Requester User",
        hashed_password=hash_password("requesterpass"),
        role=UserRole.REQUESTER,
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()
    return user


@pytest.fixture
def second_requester_user(db_session: Session) -> User:
    """Create and return another user with REQUESTER role."""
    user = User(
        email="requester2@example.com",
        full_name="Second Requester",
        hashed_password=hash_password("requesterpass2"),
        role=UserRole.REQUESTER,
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()
    return user


@pytest.fixture
def agent_user(db_session: Session) -> User:
    """Create and return a user with AGENT role."""
    user = User(
        email="agent@example.com",
        full_name="Agent User",
        hashed_password=hash_password("agentpass"),
        role=UserRole.AGENT,
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()
    return user


@pytest.fixture
def admin_user(db_session: Session) -> User:
    """Create and return a user with ADMIN role."""
    user = User(
        email="admin@example.com",
        full_name="Admin User",
        hashed_password=hash_password("adminpass"),
        role=UserRole.ADMIN,
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()
    return user


@pytest.fixture
def requester_token(requester_user: User) -> str:
    """Return a valid JWT access token for the requester."""
    return create_access_token(data={"sub": str(requester_user.id)})


@pytest.fixture
def second_requester_token(second_requester_user: User) -> str:
    """Return a valid JWT access token for the second requester."""
    return create_access_token(data={"sub": str(second_requester_user.id)})


@pytest.fixture
def agent_token(agent_user: User) -> str:
    """Return a valid JWT access token for the agent."""
    return create_access_token(data={"sub": str(agent_user.id)})


@pytest.fixture
def admin_token(admin_user: User) -> str:
    """Return a valid JWT access token for the admin."""
    return create_access_token(data={"sub": str(admin_user.id)})


@pytest.fixture
def requester_auth_headers(requester_token: str) -> dict[str, str]:
    """Return Authorization header dictionary for the requester."""
    return {"Authorization": f"Bearer {requester_token}"}


@pytest.fixture
def second_requester_auth_headers(second_requester_token: str) -> dict[str, str]:
    """Return Authorization header dictionary for the second requester."""
    return {"Authorization": f"Bearer {second_requester_token}"}


@pytest.fixture
def agent_auth_headers(agent_token: str) -> dict[str, str]:
    """Return Authorization header dictionary for the agent."""
    return {"Authorization": f"Bearer {agent_token}"}


@pytest.fixture
def admin_auth_headers(admin_token: str) -> dict[str, str]:
    """Return Authorization header dictionary for the admin."""
    return {"Authorization": f"Bearer {admin_token}"}
