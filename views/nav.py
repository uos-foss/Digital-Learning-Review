import streamlit as st


def render_back_to_school_dashboard(key):
    """Back link to the School Dashboard for pages reached from its tables.

    Only offered to roles holding view_school_dashboard: pg_school is not
    registered for the rest, and st.switch_page raises on an unregistered
    page. The dashboard restores its view and lens filters itself (plain
    session values, see views/school_dashboard.py).
    """
    caps = [str(c).lower() for c in st.session_state.get("capabilities", [])]
    pg = st.session_state.get("pg_school")
    if "view_school_dashboard" in caps and pg is not None:
        if st.button("← Back to School Dashboard", key=key):
            st.switch_page(pg)
