import uuid
import re
import streamlit as st
from utils.auth import require_auth, require_role, render_sidebar
from utils.storage import upload_pdf
from utils.db import (
    insert_report,
    update_report,
    insert_sample_set,
    insert_cylinder,
    insert_flag,
    find_report_by_base_number,
    supersede_report,
)
from utils.classifier import classify_report
from utils.pdf_parser import extract_raw_text, parse_concrete_compressive
from utils.flagging_engine import run_flags

st.set_page_config(page_title="Upload — Report Intelligence", layout="wide")

user, role, project_id = require_auth()
render_sidebar(user, role)
require_role(role, "engineer")

st.title("📤 Upload Reports")
st.caption("Supported format: Concrete Compressive Strength Test Reports (PDF)")

uploaded_files = st.file_uploader(
    "Upload reports",
    type=["pdf"],
    accept_multiple_files=True,
    label_visibility="collapsed",
)

if uploaded_files:
    if st.button("Process Reports", type="primary"):
        summary_rows = []

        for uploaded_file in uploaded_files:
            file_name = uploaded_file.name
            st.markdown(f"---\n**Processing: {file_name}**")

            status_placeholder = st.empty()
            status_placeholder.info("⏳ Uploading…")

            report_id = None
            try:
                pdf_bytes = uploaded_file.read()

                # ── Stage 1: Upload to storage ──────────────────────────────
                storage_path = f"{project_id}/{uuid.uuid4()}.pdf"
                upload_pdf(pdf_bytes, storage_path)
                status_placeholder.info("🔍 Classifying…")

                # ── Stage 2: Extract text + classify ──────────────────────
                raw_text, pages = extract_raw_text(pdf_bytes)
                classification = classify_report(raw_text)
                report_type = classification["report_type"]

                if report_type != "concrete_compressive_strength":
                    status_placeholder.warning(
                        f"⚠️ Report type '{report_type}' detected — only concrete compressive strength is fully supported in Phase 1."
                    )

                # ── Stage 3: Parse header to get report number ─────────────
                status_placeholder.info("📄 Parsing…")
                parsed = parse_concrete_compressive(raw_text, pages)
                header = parsed["header"]
                sample_sets = parsed["sample_sets"]

                report_number = header.get("report_number") or file_name.replace(".pdf", "")

                # ── Revision detection ─────────────────────────────────────
                rev_match = re.search(r'(Rev\d+)$', report_number, re.IGNORECASE)
                base_number = re.sub(r'Rev\d+$', '', report_number, flags=re.IGNORECASE).strip()
                revision_number = int(rev_match.group(1)[3:]) if rev_match else 0

                existing = find_report_by_base_number(project_id, base_number)
                supersede_msg = None
                if existing:
                    supersede_msg = f"Supersedes existing report {existing['report_number']} (Rev{existing.get('revision_number', 0)})"

                # ── Insert reports row ─────────────────────────────────────
                report_row = insert_report({
                    "project_id": project_id,
                    "report_number": report_number,
                    "report_type": report_type,
                    "service_date": header.get("service_date"),
                    "report_date": header.get("report_date"),
                    "task": header.get("task"),
                    "pdf_storage_path": storage_path,
                    "status": "processing",
                    "revision_number": revision_number,
                    "parsed_data": header,
                    "uploaded_by": user.id,
                })
                report_id = report_row["id"]

                if existing:
                    supersede_report(existing["id"], report_id)
                    st.warning(f"ℹ️ {supersede_msg}")

                # ── Stage 4: Write sample sets + cylinders ─────────────────
                total_flags = {"critical": 0, "warning": 0, "info": 0}

                status_placeholder.info("🚩 Flagging…")
                for ss in sample_sets:
                    cylinders_data = ss.pop("cylinders", [])

                    ss_row = insert_sample_set({"report_id": report_id, **ss})
                    ss_id = ss_row["id"]

                    cyl_rows = []
                    for cyl in cylinders_data:
                        cyl_row = insert_cylinder({"sample_set_id": ss_id, **cyl})
                        cyl_rows.append(cyl_row)

                    # Attach db ids to cylinders for flagging
                    for i, cyl in enumerate(cylinders_data):
                        if i < len(cyl_rows):
                            cyl["id"] = cyl_rows[i]["id"]

                    # ── Stage 5: Run flagging engine ───────────────────────
                    flags = run_flags(ss_row, cyl_rows)
                    for flag in flags:
                        cyl_id = flag.pop("cylinder_id", None)
                        insert_flag({
                            "report_id": report_id,
                            "sample_set_id": ss_id,
                            "cylinder_id": cyl_id,
                            **flag,
                        })
                        sev = flag.get("severity", "info")
                        total_flags[sev] = total_flags.get(sev, 0) + 1

                # ── Stage 6: Mark ready ────────────────────────────────────
                update_report(report_id, {"status": "ready"})
                status_placeholder.success("✅ Done")

                summary_rows.append({
                    "File": file_name,
                    "Report No.": report_number,
                    "Type": report_type.replace("_", " ").title(),
                    "Service Date": header.get("service_date") or "—",
                    "🔴 Critical": total_flags.get("critical", 0),
                    "🟡 Warning": total_flags.get("warning", 0),
                    "🔵 Info": total_flags.get("info", 0),
                    "Status": "✅ Ready",
                })

            except Exception as e:
                err_msg = str(e)
                status_placeholder.error(f"❌ Error: {err_msg}")
                if report_id:
                    update_report(report_id, {"status": "error", "error_message": err_msg})
                summary_rows.append({
                    "File": file_name,
                    "Report No.": "—",
                    "Type": "—",
                    "Service Date": "—",
                    "🔴 Critical": 0,
                    "🟡 Warning": 0,
                    "🔵 Info": 0,
                    "Status": f"❌ Error: {err_msg[:60]}",
                })

        # ── Summary table ──────────────────────────────────────────────────
        if summary_rows:
            st.divider()
            st.subheader("Processing Summary")
            import pandas as pd
            st.dataframe(pd.DataFrame(summary_rows), use_container_width=True, hide_index=True)

elif not uploaded_files:
    st.info("Select one or more PDF files above to begin. The app will automatically classify, parse, and flag compliance issues.")
