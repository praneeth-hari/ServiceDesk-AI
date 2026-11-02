from pathlib import Path
from unittest import mock
import pytest
from streamlit.testing.v1 import AppTest

from dashboard.api_client import APIConnectionError, HelpdeskAPIClient

DASHBOARD_APP_PATH = Path(__file__).resolve().parent.parent.parent / "dashboard" / "app.py"


def test_login_screen_renders_smoke():
    """Smoke test that the HelpDesk dashboard login screen renders without unhandled exceptions."""
    at = AppTest.from_file(str(DASHBOARD_APP_PATH), default_timeout=10)
    at.run()
    assert not at.exception
    # Verifies the login gate is rendered with tabs and inputs
    assert len(at.tabs) >= 2 or len(at.text_input) >= 1


def test_holidays_view_renders_smoke():
    """Smoke test that Holidays view renders without unhandled exceptions for an agent."""
    with mock.patch.object(
        HelpdeskAPIClient,
        "list_holidays",
        return_value=[{"id": 1, "holiday_date": "2026-01-01", "name": "New Year"}],
    ):
        at = AppTest.from_file(str(DASHBOARD_APP_PATH), default_timeout=10)
        at.session_state["token"] = "fake-jwt-token"
        at.session_state["user"] = {"id": 2, "email": "agent@example.com", "role": "agent"}
        at.session_state["current_page"] = "Holidays"
        at.run()
        assert not at.exception


def test_new_ticket_suggest_and_apply():
    """Test clicking suggest, rendering AI suggestion box, and applying category and priority."""
    mock_suggestion = {
        "suggested_category": "network",
        "suggested_priority": "urgent",
        "confidence": 0.88,
        "evidence": [
            {
                "id": 12,
                "title": "VPN gateway failure",
                "status": "resolved",
                "category": "network",
                "priority": "urgent",
                "similarity": 0.92,
            }
        ],
        "possible_duplicates": [],
        "embedder": "hashing-v2",
    }

    with mock.patch.object(HelpdeskAPIClient, "suggest_triage", return_value=mock_suggestion) as mock_sugg:
        at = AppTest.from_file(str(DASHBOARD_APP_PATH), default_timeout=10)
        at.session_state["token"] = "fake-jwt-token"
        at.session_state["user"] = {"id": 1, "email": "requester@example.com", "role": "requester"}
        at.session_state["current_page"] = "New ticket"
        at.run()
        assert not at.exception

        # Input title and description
        at.text_input(key="new_ticket_title").input("VPN connection dropped").run()
        at.text_area(key="new_ticket_desc").input("Cannot reach corporate database server").run()

        # Click suggest button
        at.button(key="btn_suggest_triage").click().run()
        assert not at.exception
        mock_sugg.assert_called_once_with("VPN connection dropped", "Cannot reach corporate database server")

        # Verify suggestion box and progress
        assert len(at.progress) >= 1
        assert at.progress[0].value in (88, 0.88)

        # Click Apply category
        at.button(key="btn_apply_category").click().run()
        assert not at.exception
        assert at.selectbox(key="new_ticket_cat").value == "network"

        # Click Apply priority
        at.button(key="btn_apply_priority").click().run()
        assert not at.exception
        assert at.selectbox(key="new_ticket_prio").value == "urgent"


def test_new_ticket_possible_duplicates_navigation():
    """Test duplicate detection warning and clicking Open #id navigates to ticket detail."""
    mock_suggestion = {
        "suggested_category": "hardware",
        "suggested_priority": "low",
        "confidence": 0.72,
        "evidence": [],
        "possible_duplicates": [
            {
                "id": 55,
                "title": "Laptop screen flickering",
                "status": "open",
                "category": "hardware",
                "priority": "medium",
                "similarity": 0.94,
            }
        ],
        "embedder": "hashing-v2",
    }

    mock_detail = {
        "id": 55,
        "title": "Laptop screen flickering",
        "description": "Dell XPS monitor flashes",
        "status": "open",
        "category": "hardware",
        "priority": "medium",
        "requester_id": 1,
        "created_at": "2026-10-27T10:00:00Z",
    }

    with mock.patch.object(
        HelpdeskAPIClient, "suggest_triage", return_value=mock_suggestion
    ), mock.patch.object(
        HelpdeskAPIClient, "get_ticket", return_value=mock_detail
    ), mock.patch.object(
        HelpdeskAPIClient, "get_comments", return_value=[]
    ), mock.patch.object(
        HelpdeskAPIClient, "get_history", return_value=[]
    ):
        at = AppTest.from_file(str(DASHBOARD_APP_PATH), default_timeout=10)
        at.session_state["token"] = "fake-jwt-token"
        at.session_state["user"] = {"id": 1, "email": "requester@example.com", "role": "requester"}
        at.session_state["current_page"] = "New ticket"
        at.run()

        at.text_input(key="new_ticket_title").input("Screen flicker").run()
        at.text_area(key="new_ticket_desc").input("Dell XPS monitor flashes").run()

        at.button(key="btn_suggest_triage").click().run()
        assert not at.exception

        # Warning is displayed
        assert any("Possible duplicate" in w.value for w in at.warning)

        # Click Open #55
        at.button(key="btn_open_dup_55").click().run()
        assert not at.exception
        assert at.session_state["selected_ticket_id"] == 55
        assert at.session_state["current_page"] == "Ticket Detail"


def test_new_ticket_no_confident_suggestion():
    """Test empty suggestion displays grey info notification."""
    mock_suggestion = {
        "suggested_category": None,
        "suggested_priority": None,
        "confidence": 0.0,
        "evidence": [],
        "possible_duplicates": [],
        "embedder": "hashing-v2",
    }

    with mock.patch.object(HelpdeskAPIClient, "suggest_triage", return_value=mock_suggestion):
        at = AppTest.from_file(str(DASHBOARD_APP_PATH), default_timeout=10)
        at.session_state["token"] = "fake-jwt-token"
        at.session_state["user"] = {"id": 1, "email": "requester@example.com", "role": "requester"}
        at.session_state["current_page"] = "New ticket"
        at.run()

        at.text_input(key="new_ticket_title").input("Obscure error code 99999").run()
        at.text_area(key="new_ticket_desc").input("Unknown unusual subsystem issue").run()

        at.button(key="btn_suggest_triage").click().run()
        assert not at.exception

        assert any("No confident suggestion yet" in i.value for i in at.info)


def test_new_ticket_failing_suggest_allows_ticket_creation():
    """Test that if suggest_triage raises an error, a warning is shown and ticket creation succeeds."""
    mock_ticket = {
        "id": 101,
        "title": "Printer issue",
        "description": "Paper jam tray 2",
        "category": "hardware",
        "priority": "low",
        "status": "open",
        "due_at": "2026-10-28T14:00:00Z",
    }

    with mock.patch.object(
        HelpdeskAPIClient, "suggest_triage", side_effect=APIConnectionError("API Unreachable")
    ), mock.patch.object(HelpdeskAPIClient, "create_ticket", return_value=mock_ticket) as mock_create:
        at = AppTest.from_file(str(DASHBOARD_APP_PATH), default_timeout=10)
        at.session_state["token"] = "fake-jwt-token"
        at.session_state["user"] = {"id": 1, "email": "requester@example.com", "role": "requester"}
        at.session_state["current_page"] = "New ticket"
        at.run()

        at.text_input(key="new_ticket_title").input("Printer issue").run()
        at.text_area(key="new_ticket_desc").input("Paper jam tray 2").run()

        # Suggest fails gracefully
        at.button(key="btn_suggest_triage").click().run()
        assert not at.exception
        assert any("AI suggestion unavailable" in w.value for w in at.warning)

        # Ticket creation still works
        at.button(key="btn_submit_ticket").click().run()
        assert not at.exception
        mock_create.assert_called_once()
        assert any("Ticket **#101** created successfully" in s.value for s in at.success)


def test_new_ticket_text_changed_shows_caption():
    """Test that modifying title or description after suggestion shows 'Text changed' caption."""
    mock_suggestion = {
        "suggested_category": "software",
        "suggested_priority": "medium",
        "confidence": 0.70,
        "evidence": [],
        "possible_duplicates": [],
        "embedder": "hashing-v2",
    }

    with mock.patch.object(HelpdeskAPIClient, "suggest_triage", return_value=mock_suggestion):
        at = AppTest.from_file(str(DASHBOARD_APP_PATH), default_timeout=10)
        at.session_state["token"] = "fake-jwt-token"
        at.session_state["user"] = {"id": 1, "email": "requester@example.com", "role": "requester"}
        at.session_state["current_page"] = "New ticket"
        at.run()

        at.text_input(key="new_ticket_title").input("Initial title").run()
        at.text_area(key="new_ticket_desc").input("Initial description").run()

        at.button(key="btn_suggest_triage").click().run()
        assert not at.exception
        assert not any("Text changed" in c.value for c in at.caption)

        # Change title
        at.text_input(key="new_ticket_title").input("Modified title after suggestion").run()
        assert any("Text changed, click Suggest again" in c.value for c in at.caption)


def test_ticket_detail_similar_tickets_agent_vs_requester():
    """
    Test Similar tickets section:
    - Renders for agent role and calls get_similar_tickets.
    - Does NOT render for requester role and does NOT call get_similar_tickets.
    """
    mock_ticket = {
        "id": 1,
        "title": "Wi-Fi Drops in Meeting Room",
        "description": "Signal drops when more than 10 people connect",
        "status": "open",
        "category": "network",
        "priority": "high",
        "requester_id": 10,
        "created_at": "2026-10-25T10:00:00Z",
    }
    mock_similar = [
        {
            "id": 5,
            "title": "Access point overload in Conf B",
            "status": "resolved",
            "category": "network",
            "priority": "high",
            "similarity": 0.89,
        }
    ]

    with mock.patch.object(HelpdeskAPIClient, "get_ticket", return_value=mock_ticket), mock.patch.object(
        HelpdeskAPIClient, "get_comments", return_value=[]
    ), mock.patch.object(HelpdeskAPIClient, "get_history", return_value=[]), mock.patch.object(
        HelpdeskAPIClient, "get_similar_tickets", return_value=mock_similar
    ) as mock_get_sim:

        # 1. Agent: renders similar tickets
        at_agent = AppTest.from_file(str(DASHBOARD_APP_PATH), default_timeout=10)
        at_agent.session_state["token"] = "agent-token"
        at_agent.session_state["user"] = {"id": 2, "email": "agent@example.com", "role": "agent"}
        at_agent.session_state["selected_ticket_id"] = 1
        at_agent.session_state["current_page"] = "Ticket Detail"
        at_agent.run()
        assert not at_agent.exception
        mock_get_sim.assert_called_once_with(1, limit=5)
        assert any("Ranked by text similarity" in c.value for c in at_agent.caption)
        assert at_agent.button(key="btn_open_similar_5") is not None

        # 2. Requester: does NOT render similar tickets and does NOT call endpoint
        mock_get_sim.reset_mock()
        at_req = AppTest.from_file(str(DASHBOARD_APP_PATH), default_timeout=10)
        at_req.session_state["token"] = "req-token"
        at_req.session_state["user"] = {"id": 10, "email": "req@example.com", "role": "requester"}
        at_req.session_state["selected_ticket_id"] = 1
        at_req.session_state["current_page"] = "Ticket Detail"
        at_req.run()
        assert not at_req.exception
        mock_get_sim.assert_not_called()
        assert not any("Ranked by text similarity" in c.value for c in at_req.caption)
