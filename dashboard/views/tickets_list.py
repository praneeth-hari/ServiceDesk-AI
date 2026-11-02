import math
import streamlit as st

from dashboard.api_client import (
    APIConnectionError,
    APIError,
    HelpdeskAPIClient,
    SessionExpiredError,
)
from dashboard.formatting import format_datetime, format_due_display, format_user_display


def render_tickets_list(client: HelpdeskAPIClient) -> None:
    """Render tickets list with server-side filters, search, and pagination."""
    st.subheader("📋 Tickets")

    if "tickets_page" not in st.session_state:
        st.session_state.tickets_page = 1

    def _reset_page() -> None:
        """Reset pagination to page 1 whenever filters change."""
        st.session_state.tickets_page = 1

    # Filters row: Status, Priority, Category, Search keyword, Overdue only
    col1, col2, col3, col4, col5 = st.columns([2, 2, 2, 3, 2])
    with col1:
        status_filter = st.selectbox(
            "Status",
            ["All", "open", "in_progress", "waiting_on_requester", "resolved", "closed"],
            index=0,
            key="filter_status",
            on_change=_reset_page,
        )
    with col2:
        priority_filter = st.selectbox(
            "Priority",
            ["All", "low", "medium", "high", "urgent"],
            index=0,
            key="filter_priority",
            on_change=_reset_page,
        )
    with col3:
        category_filter = st.selectbox(
            "Category",
            ["All", "network", "hardware", "software", "access", "email", "other"],
            index=0,
            key="filter_category",
            on_change=_reset_page,
        )
    with col4:
        search_query = st.text_input(
            "Search keyword",
            placeholder="Title or description...",
            key="filter_q",
            on_change=_reset_page,
        ).strip()
    with col5:
        st.write("")
        st.write("")
        overdue_filter = st.checkbox("Overdue only", key="filter_overdue", on_change=_reset_page)

    # Wire to API query parameters (no client-side filtering)
    status_param = status_filter if status_filter != "All" else None
    priority_param = priority_filter if priority_filter != "All" else None
    category_param = category_filter if category_filter != "All" else None
    overdue_param = True if overdue_filter else None
    q_param = search_query if search_query else None

    page_size = 10
    current_page = st.session_state.tickets_page

    try:
        data = client.list_tickets(
            page=current_page,
            page_size=page_size,
            status=status_param,
            priority=priority_param,
            category=category_param,
            overdue=overdue_param,
            q=q_param,
        )
    except SessionExpiredError:
        st.session_state.clear()
        st.session_state.session_expired_message = "Session expired, please log in again"
        st.rerun()
    except APIConnectionError as e:
        st.error(e.message)
        return
    except APIError as e:
        st.error(e.message)
        return

    items = data.get("items", [])
    total = data.get("total", 0)
    total_pages = max(1, math.ceil(total / page_size)) if total > 0 else 1

    if current_page > total_pages:
        st.session_state.tickets_page = total_pages
        st.rerun()

    start_idx = (current_page - 1) * page_size + 1 if total > 0 else 0
    end_idx = min(current_page * page_size, total)

    st.markdown(f"**Showing {start_idx}–{end_idx} of {total} tickets** (Page {current_page} of {total_pages})")

    if not items:
        st.info("No tickets match the selected filters.")
    else:
        # Table column widths: ID, Title, Category, Status, Priority, Assignee, Due, Action
        col_widths = [1, 3, 2, 2, 2, 2, 3, 1]

        # Column headers
        with st.container():
            h1, h2, h3, h4, h5, h6, h7, h8 = st.columns(col_widths)
            h1.markdown("**ID**")
            h2.markdown("**Title**")
            h3.markdown("**Category**")
            h4.markdown("**Status**")
            h5.markdown("**Priority**")
            h6.markdown("**Assignee**")
            h7.markdown("**Due**")
            h8.markdown("**Action**")
            st.divider()

        # Render tickets
        for t in items:
            ticket_id = t["id"]
            title = t["title"]
            cat_val = t.get("category", "other").capitalize()
            status_val = t["status"].upper()
            prio_val = t["priority"].upper()

            # Show assignee as a name if API returns it, otherwise User #<id>, and "-" if unassigned
            assignee = format_user_display(t.get("assignee_name"), t.get("assignee_id"), fallback_unassigned="-")

            due_display = format_due_display(
                due_at=t.get("due_at"),
                is_overdue=t.get("is_overdue", False),
                sla_paused_at=t.get("sla_paused_at"),
            )

            with st.container():
                c1, c2, c3, c4, c5, c6, c7, c8 = st.columns(col_widths)
                c1.markdown(f"**#{ticket_id}**")
                c2.markdown(f"**{title}**")
                c3.markdown(f"`{cat_val}`")
                c4.markdown(f"`{status_val}`")
                c5.markdown(f"*{prio_val}*")
                c6.markdown(f"{assignee}")
                c7.markdown(due_display, unsafe_allow_html=True)
                if c8.button("View", key=f"btn_ticket_{ticket_id}", use_container_width=True):
                    st.session_state.selected_ticket_id = ticket_id
                    st.session_state.current_page = "Ticket Detail"
                    st.rerun()
                st.divider()

    # Pagination controls
    p_col1, p_col2, p_col3 = st.columns([2, 4, 2])
    with p_col1:
        if st.button("⬅️ Previous", disabled=(current_page <= 1), use_container_width=True):
            st.session_state.tickets_page -= 1
            st.rerun()
    with p_col2:
        st.markdown(
            f"<div style='text-align: center; padding-top: 6px;'>Page {current_page} of {total_pages}</div>",
            unsafe_allow_html=True,
        )
    with p_col3:
        if st.button("Next ➡️", disabled=(current_page >= total_pages), use_container_width=True):
            st.session_state.tickets_page += 1
            st.rerun()
