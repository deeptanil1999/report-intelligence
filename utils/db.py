import streamlit as st
from utils.auth import init_supabase


@st.cache_data(ttl=60)
def get_projects(org_id: str) -> list[dict]:
    supabase = init_supabase()
    res = supabase.table("projects").select("*").eq("org_id", org_id).execute()
    return res.data or []


@st.cache_data(ttl=60)
def get_reports(project_id: str) -> list[dict]:
    supabase = init_supabase()
    res = (
        supabase.table("reports")
        .select("*")
        .eq("project_id", project_id)
        .order("service_date", desc=True)
        .execute()
    )
    return res.data or []


@st.cache_data(ttl=60)
def get_report(report_id: str) -> dict | None:
    supabase = init_supabase()
    res = supabase.table("reports").select("*").eq("id", report_id).single().execute()
    return res.data


@st.cache_data(ttl=60)
def get_sample_sets(report_id: str) -> list[dict]:
    supabase = init_supabase()
    res = (
        supabase.table("sample_sets")
        .select("*")
        .eq("report_id", report_id)
        .order("set_number")
        .execute()
    )
    return res.data or []


@st.cache_data(ttl=60)
def get_cylinders(sample_set_id: str) -> list[dict]:
    supabase = init_supabase()
    res = (
        supabase.table("cylinders")
        .select("*")
        .eq("sample_set_id", sample_set_id)
        .execute()
    )
    return res.data or []


@st.cache_data(ttl=60)
def get_flags(report_id: str) -> list[dict]:
    supabase = init_supabase()
    res = (
        supabase.table("flags")
        .select("*")
        .eq("report_id", report_id)
        .order("severity")
        .execute()
    )
    return res.data or []


@st.cache_data(ttl=60)
def get_flag_events(flag_id: str) -> list[dict]:
    supabase = init_supabase()
    res = (
        supabase.table("flag_events")
        .select("*, auth.users(email)")
        .eq("flag_id", flag_id)
        .order("created_at")
        .execute()
    )
    return res.data or []


@st.cache_data(ttl=300)
def get_dashboard_data(project_id: str) -> dict:
    supabase = init_supabase()

    reports_res = (
        supabase.table("reports")
        .select("id, report_number, service_date, status")
        .eq("project_id", project_id)
        .execute()
    )
    reports = reports_res.data or []
    report_ids = [r["id"] for r in reports]

    critical_flags = []
    warning_flags = []
    if report_ids:
        flags_res = (
            supabase.table("flags")
            .select("*")
            .in_("report_id", report_ids)
            .eq("status", "active")
            .execute()
        )
        all_flags = flags_res.data or []
        critical_flags = [f for f in all_flags if f["severity"] == "critical"]
        warning_flags = [f for f in all_flags if f["severity"] == "warning"]

    return {
        "reports": reports,
        "critical_flags": critical_flags,
        "warning_flags": warning_flags,
    }


@st.cache_data(ttl=300)
def get_strength_chart_data(project_id: str) -> list[dict]:
    supabase = init_supabase()
    res = (
        supabase.table("sample_sets")
        .select(
            "avg_28_day_strength_psi, specified_strength_psi, sample_date, "
            "placement_location, report_id, reports!inner(project_id, service_date, report_number)"
        )
        .eq("reports.project_id", project_id)
        .not_.is_("avg_28_day_strength_psi", "null")
        .execute()
    )
    return res.data or []


@st.cache_data(ttl=60)
def get_all_active_flags(project_id: str) -> list[dict]:
    supabase = init_supabase()
    res = (
        supabase.table("flags")
        .select(
            "*, reports!inner(project_id, report_number, service_date), "
            "sample_sets(placement_location)"
        )
        .eq("reports.project_id", project_id)
        .eq("status", "active")
        .execute()
    )
    return res.data or []


@st.cache_data(ttl=60)
def get_team_members(org_id: str) -> list[dict]:
    supabase = init_supabase()
    res = (
        supabase.table("organization_members")
        .select("id, role, joined_at, user_id")
        .eq("org_id", org_id)
        .execute()
    )
    return res.data or []


def insert_report(data: dict) -> dict:
    supabase = init_supabase()
    res = supabase.table("reports").insert(data).execute()
    return res.data[0]


def update_report(report_id: str, data: dict):
    supabase = init_supabase()
    supabase.table("reports").update(data).eq("id", report_id).execute()


def insert_sample_set(data: dict) -> dict:
    supabase = init_supabase()
    res = supabase.table("sample_sets").insert(data).execute()
    return res.data[0]


def insert_cylinder(data: dict) -> dict:
    supabase = init_supabase()
    res = supabase.table("cylinders").insert(data).execute()
    return res.data[0]


def insert_flag(data: dict) -> dict:
    supabase = init_supabase()
    res = supabase.table("flags").insert(data).execute()
    return res.data[0]


def update_flag_status(flag_id: str, status: str):
    supabase = init_supabase()
    supabase.table("flags").update({"status": status}).eq("id", flag_id).execute()


def insert_flag_event(data: dict) -> dict:
    supabase = init_supabase()
    res = supabase.table("flag_events").insert(data).execute()
    return res.data[0]


def find_report_by_base_number(project_id: str, base_number: str) -> dict | None:
    supabase = init_supabase()
    res = (
        supabase.table("reports")
        .select("*")
        .eq("project_id", project_id)
        .ilike("report_number", f"{base_number}%")
        .neq("status", "superseded")
        .execute()
    )
    if res.data:
        return res.data[0]
    return None


def supersede_report(old_report_id: str, new_report_id: str):
    supabase = init_supabase()
    supabase.table("reports").update({
        "superseded_by": new_report_id,
        "status": "superseded",
    }).eq("id", old_report_id).execute()


def update_org_member_role(member_id: str, role: str):
    supabase = init_supabase()
    supabase.table("organization_members").update({"role": role}).eq("id", member_id).execute()


def remove_org_member(member_id: str):
    supabase = init_supabase()
    supabase.table("organization_members").delete().eq("id", member_id).execute()


def add_org_member(org_id: str, user_id: str, role: str, invited_by: str):
    supabase = init_supabase()
    supabase.table("organization_members").insert({
        "org_id": org_id,
        "user_id": user_id,
        "role": role,
        "invited_by": invited_by,
    }).execute()
