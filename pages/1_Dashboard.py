import streamlit as st
import plotly.graph_objects as go
from datetime import date, timedelta
from utils.auth import require_auth, render_sidebar
from utils.db import get_dashboard_data, get_strength_chart_data, get_all_active_flags

st.set_page_config(page_title="Dashboard — Report Intelligence", layout="wide")

user, role, project_id = require_auth()
render_sidebar(user, role)

st.title("📊 Dashboard")
project_name = st.session_state.get("project_name", "")
if project_name:
    st.caption(f"Project: **{project_name}**")

# ── Load data ─────────────────────────────────────────────────────────────────
with st.spinner("Loading dashboard data…"):
    data = get_dashboard_data(project_id)
    chart_data = get_strength_chart_data(project_id)
    active_flags = get_all_active_flags(project_id)

reports = data["reports"]
critical_flags = data["critical_flags"]
warning_flags = data["warning_flags"]

# ── Summary cards ─────────────────────────────────────────────────────────────
today = date.today()
seven_days_ago = today - timedelta(days=7)

total_reports = len([r for r in reports if r.get("status") != "superseded"])

# Reports with active (not acknowledged) critical flags
reports_with_critical = len({f["report_id"] for f in critical_flags})

# Reports with pending 28-day results (status = ready but avg_28 still null — approximated via flag)
pending_28_reports = len({
    f["report_id"] for f in active_flags
    if f.get("flag_code") == "RESULT_PENDING_OVERDUE"
})

# Reports processed in last 7 days
recent_reports = sum(
    1 for r in reports
    if r.get("created_at") and r["created_at"][:10] >= seven_days_ago.isoformat()
)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Total Reports", total_reports)
c2.metric("Reports w/ Critical Flags", reports_with_critical, delta=None)
c3.metric("28-Day Results Pending", pending_28_reports)
c4.metric("Processed (Last 7 Days)", recent_reports)

st.divider()

left_col, right_col = st.columns([3, 2])

# ── Strength chart ─────────────────────────────────────────────────────────────
with left_col:
    st.subheader("Compressive Strength by Service Date")

    if not chart_data:
        st.info("No compressive strength data yet — upload your first PDF on the Upload page.")
    else:
        dates = []
        strengths = []
        spec_strengths = []
        labels = []

        for row in chart_data:
            report_info = row.get("reports") or {}
            svc_date = report_info.get("service_date") or row.get("sample_date")
            avg = row.get("avg_28_day_strength_psi")
            spec = row.get("specified_strength_psi")
            if svc_date and avg:
                dates.append(svc_date)
                strengths.append(avg)
                spec_strengths.append(spec or 0)
                labels.append(
                    f"Report: {report_info.get('report_number', 'N/A')}<br>"
                    f"Location: {row.get('placement_location', 'N/A')}<br>"
                    f"28-day avg: {avg} psi"
                )

        if dates:
            bar_colors = [
                "#639922" if s >= (spec_strengths[i] or 0) else "#E24B4A"
                for i, s in enumerate(strengths)
            ]

            fig = go.Figure()
            fig.add_trace(go.Bar(
                x=dates,
                y=strengths,
                marker_color=bar_colors,
                text=[f"{s:,.0f}" for s in strengths],
                textposition="outside",
                hovertext=labels,
                hoverinfo="text",
                name="28-day Avg Strength",
            ))

            # Draw f'c line for each unique spec strength
            unique_specs = list(set(s for s in spec_strengths if s))
            for fc in unique_specs:
                fig.add_hline(
                    y=fc,
                    line_dash="dash",
                    line_color="#E24B4A",
                    annotation_text=f"f'c = {fc:,} psi",
                    annotation_position="top right",
                )

            fig.update_layout(
                xaxis_title="Service Date",
                yaxis_title="Compressive Strength (psi)",
                showlegend=False,
                margin=dict(t=30, b=30),
                height=400,
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No 28-day strength results available yet.")

# ── Open flags tables ──────────────────────────────────────────────────────────
with right_col:
    st.subheader("Open Critical Flags")

    critical_active = [f for f in active_flags if f.get("severity") == "critical"]
    if not critical_active:
        st.success("No active critical flags.")
    else:
        import pandas as pd

        rows = []
        for f in critical_active:
            report_info = f.get("reports") or {}
            ss_info = f.get("sample_sets") or {}
            created_at = f.get("created_at", "")
            if created_at:
                try:
                    opened = date.fromisoformat(created_at[:10])
                    days_open = (today - opened).days
                except Exception:
                    days_open = "—"
            else:
                days_open = "—"

            rows.append({
                "Report No.": report_info.get("report_number", "—"),
                "Location": ss_info.get("placement_location", "—"),
                "Flag": f.get("flag_code", ""),
                "Days Open": days_open,
            })

        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("Open Warning Flags")

    warning_active = [f for f in active_flags if f.get("severity") == "warning"]
    if not warning_active:
        st.success("No active warning flags.")
    else:
        rows = []
        for f in warning_active:
            report_info = f.get("reports") or {}
            rows.append({
                "Report No.": report_info.get("report_number", "—"),
                "Flag": f.get("flag_code", ""),
                "Description": f.get("description", "")[:80],
            })
        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True, hide_index=True)
