"""Reports and analytics view for Agents and Admins."""

from typing import Any
import pandas as pd
import streamlit as st

from dashboard.api_client import (
    APIConnectionError,
    APIError,
    HelpdeskAPIClient,
    SessionExpiredError,
)


def render_reports(client: HelpdeskAPIClient) -> None:
    """Render the analytics and reports dashboard."""
    user = st.session_state.get("user") or {}
    role = user.get("role", "")

    if role not in ("agent", "admin"):
        st.error("Access denied: Reports are only available to Agents and Admins.")
        return

    st.title("📊 HelpDesk Reports & Analytics")
    st.markdown("Real-time operational performance metrics, SLA compliance, and category analytics.")

    days_window = st.sidebar.slider("Daily Volume Window (Days)", min_value=7, max_value=90, value=30, step=7)

    try:
        with st.spinner("Loading report metrics..."):
            status_data = client.get_report_tickets_by_status()
            overdue_data = client.get_report_overdue()
            resolution_data = client.get_report_resolution_time()
            ranking_data = client.get_report_agent_ranking()
            daily_data = client.get_report_daily_volume(days=days_window)
            sla_data = client.get_report_sla_breach_rate()
            res_cat_data = client.get_report_resolution_time_by_category()
            workload_data = client.get_report_agent_workload()
            tickets_cat_data = client.get_report_tickets_by_category(breakdown_by_status=False)
    except SessionExpiredError:
        st.session_state.clear()
        st.session_state["session_expired_message"] = "Session expired, please log in again"
        st.rerun()
    except APIConnectionError as exc:
        st.error(str(exc))
        return
    except APIError as exc:
        st.error(f"Failed to load reports: {exc.message}")
        return

    # --- KPI Cards ---
    open_count = sum(item.get("count", 0) for item in status_data if item.get("status") == "open")
    in_progress_count = sum(item.get("count", 0) for item in status_data if item.get("status") == "in_progress")
    overdue_count = len(overdue_data)

    # SLA breach rate overall calculation
    total_sla_tickets = sum(item.get("total_tickets", 0) for item in sla_data)
    total_breached_tickets = sum(item.get("breached_sla", 0) for item in sla_data)
    if total_sla_tickets > 0:
        overall_breach_rate = round(100.0 * total_breached_tickets / total_sla_tickets, 1)
        breach_rate_display = f"{overall_breach_rate:.1f}%"
    else:
        breach_rate_display = "0.0%" if sla_data else "N/A"

    # Resolution hours calculation (weighted by ticket_count)
    total_resolved = sum(item.get("ticket_count", 0) for item in resolution_data)
    weighted_hours = sum(item.get("avg_resolution_hours", 0.0) * item.get("ticket_count", 0) for item in resolution_data)
    avg_resolution_hours = (weighted_hours / total_resolved) if total_resolved > 0 else None
    avg_res_display = f"{avg_resolution_hours:.1f} hrs" if avg_resolution_hours is not None else "N/A"

    # Display KPI metrics
    kpi_cols = st.columns(5)
    with kpi_cols[0]:
        st.metric("Open Tickets", f"{open_count}")
    with kpi_cols[1]:
        st.metric("In Progress", f"{in_progress_count}")
    with kpi_cols[2]:
        st.metric("Overdue Tickets", f"{overdue_count}")
    with kpi_cols[3]:
        st.metric("SLA Breach Rate", breach_rate_display)
    with kpi_cols[4]:
        st.metric("Avg Resolution Time", avg_res_display)

    st.markdown("---")

    # --- Row 1: Tickets by Status & Tickets by Category ---
    col_status, col_cat = st.columns([1, 1], gap="large")

    with col_status:
        st.subheader("Tickets by Status")
        if status_data:
            status_totals: dict[str, int] = {}
            for item in status_data:
                s = item.get("status", "unknown")
                status_totals[s] = status_totals.get(s, 0) + item.get("count", 0)

            df_status = pd.DataFrame(
                [{"Status": k.replace("_", " ").title(), "Count": v} for k, v in status_totals.items()]
            ).set_index("Status")
            st.bar_chart(df_status)
        else:
            st.info("No ticket status data available.")

    with col_cat:
        st.subheader("Tickets by Category")
        if tickets_cat_data:
            df_cat = pd.DataFrame(
                [
                    {
                        "Category": item.get("category", "other").capitalize(),
                        "Tickets": item.get("count", 0),
                    }
                    for item in tickets_cat_data
                ]
            ).set_index("Category")
            st.bar_chart(df_cat)
        else:
            st.info("No ticket category data available.")

    st.markdown("---")

    # --- Row 2: SLA Breach Rate by Priority & Resolution Time by Category ---
    col_sla, col_res_cat = st.columns([1, 1], gap="large")

    with col_sla:
        st.subheader("SLA Breach Rate by Priority")
        if sla_data:
            df_sla = pd.DataFrame(
                [
                    {
                        "Priority": item.get("priority", "").upper(),
                        "Met SLA": item.get("met_sla", 0),
                        "Breached SLA": item.get("breached_sla", 0),
                    }
                    for item in sla_data
                ]
            ).set_index("Priority")
            st.bar_chart(df_sla)
        else:
            st.info("No SLA breach rate data available.")

    with col_res_cat:
        st.subheader("Average Resolution Time by Category (Hours)")
        if res_cat_data:
            cat_totals: dict[str, dict[str, float]] = {}
            for item in res_cat_data:
                cat = item.get("category", "other").capitalize()
                hrs = item.get("avg_resolution_hours", 0.0)
                cnt = item.get("ticket_count", 0)
                if cat not in cat_totals:
                    cat_totals[cat] = {"total_hours": 0.0, "count": 0}
                cat_totals[cat]["total_hours"] += hrs * cnt
                cat_totals[cat]["count"] += cnt

            df_res_cat = pd.DataFrame(
                [
                    {
                        "Category": cat,
                        "Avg Hours": round(info["total_hours"] / info["count"], 1) if info["count"] > 0 else 0.0,
                    }
                    for cat, info in cat_totals.items()
                ]
            ).set_index("Category")
            st.bar_chart(df_res_cat)
        else:
            st.info("No resolution time by category data available.")

    st.markdown("---")

    # --- Row 3: Agent Rankings & Agent Workload ---
    col_rank, col_workload = st.columns([1, 1], gap="large")

    with col_rank:
        st.subheader("Agent Rankings")
        if ranking_data:
            df_ranking = pd.DataFrame(
                [
                    {
                        "Rank": item.get("rank"),
                        "Agent": item.get("agent_name"),
                        "Resolved Tickets": item.get("resolved_count"),
                    }
                    for item in ranking_data
                ]
            )
            st.dataframe(df_ranking, hide_index=True, use_container_width=True)
        else:
            st.info("No resolved tickets or agent rankings available.")

    with col_workload:
        st.subheader("Agent Workload")
        if workload_data:
            df_workload = pd.DataFrame(
                [
                    {
                        "Agent": item.get("agent_name"),
                        "Open Work": item.get("open_tickets", 0),
                        "Overdue": item.get("overdue_tickets", 0),
                        "Resolved": item.get("resolved_tickets", 0),
                    }
                    for item in workload_data
                ]
            )
            st.dataframe(df_workload, hide_index=True, use_container_width=True)
        else:
            st.info("No agent workload data available.")

    st.markdown("---")

    # --- Row 4: Line Chart: Daily Volume ---
    st.subheader(f"Tickets Created per Day (Last {days_window} Days)")
    if daily_data:
        df_daily = pd.DataFrame(daily_data)
        if not df_daily.empty and "date" in df_daily.columns:
            df_daily = df_daily.rename(columns={"date": "Date", "ticket_count": "Tickets Created"})
            df_daily = df_daily.set_index("Date")
            st.line_chart(df_daily)
        else:
            st.info("No volume records found for this period.")
    else:
        st.info("No daily volume data available.")
