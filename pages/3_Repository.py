import streamlit as st
import pandas as pd
from utils.auth import require_auth, render_sidebar
from utils.db import get_reports, get_flags, get_sample_sets

st.set_page_config(page_title="Repository — Report Intelligence", layout="wide")

user, role, project_id = require_auth()
render_sidebar(user, role)

st.title("📁 Report Repository")
project_name = st.session_state.get("project_name", "")
if project_name:
    st.caption(f"Project: **{project_name}**")


def severity_badge(severity: str) -> str:
    colors = {"critical": "#E24B4A", "warning": "#EF9F27", "info": "#378ADD"}
    labels = {"critical": "🔴 Critical", "warning": "🟡 Warning", "info": "🔵 Info"}
    c = colors.get(severity, "#888")
    l = labels.get(severity, severity)
    return f'<span style="background:{c};color:white;padding:2px 6px;border-radius:4px;font-size:11px">{l}</span>'


with st.spinner("Loading reports…"):
    reports = get_reports(project_id)

if not reports:
    st.info("No reports yet — upload your first PDF on the Upload page.")
    st.stop()

# ── Filters ───────────────────────────────────────────────────────────────────
col_search, col_status, col_severity = st.columns([3, 2, 2])

with col_search:
    search_query = st.text_input("Search", placeholder="Report number, location, mix ID…", label_visibility="collapsed")

with col_status:
    status_filter = st.selectbox(
        "Status",
        ["All", "ready", "processing", "error", "superseded"],
        label_visibility="collapsed",
    )

with col_severity:
    severity_filter = st.selectbox(
        "Flag Severity",
        ["All", "critical", "warning", "info", "none"],
        label_visibility="collapsed",
    )

# ── Fetch flags + sample sets for enrichment ──────────────────────────────────
all_report_ids = [r["id"] for r in reports]

# Build flag count lookup
flag_counts: dict[str, dict] = {}
sample_data: dict[str, dict] = {}

for report in reports:
    rid = report["id"]
    flags = get_flags(rid)
    flag_counts[rid] = {
        "critical": sum(1 for f in flags if f["severity"] == "critical" and f["status"] == "active"),
        "warning": sum(1 for f in flags if f["severity"] == "warning" and f["status"] == "active"),
        "info": sum(1 for f in flags if f["severity"] == "info" and f["status"] == "active"),
    }
    sets = get_sample_sets(rid)
    if sets:
        ss = sets[0]
        sample_data[rid] = {
            "mix_id": ss.get("mix_id", ""),
            "placement_location": ss.get("placement_location", ""),
            "specified_strength_psi": ss.get("specified_strength_psi"),
            "avg_28_day_strength_psi": ss.get("avg_28_day_strength_psi"),
        }
    else:
        sample_data[rid] = {}

# ── Apply filters ─────────────────────────────────────────────────────────────
filtered = reports

if status_filter != "All":
    filtered = [r for r in filtered if r.get("status") == status_filter]

if search_query:
    q = search_query.lower()
    filtered = [
        r for r in filtered
        if q in (r.get("report_number") or "").lower()
        or q in (sample_data.get(r["id"], {}).get("placement_location") or "").lower()
        or q in (sample_data.get(r["id"], {}).get("mix_id") or "").lower()
    ]

if severity_filter == "none":
    filtered = [
        r for r in filtered
        if all(v == 0 for v in flag_counts.get(r["id"], {}).values())
    ]
elif severity_filter != "All":
    filtered = [
        r for r in filtered
        if flag_counts.get(r["id"], {}).get(severity_filter, 0) > 0
    ]

st.caption(f"Showing {len(filtered)} of {len(reports)} reports")

# ── Render table ──────────────────────────────────────────────────────────────
if not filtered:
    st.info("No reports match the current filters.")
    st.stop()

for report in filtered:
    rid = report["id"]
    rnum = report.get("report_number", "—")
    rtype = (report.get("report_type") or "").replace("_", " ").title()
    svc_date = report.get("service_date") or "—"
    status = report.get("status", "")
    fc = flag_counts.get(rid, {})
    sd = sample_data.get(rid, {})

    # Status display
    status_map = {
        "ready": "✅ Ready",
        "processing": "⏳ Processing",
        "error": "❌ Error",
        "uploading": "⬆️ Uploading",
        "superseded": "🔁 Superseded",
    }
    status_label = status_map.get(status, status)

    is_superseded = status == "superseded"
    style_open = '<div style="opacity:0.5;font-style:italic">' if is_superseded else "<div>"

    with st.container():
        col1, col2, col3, col4, col5, col6, col7 = st.columns([2, 2, 1.5, 2, 1, 1, 1.5])

        with col1:
            st.markdown(f"**{rnum}**")
            if is_superseded:
                st.caption("🔁 Superseded")
        with col2:
            st.caption(rtype)
            st.caption(f"Service: {svc_date}")
        with col3:
            loc = sd.get("placement_location") or "—"
            st.caption(loc[:40])
        with col4:
            mix = sd.get("mix_id") or "—"
            spec = sd.get("specified_strength_psi")
            avg28 = sd.get("avg_28_day_strength_psi")
            st.caption(f"Mix: {mix}")
            if spec:
                st.caption(f"f'c: {spec:,} psi")
            if avg28:
                color = "green" if avg28 >= (spec or 0) else "red"
                st.markdown(
                    f'<span style="color:{color};font-size:12px">28-day: {avg28:,.0f} psi</span>',
                    unsafe_allow_html=True,
                )
        with col5:
            if fc.get("critical", 0):
                st.markdown(
                    f'<span style="background:#E24B4A;color:white;padding:2px 6px;border-radius:4px;font-size:11px">🔴 {fc["critical"]}</span>',
                    unsafe_allow_html=True,
                )
        with col6:
            if fc.get("warning", 0):
                st.markdown(
                    f'<span style="background:#EF9F27;color:white;padding:2px 6px;border-radius:4px;font-size:11px">🟡 {fc["warning"]}</span>',
                    unsafe_allow_html=True,
                )
            if fc.get("info", 0):
                st.markdown(
                    f'<span style="background:#378ADD;color:white;padding:2px 6px;border-radius:4px;font-size:11px">🔵 {fc["info"]}</span>',
                    unsafe_allow_html=True,
                )
        with col7:
            if st.button("View →", key=f"view_{rid}"):
                st.query_params["report_id"] = rid
                st.switch_page("pages/4_Report_Detail.py")

        st.divider()
