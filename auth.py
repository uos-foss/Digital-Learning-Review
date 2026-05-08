import os
import streamlit as st
import extra_streamlit_components as stx
from datetime import datetime, timedelta

# Create the cookie manager
cookie_manager = stx.CookieManager(key="vle_auth_cookies")

def check_password():
    """Returns `True` if the user is authenticated (via session or persistent cookie)."""
    COOKIE_NAME = "vle_auth_user"
    COOKIE_TTL_HOURS = 8

    # Load credentials dynamically from .env variables
    USER_CREDENTIALS = {
        "ALA": os.getenv("USER_ALA"),
        "ECN": os.getenv("USER_ECN"),
        "EDC": os.getenv("USER_EDC"),
        "GPL": os.getenv("USER_GPL"),
        "IJC": os.getenv("USER_IJC"),
        "MGT": os.getenv("USER_MGT"),
        "SPR": os.getenv("USER_SPR"),
        "FACULTY": os.getenv("USER_FACULTY")
    }
    # Filter out empty keys to prevent empty password logins
    USER_CREDENTIALS = {k: v for k, v in USER_CREDENTIALS.items() if v}

    # Session State Initialization
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False
    if "saved_school" not in st.session_state:
        st.session_state.saved_school = "All"
    if "username" not in st.session_state:
        st.session_state.username = ""
    if "semester" not in st.session_state:
        st.session_state.semester = "Autumn"
    if "logged_out_this_session" not in st.session_state:
        st.session_state.logged_out_this_session = False
    if "logout_pending" not in st.session_state:
        st.session_state.logout_pending = False

    # Handle pending logout safely
    if st.session_state.get("logout_pending"):
        try:
            cookie_manager.delete(COOKIE_NAME)
        except KeyError:
            pass
        cookie_manager.set(COOKIE_NAME, "")
        st.session_state["logout_pending"] = False

    # Restore session from browser cookie on page reload
    if not st.session_state.logged_in:
        stored_user = cookie_manager.get(COOKIE_NAME)
        if stored_user and stored_user in USER_CREDENTIALS:
            if not st.session_state.get("logged_out_this_session"):
                st.session_state.logged_in = True
                st.session_state.username = stored_user
                if stored_user == "FACULTY":
                    st.session_state.saved_school = "All"
                else:
                    st.session_state.saved_school = stored_user
                st.rerun()

    if st.session_state.logged_in:
        return True

    def password_entered():
        """Checks whether credentials entered by the user are correct."""
        entered_user = str(st.session_state.get("login_username", "")).strip().upper()
        entered_pass = str(st.session_state.get("login_password", "")).strip()

        if entered_user in USER_CREDENTIALS and USER_CREDENTIALS[entered_user] == entered_pass:
            st.session_state.logged_in = True
            st.session_state.username = entered_user
            if entered_user == "FACULTY":
                st.session_state.saved_school = "All"
            else:
                st.session_state.saved_school = entered_user
            st.session_state.logged_out_this_session = False
            
            # Persist in browser cookie
            expires_at = datetime.now() + timedelta(hours=COOKIE_TTL_HOURS)
            cookie_manager.set(COOKIE_NAME, entered_user, expires_at=expires_at)
        else:
            st.session_state.logged_in = False
            st.error("😕 Invalid username or password. Please try again.")

    # Show login form
    st.title("🔒 Digital Learning Review Portal")
    st.write("Please sign in to access your school's dashboard and tools.")
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.subheader("Sign In")
        st.text_input("Username (School Code or FACULTY)", placeholder="e.g. ECN, EDC, FACULTY", key="login_username")
        st.text_input("Password", type="password", key="login_password", on_change=password_entered)
        st.caption("Press Enter after typing your password to sign in.")
    
    st.divider()
    return False
