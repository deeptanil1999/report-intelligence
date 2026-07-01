import streamlit as st
from supabase import create_client, Client

ROLE_HIERARCHY = {"viewer": 0, "engineer": 1, "admin": 2, "owner": 3}


def _clean(value: str) -> str:
    import re
    # Remove ALL whitespace including embedded newlines from line-wrapped pastes
    return re.sub(r"\s+", "", str(value)).encode("ascii", "ignore").decode("ascii")


def init_supabase() -> Client:
    url = _clean(st.secrets["SUPABASE_URL"])
    key = _clean(st.secrets["SUPABASE_ANON_KEY"])
    return create_client(url, key)


def init_supabase_service() -> Client:
    url = _clean(st.secrets["SUPABASE_URL"])
    key = _clean(st.secrets["SUPABASE_SERVICE_KEY"])
    return create_client(url, key)


def get_user_role(user_id: str, org_id: str) -> str | None:
    supabase = init_supabase()
    res = (
        supabase.table("organization_members")
        .select("role")
        .eq("user_id", user_id)
        .eq("org_id", org_id)
        .single()
        .execute()
    )
    if res.data:
        return res.data["role"]
    return None


def require_auth():
    """
    Checks session state for a valid auth session.
    If none, renders the login form and calls st.stop().
    Returns (user, role, project_id) on success.
    """
    supabase = init_supabase()

    # Handle OAuth callback or token refresh if needed
    if "user" not in st.session_state or st.session_state.user is None:
        _show_login_form(supabase)
        st.stop()

    user = st.session_state.user
    role = st.session_state.get("role")
    project_id = st.session_state.get("project_id")

    if not role or not project_id:
        _show_org_setup(supabase, user)
        st.stop()

    return user, role, project_id


def _show_login_form(supabase: Client):
    st.set_page_config(page_title="Report Intelligence — Login", layout="centered")
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("## Report Intelligence")
        st.markdown("Construction QA Report Platform")
        st.divider()

        tab_login, tab_signup = st.tabs(["Sign In", "Create Account"])

        with tab_login:
            with st.form("login_form"):
                email = st.text_input("Email")
                password = st.text_input("Password", type="password")
                submitted = st.form_submit_button("Sign In", use_container_width=True)

            if submitted:
                if not email or not password:
                    st.error("Please enter your email and password.")
                    return
                try:
                    res = supabase.auth.sign_in_with_password({"email": email, "password": password})
                    if res.user:
                        st.session_state.user = res.user
                        st.session_state.session = res.session
                        _load_user_org(supabase, res.user)
                        st.rerun()
                    else:
                        st.error("Invalid credentials.")
                except Exception as e:
                    st.error(f"Login failed: {e}")

        with tab_signup:
            with st.form("signup_form"):
                new_email = st.text_input("Email", key="signup_email")
                new_password = st.text_input("Password", type="password", key="signup_pw")
                confirm_password = st.text_input("Confirm Password", type="password", key="signup_confirm")
                submitted_signup = st.form_submit_button("Create Account", use_container_width=True)

            if submitted_signup:
                if not new_email or not new_password:
                    st.error("Please fill in all fields.")
                    return
                if new_password != confirm_password:
                    st.error("Passwords do not match.")
                    return
                try:
                    res = supabase.auth.sign_up({"email": new_email, "password": new_password})
                    if res.user:
                        st.success("Account created! Please check your email to confirm, then sign in.")
                    else:
                        st.error("Sign-up failed.")
                except Exception as e:
                    st.error(f"Sign-up failed: {e}")


def _load_user_org(supabase: Client, user):
    res = (
        supabase.table("organization_members")
        .select("org_id, role")
        .eq("user_id", user.id)
        .execute()
    )
    if res.data:
        membership = res.data[0]
        st.session_state.org_id = membership["org_id"]
        st.session_state.role = membership["role"]
        # Load projects for this org
        proj_res = (
            supabase.table("projects")
            .select("id, name")
            .eq("org_id", membership["org_id"])
            .execute()
        )
        projects = proj_res.data or []
        st.session_state.projects = projects
        if projects:
            # Default to first project if none selected
            if "project_id" not in st.session_state or not st.session_state.project_id:
                st.session_state.project_id = projects[0]["id"]
                st.session_state.project_name = projects[0]["name"]
    else:
        st.session_state.org_id = None
        st.session_state.role = None
        st.session_state.project_id = None
        st.session_state.projects = []


def _show_org_setup(supabase: Client, user):
    st.set_page_config(page_title="Report Intelligence — Setup", layout="centered")
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("## Welcome to Report Intelligence")
        st.markdown("You're not part of an organization yet. Create one or join with an invite code.")
        st.divider()

        tab_create, tab_join = st.tabs(["Create Organization", "Join with Invite"])

        with tab_create:
            with st.form("create_org_form"):
                org_name = st.text_input("Organization Name")
                proj_name = st.text_input("First Project Name")
                proj_number = st.text_input("Project Number (optional)")
                proj_client = st.text_input("Client (optional)")
                submitted = st.form_submit_button("Create", use_container_width=True)

            if submitted:
                if not org_name or not proj_name:
                    st.error("Organization name and project name are required.")
                    return
                try:
                    org_res = supabase.table("organizations").insert({"name": org_name}).execute()
                    org_id = org_res.data[0]["id"]

                    supabase.table("organization_members").insert({
                        "org_id": org_id,
                        "user_id": user.id,
                        "role": "owner",
                    }).execute()

                    proj_data = {"org_id": org_id, "name": proj_name}
                    if proj_number:
                        proj_data["project_number"] = proj_number
                    if proj_client:
                        proj_data["client"] = proj_client
                    proj_res = supabase.table("projects").insert(proj_data).execute()
                    project_id = proj_res.data[0]["id"]

                    st.session_state.org_id = org_id
                    st.session_state.role = "owner"
                    st.session_state.project_id = project_id
                    st.session_state.project_name = proj_name
                    st.session_state.projects = [{"id": project_id, "name": proj_name}]
                    st.success("Organization created!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed to create organization: {e}")

        with tab_join:
            st.info("Ask your organization owner to invite you by email. Once invited, sign in with the credentials from your invite email.")


def require_role(user_role: str, minimum: str):
    if ROLE_HIERARCHY.get(user_role, -1) < ROLE_HIERARCHY.get(minimum, 999):
        st.error(f"This page requires at least the '{minimum}' role. Your role is '{user_role}'.")
        st.stop()


def render_sidebar(user, role: str):
    with st.sidebar:
        st.markdown("## Report Intelligence")
        st.caption(f"Signed in as **{user.email}**")

        role_colors = {"owner": "🟣", "admin": "🔵", "engineer": "🟢", "viewer": "⚪"}
        st.caption(f"{role_colors.get(role, '⚪')} Role: **{role.capitalize()}**")

        st.divider()

        supabase = init_supabase()
        projects = st.session_state.get("projects", [])
        if projects:
            project_names = [p["name"] for p in projects]
            current_name = st.session_state.get("project_name", project_names[0])
            try:
                current_idx = project_names.index(current_name)
            except ValueError:
                current_idx = 0

            selected = st.selectbox("Project", project_names, index=current_idx, key="project_selector")
            for p in projects:
                if p["name"] == selected:
                    st.session_state.project_id = p["id"]
                    st.session_state.project_name = p["name"]
                    break
        else:
            st.warning("No projects found.")

        st.divider()

        if st.button("Sign Out", use_container_width=True):
            try:
                supabase.auth.sign_out()
            except Exception:
                pass
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()
