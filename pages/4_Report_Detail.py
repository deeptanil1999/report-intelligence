import streamlit as st
from datetime import date
from utils.auth import require_auth, render_sidebar, ROLE_HIERARCHY
from utils.db import (
    get_report,
    get_sample_sets,
    get_cylinders,
    get_flags,
    get_flag_events,
    update_flag_status,
    insert_flag_event,
)
from utils.storage import get_signed_url

st.set_page_config(page_title="Report Detail — Report Intelligence", layout="wide")

user, role, project_id = require_auth()
render_sidebar(user, role)

# ── Load report ───────────────────────────────────────────────────────────────
report_id = st.query_params.get("report_id")
if not report_id:
    st.warning("No report selected. Go to the Repository to select a report.")
    st.stop()

report = get_report(report_id)
if not report:
    st.error("Report not found.")
    st.stop()


def severity_badge(severity: str) -> str:
    colors = {"critical": "#E24B4A", "warning": "#EF9F27", "info": "#378ADD"}
    labels = {"critical": "🔴 Critical", "warning": "🟡 Warning", "info": "🔵 Info"}
    c = colors.get(severity, "#888")
    l = labels.get(severity, severity)
    return f'<span style="background:{c};color:white;padding:2px 8px;border-radius:4px;font-size:12px">{l}</span>'


can_action = ROLE_HIERARCHY.get(role, 0) >= ROLE_HIERARCHY.get("engineer", 0)

left_col, right_col = st.columns([3, 2])

# ═══════════════════════════════════════════════════════════
# LEFT COLUMN — Report data
# ═══════════════════════════════════════════════════════════
with left_col:
    # ── Header card ──────────────────────────────────────────
    status_map = {
        "ready": "✅ Ready",
        "processing": "⏳ Processing",
        "error": "❌ Error",
        "uploading": "⬆️ Uploading",
        "superseded": "🔁 Superseded",
    }
    status_label = status_map.get(report.get("status"), report.get("status", ""))

    st.markdown(f"## Report {report.get('report_number', '—')}")
    col_a, col_b, col_c = st.columns(3)
    col_a.metric("Service Date", report.get("service_date") or "—")
    col_b.metric("Report Date", report.get("report_date") or "—")
    col_c.metric("Status", status_label)

    if report.get("task"):
        st.caption(f"Task: {report['task']}")
    if report.get("error_message"):
        with st.expander("❌ Processing Error"):
            st.error(report["error_message"])

    # ── Embedded PDF viewer ───────────────────────────────────
    st.subheader("PDF Document")
    try:
        signed_url = get_signed_url(report["pdf_storage_path"], expires_in=3600)
        if signed_url:
            st.markdown(
                f'<iframe src="{signed_url}" width="100%" height="600px" '
                'style="border:1px solid #ddd;border-radius:4px;"></iframe>',
                unsafe_allow_html=True,
            )
        else:
            st.warning("Could not generate PDF link.")
    except Exception as e:
        st.error(f"Error loading PDF: {e}")

    # ── Sample sets ───────────────────────────────────────────
    sample_sets = get_sample_sets(report_id)

    if not sample_sets:
        st.info("No sample set data parsed for this report.")
    else:
        for ss in sample_sets:
            ss_id = ss["id"]
            label = f"Sample Set {ss['set_number']}"
            if ss.get("ticket_number"):
                label += f" — Ticket {ss['ticket_number']}"
            if ss.get("placement_location"):
                label += f" | {ss['placement_location']}"

            with st.expander(label, expanded=True):
                # Material info
                st.markdown("**Material Information**")
                mat_cols = st.columns(3)
                mat_fields = [
                    ("Mix ID", "mix_id"),
                    ("Supplier", "supplier"),
                    ("Ticket No.", "ticket_number"),
                    ("Batch Time", "batch_time"),
                    ("Truck No.", "truck_number"),
                    ("Plant", "plant"),
                    ("Specified Strength", "specified_strength_psi"),
                    ("Strength Age", "strength_age_days"),
                    ("Sample Date", "sample_date"),
                ]
                for i, (label_txt, key) in enumerate(mat_fields):
                    val = ss.get(key)
                    if val is not None:
                        unit = " psi" if key == "specified_strength_psi" else (" days" if key == "strength_age_days" else "")
                        mat_cols[i % 3].metric(label_txt, f"{val}{unit}")

                st.markdown("**Field Test Data**")

                def _field_row(label, result, spec_min, spec_max, unit=""):
                    if result is None:
                        return
                    if spec_min is not None and spec_max is not None:
                        in_spec = spec_min <= result <= spec_max
                        status_icon = "✅" if in_spec else "❌"
                        spec_str = f"{spec_min} – {spec_max}{unit}"
                    elif spec_max is not None:
                        in_spec = result <= spec_max
                        status_icon = "✅" if in_spec else "❌"
                        spec_str = f"MAX {spec_max}{unit}"
                    else:
                        status_icon = "—"
                        spec_str = "—"
                    st.markdown(
                        f"| {label} | {result}{unit} | {spec_str} | {status_icon} |",
                        unsafe_allow_html=False,
                    )

                field_table_rows = []
                fields_to_show = [
                    ("Slump", "slump_result", "slump_spec_min", "slump_spec_max", '"'),
                    ("Air Content", "air_content_result", "air_content_spec_min", "air_content_spec_max", "%"),
                    ("Concrete Temp", "concrete_temp_result", None, "concrete_temp_spec_max", "°F"),
                    ("Ambient Temp", "ambient_temp", None, None, "°F"),
                    ("Unit Weight", "plastic_unit_weight", None, None, " pcf"),
                    ("Water Before (gal)", "water_added_before_gal", None, None, ""),
                    ("Water After (gal)", "water_added_after_gal", None, None, ""),
                ]

                header_written = False
                for label_txt, res_key, min_key, max_key, unit in fields_to_show:
                    res = ss.get(res_key)
                    if res is None:
                        continue
                    mn = ss.get(min_key) if min_key else None
                    mx = ss.get(max_key) if max_key else None
                    if mn is not None and mx is not None:
                        in_spec = mn <= res <= mx
                        status_icon = "✅" if in_spec else "❌"
                        spec_str = f"{mn} – {mx}{unit}"
                    elif mx is not None:
                        in_spec = res <= mx
                        status_icon = "✅" if in_spec else "❌"
                        spec_str = f"MAX {mx}{unit}"
                    else:
                        status_icon = "—"
                        spec_str = "—"
                    field_table_rows.append({
                        "Test": label_txt,
                        "Result": f"{res}{unit}",
                        "Specification": spec_str,
                        "Status": status_icon,
                    })

                if field_table_rows:
                    import pandas as pd
                    st.dataframe(pd.DataFrame(field_table_rows), use_container_width=True, hide_index=True)

                # Cylinder results
                st.markdown("**Laboratory Test Data**")
                cylinders = get_cylinders(ss_id)
                if not cylinders:
                    st.caption("No cylinder data recorded.")
                else:
                    spec_strength = ss.get("specified_strength_psi")
                    cyl_rows = []
                    for cyl in cylinders:
                        strength = cyl.get("comp_strength_psi")
                        age = cyl.get("age_at_test_days")

                        below_min = False
                        if age == 28 and strength is not None and spec_strength:
                            if spec_strength <= 5000:
                                minimum = spec_strength - 500
                            else:
                                minimum = 0.90 * spec_strength
                            below_min = strength < minimum

                        strength_disp = f"{'⚠️ ' if below_min else ''}{strength:,.0f}" if strength else "Pending"

                        cyl_rows.append({
                            "Spec ID": cyl.get("spec_id", ""),
                            "Condition": cyl.get("cylinder_condition", ""),
                            "Diam (in)": cyl.get("avg_diameter_in"),
                            "Date Tested": cyl.get("date_tested") or "—",
                            "Age (days)": cyl.get("age_at_test_days"),
                            "Comp Strength (psi)": strength_disp,
                            "Frac Type": cyl.get("frac_type", ""),
                        })

                    df_cyl = pd.DataFrame(cyl_rows)
                    st.dataframe(df_cyl, use_container_width=True, hide_index=True)

                    if ss.get("avg_28_day_strength_psi"):
                        avg28 = ss["avg_28_day_strength_psi"]
                        color = "green" if spec_strength and avg28 >= spec_strength else "red"
                        st.markdown(
                            f'<b>28-day Average: <span style="color:{color}">{avg28:,.0f} psi</span></b>',
                            unsafe_allow_html=True,
                        )


# ═══════════════════════════════════════════════════════════
# RIGHT COLUMN — Flags panel
# ═══════════════════════════════════════════════════════════
with right_col:
    st.subheader("Compliance Flags")

    flags = get_flags(report_id)

    if not flags:
        st.success("No compliance flags for this report.")
    else:
        # Group by severity
        severity_order = ["critical", "warning", "info"]
        grouped = {sev: [f for f in flags if f["severity"] == sev] for sev in severity_order}

        for severity in severity_order:
            sev_flags = grouped[severity]
            if not sev_flags:
                continue

            colors = {"critical": "#E24B4A", "warning": "#EF9F27", "info": "#378ADD"}
            color = colors[severity]
            st.markdown(
                f'<h4 style="color:{color}">{severity.capitalize()} ({len(sev_flags)})</h4>',
                unsafe_allow_html=True,
            )

            for flag in sev_flags:
                flag_id = flag["id"]
                flag_status = flag.get("status", "active")

                with st.expander(f"{flag['flag_code']} — {flag_status.upper()}", expanded=(flag_status == "active")):
                    st.markdown(
                        severity_badge(severity),
                        unsafe_allow_html=True,
                    )
                    st.markdown(f"**{flag['description']}**")

                    if flag.get("standard_reference"):
                        st.caption(f"Reference: {flag['standard_reference']}")

                    if flag.get("field_value") or flag.get("spec_value"):
                        col_fv, col_sv = st.columns(2)
                        if flag.get("field_value"):
                            col_fv.metric("Measured", flag["field_value"])
                        if flag.get("spec_value"):
                            col_sv.metric("Specification", flag["spec_value"])

                    st.caption(f"Created: {flag.get('created_at', '')[:10]}")

                    # Action buttons (engineer+ only)
                    if can_action and flag_status == "active":
                        action_col1, action_col2 = st.columns(2)
                        with action_col1:
                            if st.button("Acknowledge", key=f"ack_{flag_id}"):
                                st.session_state[f"action_{flag_id}"] = "acknowledged"
                        with action_col2:
                            if st.button("Dispute", key=f"dis_{flag_id}"):
                                st.session_state[f"action_{flag_id}"] = "disputed"

                    pending_action = st.session_state.get(f"action_{flag_id}")
                    if pending_action:
                        with st.form(f"form_{flag_id}"):
                            note = st.text_area("Note (optional)", key=f"note_{flag_id}")
                            submitted = st.form_submit_button(f"Confirm {pending_action.capitalize()}")
                        if submitted:
                            update_flag_status(flag_id, pending_action)
                            insert_flag_event({
                                "flag_id": flag_id,
                                "user_id": user.id,
                                "action": pending_action,
                                "note": note or None,
                            })
                            del st.session_state[f"action_{flag_id}"]
                            # Clear cache
                            get_flags.clear()
                            st.success(f"Flag marked as {pending_action}.")
                            st.rerun()

                    # Audit trail
                    events = get_flag_events(flag_id)
                    if events:
                        st.markdown("**Audit Trail**")
                        for event in events:
                            user_info = event.get("auth.users") or {}
                            email = user_info.get("email", "Unknown user") if isinstance(user_info, dict) else "Unknown user"
                            action = event.get("action", "")
                            created = event.get("created_at", "")[:10]
                            note_txt = f" — '{event['note']}'" if event.get("note") else ""
                            st.caption(f"🕐 {email} {action} on {created}{note_txt}")
