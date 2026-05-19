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

__version__ = "1.6.0"

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

# Initialize session state variables
if "semester" not in st.session_state:
    st.session_state.semester = "Autumn"
if "select_semester_widget" not in st.session_state:
    st.session_state.select_semester_widget = st.session_state.semester

def update_semester():
    st.session_state.semester = st.session_state.select_semester_widget

# Relocate the Select Semester radio group directly beneath the main "Go to" navigation radio group.
st.sidebar.radio(
    "Select Semester", 
    ["Autumn", "Spring"], 
    key="select_semester_widget",
    on_change=update_semester,
    help="Active semester filter for school and module-level data."
)

# Update view selection if radio button is changed by user
if selected_radio and selected_radio != current_core_page:
    st.session_state.view_selection = selected_radio
    st.rerun()

# Compact utility buttons at the bottom of the sidebar
with st.sidebar:
    st.markdown("---")
    if st.button("💬 App Feedback", use_container_width=True, key="side_btn_fb"):
        st.session_state.view_selection = "💬 App Feedback"
        st.rerun()
    if st.session_state.username in ["DLA", "ADMIN"]:
        if st.button("🤝 How to Contribute", use_container_width=True, key="side_btn_contrib"):
            st.session_state.view_selection = "🤝 How to Contribute"
            st.rerun()
    if st.button("💡 Help & Support", use_container_width=True, key="side_btn_help"):
        st.session_state.view_selection = "💡 Help & Support"
        st.rerun()
    if st.button("📜 Release Changelog", use_container_width=True, key="side_btn_change"):
        st.session_state.view_selection = "📜 Release Changelog"
        st.rerun()
    if st.session_state.username in ["DLA", "ADMIN"]:
        if st.button("💻 Developer Guide", use_container_width=True, key="side_btn_dev"):
            st.session_state.view_selection = "💻 Developer Guide"
            st.rerun()

    # Consolidated footer row
    st.markdown("---")
    if st.button(f"Logout - {st.session_state.username}", use_container_width=True, key="btn_logout"):
        st.session_state.logged_in = False
        st.session_state.saved_school = "All"
        st.session_state.username = ""
        st.session_state.logged_out_this_session = True
        st.session_state.logout_pending = True
        st.rerun()
    st.caption(f"Portal Version: v{__version__}")


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

@st.cache_data(ttl=3600)
def load_assessment_data():
    logging.info("📥 Fetching SITS assessment data from Google Sheets (Cache Miss)...")
    assessment_id = os.getenv("ASSESSMENT_SPREADSHEET_ID")
    if not assessment_id:
        logging.warning("⚠️ ASSESSMENT_SPREADSHEET_ID not configured in env.")
        return pd.DataFrame()
    from processing import get_assessment_data
    df_assess = get_assessment_data(assessment_id)
    logging.info(f"✅ SITS assessment data successfully loaded ({len(df_assess)} rows).")
    return df_assess

# Load the data
with st.spinner("Fetching data from Google Sheets..."):
    df_aut, df_spr = load_audit_data()
    checklist_sums = load_checklist_data()
    df_assess = load_assessment_data()

# Page Routing
view = st.session_state.view_selection

# Restrict admin/dla-only pages from unauthorized access
if view in ["💻 Developer Guide", "🤝 How to Contribute"] and st.session_state.username not in ["DLA", "ADMIN"]:
    st.session_state.view_selection = "🏛️ Faculty Overview"
    view = "🏛️ Faculty Overview"

if view == "🏛️ Faculty Overview":
    view_faculty_overview(df_aut, df_spr, checklist_sums, df_assess)
elif view == "🏫 School Dashboard":
    view_school_dashboard(df_aut, df_spr, checklist_sums, df_assess)
elif view == "📋 Module Report Card":
    view_module_report_card(df_aut, df_spr, checklist_sums, df_assess)
elif view == "✅ Module Lead Checklist":
    view_module_lead_checklist(df_aut, df_spr, load_checklist_data, df_assess)
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
