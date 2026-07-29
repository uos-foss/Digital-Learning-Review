import os
import streamlit as st
import extra_streamlit_components as stx
from datetime import datetime, timedelta
from dotenv import load_dotenv
import logging

# Explicitly load environment variables to ensure credentials are valid immediately on module load
load_dotenv(override=True)

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
            return "admin"
        elif entered_user == "DLA":
            return "DLA"
        elif entered_user == "FACULTY":
            return "FOSS"
        return "ML"

    def get_user_capabilities(self, username: str) -> list:
        role = self.get_user_role(username)
        if role == "admin":
            return ["view_all", "edit_checklist", "access_admin_panel"]
        elif role == "DLA":
            return ["view_all", "edit_checklist"]
        elif role == "FOSS":
            return ["view_all"]
        elif role == "ML":
            return ["view_school", "edit_checklist"]
        elif role == "SA":
            return ["view_school"]
        elif role == "SL":
            return ["view_all", "view_school"]
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
        return "ML"

    def get_user_capabilities(self, username: str) -> list:
        users = load_sqlite_users()
        uname = str(username).strip().upper()
        if uname in users:
            role = users[uname]["Role"]
            roles_map = load_sqlite_roles()
            if role.lower() in roles_map:
                caps_str = roles_map[role.lower()]["Capabilities"]
                return [c.strip().lower() for c in caps_str.split(",") if c.strip()]
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
        return "ML"

    def get_user_capabilities(self, username: str) -> list:
        return ["view_school", "edit_checklist"]

class GoogleOAuthProvider(BaseAuthProvider):
    """
    OAuth2-based authentication provider using Google.
    Delegates role and capability lookups to SQLite queries using the verified email as the Username.
    """
    def __init__(self):
        self.db_provider = SQLiteAuthProvider()

    def authenticate(self, email: str, id_token_or_code: str) -> bool:
        return self.is_valid_user(email)

    def is_valid_user(self, email: str) -> bool:
        return self.db_provider.is_valid_user(email)

    def get_school_context(self, email: str) -> str:
        return self.db_provider.get_school_context(email)

    def get_user_role(self, email: str) -> str:
        return self.db_provider.get_user_role(email)

    def get_user_capabilities(self, email: str) -> list:
        return self.db_provider.get_user_capabilities(email)

def get_auth_provider() -> BaseAuthProvider:
    """Factory to retrieve the active Auth Provider configured in the environment."""
    provider_name = os.getenv("AUTH_PROVIDER", "").strip().upper()
    if provider_name == "ENV":
        return EnvAuthProvider()
    elif provider_name in ["AD", "ACTIVE_DIRECTORY"]:
        return ActiveDirectoryAuthProvider()
    elif provider_name in ["GOOGLE", "GOOGLE_OAUTH"]:
        return GoogleOAuthProvider()
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

    # Check Google OAuth code callback BEFORE instantiating CookieManager.
    # This prevents the async component rendering from triggering interrupting reruns during token exchange.
    if isinstance(provider, GoogleOAuthProvider) and not st.session_state.logged_in:
        query_params = st.query_params
        if "code" in query_params:
            code = query_params["code"]
            
            client_id = os.getenv("GOOGLE_CLIENT_ID", "").strip()
            client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "").strip()
            redirect_uri = os.getenv("OAUTH_REDIRECT_URI", os.getenv("REDIRECT_URI", "http://localhost:8500/digital-learning-review/")).strip()
            
            if not client_id or not client_secret:
                st.error("😕 OAuth credentials missing in environment.")
                st.query_params.clear()
            else:
                import requests
                token_url = "https://oauth2.googleapis.com/token"
                data = {
                    "code": code,
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code"
                }
                try:
                    resp = requests.post(token_url, data=data)
                    if resp.status_code != 200:
                        logging.error(f"❌ Google Token Exchange failed with code {resp.status_code}: {resp.text}")
                        logging.error(f"❌ Parameters sent: client_id='{client_id}', redirect_uri='{redirect_uri}'")
                    resp.raise_for_status()
                    tokens = resp.json()
                    access_token = tokens.get("access_token")
                    
                    if access_token:
                        # Fetch user info from Google API directly (avoids clock-skew issues with id_token)
                        userinfo_url = "https://www.googleapis.com/oauth2/v3/userinfo"
                        headers = {"Authorization": f"Bearer {access_token}"}
                        user_resp = requests.get(userinfo_url, headers=headers)
                        user_resp.raise_for_status()
                        user_info = user_resp.json()
                        email = user_info.get("email", "").strip().lower()
                        
                        if email:
                            if provider.is_valid_user(email):
                                st.session_state.logged_in = True
                                st.session_state.username = email.upper()
                                st.session_state.saved_school = provider.get_school_context(email)
                                st.session_state.capabilities = provider.get_user_capabilities(email)
                                st.session_state.user_role = provider.get_user_role(email)
                                st.session_state.logged_out_this_session = False
                                
                                # Queue cookie write since CookieManager isn't instantiated yet
                                st.session_state.needs_cookie_write = email.upper()
                                logging.info(f"🔑 User '{email.upper()}' authenticated successfully via Google OAuth.")
                                st.query_params.clear()
                                st.rerun()
                            else:
                                st.error(f"😕 Access Denied: User '{email}' is not on the whitelist.")
                                logging.warning(f"⚠️ Failed login attempt: '{email}' is not whitelisted.")
                                st.query_params.clear()
                        else:
                            st.error("😕 Could not retrieve email from Google.")
                            st.query_params.clear()
                    else:
                        st.error("😕 Authentication failed: could not retrieve access token from Google.")
                        logging.error(f"❌ OAuth exchange failed: {tokens}")
                        st.query_params.clear()
                except Exception as e:
                    st.error(f"😕 Authentication failed: {e}")
                    logging.error(f"❌ OAuth authentication error: {e}")
                    st.query_params.clear()

    # [CRITICAL FIX]: If securely logged in and not actively logging out, bypass the cookie component.
    # This silences background async events completely during active usage, preventing UI resetting.
    if st.session_state.logged_in and not st.session_state.logout_pending:
        return True

    # Instantiate CookieManager only when needed for state transitions (restoring or logging out)
    cookie_manager = stx.CookieManager(key="vle_auth_cookies")
    COOKIE_NAME = "vle_auth_user"
    COOKIE_TTL_HOURS = 8

    # Handle queued cookie write from successful Google login
    if st.session_state.logged_in and st.session_state.get("needs_cookie_write"):
        expires_at = datetime.now() + timedelta(hours=COOKIE_TTL_HOURS)
        cookie_manager.set(COOKIE_NAME, st.session_state.needs_cookie_write, expires_at=expires_at)
        st.session_state.needs_cookie_write = None

    # Handle pending logout safely
    if st.session_state.get("logout_pending"):
        try:
            cookie_manager.delete(COOKIE_NAME)
        except KeyError:
            pass
        cookie_manager.set(COOKIE_NAME, "")
        st.session_state["logout_pending"] = False
        logging.info("🚪 User logged out. Browser session and cookies securely cleared.")
        
        # Force a client-side redirect to clean URL query parameters completely
        redirect_uri = os.getenv("OAUTH_REDIRECT_URI", os.getenv("REDIRECT_URI", "http://localhost:8500/digital-learning-review/")).strip()
        st.markdown(f'<meta http-equiv="refresh" content="0; url={redirect_uri}">', unsafe_allow_html=True)
        st.stop()

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

        # If it's GoogleOAuthProvider, we can authenticate using the underlying db_provider
        auth_provider = provider.db_provider if isinstance(provider, GoogleOAuthProvider) else provider

        if auth_provider.authenticate(entered_user, entered_pass):
            st.session_state.logged_in = True
            st.session_state.username = entered_user.upper()
            st.session_state.saved_school = auth_provider.get_school_context(entered_user)
            st.session_state.capabilities = auth_provider.get_user_capabilities(entered_user)
            st.session_state.user_role = auth_provider.get_user_role(entered_user)
            st.session_state.logged_out_this_session = False
            
            # Persist in browser cookie
            expires_at = datetime.now() + timedelta(hours=COOKIE_TTL_HOURS)
            cookie_manager.set(COOKIE_NAME, entered_user.upper(), expires_at=expires_at)
            logging.info(f"🔑 User '{entered_user.upper()}' authenticated successfully via login form.")
        else:
            st.session_state.logged_in = False
            st.error("😕 Invalid username or password. Please try again.")
            logging.warning(f"⚠️ Failed login attempt for username '{entered_user}'.")

    # Show login form (Username/Password is the default UI)
    st.title("🔒 Digital Learning Review Portal")
    st.write("Please sign in to access your school's dashboard and tools.")
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.subheader("Sign In")
        st.text_input("Username (School Code, email, or FACULTY):", placeholder="e.g. ECN, EDC, or user@domain.com", key="login_username")
        st.text_input("Password", type="password", key="login_password", on_change=password_entered)
        st.caption("Press Enter after typing your password to sign in.")
        
        # If Google OAuth is enabled, show the "Sign in with Google" button below the credentials form
        if isinstance(provider, GoogleOAuthProvider):
            st.markdown("<div style='text-align: center; margin: 20px 0;'><strong>OR</strong></div>", unsafe_allow_html=True)
            
            client_id = os.getenv("GOOGLE_CLIENT_ID", "").strip()
            redirect_uri = os.getenv("OAUTH_REDIRECT_URI", os.getenv("REDIRECT_URI", "http://localhost:8500/digital-learning-review/")).strip()
            
            auth_url = (
                f"https://accounts.google.com/o/oauth2/v2/auth?"
                f"client_id={client_id}&"
                f"response_type=code&"
                f"scope=openid%20email%20profile&"
                f"redirect_uri={redirect_uri}&"
                f"state=state_parameter_passthrough_value&"
                f"prompt=select_account&"
                f"access_type=online"
            )
            
            st.markdown(
                f'<a href="{auth_url}" target="_self" style="'
                f'display: block; text-align: center; background-color: #4285F4; color: white; '
                f'padding: 12px 24px; border-radius: 4px; text-decoration: none; font-weight: bold; '
                f'box-shadow: 0 2px 4px rgba(0,0,0,0.25); font-family: Roboto, sans-serif; transition: background-color .2s;'
                f'" onmouseover="this.style.backgroundColor=\'#357ae8\'" onmouseout="this.style.backgroundColor=\'#4285F4\'">'
                f'Sign In with Google'
                f'</a>',
                unsafe_allow_html=True
            )
            
    st.divider()
    return False
