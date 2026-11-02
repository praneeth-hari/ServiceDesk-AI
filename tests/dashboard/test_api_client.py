from unittest import mock
import pytest
import requests

from dashboard.api_client import (
    APIConnectionError,
    APIError,
    HelpdeskAPIClient,
    SessionExpiredError,
)


@pytest.fixture
def api_client():
    """Create a test HelpdeskAPIClient instance."""
    return HelpdeskAPIClient(base_url="http://testserver/api/v1", timeout=5.0)


def test_login_success(api_client: HelpdeskAPIClient):
    """Test successful login saves the token and returns response data."""
    mock_resp = mock.MagicMock(spec=requests.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"access_token": "valid_token_xyz", "token_type": "bearer"}

    with mock.patch("requests.request", return_value=mock_resp) as mock_req:
        result = api_client.login("agent@example.com", "password123")
        assert result["access_token"] == "valid_token_xyz"
        assert api_client.token == "valid_token_xyz"
        mock_req.assert_called_once_with(
            method="POST",
            url="http://testserver/api/v1/auth/login",
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            params=None,
            json={"email": "agent@example.com", "password": "password123"},
            timeout=5.0,
        )


def test_login_failure(api_client: HelpdeskAPIClient):
    """Test login failure raises SessionExpiredError/APIError on 401."""
    mock_resp = mock.MagicMock(spec=requests.Response)
    mock_resp.status_code = 401
    mock_resp.json.return_value = {"error": {"message": "Invalid email or password"}}

    with mock.patch("requests.request", return_value=mock_resp):
        with pytest.raises(SessionExpiredError) as exc_info:
            api_client.login("user@example.com", "wrongpass")
        assert exc_info.value.status_code == 401
        assert "Session expired, please log in again" in str(exc_info.value)


def test_auth_header_added(api_client: HelpdeskAPIClient):
    """Test Authorization Bearer header is included on authenticated requests."""
    api_client.set_token("my_secret_token_123")

    mock_resp = mock.MagicMock(spec=requests.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"id": 1, "email": "me@example.com", "role": "agent"}

    with mock.patch("requests.request", return_value=mock_resp) as mock_req:
        res = api_client.get_me()
        assert res["email"] == "me@example.com"
        call_kwargs = mock_req.call_args[1]
        assert call_kwargs["headers"]["Authorization"] == "Bearer my_secret_token_123"


def test_401_handling_raises_session_expired(api_client: HelpdeskAPIClient):
    """Test 401 response on any route raises SessionExpiredError."""
    api_client.set_token("expired_jwt_token")

    mock_resp = mock.MagicMock(spec=requests.Response)
    mock_resp.status_code = 401
    mock_resp.json.return_value = {"error": {"message": "Token expired"}}

    with mock.patch("requests.request", return_value=mock_resp):
        with pytest.raises(SessionExpiredError) as exc_info:
            api_client.get_me()
        assert exc_info.value.status_code == 401
        assert "Session expired, please log in again" in str(exc_info.value)


def test_list_tickets_with_filters_and_pagination(api_client: HelpdeskAPIClient):
    """Test list_tickets serializes pagination, sorting, search, category, and filters accurately."""
    api_client.set_token("token_abc")

    mock_resp = mock.MagicMock(spec=requests.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"items": [], "total": 0, "page": 2, "page_size": 15}

    with mock.patch("requests.request", return_value=mock_resp) as mock_req:
        res = api_client.list_tickets(
            page=2,
            page_size=15,
            status="open",
            priority="urgent",
            category="hardware",
            assignee_id=5,
            overdue=True,
            q="database issue",
            sort_by="due_at",
            order="asc",
        )
        assert res["page"] == 2
        call_kwargs = mock_req.call_args[1]
        expected_params = {
            "page": 2,
            "page_size": 15,
            "status": "open",
            "priority": "urgent",
            "category": "hardware",
            "assignee_id": 5,
            "overdue": "true",
            "q": "database issue",
            "sort_by": "due_at",
            "order": "asc",
        }
        assert call_kwargs["params"] == expected_params


def test_create_ticket(api_client: HelpdeskAPIClient):
    """Test create_ticket passes title, description, priority, category in body."""
    api_client.set_token("token_abc")

    mock_resp = mock.MagicMock(spec=requests.Response)
    mock_resp.status_code = 201
    mock_resp.json.return_value = {
        "id": 101,
        "title": "Email server offline",
        "description": "Port 25 unreachable",
        "priority": "urgent",
        "category": "email",
        "due_at": "2026-10-25T18:00:00Z",
    }

    with mock.patch("requests.request", return_value=mock_resp) as mock_req:
        ticket = api_client.create_ticket(
            "Email server offline",
            "Port 25 unreachable",
            priority="urgent",
            category="email",
        )
        assert ticket["id"] == 101
        assert ticket["category"] == "email"
        call_kwargs = mock_req.call_args[1]
        assert call_kwargs["method"] == "POST"
        assert call_kwargs["url"] == "http://testserver/api/v1/tickets"
        assert call_kwargs["json"] == {
            "title": "Email server offline",
            "description": "Port 25 unreachable",
            "priority": "urgent",
            "category": "email",
        }


def test_update_ticket(api_client: HelpdeskAPIClient):
    """Test update_ticket sends PATCH with updated fields including category."""
    api_client.set_token("token_abc")

    mock_resp = mock.MagicMock(spec=requests.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "id": 101,
        "title": "Updated Title",
        "category": "software",
    }

    with mock.patch("requests.request", return_value=mock_resp) as mock_req:
        res = api_client.update_ticket(
            ticket_id=101,
            category="software",
        )
        assert res["category"] == "software"
        call_kwargs = mock_req.call_args[1]
        assert call_kwargs["method"] == "PATCH"
        assert call_kwargs["url"] == "http://testserver/api/v1/tickets/101"
        assert call_kwargs["json"] == {"category": "software"}


def test_change_status_409(api_client: HelpdeskAPIClient):
    """Test 409 Conflict status update parses error message and raises APIError."""
    api_client.set_token("token_abc")

    mock_resp = mock.MagicMock(spec=requests.Response)
    mock_resp.status_code = 409
    mock_resp.json.return_value = {
        "error": {"message": "Cannot transition ticket status from 'open' to 'closed'"}
    }

    with mock.patch("requests.request", return_value=mock_resp):
        with pytest.raises(APIError) as exc_info:
            api_client.update_ticket_status(ticket_id=12, status="closed")
        assert exc_info.value.status_code == 409
        assert "Cannot transition ticket status from 'open' to 'closed'" in str(exc_info.value)


def test_connection_error(api_client: HelpdeskAPIClient):
    """Test connection error raises APIConnectionError with user-friendly message."""
    with mock.patch("requests.request", side_effect=requests.exceptions.ConnectionError("Connection refused")):
        with pytest.raises(APIConnectionError) as exc_info:
            api_client.get_me()
        assert "Cannot reach the API at http://testserver/api/v1" in str(exc_info.value)


def test_reports_methods_and_routes(api_client: HelpdeskAPIClient):
    """Test all 9 report client methods invoke the correct endpoints."""
    api_client.set_token("token_abc")

    mock_resp = mock.MagicMock(spec=requests.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = []

    with mock.patch("requests.request", return_value=mock_resp) as mock_req:
        # 1. Existing 5 reports
        api_client.get_report_tickets_by_status()
        assert mock_req.call_args[1]["url"].endswith("/reports/tickets-by-status")

        api_client.get_report_overdue()
        assert mock_req.call_args[1]["url"].endswith("/reports/overdue")

        api_client.get_report_resolution_time()
        assert mock_req.call_args[1]["url"].endswith("/reports/resolution-time")

        api_client.get_report_agent_ranking()
        assert mock_req.call_args[1]["url"].endswith("/reports/agent-ranking")

        api_client.get_report_daily_volume(days=14)
        assert mock_req.call_args[1]["url"].endswith("/reports/daily-volume")
        assert mock_req.call_args[1]["params"] == {"days": 14}

        # 2. Four new reports
        api_client.get_report_sla_breach_rate()
        assert mock_req.call_args[1]["url"].endswith("/reports/sla-breach-rate")

        api_client.get_report_resolution_time_by_category()
        assert mock_req.call_args[1]["url"].endswith("/reports/resolution-time-by-category")

        api_client.get_report_agent_workload()
        assert mock_req.call_args[1]["url"].endswith("/reports/agent-workload")

        api_client.get_report_tickets_by_category(breakdown_by_status=False)
        assert mock_req.call_args[1]["url"].endswith("/reports/tickets-by-category")
        assert mock_req.call_args[1]["params"] is None

        api_client.get_report_tickets_by_category(breakdown_by_status=True)
        assert mock_req.call_args[1]["url"].endswith("/reports/tickets-by-category")
        assert mock_req.call_args[1]["params"] == {"breakdown_by_status": "true"}


def test_new_reports_error_handling(api_client: HelpdeskAPIClient):
    """Test 401 and connection error handling on new report methods."""
    api_client.set_token("expired_token")

    mock_401 = mock.MagicMock(spec=requests.Response)
    mock_401.status_code = 401
    mock_401.json.return_value = {"error": {"message": "Invalid token"}}

    with mock.patch("requests.request", return_value=mock_401):
        with pytest.raises(SessionExpiredError):
            api_client.get_report_sla_breach_rate()
        with pytest.raises(SessionExpiredError):
            api_client.get_report_agent_workload()

    with mock.patch("requests.request", side_effect=requests.exceptions.ConnectionError("Down")):
        with pytest.raises(APIConnectionError):
            api_client.get_report_resolution_time_by_category()
        with pytest.raises(APIConnectionError):
            api_client.get_report_tickets_by_category()


def test_list_holidays(api_client: HelpdeskAPIClient):
    """Test list_holidays with and without year filter."""
    api_client.set_token("token_123")
    mock_resp = mock.MagicMock(spec=requests.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = [{"id": 1, "holiday_date": "2026-01-01", "name": "New Year"}]

    with mock.patch("requests.request", return_value=mock_resp) as mock_req:
        res = api_client.list_holidays()
        assert len(res) == 1
        assert res[0]["name"] == "New Year"
        assert mock_req.call_args[1]["params"] is None

        api_client.list_holidays(year=2026)
        assert mock_req.call_args[1]["params"] == {"year": 2026}


def test_create_holiday_success_and_errors(api_client: HelpdeskAPIClient):
    """Test create_holiday for success, 409 duplicate date, and 403 forbidden."""
    api_client.set_token("token_admin")

    # 1. Success
    mock_201 = mock.MagicMock(spec=requests.Response)
    mock_201.status_code = 201
    mock_201.json.return_value = {"id": 10, "holiday_date": "2026-12-25", "name": "Christmas"}

    with mock.patch("requests.request", return_value=mock_201) as mock_req:
        res = api_client.create_holiday("2026-12-25", "Christmas")
        assert res["id"] == 10
        assert mock_req.call_args[1]["json"] == {"holiday_date": "2026-12-25", "name": "Christmas"}

    # 2. 409 Conflict duplicate date
    mock_409 = mock.MagicMock(spec=requests.Response)
    mock_409.status_code = 409
    mock_409.json.return_value = {"error": {"message": "A holiday is already registered for date 2026-12-25"}}

    with mock.patch("requests.request", return_value=mock_409):
        with pytest.raises(APIError) as exc_info:
            api_client.create_holiday("2026-12-25", "Christmas")
        assert exc_info.value.status_code == 409
        assert "A holiday is already registered" in str(exc_info.value)

    # 3. 403 Forbidden
    mock_403 = mock.MagicMock(spec=requests.Response)
    mock_403.status_code = 403
    mock_403.json.return_value = {"error": {"message": "You do not have permission to access this resource"}}

    with mock.patch("requests.request", return_value=mock_403):
        with pytest.raises(APIError) as exc_info:
            api_client.create_holiday("2026-12-25", "Christmas")
        assert exc_info.value.status_code == 403
        assert "permission" in str(exc_info.value)


def test_delete_holiday_success_and_errors(api_client: HelpdeskAPIClient):
    """Test delete_holiday success (204), 404 missing, 403 forbidden."""
    api_client.set_token("token_admin")

    # 1. Success 204
    mock_204 = mock.MagicMock(spec=requests.Response)
    mock_204.status_code = 204

    with mock.patch("requests.request", return_value=mock_204) as mock_req:
        res = api_client.delete_holiday(10)
        assert res is None
        assert mock_req.call_args[1]["url"].endswith("/holidays/10")

    # 2. 404 Not Found
    mock_404 = mock.MagicMock(spec=requests.Response)
    mock_404.status_code = 404
    mock_404.json.return_value = {"error": {"message": "Holiday not found"}}

    with mock.patch("requests.request", return_value=mock_404):
        with pytest.raises(APIError) as exc_info:
            api_client.delete_holiday(999)
        assert exc_info.value.status_code == 404
        assert "Holiday not found" in str(exc_info.value)

    # 3. 403 Forbidden
    mock_403 = mock.MagicMock(spec=requests.Response)
    mock_403.status_code = 403
    mock_403.json.return_value = {"error": {"message": "Forbidden"}}

    with mock.patch("requests.request", return_value=mock_403):
        with pytest.raises(APIError) as exc_info:
            api_client.delete_holiday(10)
        assert exc_info.value.status_code == 403


def test_holiday_session_expired_and_connection_error(api_client: HelpdeskAPIClient):
    """Test 401 raises SessionExpiredError and network failure raises APIConnectionError."""
    mock_401 = mock.MagicMock(spec=requests.Response)
    mock_401.status_code = 401
    mock_401.json.return_value = {"error": {"message": "Expired"}}

    with mock.patch("requests.request", return_value=mock_401):
        with pytest.raises(SessionExpiredError):
            api_client.list_holidays()

    with mock.patch("requests.request", side_effect=requests.exceptions.ConnectionError("Unreachable")):
        with pytest.raises(APIConnectionError):
            api_client.create_holiday("2026-05-01", "May Day")


def test_suggest_triage_api_client(api_client: HelpdeskAPIClient):
    """Test suggest_triage method with success response, auth header, and error handling."""
    api_client.set_token("token_requester")

    # 1. Success
    mock_resp = mock.MagicMock(spec=requests.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "suggested_category": "network",
        "suggested_priority": "high",
        "confidence": 0.85,
        "evidence": [{"id": 1, "title": "VPN issue", "category": "network", "priority": "high", "similarity": 0.88}],
        "possible_duplicates": [],
        "embedder": "hashing-v2",
    }

    with mock.patch("requests.request", return_value=mock_resp) as mock_req:
        res = api_client.suggest_triage("VPN drops", "Error 54")
        assert res["suggested_category"] == "network"
        assert res["confidence"] == 0.85
        assert len(res["evidence"]) == 1
        assert mock_req.call_args[1]["url"].endswith("/triage/suggest")
        assert mock_req.call_args[1]["json"] == {"title": "VPN drops", "description": "Error 54"}
        assert mock_req.call_args[1]["headers"]["Authorization"] == "Bearer token_requester"

    # 2. 401 Session expired
    mock_401 = mock.MagicMock(spec=requests.Response)
    mock_401.status_code = 401
    with mock.patch("requests.request", return_value=mock_401):
        with pytest.raises(SessionExpiredError):
            api_client.suggest_triage("VPN drops", "Error 54")

    # 3. Connection error
    with mock.patch("requests.request", side_effect=requests.exceptions.ConnectionError("Down")):
        with pytest.raises(APIConnectionError):
            api_client.suggest_triage("VPN drops", "Error 54")


def test_get_similar_tickets_api_client(api_client: HelpdeskAPIClient):
    """Test get_similar_tickets with success, empty, 403, 404, and connection errors."""
    api_client.set_token("token_agent")

    # 1. Success
    mock_resp = mock.MagicMock(spec=requests.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = [
        {
            "id": 2,
            "title": "Switch down",
            "status": "resolved",
            "category": "network",
            "priority": "urgent",
            "similarity": 0.91,
        }
    ]

    with mock.patch("requests.request", return_value=mock_resp) as mock_req:
        res = api_client.get_similar_tickets(10, limit=5)
        assert len(res) == 1
        assert res[0]["id"] == 2
        assert mock_req.call_args[1]["url"].endswith("/tickets/10/similar")
        assert mock_req.call_args[1]["params"] == {"limit": 5}
        assert mock_req.call_args[1]["headers"]["Authorization"] == "Bearer token_agent"

    # 2. Empty list
    mock_empty = mock.MagicMock(spec=requests.Response)
    mock_empty.status_code = 200
    mock_empty.json.return_value = []
    with mock.patch("requests.request", return_value=mock_empty):
        assert api_client.get_similar_tickets(10) == []

    # 3. 403 Forbidden
    mock_403 = mock.MagicMock(spec=requests.Response)
    mock_403.status_code = 403
    mock_403.json.return_value = {"error": {"message": "Only agents and admins can access similar tickets"}}
    with mock.patch("requests.request", return_value=mock_403):
        with pytest.raises(APIError) as exc_info:
            api_client.get_similar_tickets(10)
        assert exc_info.value.status_code == 403

    # 4. 404 Not Found
    mock_404 = mock.MagicMock(spec=requests.Response)
    mock_404.status_code = 404
    mock_404.json.return_value = {"error": {"message": "Ticket not found"}}
    with mock.patch("requests.request", return_value=mock_404):
        with pytest.raises(APIError) as exc_info:
            api_client.get_similar_tickets(999)
        assert exc_info.value.status_code == 404

    # 5. Connection error
    with mock.patch("requests.request", side_effect=requests.exceptions.ConnectionError("Down")):
        with pytest.raises(APIConnectionError):
            api_client.get_similar_tickets(10)


