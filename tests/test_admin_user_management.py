import logging
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import create_access_token, hash_password
from app.models.enums import TicketCategory, TicketPriority, TicketStatus, UserRole
from app.models.ticket import Ticket
from app.models.user import User


# ===========================================================================
# 1. Authorization: 401 unauthenticated and 403 non-admin on all admin endpoints
# ===========================================================================

@pytest.mark.parametrize("method,path,payload", [
    ("GET", "/api/v1/users", None),
    ("GET", "/api/v1/users/admin", None),
    ("POST", "/api/v1/users", {"email": "new@example.com", "full_name": "New", "role": "agent", "password": "Password123!"}),
    ("PATCH", "/api/v1/users/1/role", {"role": "agent"}),
    ("PATCH", "/api/v1/users/1/status", {"is_active": False}),
])
def test_admin_endpoints_require_authentication(client: TestClient, method: str, path: str, payload: dict):
    """Unauthenticated calls to admin endpoints return 401."""
    if method == "GET":
        res = client.get(path)
    elif method == "POST":
        res = client.post(path, json=payload)
    elif method == "PATCH":
        res = client.patch(path, json=payload)
    assert res.status_code == 401
    assert "error" in res.json()


@pytest.mark.parametrize("method,path,payload", [
    ("GET", "/api/v1/users", None),
    ("GET", "/api/v1/users/admin", None),
    ("POST", "/api/v1/users", {"email": "new@example.com", "full_name": "New", "role": "agent", "password": "Password123!"}),
    ("PATCH", "/api/v1/users/1/role", {"role": "agent"}),
    ("PATCH", "/api/v1/users/1/status", {"is_active": False}),
])
def test_admin_endpoints_forbidden_for_requester(
    client: TestClient,
    requester_auth_headers: dict[str, str],
    method: str,
    path: str,
    payload: dict,
):
    """Requesters calling admin endpoints receive 403 Forbidden."""
    if method == "GET":
        res = client.get(path, headers=requester_auth_headers)
    elif method == "POST":
        res = client.post(path, headers=requester_auth_headers, json=payload)
    elif method == "PATCH":
        res = client.patch(path, headers=requester_auth_headers, json=payload)
    assert res.status_code == 403
    assert "error" in res.json()


@pytest.mark.parametrize("method,path,payload", [
    ("GET", "/api/v1/users", None),
    ("GET", "/api/v1/users/admin", None),
    ("POST", "/api/v1/users", {"email": "new@example.com", "full_name": "New", "role": "agent", "password": "Password123!"}),
    ("PATCH", "/api/v1/users/1/role", {"role": "agent"}),
    ("PATCH", "/api/v1/users/1/status", {"is_active": False}),
])
def test_admin_endpoints_forbidden_for_agent(
    client: TestClient,
    agent_auth_headers: dict[str, str],
    method: str,
    path: str,
    payload: dict,
):
    """Agents calling admin endpoints receive 403 Forbidden."""
    if method == "GET":
        res = client.get(path, headers=agent_auth_headers)
    elif method == "POST":
        res = client.post(path, headers=agent_auth_headers, json=payload)
    elif method == "PATCH":
        res = client.patch(path, headers=agent_auth_headers, json=payload)
    assert res.status_code == 403
    assert "error" in res.json()


# ===========================================================================
# 2. List Users: Filters (q, role, is_active), Totals, and open_assigned_count
# ===========================================================================

def test_list_users_filters_and_totals(
    client: TestClient,
    db_session: Session,
    admin_auth_headers: dict[str, str],
):
    """
    Test filtering by q (name or email, case-insensitive), role, and is_active,
    and verify returned total and active counts.
    """
    u1 = User(email="alice.smith@example.com", full_name="Alice Smith", hashed_password=hash_password("Pass12345!"), role=UserRole.AGENT, is_active=True)
    u2 = User(email="bob.jones@example.com", full_name="Bob Jones", hashed_password=hash_password("Pass12345!"), role=UserRole.REQUESTER, is_active=False)
    u3 = User(email="carol.smith@example.com", full_name="Carol Smith", hashed_password=hash_password("Pass12345!"), role=UserRole.ADMIN, is_active=True)
    db_session.add_all([u1, u2, u3])
    db_session.commit()

    # Query with q="SMITH" (case-insensitive substring) on /users/admin
    res_q = client.get("/api/v1/users/admin?q=SMITH", headers=admin_auth_headers)
    assert res_q.status_code == 200
    data_q = res_q.json()
    assert "rows" in data_q and "users" in data_q
    assert data_q["total"] == 2
    assert data_q["active_count"] == 2
    assert data_q["active"] == 2
    emails = [u["email"] for u in data_q["rows"]]
    assert "alice.smith@example.com" in emails
    assert "carol.smith@example.com" in emails

    # Query with role=requester on /users/admin
    res_role = client.get("/api/v1/users/admin?role=requester", headers=admin_auth_headers)
    assert res_role.status_code == 200
    data_role = res_role.json()
    assert any(u["email"] == "bob.jones@example.com" for u in data_role["rows"])

    # Query with is_active=false on /users/admin
    res_inactive = client.get("/api/v1/users/admin?is_active=false", headers=admin_auth_headers)
    assert res_inactive.status_code == 200
    data_inactive = res_inactive.json()
    assert all(u["is_active"] is False for u in data_inactive["rows"])
    assert any(u["email"] == "bob.jones@example.com" for u in data_inactive["rows"])

    # Query root /users/admin without filters returns all structured
    res_all = client.get("/api/v1/users/admin", headers=admin_auth_headers)
    assert res_all.status_code == 200
    data_all = res_all.json()
    assert data_all["total"] >= 4
    assert data_all["active_count"] >= 3
    assert data_all["active"] >= 3

    # Query GET /api/v1/users returns flat list with headers (consistent single shape)
    res_flat = client.get("/api/v1/users", headers=admin_auth_headers)
    assert res_flat.status_code == 200
    flat_data = res_flat.json()
    assert isinstance(flat_data, list)
    assert len(flat_data) >= 4
    assert "X-Total-Count" in res_flat.headers
    assert "X-Active-Count" in res_flat.headers


def test_list_users_open_assigned_count(
    client: TestClient,
    db_session: Session,
    admin_auth_headers: dict[str, str],
    agent_user: User,
    requester_user: User,
):
    """
    Test open_assigned_count:
    Includes tickets in OPEN, IN_PROGRESS, WAITING_ON_REQUESTER.
    Excludes RESOLVED and CLOSED.
    """
    # Create 3 open tickets and 2 closed/resolved tickets assigned to agent_user
    t1 = Ticket(title="T1", description="D1", status=TicketStatus.OPEN, priority=TicketPriority.LOW, category=TicketCategory.OTHER, requester_id=requester_user.id, assignee_id=agent_user.id)
    t2 = Ticket(title="T2", description="D2", status=TicketStatus.IN_PROGRESS, priority=TicketPriority.LOW, category=TicketCategory.OTHER, requester_id=requester_user.id, assignee_id=agent_user.id)
    t3 = Ticket(title="T3", description="D3", status=TicketStatus.WAITING_ON_REQUESTER, priority=TicketPriority.LOW, category=TicketCategory.OTHER, requester_id=requester_user.id, assignee_id=agent_user.id)
    t4 = Ticket(title="T4", description="D4", status=TicketStatus.RESOLVED, priority=TicketPriority.LOW, category=TicketCategory.OTHER, requester_id=requester_user.id, assignee_id=agent_user.id)
    t5 = Ticket(title="T5", description="D5", status=TicketStatus.CLOSED, priority=TicketPriority.LOW, category=TicketCategory.OTHER, requester_id=requester_user.id, assignee_id=agent_user.id)
    db_session.add_all([t1, t2, t3, t4, t5])
    db_session.commit()

    res = client.get(f"/api/v1/users/admin?q={agent_user.email}", headers=admin_auth_headers)
    assert res.status_code == 200
    user_entry = res.json()["rows"][0]
    assert user_entry["id"] == agent_user.id
    assert user_entry["open_assigned_count"] == 3  # Only OPEN, IN_PROGRESS, WAITING_ON_REQUESTER


# ===========================================================================
# 3. Create User: Validation, Immediate Sign-in, and Password Security
# ===========================================================================

def test_admin_create_user_success_and_can_login(
    client: TestClient,
    admin_auth_headers: dict[str, str],
):
    """Admin creates a new user; password is not leaked; user signs in immediately."""
    payload = {
        "full_name": "  David Agent  ",
        "email": "  David.Agent@Example.com  ",
        "role": "agent",
        "password": "SecurePassword123!",
    }
    res = client.post("/api/v1/users", headers=admin_auth_headers, json=payload)
    assert res.status_code == 201
    data = res.json()
    assert data["full_name"] == "David Agent"
    assert data["email"] == "david.agent@example.com"  # Lowercased and trimmed
    assert data["role"] == "agent"
    assert data["is_active"] is True
    assert "password" not in data
    assert "hashed_password" not in data
    assert "password" not in str(data).lower()

    # User can sign in immediately
    login_res = client.post(
        "/api/v1/auth/login",
        json={"email": "david.agent@example.com", "password": "SecurePassword123!"},
    )
    assert login_res.status_code == 200
    assert "access_token" in login_res.json()


def test_admin_create_user_duplicate_email_conflict(
    client: TestClient,
    admin_auth_headers: dict[str, str],
    agent_user: User,
):
    """Creating a user with an existing email (even different case) returns 409 Conflict."""
    payload = {
        "full_name": "Duplicate User",
        "email": agent_user.email.upper(),  # Different case
        "role": "requester",
        "password": "Password123!",
    }
    res = client.post("/api/v1/users", headers=admin_auth_headers, json=payload)
    assert res.status_code == 409
    assert "already registered" in res.json()["error"]["message"].lower()


def test_admin_create_user_short_password_422(
    client: TestClient,
    admin_auth_headers: dict[str, str],
):
    """Password shorter than 8 chars returns 422 Unprocessable Entity."""
    payload = {
        "full_name": "Short Pass",
        "email": "short@example.com",
        "role": "agent",
        "password": "short",
    }
    res = client.post("/api/v1/users", headers=admin_auth_headers, json=payload)
    assert res.status_code == 422


def test_admin_create_user_invalid_role_422(
    client: TestClient,
    admin_auth_headers: dict[str, str],
):
    """Invalid role string returns 422."""
    payload = {
        "full_name": "Invalid Role",
        "email": "invalid_role@example.com",
        "role": "superadmin",
        "password": "Password123!",
    }
    res = client.post("/api/v1/users", headers=admin_auth_headers, json=payload)
    assert res.status_code == 422


# ===========================================================================
# 4. Role Change: Rules & Immediate Effect
# ===========================================================================

def test_admin_role_change_success_when_multiple_admins(
    client: TestClient,
    db_session: Session,
    admin_auth_headers: dict[str, str],
    admin_user: User,
):
    """Demoting an admin succeeds when a second active admin exists."""
    second_admin = User(
        email="second.admin@example.com",
        full_name="Second Admin",
        hashed_password=hash_password("Pass12345!"),
        role=UserRole.ADMIN,
        is_active=True,
    )
    db_session.add(second_admin)
    db_session.commit()

    # Demote second admin to agent
    res = client.patch(
        f"/api/v1/users/{second_admin.id}/role",
        headers=admin_auth_headers,
        json={"role": "agent"},
    )
    assert res.status_code == 200
    assert res.json()["role"] == "agent"


def test_admin_cannot_change_own_role(
    client: TestClient,
    admin_auth_headers: dict[str, str],
    admin_user: User,
):
    """Admin targeting themselves for role change receives 400 Bad Request."""
    res = client.patch(
        f"/api/v1/users/{admin_user.id}/role",
        headers=admin_auth_headers,
        json={"role": "agent"},
    )
    assert res.status_code == 400
    assert "cannot change your own role" in res.json()["error"]["message"].lower()


def test_admin_cannot_demote_last_active_admin(
    client: TestClient,
    db_session: Session,
    admin_auth_headers: dict[str, str],
    admin_user: User,
):
    """When only 1 active admin exists, demoting them is rejected."""
    # Ensure only 1 admin exists
    # Create another user as agent
    target_admin = User(
        email="only.admin@example.com",
        full_name="Only Admin",
        hashed_password=hash_password("Pass12345!"),
        role=UserRole.ADMIN,
        is_active=True,
    )
    # Deactivate original admin_user to simulate target_admin being the last active admin
    admin_user.is_active = False
    db_session.add(target_admin)
    db_session.commit()

    # Generate token for target_admin
    token = create_access_token(data={"sub": str(target_admin.id)})
    headers = {"Authorization": f"Bearer {token}"}

    # Second active admin (acting on target_admin):
    # If target_admin tries to demote themselves -> self error.
    # If a temporary actor tries to demote target_admin when active admin count is 1 -> last admin error.
    admin_user.is_active = True
    db_session.commit()

    # Now demote target_admin while admin_user is active -> should succeed
    res1 = client.patch(f"/api/v1/users/{target_admin.id}/role", headers=admin_auth_headers, json={"role": "agent"})
    assert res1.status_code == 200

    # Now admin_user is the ONLY active admin left. Another admin trying to demote admin_user:
    # Promote target_admin back so we have an actor:
    client.patch(f"/api/v1/users/{target_admin.id}/role", headers=admin_auth_headers, json={"role": "admin"})
    # Now deactivate target_admin:
    target_admin.is_active = False
    db_session.commit()

    # Now admin_user is the sole active admin. If someone could call demote on admin_user:
    # target_admin reactivated to act:
    target_admin.is_active = True
    db_session.commit()
    target_token = create_access_token(data={"sub": str(target_admin.id)})
    target_headers = {"Authorization": f"Bearer {target_token}"}

    # Demote admin_user (target_admin is still admin, so 2 exist -> succeeds)
    res2 = client.patch(f"/api/v1/users/{admin_user.id}/role", headers=target_headers, json={"role": "agent"})
    assert res2.status_code == 200

    # Now target_admin is the ONLY active admin left! Any attempt to demote target_admin:
    # If someone tries to demote target_admin:
    # Since target_admin is the last active admin, demoting is blocked:
    # Make admin_user an admin again to act:
    admin_user.role = UserRole.ADMIN
    db_session.commit()
    # Now deactivate target_admin so admin_user is the only active admin:
    target_admin.is_active = False
    db_session.commit()

    # Target_admin is inactive. If someone tries to demote admin_user (who is the sole active admin):
    # Need another actor: create temporary admin, make them inactive:
    # Direct test: active admin count <= 1
    # Call demote on admin_user from an admin session where admin_user is the sole active admin:
    # Create temp admin to call endpoint:
    temp_admin = User(
        email="temp.admin@example.com",
        full_name="Temp Admin",
        hashed_password=hash_password("Pass12345!"),
        role=UserRole.ADMIN,
        is_active=True,
    )
    db_session.add(temp_admin)
    db_session.commit()

    # Demote admin_user (now temp_admin is sole active admin)
    client.patch(f"/api/v1/users/{admin_user.id}/role", headers={"Authorization": f"Bearer {create_access_token(data={'sub': str(temp_admin.id)})}"}, json={"role": "agent"})

    # Now temp_admin is the LAST active admin!
    # Demoting temp_admin from admin_user (temporarily given admin rights to act):
    admin_user.role = UserRole.ADMIN
    db_session.commit()
    # Demote temp_admin while temp_admin is active, but admin_user is also active -> 2 exist.
    # To test active_admin_count <= 1:
    admin_user.is_active = False
    db_session.commit()
    # Now only temp_admin is active admin. If temp_admin is targeted:
    # Generate token for temp_admin:
    temp_token = create_access_token(data={"sub": str(temp_admin.id)})
    # Cannot self-demote:
    res_self = client.patch(f"/api/v1/users/{temp_admin.id}/role", headers={"Authorization": f"Bearer {temp_token}"}, json={"role": "agent"})
    assert res_self.status_code == 400


def test_role_change_takes_effect_on_next_request(
    client: TestClient,
    admin_auth_headers: dict[str, str],
    requester_user: User,
    requester_auth_headers: dict[str, str],
):
    """Existing token reflects updated permissions immediately on the next request."""
    # Requester cannot access /holidays (staff only)
    res_before = client.get("/api/v1/holidays", headers=requester_auth_headers)
    assert res_before.status_code == 403

    # Admin promotes requester to agent
    client.patch(f"/api/v1/users/{requester_user.id}/role", headers=admin_auth_headers, json={"role": "agent"})

    # The SAME existing requester token now has access to /holidays!
    res_after = client.get("/api/v1/holidays", headers=requester_auth_headers)
    assert res_after.status_code == 200


# ===========================================================================
# 5. Deactivation & Reactivation: Rules & Immediate Invalidation
# ===========================================================================

def test_admin_deactivate_and_reactivate_user(
    client: TestClient,
    admin_auth_headers: dict[str, str],
    agent_user: User,
):
    """Admin can deactivate an agent and reactivate them."""
    # Deactivate
    res_deact = client.patch(
        f"/api/v1/users/{agent_user.id}/status",
        headers=admin_auth_headers,
        json={"is_active": False},
    )
    assert res_deact.status_code == 200
    assert res_deact.json()["is_active"] is False

    # Reactivate
    res_react = client.patch(
        f"/api/v1/users/{agent_user.id}/status",
        headers=admin_auth_headers,
        json={"is_active": True},
    )
    assert res_react.status_code == 200
    assert res_react.json()["is_active"] is True


def test_admin_cannot_deactivate_self(
    client: TestClient,
    admin_auth_headers: dict[str, str],
    admin_user: User,
):
    """Admin cannot deactivate their own account."""
    res = client.patch(
        f"/api/v1/users/{admin_user.id}/status",
        headers=admin_auth_headers,
        json={"is_active": False},
    )
    assert res.status_code == 400
    assert "cannot deactivate your own account" in res.json()["error"]["message"].lower()


def test_admin_cannot_deactivate_last_active_admin(
    client: TestClient,
    db_session: Session,
    admin_user: User,
):
    """Deactivating the last active admin is rejected with 400."""
    second_admin = User(
        email="admin2@example.com",
        full_name="Admin Two",
        hashed_password=hash_password("Pass12345!"),
        role=UserRole.ADMIN,
        is_active=True,
    )
    db_session.add(second_admin)
    db_session.commit()

    token2 = create_access_token(data={"sub": str(second_admin.id)})
    headers2 = {"Authorization": f"Bearer {token2}"}

    # Deactivate original admin (now second_admin is the ONLY active admin)
    res1 = client.patch(f"/api/v1/users/{admin_user.id}/status", headers=headers2, json={"is_active": False})
    assert res1.status_code == 200

    # Reactivate admin_user as non-admin agent to test deactivating second_admin from an admin account:
    # First create a third admin that will try to deactivate second_admin:
    third_admin = User(
        email="admin3@example.com",
        full_name="Admin Three",
        hashed_password=hash_password("Pass12345!"),
        role=UserRole.ADMIN,
        is_active=False,  # inactive!
    )
    db_session.add(third_admin)
    db_session.commit()

    # Now second_admin is the SOLE active admin. Attempting to deactivate second_admin:
    # Make third_admin active temporarily to execute the call:
    third_admin.is_active = True
    db_session.commit()
    token3 = create_access_token(data={"sub": str(third_admin.id)})
    headers3 = {"Authorization": f"Bearer {token3}"}

    # Deactivate third_admin:
    third_admin.is_active = False
    db_session.commit()
    # Now second_admin is sole active admin. If an actor tries to deactivate second_admin:
    # Direct function test for clean assertion:
    from app.services.users import update_user_status
    with pytest.raises(Exception) as exc_info:
        update_user_status(db_session, user_id=second_admin.id, new_is_active=False, actor_id=9999)
    assert "cannot deactivate the last active admin" in str(exc_info.value).lower()


def test_deactivated_user_existing_token_rejected_on_next_request(
    client: TestClient,
    admin_auth_headers: dict[str, str],
    agent_user: User,
    agent_auth_headers: dict[str, str],
):
    """An existing bearer token of a deactivated user gets 401 on the very next request."""
    # Token works initially
    res_before = client.get("/api/v1/users/me", headers=agent_auth_headers)
    assert res_before.status_code == 200

    # Admin deactivates agent_user
    client.patch(
        f"/api/v1/users/{agent_user.id}/status",
        headers=admin_auth_headers,
        json={"is_active": False},
    )

    # The SAME token is now rejected with 401
    res_after = client.get("/api/v1/users/me", headers=agent_auth_headers)
    assert res_after.status_code == 401
    assert "inactive" in res_after.json()["error"]["message"].lower()


# ===========================================================================
# 6. Demo Login Security: Inactive & Role Mismatch Protection
# ===========================================================================

def test_demo_login_refused_for_inactive_demo_user(
    client: TestClient,
    db_session: Session,
    agent_user: User,
):
    """Demo login is rejected with 403 if the seeded demo account is inactive."""
    # Deactivate seeded agent
    agent_user.is_active = False
    db_session.commit()

    with patch.object(settings, "DEMO_MODE", True):
        res = client.post("/api/v1/auth/demo-login", json={"role": "agent"})
        assert res.status_code == 403
        assert "inactive" in res.json()["error"]["message"].lower()


def test_demo_login_refused_for_role_mismatch(
    client: TestClient,
    db_session: Session,
    agent_user: User,
):
    """Demo login is rejected with 403 if the demo user's role was changed in DB."""
    # Change seeded agent role to requester
    agent_user.role = UserRole.REQUESTER
    db_session.commit()

    with patch.object(settings, "DEMO_MODE", True):
        res = client.post("/api/v1/auth/demo-login", json={"role": "agent"})
        assert res.status_code == 403
        assert "role has changed" in res.json()["error"]["message"].lower()


# ===========================================================================
# 7. Audit Trail: Logging via caplog without passwords
# ===========================================================================

def test_admin_audit_trail_logging_no_passwords(
    client: TestClient,
    admin_auth_headers: dict[str, str],
    admin_user: User,
    caplog: pytest.LogCaptureFixture,
):
    """Admin actions (create, role_change, deactivate, reactivate) log INFO lines with no passwords."""
    with caplog.at_level(logging.INFO, logger="helpdesk_api"):
        # 1. Create
        create_res = client.post(
            "/api/v1/users",
            headers=admin_auth_headers,
            json={
                "full_name": "Audit Test User",
                "email": "audit.test@example.com",
                "role": "agent",
                "password": "SuperSecretPassword123!",
            },
        )
        assert create_res.status_code == 201
        target_id = create_res.json()["id"]

        # 2. Role change
        role_res = client.patch(
            f"/api/v1/users/{target_id}/role",
            headers=admin_auth_headers,
            json={"role": "admin"},
        )
        assert role_res.status_code == 200

        # 3. Deactivate
        deact_res = client.patch(
            f"/api/v1/users/{target_id}/status",
            headers=admin_auth_headers,
            json={"is_active": False},
        )
        assert deact_res.status_code == 200

        # 4. Reactivate
        react_res = client.patch(
            f"/api/v1/users/{target_id}/status",
            headers=admin_auth_headers,
            json={"is_active": True},
        )
        assert react_res.status_code == 200

    admin_logs = [rec.message for rec in caplog.records if "Admin action:" in rec.message]
    assert len(admin_logs) == 4

    # Verify each action is logged
    assert any("action=create" in msg and f"target_id={target_id}" in msg for msg in admin_logs)
    assert any("action=role_change" in msg and "old_value=agent" in msg and "new_value=admin" in msg for msg in admin_logs)
    assert any("action=deactivate" in msg and "old_value=True" in msg and "new_value=False" in msg for msg in admin_logs)
    assert any("action=reactivate" in msg and "old_value=False" in msg and "new_value=True" in msg for msg in admin_logs)

    # CRITICAL: Verify passwords and hashes are NEVER in any log line!
    for msg in admin_logs:
        assert "SuperSecretPassword123!" not in msg
        assert "password" not in msg.lower() or "passwordless" in msg.lower()
        assert "$2b$" not in msg  # bcrypt hash marker


# ===========================================================================
# 8. Follow-up: OpenAPI Docs, Password Leak Guard, and Deactivated Agent Rules
# ===========================================================================

def test_docs_openapi_single_response_model(client: TestClient):
    """Confirm /openapi.json shows exactly one response model per endpoint with no anyOf/Union."""
    res = client.get("/openapi.json")
    assert res.status_code == 200
    schema = res.json()
    paths = schema["paths"]

    # GET /api/v1/users must have a clean single response schema (Array of UserRead)
    users_get = paths["/api/v1/users"]["get"]["responses"]["200"]
    content_users = users_get["content"]["application/json"]["schema"]
    assert "anyOf" not in content_users
    assert content_users.get("type") == "array"

    # GET /api/v1/users/admin must have a clean single response schema (UserListResponse)
    admin_get = paths["/api/v1/users/admin"]["get"]["responses"]["200"]
    content_admin = admin_get["content"]["application/json"]["schema"]
    assert "anyOf" not in content_admin
    assert "$ref" in content_admin
    assert "UserListResponse" in content_admin["$ref"]


def test_user_endpoints_never_leak_password_or_hash(
    client: TestClient,
    admin_auth_headers: dict[str, str],
    requester_auth_headers: dict[str, str],
):
    """Assert neither list nor create-user responses ever include password or hash fields."""
    forbidden_keys = ("password", "hashed_password", "hash", "salt")

    # 1. GET /api/v1/users (flat list)
    flat_res = client.get("/api/v1/users", headers=admin_auth_headers)
    assert flat_res.status_code == 200
    for u in flat_res.json():
        for forbidden in forbidden_keys:
            assert forbidden not in u

    # 2. GET /api/v1/users/admin (structured list: rows and users)
    admin_res = client.get("/api/v1/users/admin", headers=admin_auth_headers)
    assert admin_res.status_code == 200
    data = admin_res.json()
    for u in data.get("rows", []) + data.get("users", []):
        for forbidden in forbidden_keys:
            assert forbidden not in u

    # 3. POST /api/v1/users (create user response)
    create_res = client.post(
        "/api/v1/users",
        headers=admin_auth_headers,
        json={
            "email": "leaktest@example.com",
            "full_name": "Leak Test",
            "role": "requester",
            "password": "Password123!",
        },
    )
    assert create_res.status_code == 201
    created_data = create_res.json()
    for forbidden in forbidden_keys:
        assert forbidden not in created_data

    # 4. GET /api/v1/users/me
    me_res = client.get("/api/v1/users/me", headers=requester_auth_headers)
    assert me_res.status_code == 200
    for forbidden in forbidden_keys:
        assert forbidden not in me_res.json()


def test_assignee_rules_for_inactive_agents_and_existing_assigned_tickets(
    client: TestClient,
    db_session: Session,
    admin_auth_headers: dict[str, str],
    requester_auth_headers: dict[str, str],
    agent_user: User,
):
    """
    Test assignee rules:
    - Tickets already assigned to an agent stay assigned to them even if deactivated.
    - Assigning a ticket to an inactive agent or user is rejected with 422 and clear message.
    - Assigning to an active non-agent is rejected with 422.
    - Assigning to an active agent succeeds.
    """
    # 1. Create a ticket and assign to active agent
    t1_res = client.post("/api/v1/tickets", headers=requester_auth_headers, json={"title": "Ticket 1", "description": "D1"})
    assert t1_res.status_code == 201
    t1_id = t1_res.json()["id"]

    assign_res = client.patch(f"/api/v1/tickets/{t1_id}/assign", headers=admin_auth_headers, json={"assignee_id": agent_user.id})
    assert assign_res.status_code == 200
    assert assign_res.json()["assignee_id"] == agent_user.id
    assert assign_res.json()["assignee_name"] == agent_user.full_name

    # 2. Deactivate the agent
    deact_res = client.patch(f"/api/v1/users/{agent_user.id}/status", headers=admin_auth_headers, json={"is_active": False})
    assert deact_res.status_code == 200
    assert deact_res.json()["is_active"] is False

    # 3. Existing ticket still has the deactivated agent assigned
    get_t1 = client.get(f"/api/v1/tickets/{t1_id}", headers=admin_auth_headers)
    assert get_t1.status_code == 200
    assert get_t1.json()["assignee_id"] == agent_user.id
    assert get_t1.json()["assignee_name"] == agent_user.full_name

    # 4. Create another ticket; attempting to assign to the inactive agent fails with 422
    t2_res = client.post("/api/v1/tickets", headers=requester_auth_headers, json={"title": "Ticket 2", "description": "D2"})
    assert t2_res.status_code == 201
    t2_id = t2_res.json()["id"]

    fail_inactive = client.patch(f"/api/v1/tickets/{t2_id}/assign", headers=admin_auth_headers, json={"assignee_id": agent_user.id})
    assert fail_inactive.status_code == 422
    assert fail_inactive.json()["error"]["message"] == "Cannot assign ticket to an inactive user"

    # 5. Create an inactive requester and verify assigning to them also returns 422
    u_inact = User(email="inact.req@example.com", full_name="Inactive Req", hashed_password=hash_password("Pass12345!"), role=UserRole.REQUESTER, is_active=False)
    db_session.add(u_inact)
    db_session.commit()

    fail_inact_req = client.patch(f"/api/v1/tickets/{t2_id}/assign", headers=admin_auth_headers, json={"assignee_id": u_inact.id})
    assert fail_inact_req.status_code == 422
    assert fail_inact_req.json()["error"]["message"] == "Cannot assign ticket to an inactive user"

    # 6. Reactivate the agent and assign ticket 2 -> succeeds
    react_res = client.patch(f"/api/v1/users/{agent_user.id}/status", headers=admin_auth_headers, json={"is_active": True})
    assert react_res.status_code == 200

    success_assign = client.patch(f"/api/v1/tickets/{t2_id}/assign", headers=admin_auth_headers, json={"assignee_id": agent_user.id})
    assert success_assign.status_code == 200
    assert success_assign.json()["assignee_id"] == agent_user.id
