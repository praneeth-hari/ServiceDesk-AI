import streamlit as st

from dashboard.api_client import (
    APIConnectionError,
    APIError,
    HelpdeskAPIClient,
    SessionExpiredError,
)
from dashboard.formatting import format_datetime, format_similar_ticket_row


def _apply_category(cat: str) -> None:
    val = (cat or "").strip().lower()
    if val in ["network", "hardware", "software", "access", "email", "other"]:
        st.session_state.new_ticket_cat = val


def _apply_priority(prio: str) -> None:
    val = (prio or "").strip().lower()
    if val in ["low", "medium", "high", "urgent"]:
        st.session_state.new_ticket_prio = val


def _open_ticket(ticket_id: int) -> None:
    st.session_state.selected_ticket_id = ticket_id
    st.session_state.current_page = "Ticket Detail"
    st.session_state.sidebar_navigation = "Tickets"
    st.session_state.pop("last_created_ticket_id", None)
    st.session_state.pop("submit_success", None)


def _submit_ticket_callback(client: HelpdeskAPIClient) -> None:
    title_val = (st.session_state.get("new_ticket_title") or "").strip()
    desc_val = (st.session_state.get("new_ticket_desc") or "").strip()
    prio_val = st.session_state.get("new_ticket_prio", "medium")
    cat_val = st.session_state.get("new_ticket_cat", "other")

    if not title_val:
        st.session_state["submit_error"] = "Title cannot be empty."
        return
    if not desc_val:
        st.session_state["submit_error"] = "Description cannot be empty."
        return

    try:
        ticket = client.create_ticket(
            title=title_val,
            description=desc_val,
            priority=prio_val,
            category=cat_val,
        )
        st.session_state["submit_success"] = ticket
        st.session_state.last_created_ticket_id = ticket["id"]
        # Clear form inputs and AI suggestion
        st.session_state.new_ticket_title = ""
        st.session_state.new_ticket_desc = ""
        st.session_state.new_ticket_cat = "other"
        st.session_state.new_ticket_prio = "medium"
        st.session_state.triage_suggestion = None
        st.session_state.triage_text = None
        st.session_state.pop("submit_error", None)
    except SessionExpiredError:
        st.session_state.clear()
        st.session_state.session_expired_message = "Session expired, please log in again"
        st.rerun()
    except (APIConnectionError, APIError) as e:
        st.session_state["submit_error"] = e.message


def render_new_ticket(client: HelpdeskAPIClient) -> None:
    """Render the Create New Ticket form with advisory AI triage and duplicate detection."""
    st.subheader("➕ Create a New Ticket")

    # Initialize widget and suggestion states
    if "new_ticket_title" not in st.session_state:
        st.session_state.new_ticket_title = ""
    if "new_ticket_desc" not in st.session_state:
        st.session_state.new_ticket_desc = ""
    if "new_ticket_cat" not in st.session_state:
        st.session_state.new_ticket_cat = "other"
    if "new_ticket_prio" not in st.session_state:
        st.session_state.new_ticket_prio = "medium"

    # 1. Title and Description Inputs
    st.text_input(
        "Title",
        key="new_ticket_title",
        placeholder="e.g. Cannot access corporate VPN",
    )

    st.text_area(
        "Description",
        key="new_ticket_desc",
        placeholder="Provide detailed steps or context...",
        height=150,
    )

    # 2. AI Triage Suggestion Button
    col_suggest, _ = st.columns([3, 7])
    with col_suggest:
        if st.button("🤖 Suggest category & priority", key="btn_suggest_triage"):
            st.session_state.pop("submit_success", None)
            current_title = (st.session_state.get("new_ticket_title") or "").strip()
            current_desc = (st.session_state.get("new_ticket_desc") or "").strip()
            if not current_title and not current_desc:
                st.warning("Please enter a title or description first.")
            else:
                try:
                    suggestion = client.suggest_triage(current_title, current_desc)
                    st.session_state.triage_suggestion = suggestion
                    st.session_state.triage_text = (current_title, current_desc)
                except SessionExpiredError:
                    st.session_state.clear()
                    st.session_state.session_expired_message = "Session expired, please log in again"
                    st.rerun()
                except (APIConnectionError, APIError, Exception) as exc:
                    st.session_state.triage_suggestion = None
                    st.session_state.triage_text = None
                    st.warning(f"AI suggestion unavailable: {exc}")

    # 3. Suggestion & Duplicate Box
    suggestion = st.session_state.get("triage_suggestion")
    saved_text = st.session_state.get("triage_text")
    active_text = (
        (st.session_state.get("new_ticket_title") or "").strip(),
        (st.session_state.get("new_ticket_desc") or "").strip(),
    )

    if suggestion is not None:
        if saved_text != active_text:
            st.caption("Text changed, click Suggest again")
        else:
            sugg_cat = suggestion.get("suggested_category")
            confidence = float(suggestion.get("confidence", 0.0) or 0.0)
            evidence = suggestion.get("evidence", [])
            duplicates = suggestion.get("possible_duplicates", [])

            if not sugg_cat and confidence <= 0.0:
                st.info(
                    "No confident suggestion yet. Not enough similar resolved tickets. Please choose the category yourself."
                )
            else:
                with st.container(border=True):
                    st.markdown("#### 🤖 AI Suggestion")
                    c_col1, c_col2 = st.columns([3, 2])
                    with c_col1:
                        cat_label = str(sugg_cat).lower()
                        st.markdown(
                            f"**Category:** <span style='background-color: #3182ce; color: white; padding: 3px 8px; border-radius: 4px; font-weight: bold;'>{cat_label.capitalize()}</span>",
                            unsafe_allow_html=True,
                        )
                        st.button(
                            f"Apply category ({cat_label})",
                            key="btn_apply_category",
                            on_click=_apply_category,
                            args=(cat_label,),
                        )
                    with c_col2:
                        conf_pct = min(max(confidence, 0.0), 1.0)
                        st.progress(conf_pct, text=f"Confidence: {int(round(conf_pct * 100))}%")

                    sugg_prio = suggestion.get("suggested_priority")
                    if sugg_prio:
                        prio_label = str(sugg_prio).lower()
                        st.caption(f"Priority hint: {prio_label} (low reliability, check it yourself)")
                        st.button(
                            f"Apply priority ({prio_label})",
                            key="btn_apply_priority",
                            on_click=_apply_priority,
                            args=(prio_label,),
                        )

                    if evidence:
                        with st.expander(f"Based on {len(evidence)} similar resolved tickets"):
                            for ev in evidence:
                                ev_row = format_similar_ticket_row(ev)
                                st.markdown(
                                    f"- **#{ev_row['id']}** {ev_row['title']} · "
                                    f"`{ev_row['category'].capitalize()}` · "
                                    f"**{ev_row['similarity_pct']} match**"
                                )

            if duplicates:
                st.warning("⚠️ **Possible duplicate**")
                for dup in duplicates:
                    dup_row = format_similar_ticket_row(dup)
                    d_col1, d_col2 = st.columns([8, 2])
                    with d_col1:
                        st.markdown(
                            f"- **#{dup_row['id']}** {dup_row['title']} "
                            f"(<span style='color: {dup_row['status_color']}; font-weight: bold;'>{dup_row['status_label']}</span>, "
                            f"**{dup_row['similarity_pct']} match**)",
                            unsafe_allow_html=True,
                        )
                    with d_col2:
                        st.button(
                            f"Open #{dup_row['id']}",
                            key=f"btn_open_dup_{dup_row['id']}",
                            on_click=_open_ticket,
                            args=(dup_row["id"],),
                        )

    # 4. Priority and Category Selection Widgets
    prio_options = ["low", "medium", "high", "urgent"]
    cat_options = ["network", "hardware", "software", "access", "email", "other"]

    col_prio, col_cat = st.columns(2)
    with col_prio:
        st.selectbox("Priority", prio_options, key="new_ticket_prio")
    with col_cat:
        st.selectbox("Category", cat_options, key="new_ticket_cat")

    # 5. Submit / Create Ticket
    st.button(
        "Submit Ticket",
        key="btn_submit_ticket",
        on_click=_submit_ticket_callback,
        args=(client,),
        use_container_width=True,
    )

    if "submit_error" in st.session_state:
        st.error(st.session_state["submit_error"])
        del st.session_state["submit_error"]

    if "submit_success" in st.session_state:
        ticket = st.session_state["submit_success"]
        due_date = format_datetime(ticket.get("due_at"))
        st.success(
            f"🎉 Ticket **#{ticket['id']}** created successfully!\n\n"
            f"**Category:** {ticket.get('category', 'other').capitalize()} | "
            f"**Priority:** {ticket['priority'].upper()} | "
            f"**SLA Due Date:** {due_date}"
        )

    if st.session_state.get("last_created_ticket_id"):
        created_id = st.session_state.last_created_ticket_id
        st.button(
            f"Go to Ticket #{created_id}",
            key="go_to_created_ticket",
            on_click=_open_ticket,
            args=(created_id,),
        )
