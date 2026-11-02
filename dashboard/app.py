"""Main entry point for the Helpdesk Streamlit dashboard."""

import os
import sys
from pathlib import Path

# Ensure repository root is in sys.path so 'dashboard' package imports work under Streamlit
_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import streamlit as st

from dashboard.api_client import (
    APIConnectionError,
    HelpdeskAPIClient,
    SessionExpiredError,
)
from dashboard.views.holidays import render_holidays
from dashboard.views.login import render_login
from dashboard.views.new_ticket import render_new_ticket
from dashboard.views.reports import render_reports
from dashboard.views.ticket_detail import render_ticket_detail
from dashboard.views.tickets_list import render_tickets_list


def main() -> None:
    st.set_page_config(
        page_title="HelpDesk Portal",
        page_icon="🎫",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    api_url = os.getenv("HELPDESK_API_URL", "http://localhost:8000/api/v1")
    token = st.session_state.get("token")
    client = HelpdeskAPIClient(base_url=api_url, token=token)

    # 1. Login Gate
    if not token or not st.session_state.get("user"):
        render_login(client)
        return

    user = st.session_state.get("user", {})
    email = user.get("email", "")
    role = user.get("role", "requester")

    # 2. Sidebar
    st.sidebar.title("🎫 HelpDesk")
    st.sidebar.write(f"Signed in as: **{email}**")
    st.sidebar.markdown(f"Role: `{role}`")
    st.sidebar.markdown("---")

    nav_options = ["Tickets", "New ticket"]
    if role in ("agent", "admin"):
        nav_options.append("Reports")
        nav_options.append("Holidays")

    # Keep track of current page
    current_page = st.session_state.get("current_page", "Tickets")
    if current_page not in nav_options and current_page != "Ticket Detail":
        current_page = "Tickets"
        st.session_state.current_page = current_page

    default_nav_idx = nav_options.index(current_page) if current_page in nav_options else 0

    selected_nav = st.sidebar.radio(
        "Navigation",
        options=nav_options,
        index=default_nav_idx,
        key="sidebar_navigation",
    )

    # If user changed navigation from the sidebar, switch views
    if selected_nav != current_page and (current_page != "Ticket Detail" or selected_nav != "Tickets"):
        st.session_state.current_page = selected_nav
        current_page = selected_nav

    st.sidebar.markdown("---")
    if st.sidebar.button("Log out", use_container_width=True):
        st.session_state.clear()
        st.rerun()

    # 3. Screen Router with Error Handling
    try:
        if current_page == "Ticket Detail":
            render_ticket_detail(client)
        elif current_page == "New ticket":
            render_new_ticket(client)
        elif current_page == "Reports" and role in ("agent", "admin"):
            render_reports(client)
        elif current_page == "Holidays" and role in ("agent", "admin"):
            render_holidays(client)
        else:
            render_tickets_list(client)
    except SessionExpiredError:
        st.session_state.clear()
        st.session_state["session_expired_message"] = "Session expired, please log in again"
        st.rerun()
    except APIConnectionError as exc:
        st.error(str(exc))


if __name__ == "__main__":
    main()
