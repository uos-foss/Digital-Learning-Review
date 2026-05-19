import streamlit as st
import pandas as pd
import os
import datetime
import logging

# Configure local text-file logging
logging.basicConfig(
    filename="app.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

__version__ = "1.4.0"

# Import modularized views
from views.faculty_overview import view_faculty_overview
from views.school_dashboard import view_school_dashboard
from views.module_report_card import view_module_report_card
from views.module_lead_checklist import view_module_lead_checklist
from views.docs import view_help, view_changelog, view_developer_guide, view_contribute
from views.feedback import view_feedback

# Page configuration
st.set_page_config(
    page_title="Digital Learning Review Dashboard",
    page_icon="📊",
    layout="wide"
)

from auth import check_password

# Secure Authentication & Session Persistence
if not check_password():
    st.stop()

if "view_selection" not in st.session_state:
    st.session_state.view_selection = "🏛️ Faculty Overview"

# Sidebar Navigation (Accessible only after login)
st.sidebar.title("FoSS Digital Learning Review Portal")
core_pages = ["🏛️ Faculty Overview", "🏫 School Dashboard", "📋 Module Report Card", "✅ Module Lead Checklist"]

# Determine current selected core page (None if currently viewing documentation)
current_core_page = st.session_state.view_selection if st.session_state.view_selection in core_pages else None

selected_radio = st.sidebar.radio(
    "Go to",
    core_pages,
    index=core_pages.index(current_core_page) if current_core_page else None
)

# Update view selection if radio button is changed by user
if selected_radio and selected_radio != current_core_page:
    st.session_state.view_selection = selected_radio
    st.rerun()

st.sidebar.divider()

# Saved School View / Multi-Tenancy Preferences
st.sidebar.subheader("👤 User Session")
st.sidebar.write(f"Logged in as: **{st.session_state.username}**")

schools_list = ["ALA", "ECN", "EDC", "GPL", "IJC", "MGT", "SPR"]

saved_school_idx = 0
if st.session_state.saved_school in schools_list:
    saved_school_idx = schools_list.index(st.session_state.saved_school) + 1

selected_saved_school = st.sidebar.selectbox(
    "Active School View",
    ["All Schools"] + schools_list,
    index=saved_school_idx,
    help="Default school view for team-level ownership without data siloing."
)

if selected_saved_school == "All Schools":
    st.session_state.saved_school = "All"
else:
    st.session_state.saved_school = selected_saved_school

# Semester Selector (Moved to User Session area)
selected_semester = st.sidebar.radio(
    "Select Semester", 
    ["Autumn", "Spring"], 
    index=0 if st.session_state.semester == "Autumn" else 1,
    help="Active semester filter for school and module-level data."
)
st.session_state.semester = selected_semester

st.sidebar.divider()
st.sidebar.subheader("📣 Collaborate & Feedback")

if st.sidebar.button("💬 App Feedback", width="stretch"):
    st.session_state.view_selection = "💬 App Feedback"
    st.rerun()

if st.sidebar.button("🤝 How to Contribute", width="stretch"):
    st.session_state.view_selection = "🤝 How to Contribute"
    st.rerun()

st.sidebar.divider()
st.sidebar.subheader("📄 Documentation")

if st.sidebar.button("💡 Help & Support", width="stretch"):
    st.session_state.view_selection = "💡 Help & Support"
    st.rerun()

if st.sidebar.button("📜 Release Changelog", width="stretch"):
    st.session_state.view_selection = "📜 Release Changelog"
    st.rerun()

if st.sidebar.button("💻 Developer Guide", width="stretch"):
    st.session_state.view_selection = "💻 Developer Guide"
    st.rerun()

# Display portal version aligned with Git tag history
st.sidebar.caption(f"Portal Version: v{__version__}")

st.sidebar.divider()

if st.sidebar.button("Log Out", width="stretch"):
    st.session_state.logged_in = False
    st.session_state.saved_school = "All"
    st.session_state.username = ""
    st.session_state.logged_out_this_session = True
    st.session_state.logout_pending = True
    st.rerun()

st.sidebar.divider()
st.sidebar.info("Aggregating VLE Review audit data across semesters.")

# Data Loading
@st.cache_data(ttl=3600)
def load_audit_data():
    logging.info("📥 Fetching VLE Review main audit data from Google Sheets (Cache Miss)...")
    main_id = os.getenv("MAIN_SPREADSHEET_ID")
    from data_manager import get_spreadsheet_data
    from processing import get_processed_audit_data
    ss, _ = get_spreadsheet_data(main_id)
    df_aut = get_processed_audit_data(ss, "All Schools Aut")
    df_spr = get_processed_audit_data(ss, "All Schools SPR")
    # Merge updated Ally scores if ALLY_SPREADSHEET_ID is configured in env
    ally_id = os.getenv("ALLY_SPREADSHEET_ID")
    if ally_id:
        from processing import get_updated_ally_scores
        logging.info("📥 Fetching updated Ally overall scores from Google Sheets (Cache Miss)...")
        ally_map = get_updated_ally_scores(ally_id)
        if ally_map:
            # Map new Ally scores based on 'New module code' column (cleaned to match keys)
            for df in [df_aut, df_spr]:
                if not df.empty and 'New module code' in df.columns:
                    # Clean and strip 'New module code' series to map safely
                    clean_codes = df['New module code'].astype(str).str.strip().str.upper()
                    
                    df['Ally Measured'] = clean_codes.map(lambda c: ally_map.get(c, {}).get('measured') if isinstance(ally_map.get(c), dict) else None).fillna(df['Ally 25/26 All'])
                    df['Ally Weighted'] = clean_codes.map(lambda c: ally_map.get(c, {}).get('weighted') if isinstance(ally_map.get(c), dict) else None).fillna(df['Ally Measured'])
                    df['Total Files'] = clean_codes.map(lambda c: ally_map.get(c, {}).get('files') if isinstance(ally_map.get(c), dict) else 0).fillna(0)
                    
                    # Keep 'Ally 25/26 All' updated with Weighted so existing cards/charts keep working
                    df['Ally 25/26 All'] = df['Ally Weighted']
                    
                    # Calculate the shift
                    df['Ally Shift'] = df['Ally Weighted'] - df['Ally Measured']
            logging.info(f"✅ Successfully integrated {len(ally_map)} updated Ally scores and calculated shift metrics.")

    # Merge Leganto no-list data if configured
    leganto_id = os.getenv("LEGANTO_NOLIST_ID")
    if leganto_id:
        from processing import get_leganto_nolist_data
        logging.info("📥 Fetching Leganto no-list data from Google Sheets (Cache Miss)...")
        no_list_set = get_leganto_nolist_data(leganto_id)
        if no_list_set:
            for df in [df_aut, df_spr]:
                if not df.empty and 'New module code' in df.columns:
                    clean_codes = df['New module code'].astype(str).str.strip().str.upper()
                    # If contained in the 'no_list_set', Leganto is 'Missing', else 'Has List' (assumed, or we can just use a boolean)
                    # Looking at other columns, categorical or boolean works. Let's use "Leganto Status"
                    df['Leganto Missing'] = clean_codes.isin(no_list_set)
            logging.info(f"✅ Flagged {len(no_list_set)} modules that appear in the Leganto 'no list' dataset.")

    logging.info("✅ Main audit data successfully loaded and processed.")
    return df_aut, df_spr

@st.cache_data(ttl=3600)
def load_checklist_data():
    logging.info("📥 Fetching self-audit checklist data from Google Sheets (Cache Miss)...")
    checklist_id = os.getenv("CHECKLIST_SPREADSHEET_ID")
    from processing import get_checklist_summaries
    logging.info("✅ Self-audit checklist summaries successfully loaded.")
    return get_checklist_summaries(checklist_id)

# Load the data
with st.spinner("Fetching data from Google Sheets..."):
    df_aut, df_spr = load_audit_data()
    checklist_sums = load_checklist_data()

# Page Routing
view = st.session_state.view_selection

if view == "🏛️ Faculty Overview":
    view_faculty_overview(df_aut, df_spr, checklist_sums)
elif view == "🏫 School Dashboard":
    view_school_dashboard(df_aut, df_spr, checklist_sums)
elif view == "📋 Module Report Card":
    view_module_report_card(df_aut, df_spr, checklist_sums)
elif view == "✅ Module Lead Checklist":
    view_module_lead_checklist(df_aut, df_spr, load_checklist_data)
elif view == "💬 App Feedback":
    view_feedback()
elif view == "💡 Help & Support":
    view_help()
elif view == "📜 Release Changelog":
    view_changelog()
elif view == "💻 Developer Guide":
    view_developer_guide()
elif view == "🤝 How to Contribute":
    view_contribute()
