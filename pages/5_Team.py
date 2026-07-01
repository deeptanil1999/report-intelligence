import streamlit as st
from utils.auth import require_auth, require_role, render_sidebar, init_supabase_service, ROLE_HIERARCHY
from utils.db import get_team_members, update_org_member_role, remove_org_member, add_org_member

st.set_page_config(page_title="Team — Report Intelligence", layout="wide")

user, role, project_id = require_auth()
render_sidebar(user, role)
require_role(role, "admin")

org_id = st.session_state.get("org_id")
st.title("👥 Team Management")

# ── Current members ───────────────────────────────────────────────────────────
st.subheader("Team Members")

members = get_team_members(org_id)

if not members:
    st.info("No team members found.")
else:
    # Fetch user emails via service client
    supabase_service = init_supabase_service()
    user_ids = [m["user_id"] for m in members]

    email_map = {}
    try:
        for uid in user_ids:
            res = supabase_service.auth.admin.get_user_by_id(uid)
            if res and res.user:
                email_map[uid] = res.user.email
    except Exception:
        pass

    roles_options = ["owner", "admin", "engineer", "viewer"]

    col_email, col_role, col_joined, col_actions = st.columns([3, 2, 2, 2])
    col_email.markdown("**Email**")
    col_role.markdown("**Role**")
    col_joined.markdown("**Joined**")
    col_actions.markdown("**Actions**")
    st.divider()

    for member in members:
        mid = member["id"]
        uid = member["user_id"]
        mem_role = member["role"]
        joined = (member.get("joined_at") or "")[:10]
        email = email_map.get(uid, uid[:12] + "…")
        is_self = uid == user.id

        col_e, col_r, col_j, col_a = st.columns([3, 2, 2, 2])

        with col_e:
            st.write(email)
        with col_r:
            if is_self or (role == "admin" and mem_role == "owner"):
                st.write(mem_role.capitalize())
            else:
                available_roles = [r for r in roles_options if r != "owner" or role == "owner"]
                new_role = st.selectbox(
                    "Role",
                    available_roles,
                    index=available_roles.index(mem_role) if mem_role in available_roles else 0,
                    key=f"role_{mid}",
                    label_visibility="collapsed",
                )
                if new_role != mem_role:
                    if st.button("Save", key=f"save_role_{mid}"):
                        update_org_member_role(mid, new_role)
                        get_team_members.clear()
                        st.success(f"Role updated to {new_role}.")
                        st.rerun()
        with col_j:
            st.write(joined)
        with col_a:
            if not is_self and not (role == "admin" and mem_role == "owner"):
                if st.button("Remove", key=f"remove_{mid}", type="secondary"):
                    st.session_state[f"confirm_remove_{mid}"] = True

            if st.session_state.get(f"confirm_remove_{mid}"):
                st.warning(f"Remove {email}?")
                c1, c2 = st.columns(2)
                with c1:
                    if st.button("Yes, remove", key=f"yes_remove_{mid}", type="primary"):
                        remove_org_member(mid)
                        get_team_members.clear()
                        del st.session_state[f"confirm_remove_{mid}"]
                        st.rerun()
                with c2:
                    if st.button("Cancel", key=f"cancel_remove_{mid}"):
                        del st.session_state[f"confirm_remove_{mid}"]
                        st.rerun()

        st.divider()

# ── Invite new member ─────────────────────────────────────────────────────────
st.subheader("Invite Team Member")

with st.form("invite_form"):
    invite_email = st.text_input("Email address")
    invite_role = st.selectbox("Role", ["engineer", "viewer", "admin"])
    submit_invite = st.form_submit_button("Send Invite")

if submit_invite:
    if not invite_email:
        st.error("Please enter an email address.")
    else:
        try:
            supabase_service = init_supabase_service()
            # Invite user via Supabase Auth admin API
            res = supabase_service.auth.admin.invite_user_by_email(invite_email)
            invited_user_id = res.user.id if res and res.user else None

            if invited_user_id:
                add_org_member(org_id, invited_user_id, invite_role, user.id)
                get_team_members.clear()
                st.success(f"Invite sent to {invite_email} as {invite_role}.")
                st.rerun()
            else:
                st.error("Could not create the invited user. Check the email and try again.")
        except Exception as e:
            st.error(f"Invite failed: {e}")
