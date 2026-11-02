import os
from typing import Any, Optional
import requests


class APIError(Exception):
    """Base exception for API errors."""
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class APIConnectionError(APIError):
    """Raised when the API is unreachable or times out."""
    def __init__(self, message: str):
        super().__init__(message, status_code=None)


class SessionExpiredError(APIError):
    """Raised when the API returns 401 Unauthorized."""
    def __init__(self, message: str = "Session expired, please log in again"):
        super().__init__(message, status_code=401)


class HelpdeskAPIClient:
    """
    HTTP client for the Helpdesk API.
    Handles authentication, error formatting, connection errors, and timeouts.
    Free of Streamlit imports so it can be easily tested.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        token: Optional[str] = None,
        timeout: float = 10.0,
    ):
        self.base_url = (base_url or os.getenv("HELPDESK_API_URL", "http://localhost:8000/api/v1")).rstrip("/")
        self.token = token
        self.timeout = timeout

    def set_token(self, token: Optional[str]) -> None:
        """Update active bearer token."""
        self.token = token

    def _headers(self) -> dict[str, str]:
        """Generate HTTP request headers including Authorization if token is set."""
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _extract_error_message(self, response: requests.Response) -> str:
        """Extract a readable error message from API response body."""
        try:
            data = response.json()
            if isinstance(data, dict):
                error_obj = data.get("error")
                if isinstance(error_obj, dict) and "message" in error_obj:
                    return str(error_obj["message"])
                if "detail" in data:
                    detail = data["detail"]
                    if isinstance(detail, list):
                        return "; ".join(f"{'.'.join(str(l) for l in err.get('loc', []))}: {err.get('msg', '')}" for err in detail)
                    return str(detail)
                if "message" in data:
                    return str(data["message"])
        except Exception:
            pass
        return response.text or f"HTTP {response.status_code} error"

    def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[dict[str, Any]] = None,
        json: Optional[dict[str, Any]] = None,
    ) -> Any:
        """Execute HTTP request with error handling and timeouts."""
        url = f"{self.base_url}{endpoint}"
        try:
            response = requests.request(
                method=method,
                url=url,
                headers=self._headers(),
                params=params,
                json=json,
                timeout=self.timeout,
            )
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout, requests.exceptions.RequestException) as e:
            raise APIConnectionError(f"Cannot reach the API at {self.base_url}") from e

        if response.status_code == 401:
            raise SessionExpiredError("Session expired, please log in again")

        if response.status_code >= 400:
            err_msg = self._extract_error_message(response)
            raise APIError(message=err_msg, status_code=response.status_code)

        if response.status_code == 204:
            return None

        try:
            return response.json()
        except ValueError:
            return response.text

    # --- Authentication & Users ---

    def login(self, email: str, password: str) -> dict[str, Any]:
        """Authenticate with JSON body credentials and receive JWT token."""
        data = self._request("POST", "/auth/login", json={"email": email, "password": password})
        if isinstance(data, dict) and "access_token" in data:
            self.set_token(data["access_token"])
        return data

    def register(self, email: str, full_name: str, password: str) -> dict[str, Any]:
        """Register a new user account."""
        return self._request(
            "POST",
            "/auth/register",
            json={"email": email, "full_name": full_name, "password": password},
        )

    def get_me(self) -> dict[str, Any]:
        """Get profile details of the currently authenticated user."""
        return self._request("GET", "/users/me")

    def list_users(self, skip: int = 0, limit: int = 100) -> list[dict[str, Any]]:
        """List registered users (requires admin role)."""
        return self._request("GET", "/users", params={"skip": skip, "limit": limit})

    # --- Tickets ---

    def list_tickets(
        self,
        page: int = 1,
        page_size: int = 20,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        category: Optional[str] = None,
        assignee_id: Optional[int] = None,
        overdue: Optional[bool] = None,
        q: Optional[str] = None,
        sort_by: str = "created_at",
        order: str = "desc",
    ) -> dict[str, Any]:
        """List tickets with pagination, filters, search keyword, and sorting."""
        params: dict[str, Any] = {
            "page": page,
            "page_size": page_size,
            "sort_by": sort_by,
            "order": order,
        }
        if status:
            params["status"] = status
        if priority:
            params["priority"] = priority
        if category:
            params["category"] = category
        if assignee_id is not None:
            params["assignee_id"] = assignee_id
        if overdue is not None:
            params["overdue"] = "true" if overdue else "false"
        if q and q.strip():
            params["q"] = q.strip()

        return self._request("GET", "/tickets", params=params)

    def get_ticket(self, ticket_id: int) -> dict[str, Any]:
        """Retrieve a single ticket by ID."""
        return self._request("GET", f"/tickets/{ticket_id}")

    def create_ticket(
        self,
        title: str,
        description: str,
        priority: str = "medium",
        category: str = "other",
    ) -> dict[str, Any]:
        """Create a new ticket."""
        return self._request(
            "POST",
            "/tickets",
            json={
                "title": title,
                "description": description,
                "priority": priority,
                "category": category,
            },
        )

    def update_ticket(
        self,
        ticket_id: int,
        title: Optional[str] = None,
        description: Optional[str] = None,
        priority: Optional[str] = None,
        category: Optional[str] = None,
    ) -> dict[str, Any]:
        """Update ticket title, description, priority, or category."""
        payload: dict[str, Any] = {}
        if title is not None:
            payload["title"] = title
        if description is not None:
            payload["description"] = description
        if priority is not None:
            payload["priority"] = priority
        if category is not None:
            payload["category"] = category
        return self._request("PATCH", f"/tickets/{ticket_id}", json=payload)

    def update_ticket_status(self, ticket_id: int, status: str) -> dict[str, Any]:
        """Change ticket status."""
        return self._request("PATCH", f"/tickets/{ticket_id}/status", json={"status": status})

    def assign_ticket(self, ticket_id: int, assignee_id: int) -> dict[str, Any]:
        """Assign ticket to an agent."""
        return self._request("PATCH", f"/tickets/{ticket_id}/assign", json={"assignee_id": assignee_id})

    # --- Comments & History ---

    def get_comments(self, ticket_id: int) -> list[dict[str, Any]]:
        """Retrieve comments for a ticket."""
        return self._request("GET", f"/tickets/{ticket_id}/comments")

    def add_comment(
        self,
        ticket_id: int,
        body: str,
        is_internal: bool = False,
    ) -> dict[str, Any]:
        """Add a comment or internal note to a ticket."""
        return self._request(
            "POST",
            f"/tickets/{ticket_id}/comments",
            json={"body": body, "is_internal": is_internal},
        )

    def get_history(self, ticket_id: int) -> list[dict[str, Any]]:
        """Retrieve status transition audit trail for a ticket."""
        return self._request("GET", f"/tickets/{ticket_id}/history")

    # --- Reports (Agents & Admins) ---

    def get_report_tickets_by_status(self) -> list[dict[str, Any]]:
        """Get ticket counts grouped by status and priority."""
        return self._request("GET", "/reports/tickets-by-status")

    def get_report_overdue(self) -> list[dict[str, Any]]:
        """Get overdue tickets with requester and assignee."""
        return self._request("GET", "/reports/overdue")

    def get_report_resolution_time(self) -> list[dict[str, Any]]:
        """Get average resolution time in hours per assignee."""
        return self._request("GET", "/reports/resolution-time")

    def get_report_agent_ranking(self) -> list[dict[str, Any]]:
        """Get agent rankings by tickets resolved."""
        return self._request("GET", "/reports/agent-ranking")

    def get_report_daily_volume(self, days: int = 30) -> list[dict[str, Any]]:
        """Get daily ticket volume over the last N days."""
        return self._request("GET", "/reports/daily-volume", params={"days": days})

    def get_report_sla_breach_rate(self) -> list[dict[str, Any]]:
        """Get SLA breach rate and compliance per ticket priority."""
        return self._request("GET", "/reports/sla-breach-rate")

    def get_report_resolution_time_by_category(self) -> list[dict[str, Any]]:
        """Get average resolution time in hours grouped by category and priority."""
        return self._request("GET", "/reports/resolution-time-by-category")

    def get_report_agent_workload(self) -> list[dict[str, Any]]:
        """Get open work, overdue tickets, and resolved tickets per agent."""
        return self._request("GET", "/reports/agent-workload")

    def get_report_tickets_by_category(self, breakdown_by_status: bool = False) -> list[dict[str, Any]]:
        """Get count of tickets per category, optionally broken down by status."""
        params = {"breakdown_by_status": "true"} if breakdown_by_status else None
        return self._request("GET", "/reports/tickets-by-category", params=params)

    # --- Holidays (Agent & Admin) ---

    def list_holidays(self, year: Optional[int] = None) -> list[dict[str, Any]]:
        """List organizational public holidays ordered by date, with optional year filter."""
        params: dict[str, Any] = {}
        if year is not None:
            params["year"] = int(year)
        return self._request("GET", "/holidays", params=params or None)

    def create_holiday(self, holiday_date: Any, name: str) -> dict[str, Any]:
        """Register a new organizational holiday (Admin only)."""
        return self._request(
            "POST",
            "/holidays",
            json={"holiday_date": str(holiday_date), "name": name.strip()},
        )

    def delete_holiday(self, holiday_id: int) -> None:
        """Delete an organizational holiday by ID (Admin only)."""
        self._request("DELETE", f"/holidays/{holiday_id}")

    # --- AI Triage & Similarity ---

    def suggest_triage(self, title: str, description: str) -> dict[str, Any]:
        """Request advisory AI category and priority suggestions and duplicate detection."""
        return self._request(
            "POST",
            "/triage/suggest",
            json={"title": title, "description": description},
        )

    def get_similar_tickets(self, ticket_id: int, limit: int = 5) -> list[dict[str, Any]]:
        """Retrieve historical tickets similar to an existing ticket (Agent & Admin only)."""
        return self._request(
            "GET",
            f"/tickets/{ticket_id}/similar",
            params={"limit": limit},
        )


# Alias for convenience
APIClient = HelpdeskAPIClient

