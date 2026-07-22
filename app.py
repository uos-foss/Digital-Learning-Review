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

__version__ = "1.10.0"

# Import modularized views
from views.faculty_overview import view_faculty_overview
from views.school_dashboard import view_school_dashboard
from views.module_report_card import view_module_report_card
from views.module_lead_checklist import view_module_lead_checklist
from views.docs import view_help, view_changelog, view_developer_guide, view_contribute
from views.feedback import view_feedback
from views.admin_panel import view_admin_panel
from background_tasks import start_scheduler

# Start background sync daemon
start_scheduler()

# Page configuration
st.set_page_config(
    page_title="Digital Learning Review Dashboard",
    page_icon="📊",
    layout="wide"
)

# Custom CSS for Premium Design & Modern Typography (Outfit / Google Fonts)
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&display=swap');
    
    html, body, [class*="css"], .stApp {
        font-family: 'Outfit', sans-serif;
    }
    
    /* Make metric cards feel premium and card-like */
    div[data-testid="stMetric"] {
        background-color: rgba(120, 120, 120, 0.05);
        border: 1px solid rgba(120, 120, 120, 0.15);
        padding: 15px 20px;
        border-radius: 12px;
        box-shadow: 0 4px 8px rgba(0,0,0,0.02);
        transition: all 0.25s ease-in-out;
    }
    div[data-testid="stMetric"]:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 12px rgba(0,0,0,0.06);
        border-color: rgba(120, 120, 120, 0.25);
    }
    
    /* Soft border for containers and expanders */
    div[data-testid="stExpander"] {
        border-radius: 10px;
        border: 1px solid rgba(120, 120, 120, 0.15);
        box-shadow: 0 2px 4px rgba(0,0,0,0.01);
    }
    
    /* Styling headers */
    h1, h2, h3, h4, h5, h6 {
        font-family: 'Outfit', sans-serif !important;
        font-weight: 700 !important;
    }
    
    /* Style button transitions */
    button[data-testid="stBaseButton-secondary"] {
        transition: all 0.2s ease-in-out;
        border-radius: 8px;
    }
    button[data-testid="stBaseButton-secondary"]:hover {
        transform: translateY(-1px);
        box-shadow: 0 4px 8px rgba(0,0,0,0.05);
    }
    </style>
""", unsafe_allow_html=True)

from auth import check_password

# Secure Authentication & Session Persistence
if not check_password():
    st.stop()

# Load user capabilities list
user_caps = st.session_state.get("capabilities", [])
role = st.session_state.get("username", "USER")

# Determine accessible pages
can_view_faculty = any(c.lower() == "view faculty overview" for c in user_caps)
can_view_checklist = any(c.lower() in ["complete module checklist", "view module checklist"] for c in user_caps)
is_admin = role == "ADMIN"
is_dla_or_admin = role in ["DLA", "ADMIN"]

# Initialize session state variables
if "semester" not in st.session_state:
    st.session_state.semester = "Autumn"

def update_semester():
    st.session_state.semester = st.session_state.select_semester_widget


# Data Loading
@st.cache_data(ttl=3600)
def load_audit_data():
    logging.info("📥 Fetching VLE Review main audit data from local SQLite cache...")
    try:
        from database import get_db_connection
        with get_db_connection() as conn:
            df_aut = pd.read_sql_query("SELECT * FROM main_vle_audit_aut", conn)
            df_spr = pd.read_sql_query("SELECT * FROM main_vle_audit_spr", conn)
    except Exception as e:
        logging.error(f"Error reading from SQLite cache: {e}")
        df_aut, df_spr = pd.DataFrame(), pd.DataFrame()
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
    logging.info("📥 Fetching self-audit checklist data from SQLite cache...")
    try:
        from database import get_db_connection
        with get_db_connection() as conn:
            df = pd.read_sql_query("SELECT * FROM self_audit_checklist", conn)
            summaries = {}
            for _, row in df.iterrows():
                m_code = row['module_code']
                q1 = str(row['welcome_message']).upper() == "TRUE"
                q2 = str(row['contacts_complete']).upper() == "TRUE"
                q3 = str(row['outline_visible']).upper() == "TRUE"
                q4 = str(row['assessment_overview']).upper() == "TRUE"
                
                q_states = [q1, q2, q3, q4]
                true_count = sum(q_states)
                if true_count == len(q_states):
                    status = "✅ Complete"
                elif true_count > 0:
                    status = "🟡 Partial"
                else:
                    status = "❌ Incomplete"
                    
                summaries[m_code] = {
                    'Timestamp': row['timestamp'],
                    'Q1': q1, 'Q2': q2, 'Q3': q3, 'Q4': q4,
                    'Status': status,
                    'Comments': row['comments']
                }
            return summaries
    except Exception as e:
        logging.error(f"Error loading checklist from SQLite: {e}")
        return {}

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


# Page Wrapper Functions
def page_faculty_overview():
    view_faculty_overview(df_aut, df_spr, checklist_sums, df_assess)

def page_school_dashboard():
    view_school_dashboard(df_aut, df_spr, checklist_sums, df_assess)

def page_module_report_card():
    view_module_report_card(df_aut, df_spr, checklist_sums, df_assess)

def page_module_checklist():
    view_module_lead_checklist(df_aut, df_spr, load_checklist_data, df_assess)

def page_feedback():
    view_feedback()

def page_help():
    view_help()

def page_changelog():
    view_changelog()

def page_dev_guide():
    view_developer_guide()

def page_contribute():
    view_contribute()

def page_admin():
    view_admin_panel(df_aut, df_spr, checklist_sums, df_assess)

# Define st.Page objects
pg_faculty = st.Page(page_faculty_overview, title="Faculty Overview", icon=":material/account_balance:")
pg_school = st.Page(page_school_dashboard, title="School Dashboard", icon=":material/dashboard:")
pg_module = st.Page(page_module_report_card, title="Module Report Card", icon=":material/receipt_long:")
pg_checklist = st.Page(page_module_checklist, title="Module Checklist", icon=":material/fact_check:")

pg_feedback = st.Page(page_feedback, title="App Feedback", icon=":material/chat:")
pg_help = st.Page(page_help, title="Help & Support", icon=":material/lightbulb:")
pg_changelog = st.Page(page_changelog, title="Release Changelog", icon=":material/update:")

pg_dev = st.Page(page_dev_guide, title="Developer Guide", icon=":material/code:")
pg_contrib = st.Page(page_contribute, title="How to Contribute", icon=":material/handshake:")
pg_admin = st.Page(page_admin, title="Admin Panel", icon=":material/settings:")


# Build Navigation array for routing
pages_list = []
if can_view_faculty:
    pages_list.append(pg_faculty)
pages_list.append(pg_school)
pages_list.append(pg_module)
if can_view_checklist:
    pages_list.append(pg_checklist)

pages_list.extend([pg_feedback, pg_help, pg_changelog])

if is_dla_or_admin:
    pages_list.extend([pg_dev, pg_contrib])
if is_admin:
    pages_list.append(pg_admin)

nav = st.navigation(pages_list, position="hidden")

# --- CUSTOM SIDEBAR LAYOUT ---
with st.sidebar:
    st.title("FoSS Digital Learning Review Portal")
    
    # Semester Selector placed at the top (above main navigation)
    st.radio(
        "Select Semester", 
        ["Autumn", "Spring", "All year"], 
        key="select_semester_widget",
        index=["Autumn", "Spring", "All year"].index(st.session_state.semester) if st.session_state.semester in ["Autumn", "Spring", "All year"] else 0,
        on_change=update_semester,
        help="Active semester filter for school and module-level data."
    )
    
    st.divider()

    st.caption("Main")
    if can_view_faculty:
        st.page_link(pg_faculty)
    st.page_link(pg_school)
    st.page_link(pg_module)
    if can_view_checklist:
        st.page_link(pg_checklist)

    st.caption("Utilities")
    st.page_link(pg_feedback)
    st.page_link(pg_help)
    st.page_link(pg_changelog)

    if is_dla_or_admin or is_admin:
        st.caption("Admin/Developer")
        if is_dla_or_admin:
            st.page_link(pg_dev)
            st.page_link(pg_contrib)
        if is_admin:
            st.page_link(pg_admin)
            
    st.divider()
    
    def handle_logout():
        st.session_state.logged_in = False
        st.session_state.saved_school = "All"
        st.session_state.username = ""
        st.session_state.logged_out_this_session = True
        st.session_state.logout_pending = True

    st.button(f"Logout - {role}", on_click=handle_logout, use_container_width=True)
    st.caption(f"Portal Version: v{__version__}")

# Run navigation
nav.run()
