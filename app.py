import streamlit as st
from utils.auth import init_supabase, _load_user_org, _show_login_form, _show_org_setup, render_sidebar

st.set_page_config(
    page_title="Report Intelligence",
    page_icon="🏗️",
    layout="wide",
    initial_sidebar_state="expanded",
)

supabase = init_supabase()

# Restore session from Supabase if we have a stored access token
if "user" not in st.session_state:
    try:
        session = supabase.auth.get_session()
        if session and session.user:
            st.session_state.user = session.user
            st.session_state.session = session
            _load_user_org(supabase, session.user)
    except Exception:
        st.session_state.user = None

# Auth gate
if not st.session_state.get("user"):
    _show_login_form(supabase)
    st.stop()

user = st.session_state.user
role = st.session_state.get("role")
project_id = st.session_state.get("project_id")

# Org setup gate
if not role or not project_id:
    _show_org_setup(supabase, user)
    st.stop()

# Render sidebar for authenticated users
render_sidebar(user, role)

# Landing page content
st.title("Report Intelligence")
st.markdown(
    "Welcome to **Report Intelligence** — your construction QA report management platform.\n\n"
    "Use the sidebar to navigate between pages:"
)

col1, col2, col3 = st.columns(3)
with col1:
    st.info("📊 **Dashboard**\nProject-wide summary and flag overview")
with col2:
    st.info("📤 **Upload**\nUpload and process PDF reports")
with col3:
    st.info("📁 **Repository**\nSearch and browse all reports")

col4, col5, _ = st.columns(3)
with col4:
    st.info("🔍 **Report Detail**\nView report data and manage flags")
with col5:
    if role in ("admin", "owner"):
        st.info("👥 **Team**\nManage team members and roles")
