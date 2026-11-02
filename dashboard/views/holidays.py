from datetime import date, datetime
import streamlit as st

from dashboard.api_client import (
    APIConnectionError,
    APIError,
    HelpdeskAPIClient,
    SessionExpiredError,
)
from dashboard.formatting import format_day_of_week


def render_holidays(client: HelpdeskAPIClient) -> None:
    """Render holidays management view (Agent and Admin only)."""
    user = st.session_state.get("user", {})
    user_role = user.get("role", "requester")

    # Enforce role guard: only agent and admin can access this view
    if user_role not in ("agent", "admin"):
        st.error("You do not have permission to access this page.")
        return

    st.subheader("📅 Holidays")
    st.write("Days when the SLA clock does not run. Weekends are already skipped.")

    is_admin = (user_role == "admin")

    # Fetch holidays with year filter
    col_filter, _ = st.columns([3, 7])
    with col_filter:
        current_year = date.today().year
        year_options = ["All", current_year - 1, current_year, current_year + 1, current_year + 2]
        selected_year_str = st.selectbox(
            "Filter by year",
            year_options,
            index=year_options.index(current_year),
            key="holiday_year_filter",
        )

    filter_year = None if selected_year_str == "All" else int(selected_year_str)

    try:
        holidays = client.list_holidays(year=filter_year)
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

    # Holidays Table
    if not holidays:
        if filter_year:
            st.info(f"No holidays found for {filter_year}.")
        else:
            st.info("No holidays registered yet.")
    else:
        # Table column widths: Date, Day of Week, Name, [Action if admin]
        col_widths = [2, 2, 5, 2] if is_admin else [3, 3, 6]

        with st.container():
            headers = st.columns(col_widths)
            headers[0].markdown("**Date**")
            headers[1].markdown("**Day of Week**")
            headers[2].markdown("**Name**")
            if is_admin:
                headers[3].markdown("**Action**")
            st.divider()

        for h in holidays:
            h_id = h["id"]
            h_date = h["holiday_date"]
            h_day = format_day_of_week(h_date)
            h_name = h["name"]

            with st.container():
                cols = st.columns(col_widths)
                cols[0].markdown(f"**{h_date}**")
                cols[1].markdown(f"`{h_day}`")
                cols[2].markdown(h_name)

                if is_admin:
                    if cols[3].button("Delete", key=f"btn_del_holiday_{h_id}", type="secondary", use_container_width=True):
                        try:
                            client.delete_holiday(h_id)
                            st.success(f"Deleted holiday '{h_name}' ({h_date})")
                            st.rerun()
                        except SessionExpiredError:
                            st.session_state.clear()
                            st.session_state.session_expired_message = "Session expired, please log in again"
                            st.rerun()
                        except APIConnectionError as err:
                            st.error(err.message)
                        except APIError as err:
                            st.error(f"Failed to delete holiday: {err.message}")

                st.divider()

    st.markdown("---")

    # Admin controls: Add Holiday Form
    if is_admin:
        st.markdown("### ➕ Add a Holiday")
        with st.form("add_holiday_form"):
            form_col1, form_col2 = st.columns(2)
            with form_col1:
                new_date = st.date_input("Holiday Date", value=date.today())
            with form_col2:
                new_name = st.text_input("Holiday Name", placeholder="e.g. Independence Day").strip()

            add_submit = st.form_submit_button("Add holiday")

            if add_submit:
                if not new_name:
                    st.error("Please provide a holiday name.")
                else:
                    try:
                        client.create_holiday(holiday_date=new_date, name=new_name)
                        st.success(f"Added holiday '{new_name}' on {new_date}!")
                        st.rerun()
                    except SessionExpiredError:
                        st.session_state.clear()
                        st.session_state.session_expired_message = "Session expired, please log in again"
                        st.rerun()
                    except APIConnectionError as err:
                        st.error(err.message)
                    except APIError as err:
                        # Surfaces 409 duplicate date or 422 error message cleanly
                        st.error(f"Failed to add holiday: {err.message}")
    else:
        st.caption("🔒 Only administrators can add or delete holidays.")
