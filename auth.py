import os
import streamlit as st
import extra_streamlit_components as stx
from datetime import datetime, timedelta
from dotenv import load_dotenv
import logging

# Explicitly load environment variables to ensure credentials are valid immediately on module load
load_dotenv()

class BaseAuthProvider:
    """
    Abstract base class for all authentication backends.
    Defines interface for authentication checks, user checks, and capabilities.
    """
    def authenticate(self, username: str, password: str) -> bool:
        """Verifies if the credentials are valid. Returns True if verified."""
        raise NotImplementedError

    def is_valid_user(self, username: str) -> bool:
        """Verifies if the username is a valid/existing user in the system."""
        raise NotImplementedError

    def get_school_context(self, username: str) -> str:
        """Determines the default school filter context ('All' or specific code like 'ECN')."""
        raise NotImplementedError

    def get_user_capabilities(self, username: str) -> list:
        """Returns the list of capabilities allowed for this user."""
        raise NotImplementedError

    def get_user_role(self, username: str) -> str:
        """Returns the role of the user."""
        raise NotImplementedError

class EnvAuthProvider(BaseAuthProvider):
    """
    Authentication provider using local environment variables (standard configuration).
    """
    def __init__(self):
        # Load credentials dynamically from .env variables
        self.credentials = {
            "ALA": os.getenv("USER_ALA"),
            "ECN": os.getenv("USER_ECN"),
            "EDC": os.getenv("USER_EDC"),
            "GPL": os.getenv("USER_GPL"),
            "IJC": os.getenv("USER_IJC"),
            "MGT": os.getenv("USER_MGT"),
            "SPR": os.getenv("USER_SPR"),
            "FACULTY": os.getenv("USER_FACULTY"),
            "DLA": os.getenv("USER_DLA"),
            "ADMIN": os.getenv("USER_ADMIN"),
        }
        self.credentials = {k: v for k, v in self.credentials.items() if v}

    def authenticate(self, username: str, password: str) -> bool:
        entered_user = str(username).strip().upper()
        entered_pass = str(password).strip()
        return entered_user in self.credentials and self.credentials[entered_user] == entered_pass

    def is_valid_user(self, username: str) -> bool:
        return str(username).strip().upper() in self.credentials

    def get_school_context(self, username: str) -> str:
        entered_user = str(username).strip().upper()
        if entered_user in ["FACULTY", "DLA", "ADMIN"]:
            return "All"
        return entered_user

    def get_user_role(self, username: str) -> str:
        entered_user = str(username).strip().upper()
        if entered_user == "ADMIN":
            return "System Administrator"
        elif entered_user == "DLA":
            return "Digital Learning Advisor"
        elif entered_user == "FACULTY":
            return "Faculty Reviewer"
        return "School Module Lead"

    def get_user_capabilities(self, username: str) -> list:
        role = self.get_user_role(username)
        if role in ["System Administrator", "Digital Learning Advisor", "Faculty Reviewer"]:
            return ["View Faculty Overview", "complete module checklist"]
        elif role == "School Module Lead":
            return ["View only own school", "complete module checklist"]
        elif role == "School Auditor":
            return ["View only own school", "view module checklist"]
        elif role == "School Leadership":
            return ["View Faculty Overview", "View only own school", "view module checklist"]
        return []

@st.cache_data(ttl=60)
def load_sqlite_users():
    """
    Fetches the registry of users from SQLite.
    Cached for 60 seconds to allow responsive administrator updates.
    """
    import pandas as pd
    import logging
    from database import get_db_connection
    try:
        with get_db_connection() as conn:
            df = pd.read_sql_query("SELECT * FROM users", conn)
            
        users_dict = {}
        for _, row in df.iterrows():
            uname = str(row.get("Username", "")).strip().upper()
            if uname:
                users_dict[uname] = {
                    "PasswordHash": str(row.get("PasswordHash", "")).strip(),
                    "Role": str(row.get("Role", "")).strip(),
                    "School": str(row.get("School", "")).strip(),
                    "Capabilities": str(row.get("Capabilities", "")).strip(),
                    "Status": str(row.get("Status", "")).strip().upper()
                }
        return users_dict
    except Exception as e:
        logging.error(f"❌ Error loading users from SQLite: {e}")
        return {}

@st.cache_data(ttl=60)
def load_sqlite_roles():
    """
    Queries the 'roles' table from SQLite
    and returns a dictionary mapping role names to their capabilities.
    """
    import logging
    from database import get_db_connection
    try:
        import pandas as pd
        with get_db_connection() as conn:
            df = pd.read_sql_query("SELECT * FROM roles", conn)
            
        roles_dict = {}
        for _, row in df.iterrows():
            role_name = str(row.get("Role", "")).strip()
            caps_val = str(row.get("Capabilities", "")).strip()
            if role_name:
                roles_dict[role_name.lower()] = {
                    "Role": role_name,
                    "Capabilities": caps_val
                }
        return roles_dict
    except Exception as e:
        logging.error(f"❌ Error loading Roles from SQLite: {e}")
        return {}

class SQLiteAuthProvider(BaseAuthProvider):
    """
    SQLite Authentication: Queries an SQLite user ledger containing
    usernames, roles, password hashes, and user capabilities.
    """
    def authenticate(self, username: str, password: str) -> bool:
        import hashlib
        users = load_sqlite_users()
        uname = str(username).strip().upper()
        if uname in users and users[uname]["Status"] == "ACTIVE":
            entered_hash = hashlib.sha256(str(password).strip().encode("utf-8")).hexdigest()
            return users[uname]["PasswordHash"] == entered_hash
        return False

    def is_valid_user(self, username: str) -> bool:
        users = load_sqlite_users()
        uname = str(username).strip().upper()
        return uname in users and users[uname]["Status"] == "ACTIVE"

    def get_school_context(self, username: str) -> str:
        users = load_sqlite_users()
        uname = str(username).strip().upper()
        if uname in users:
            return users[uname]["School"]
        return "All"

    def get_user_role(self, username: str) -> str:
        users = load_sqlite_users()
        uname = str(username).strip().upper()
        if uname in users:
            return users[uname]["Role"]
        return "School Module Lead"

    def get_user_capabilities(self, username: str) -> list:
        users = load_sqlite_users()
        uname = str(username).strip().upper()
        if uname in users:
            role = users[uname]["Role"]
            roles_map = load_sqlite_roles()
            if role.lower() in roles_map:
                caps_str = roles_map[role.lower()]["Capabilities"]
                raw_caps = [c.strip() for c in caps_str.split(",") if c.strip()]
                resolved_caps = []
                for c in raw_caps:
                    if c == "view_all":
                        resolved_caps.extend(["View Faculty Overview", "complete module checklist"])
                    elif c == "view_school":
                        resolved_caps.extend(["View only own school", "complete module checklist"])
                    else:
                        resolved_caps.append(c)
                return list(set(resolved_caps))
        return []

class ActiveDirectoryAuthProvider(BaseAuthProvider):
    """
    Phase 3 Authentication: Authenticates credentials directly against Active Directory (AD) / LDAP server.
    """
    def authenticate(self, username: str, password: str) -> bool:
        # Placeholder for Active Directory authentication (using ldap3 or similar)
        logging.warning("⚠️ Active Directory authentication is currently unconfigured.")
        return False

    def is_valid_user(self, username: str) -> bool:
        # Placeholder: query AD server to verify if user directory exists
        return False

    def get_school_context(self, username: str) -> str:
        return "All"

    def get_user_role(self, username: str) -> str:
        return "School Module Lead"

    def get_user_capabilities(self, username: str) -> list:
        return ["View only own school", "complete module checklist"]

def get_auth_provider() -> BaseAuthProvider:
    """Factory to retrieve the active Auth Provider configured in the environment."""
    provider_name = os.getenv("AUTH_PROVIDER", "").strip().upper()
    if provider_name == "ENV":
        return EnvAuthProvider()
    elif provider_name in ["AD", "ACTIVE_DIRECTORY"]:
        return ActiveDirectoryAuthProvider()
    # SQLite is the default primary provider
    return SQLiteAuthProvider()

def check_password():
    """Returns `True` if the user is authenticated (via session or persistent cookie)."""
    
    # Initialize critical Session State keys first so we can rely on them for routing
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False
    if "logout_pending" not in st.session_state:
        st.session_state.logout_pending = False
    if "logged_out_this_session" not in st.session_state:
        st.session_state.logged_out_this_session = False
        
    # [CRITICAL FIX]: If securely logged in and not actively logging out, bypass the cookie component.
    # This silences background async events completely during active usage, preventing UI resetting.
    if st.session_state.logged_in and not st.session_state.logout_pending:
        return True

    # Create component ONLY when required for session state changes (Auth / Restore / Logout)
    cookie_manager = stx.CookieManager(key="vle_auth_cookies")
    
    COOKIE_NAME = "vle_auth_user"
    COOKIE_TTL_HOURS = 8

    # Load credentials dynamically from selection provider
    provider = get_auth_provider()

    # Ensure helper state variables exist for components downstream
    if "saved_school" not in st.session_state:
        st.session_state.saved_school = "All"
    if "username" not in st.session_state:
        st.session_state.username = ""
    if "semester" not in st.session_state:
        st.session_state.semester = "Autumn"
    if "select_semester_widget" not in st.session_state:
        st.session_state.select_semester_widget = st.session_state.semester

    # Handle pending logout safely
    if st.session_state.get("logout_pending"):
        try:
            cookie_manager.delete(COOKIE_NAME)
        except KeyError:
            pass
        cookie_manager.set(COOKIE_NAME, "")
        st.session_state["logout_pending"] = False
        logging.info("🚪 User logged out. Browser session and cookies securely cleared.")

    # Restore session from browser cookie on page reload
    if not st.session_state.logged_in:
        stored_user = cookie_manager.get(COOKIE_NAME)
        
        if stored_user and provider.is_valid_user(stored_user):
            if not st.session_state.get("logged_out_this_session"):
                st.session_state.logged_in = True
                st.session_state.username = stored_user
                st.session_state.saved_school = provider.get_school_context(stored_user)
                st.session_state.capabilities = provider.get_user_capabilities(stored_user)
                st.session_state.user_role = provider.get_user_role(stored_user)
                logging.info(f"🔄 Persistent session restored successfully from cookie for user '{stored_user}'.")

    if st.session_state.logged_in:
        return True

    def password_entered():
        """Checks whether credentials entered by the user are correct."""
        entered_user = str(st.session_state.get("login_username", "")).strip()
        entered_pass = str(st.session_state.get("login_password", "")).strip()

        if provider.authenticate(entered_user, entered_pass):
            st.session_state.logged_in = True
            st.session_state.username = entered_user.upper()
            st.session_state.saved_school = provider.get_school_context(entered_user)
            st.session_state.capabilities = provider.get_user_capabilities(entered_user)
            st.session_state.user_role = provider.get_user_role(entered_user)
            st.session_state.logged_out_this_session = False
            
            # Persist in browser cookie
            expires_at = datetime.now() + timedelta(hours=COOKIE_TTL_HOURS)
            cookie_manager.set(COOKIE_NAME, entered_user.upper(), expires_at=expires_at)
            logging.info(f"🔑 User '{entered_user.upper()}' authenticated successfully via login form.")
        else:
            st.session_state.logged_in = False
            st.error("😕 Invalid username or password. Please try again.")
            logging.warning(f"⚠️ Failed login attempt for username '{entered_user}'.")

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
