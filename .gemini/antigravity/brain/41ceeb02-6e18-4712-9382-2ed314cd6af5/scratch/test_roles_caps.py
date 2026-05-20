import sys
import os

# Add target workspace to path to allow imports
sys.path.append(r"c:\Users\fs1hpc\Documents\GitHub\Digital-Learning-Review")

import streamlit as st

# Mock streamlit session state to avoid running in a Streamlit process
if not hasattr(st, "session_state") or not st.session_state:
    class MockSessionState(dict):
        def __getattr__(self, name):
            return self.get(name)
        def __setattr__(self, name, value):
            self[name] = value
    st.session_state = MockSessionState()

from auth import EnvAuthProvider, GoogleSheetsAuthProvider

def test_env_auth_provider():
    print("--- Testing EnvAuthProvider ---")
    provider = EnvAuthProvider()
    
    # Test ADMIN
    role_admin = provider.get_user_role("ADMIN")
    caps_admin = provider.get_user_capabilities("ADMIN")
    print(f"ADMIN role: {role_admin}, capabilities: {caps_admin}")
    assert role_admin == "System Administrator"
    assert "View Faculty Overview" in caps_admin
    assert "complete module checklist" in caps_admin
    assert "View only own school" not in caps_admin
    
    # Test ECN
    role_ecn = provider.get_user_role("ECN")
    caps_ecn = provider.get_user_capabilities("ECN")
    print(f"ECN role: {role_ecn}, capabilities: {caps_ecn}")
    assert role_ecn == "School Module Lead"
    assert "View only own school" in caps_ecn
    assert "complete module checklist" in caps_ecn
    assert "View Faculty Overview" not in caps_ecn

def test_google_sheets_auth_provider():
    print("--- Testing GoogleSheetsAuthProvider ---")
    provider = GoogleSheetsAuthProvider()
    
    # Mock load_sheets_users and load_sheets_roles
    import auth
    original_load_users = auth.load_sheets_users
    original_load_roles = auth.load_sheets_roles
    
    auth.load_sheets_users = lambda: {
        "LEGACY_ALL": {
            "Role": "Faculty Reviewer",
            "School": "All",
            "Status": "ACTIVE"
        },
        "LEGACY_SCHOOL": {
            "Role": "School Module Lead",
            "School": "ECN",
            "Status": "ACTIVE"
        },
        "NEW_CONFIGURED": {
            "Role": "School Auditor",
            "School": "MGT",
            "Status": "ACTIVE"
        }
    }
    
    auth.load_sheets_roles = lambda: {
        "faculty reviewer": {
            "Role": "Faculty Reviewer",
            "Capabilities": "view_all"
        },
        "school module lead": {
            "Role": "School Module Lead",
            "Capabilities": "view_school"
        },
        "school auditor": {
            "Role": "School Auditor",
            "Capabilities": "View only own school, view module checklist"
        }
    }
    
    try:
        # Check LEGACY_ALL
        role_all = provider.get_user_role("LEGACY_ALL")
        caps_all = provider.get_user_capabilities("LEGACY_ALL")
        print(f"LEGACY_ALL role: {role_all}, caps: {caps_all}")
        assert "View Faculty Overview" in caps_all
        assert "complete module checklist" in caps_all
        assert "View only own school" not in caps_all

        # Check LEGACY_SCHOOL
        role_sch = provider.get_user_role("LEGACY_SCHOOL")
        caps_sch = provider.get_user_capabilities("LEGACY_SCHOOL")
        print(f"LEGACY_SCHOOL role: {role_sch}, caps: {caps_sch}")
        assert "View only own school" in caps_sch
        assert "complete module checklist" in caps_sch
        assert "View Faculty Overview" not in caps_sch

        # Check NEW_CONFIGURED
        role_new = provider.get_user_role("NEW_CONFIGURED")
        caps_new = provider.get_user_capabilities("NEW_CONFIGURED")
        print(f"NEW_CONFIGURED role: {role_new}, caps: {caps_new}")
        assert "View only own school" in caps_new
        assert "view module checklist" in caps_new
        assert "complete module checklist" not in caps_new
        
        print("GoogleSheetsAuthProvider tests passed successfully!")
    finally:
        auth.load_sheets_users = original_load_users
        auth.load_sheets_roles = original_load_roles

if __name__ == "__main__":
    test_env_auth_provider()
    test_google_sheets_auth_provider()
    print("All backend authentication checks passed!")
