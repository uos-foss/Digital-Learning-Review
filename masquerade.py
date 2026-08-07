import streamlit as st


def is_masquerading() -> bool:
    return bool(st.session_state.get("masquerade_active", False))


def start_masquerade(target_username: str):
    """Admin-only: shadow the real identity and adopt a target user's
    username/school/role/capabilities so the rest of the app renders exactly
    as that user would see it. View-only - callers must gate writes with
    is_masquerading().
    """
    from auth import load_sqlite_users, SQLiteAuthProvider

    uname = str(target_username).strip().upper()
    users = load_sqlite_users()
    if uname not in users:
        st.error(f"User '{uname}' not found.")
        return

    if not st.session_state.get("masquerade_active", False):
        st.session_state.real_username = st.session_state.get("username", "")
        st.session_state.real_saved_school = st.session_state.get("saved_school", "All")
        st.session_state.real_capabilities = st.session_state.get("capabilities", [])
        st.session_state.real_user_role = st.session_state.get("user_role", "")

    provider = SQLiteAuthProvider()
    st.session_state.username = uname
    st.session_state.saved_school = provider.get_school_context(uname)
    st.session_state.capabilities = provider.get_user_capabilities(uname)
    st.session_state.user_role = provider.get_user_role(uname)
    st.session_state.masquerade_active = True
    st.rerun()


def stop_masquerade():
    st.session_state.username = st.session_state.get("real_username", "")
    st.session_state.saved_school = st.session_state.get("real_saved_school", "All")
    st.session_state.capabilities = st.session_state.get("real_capabilities", [])
    st.session_state.user_role = st.session_state.get("real_user_role", "")

    for key in ("masquerade_active", "real_username", "real_saved_school", "real_capabilities", "real_user_role"):
        st.session_state.pop(key, None)
    st.rerun()


def clear_masquerade_state():
    """Drop any masquerade shadow state without restoring it - used on logout."""
    for key in ("masquerade_active", "real_username", "real_saved_school", "real_capabilities", "real_user_role"):
        st.session_state.pop(key, None)
