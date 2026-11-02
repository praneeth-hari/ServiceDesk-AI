from typing import Any
import streamlit as st

from dashboard.api_client import (
    APIConnectionError,
    APIError,
    HelpdeskAPIClient,
    SessionExpiredError,
)
from dashboard.formatting import (
    format_datetime,
    format_similar_ticket_row,
    format_user_display,
    get_status_color,
    get_transition_button_label,
)

# Workflow transitions allowed by Helpdesk API
ALLOWED_STATUS_TRANSITIONS: dict[str, list[str]] = {
    "open": ["in_progress"],
    "in_progress": ["resolved", "waiting_on_requester"],
    "waiting_on_requester": ["in_progress"],
    "resolved": ["closed", "in_progress"],
    "closed": [],
}



def render_ticket_detail(client: HelpdeskAPIClient) -> None:
    """Render ticket detail view with badges, comments, history, and actions panel."""
    ticket_id = st.session_state.get("selected_ticket_id")
    if not ticket_id:
        st.warning("No ticket selected.")
        if st.button("⬅️ Return to Tickets"):
            st.session_state.current_page = "Tickets"
            st.rerun()
        return

    user = st.session_state.get("user", {})
    user_role = user.get("role", "requester")
    user_id = user.get("id")

    # Header & Back button
    col_back, _ = st.columns([2, 8])
    with col_back:
        if st.button("⬅️ Back to Tickets", key="btn_back_to_list"):
            st.session_state.current_page = "Tickets"
            st.rerun()

    # Fetch ticket details
    try:
        ticket = client.get_ticket(ticket_id)
        comments = client.get_comments(ticket_id)
        history = client.get_history(ticket_id)
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

    is_owner = (user_id is not None and user_id == ticket.get("requester_id"))
    can_manage_actions = (user_role in ("agent", "admin") or is_owner)

    # Title & Badges
    st.markdown(f"## #{ticket['id']} — {ticket['title']}")

    badge_cols = st.columns([2, 2, 2, 2, 4])
    with badge_cols[0]:
        st_color = get_status_color(ticket["status"])
        st_label = ticket["status"].replace("_", " ").upper()
        st.markdown(f"**Status:** <span style='background-color: {st_color}; color: white; padding: 3px 8px; border-radius: 4px; font-weight: bold;'>{st_label}</span>", unsafe_allow_html=True)
    with badge_cols[1]:
        st.markdown(f"**Priority:** *{ticket['priority'].upper()}*")
    with badge_cols[2]:
        cat_display = ticket.get("category", "other").capitalize()
        st.markdown(f"**Category:** `{cat_display}`")
    with badge_cols[3]:
        if ticket.get("sla_paused_at"):
            st.markdown("<span style='background-color: #805ad5; color: white; padding: 4px 8px; border-radius: 4px; font-weight: bold;'>⏸️ SLA PAUSED</span>", unsafe_allow_html=True)
        elif ticket.get("is_overdue"):
            st.markdown("<span style='background-color: #e53e3e; color: white; padding: 4px 8px; border-radius: 4px; font-weight: bold;'>🚨 OVERDUE</span>", unsafe_allow_html=True)
        else:
            st.markdown("<span style='background-color: #38a169; color: white; padding: 4px 8px; border-radius: 4px;'>ON TIME</span>", unsafe_allow_html=True)
    with badge_cols[4]:
        due_formatted = format_datetime(ticket.get("due_at"))
        if ticket.get("sla_paused_at"):
            st.markdown(f"**SLA Due Date:** <span style='color: #805ad5; font-weight: bold;'>{due_formatted} (paused)</span>", unsafe_allow_html=True)
        elif ticket.get("is_overdue"):
            st.markdown(f"**SLA Due Date:** <span style='color: #e53e3e; font-weight: bold;'>{due_formatted}</span>", unsafe_allow_html=True)
        else:
            st.markdown(f"**SLA Due Date:** {due_formatted}")

    # Paused SLA Banner
    if ticket.get("sla_paused_at"):
        paused_formatted = format_datetime(ticket.get("sla_paused_at"))
        current_due_formatted = format_datetime(ticket.get("due_at"))
        st.info(f"⏸️ **SLA clock paused since {paused_formatted}**")
        st.caption(f"Current due date: {current_due_formatted}. It moves forward when work resumes.")

    # Metadata & Description
    with st.expander("📄 Ticket Description & Metadata", expanded=True):
        st.write(ticket["description"])
        st.divider()
        m_col1, m_col2, m_col3 = st.columns(3)
        requester_txt = format_user_display(ticket.get("requester_name"), ticket.get("requester_id"), fallback_unassigned="-")
        m_col1.caption(f"Requester: {requester_txt}")
        assignee_txt = format_user_display(ticket.get("assignee_name"), ticket.get("assignee_id"), fallback_unassigned="-")
        m_col2.caption(f"Assignee: {assignee_txt}")
        m_col3.caption(f"Created: {format_datetime(ticket.get('created_at'))}")

    # Similar Tickets section (Agent and Admin only)
    if user_role in ("agent", "admin"):
        with st.expander("🔍 Similar Tickets", expanded=True):
            st.caption("Ranked by text similarity. Open a resolved match to reuse its fix.")
            try:
                similar_tickets = client.get_similar_tickets(ticket_id, limit=5)
                if not similar_tickets:
                    st.caption("No similar tickets found.")
                else:
                    for sim in similar_tickets:
                        sim_row = format_similar_ticket_row(sim)
                        s_col1, s_col2 = st.columns([8, 2])
                        with s_col1:
                            st.markdown(
                                f"- **#{sim_row['id']}** {sim_row['title']} · "
                                f"<span style='background-color: {sim_row['status_color']}; color: white; padding: 2px 6px; border-radius: 4px; font-size: 0.85em; font-weight: bold;'>{sim_row['status_label']}</span> · "
                                f"`{sim_row['category'].capitalize()}` · "
                                f"**{sim_row['similarity_pct']} match**",
                                unsafe_allow_html=True,
                            )
                        with s_col2:
                            if st.button("Open", key=f"btn_open_similar_{sim_row['id']}"):
                                st.session_state.selected_ticket_id = sim_row["id"]
                                st.rerun()
            except SessionExpiredError:
                st.session_state.clear()
                st.session_state.session_expired_message = "Session expired, please log in again"
                st.rerun()
            except (APIError, APIConnectionError, Exception) as exc:
                st.caption(f"Could not load similar tickets: {exc}")

    # Main content layout: Left = Comments & History, Right = Actions (if authorized)
    if can_manage_actions:
        left_col, right_col = st.columns([6, 4])
    else:
        left_col = st.container()
        right_col = None

    with left_col:
        st.markdown("### 💬 Comments")
        if not comments:
            st.info("No comments yet.")
        else:
            for c in comments:
                is_internal = c.get("is_internal", False)
                author_label = f"User #{c['author_id']}"
                created_label = format_datetime(c.get("created_at"))

                if is_internal:
                    st.warning(f"🔒 **[Internal]** *{author_label}* on {created_label}\n\n{c['body']}")
                else:
                    with st.chat_message("user"):
                        st.markdown(f"**{author_label}** · *{created_label}*\n\n{c['body']}")

        # Add comment box
        st.markdown("#### Add a Comment")
        with st.form(f"comment_form_{ticket_id}"):
            comment_body = st.text_area("Your comment", placeholder="Type a response...", height=90).strip()
            is_internal_flag = False
            if user_role in ("agent", "admin"):
                is_internal_flag = st.checkbox("Internal note (visible to staff only)", key=f"internal_{ticket_id}")

            post_btn = st.form_submit_button("Post Comment")
            if post_btn:
                if not comment_body:
                    st.error("Comment cannot be empty.")
                else:
                    try:
                        client.add_comment(
                            ticket_id=ticket_id,
                            body=comment_body,
                            is_internal=is_internal_flag,
                        )
                        st.success("Comment added!")
                        st.rerun()
                    except SessionExpiredError:
                        st.session_state.clear()
                        st.session_state.session_expired_message = "Session expired, please log in again"
                        st.rerun()
                    except APIConnectionError as e:
                        st.error(e.message)
                    except APIError as e:
                        st.error(e.message)

        # Status History Timeline
        st.markdown("### 📜 Status History")
        if not history:
            st.caption("No status transitions recorded.")
        else:
            for h in history:
                from_st = h.get("from_status") or "Initial Creation"
                to_st = h.get("to_status", "")
                by_user = f"User #{h['changed_by_id']}" if h.get("changed_by_id") else "System"
                h_date = format_datetime(h.get("created_at"))
                st.markdown(f"- **{from_st.upper()}** ➔ **{to_st.upper()}** by *{by_user}* on `{h_date}`")

    # Actions panel
    if right_col is not None:
        with right_col:
            st.markdown("### ⚙️ Actions Panel")
            st.caption("Manage ticket lifecycle, category, and assignment")

            # 1. Update Category (Owner while open, Agent/Admin anytime)
            st.markdown("#### Change Category")
            categories = ["network", "hardware", "software", "access", "email", "other"]
            current_cat = ticket.get("category", "other")
            cat_idx = categories.index(current_cat) if current_cat in categories else 5

            with st.form(f"category_form_{ticket_id}"):
                new_category = st.selectbox("Select category", categories, index=cat_idx)
                cat_submit = st.form_submit_button("Update Category", use_container_width=True)

                if cat_submit:
                    try:
                        client.update_ticket(ticket_id=ticket_id, category=new_category)
                        st.success(f"Category changed to {new_category}!")
                        st.rerun()
                    except SessionExpiredError:
                        st.session_state.clear()
                        st.session_state.session_expired_message = "Session expired, please log in again"
                        st.rerun()
                    except APIConnectionError as e:
                        st.error(e.message)
                    except APIError as e:
                        # Displays API permission or validation error (e.g. 403)
                        st.error(f"Category update failed: {e.message}")

            # Staff-only controls
            if user_role in ("agent", "admin"):
                st.divider()

                # 2. Update Status
                st.markdown("#### Change Status")
                current_status = ticket["status"]
                allowed_next = ALLOWED_STATUS_TRANSITIONS.get(current_status, [])

                if not allowed_next:
                    st.info(f"Ticket is `{current_status.upper()}`. No further transitions allowed.")
                else:
                    for next_st in allowed_next:
                        btn_label = get_transition_button_label(current_status, next_st)
                        if st.button(btn_label, key=f"btn_status_{next_st}_{ticket_id}", use_container_width=True):
                            try:
                                client.update_ticket_status(ticket_id=ticket_id, status=next_st)
                                st.success(f"Status changed to {next_st.upper()}!")
                                st.rerun()
                            except SessionExpiredError:
                                st.session_state.clear()
                                st.session_state.session_expired_message = "Session expired, please log in again"
                                st.rerun()
                            except APIConnectionError as e:
                                st.error(e.message)
                            except APIError as e:
                                st.error(f"Status update failed: {e.message}")

                st.divider()

                # 3. Assign Ticket
                st.markdown("#### Assign Ticket")
                agents_list: list[dict[str, Any]] = []

                if user_role == "admin":
                    try:
                        all_users = client.list_users()
                        agents_list = [u for u in all_users if u.get("role") == "agent" and u.get("is_active")]
                    except APIError:
                        agents_list = []

                with st.form(f"assign_form_{ticket_id}"):
                    if agents_list:
                        agent_options = {f"{u['full_name']} (ID: {u['id']})": u['id'] for u in agents_list}
                        selected_agent_label = st.selectbox("Select Agent", list(agent_options.keys()))
                        chosen_agent_id = agent_options[selected_agent_label]
                    else:
                        st.caption("Enter Agent User ID (listing users requires Admin role):")
                        chosen_agent_id = st.number_input("Agent ID", min_value=1, step=1, value=1)

                    assign_submit = st.form_submit_button("Assign to Agent", use_container_width=True)

                    if assign_submit:
                        try:
                            client.assign_ticket(ticket_id=ticket_id, assignee_id=int(chosen_agent_id))
                            st.success(f"Assigned to agent #{chosen_agent_id}!")
                            st.rerun()
                        except SessionExpiredError:
                            st.session_state.clear()
                            st.session_state.session_expired_message = "Session expired, please log in again"
                            st.rerun()
                        except APIConnectionError as e:
                            st.error(e.message)
                        except APIError as e:
                            st.error(f"Assignment failed: {e.message}")
