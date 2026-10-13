import streamlit as st
import pandas as pd
import logging

  
# Configure local text-file logging
logging.basicConfig(
    filename="app.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

__version__ = "1.34.1"

from processing import fmt_report_date, can_view_sga

# Import modularized views
from views.faculty_overview import view_faculty_overview
from views.school_dashboard import view_school_dashboard
from views.module_report import view_module_report
from views.docs import view_about, view_help, view_faq, view_changelog, view_developer_guide
from views.feedback import view_feedback
from views.admin_panel import view_admin_panel
from views.audit_portal import view_audit_portal
# background sync daemon is disabled as we moved to SQLite primary database
# from background_tasks import start_scheduler
# start_scheduler()

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

# Determine accessible pages based on capabilities
can_view_faculty = any(c.lower() == "view_all" for c in user_caps)
can_view_school_dashboard = any(c.lower() == "view_school_dashboard" for c in user_caps)
is_admin = any(c.lower() == "access_admin_panel" for c in user_caps)
has_limited_admin = any(c.lower() == "access_admin_limited" for c in user_caps)
is_dla_or_admin = any(c.lower() in ["edit_checklist", "access_admin_panel"] for c in user_caps)
can_audit = any(c.lower() == "edit_checklist" for c in user_caps)

# Initialize session state variables
if "semester" not in st.session_state:
    st.session_state.semester = "Autumn"

def update_semester():
    st.session_state.semester = st.session_state.select_semester_widget


# Data Loading
# table_exists now lives in database.py, so database.py can use it too. Kept
# importable from here because several modules already reference app.table_exists.
from database import table_exists, get_last_import_dates

@st.cache_data(ttl=300)
def load_last_import_dates():
    return get_last_import_dates()

# map_level_value and the module-row assembly now live in loaders.py, which
# has no Streamlit in it so tests, scripts and the web/ spike can call them.
# Kept importable from here because several modules reference app.map_level_value.
import loaders
from loaders import map_level_value  # noqa: F401 - re-exported

# ttl is a safety net, not the primary invalidation mechanism - every real
# write path (Admin Panel imports/edits, Audit Portal saves, spot-check
# flagging) already calls st.cache_data.clear() the moment it writes. A short
# ttl here just means every click more than a few seconds after the last one
# pays the full reload cost again for no freshness benefit - these three
# loaders do several SQL queries plus Ally/Leganto/readiness aggregation each
# time. 300s still catches an external change (e.g. a sibling app writing to
# the shared database) reasonably promptly.
@st.cache_data(ttl=300)
def load_audit_data():
    """
    (df_aut, df_spr, ally_courses, ally_issues, ally_content,
    readiness_sections, sga) for every module in the current academic year.

    The assembly itself is loaders.load_audit_frames(); this wrapper exists
    only to cache it. It was ~320 lines of inline query-and-map until
    05-10-2026, which meant nothing outside a running Streamlit script could
    build a module row - see loaders.py's docstring.

    The detail frames are returned, never written to st.session_state from in
    here: on a cache HIT the body does not run, and st.cache_data's cache is
    shared across every session, so whichever session caused the one real
    execution got those keys and every other session silently did not. The
    uncached call site assigns them on every rerun instead.
    """
    return loaders.load_audit_frames()

@st.cache_data(ttl=300)
def load_checklist_data():
    """
    Per-module audit status, plus 'Actionable Items' - the outstanding-item
    count shown as a badge on School Dashboard and Faculty Overview.

    The assembly is loaders.load_checklist_summaries(); this wrapper exists
    only to cache it. That count is produced by
    processing.derive_module_findings() from the same full module record the
    module report reads, so the badge, the module report page and the Django
    School Dashboard cannot disagree about what a module has outstanding.

    Until 12-10-2026 this built its own lean module row, with no SGA data, so
    the badge never counted a module the SGA tool lists with no attributes
    mapped ("Visible, no SGAs mapped") although the module report did: 153
    modules read one lower here than on their own page. The set of modules
    in the dictionary is unchanged - some pages count it or test membership.
    """
    logging.info("📥 Fetching dynamic audit checklist data from SQLite...")
    try:
        return loaders.load_checklist_summaries()
    except Exception as e:
        logging.error(f"Error loading checklist summaries from SQLite: {e}")
        return {}

@st.cache_data(ttl=300)
def load_assessment_data():
    logging.info("📥 Fetching SITS assessment data from SQLite...")
    try:
        from database import get_db_connection
        with get_db_connection() as conn:
            if table_exists(conn, "sits_assessment_2026_27"):
                df_assess = pd.read_sql_query("SELECT * FROM sits_assessment_2026_27", conn)
                if 'CIS unit code' in df_assess.columns:
                    df_assess['CIS unit code'] = df_assess['CIS unit code'].astype(str).str.strip().str.upper()
                if 'Module code' in df_assess.columns:
                    df_assess['Module code'] = df_assess['Module code'].astype(str).str.strip().str.upper()
                logging.info(f"✅ SITS assessment data successfully loaded ({len(df_assess)} rows).")
                return df_assess
            else:
                logging.warning("⚠️ sits_assessment_2026_27 table does not exist in SQLite.")
                return pd.DataFrame()
    except Exception as e:
        logging.error(f"Error reading SITS assessment data: {e}")
        return pd.DataFrame()

# Load the data
with st.spinner("Fetching data from SQLite database..."):
    (df_aut, df_spr, df_ally_courses, df_ally_issues,
     df_ally_content, df_readiness_sections, df_sga) = load_audit_data()
    # Assigned here, outside load_audit_data() itself, so every session gets
    # these every rerun regardless of whether that call was a cache hit or
    # miss - see the docstring on load_audit_data() for why that distinction
    # matters and what broke before this was moved out.
    st.session_state["df_ally_courses"] = df_ally_courses
    st.session_state["df_ally_issues"] = df_ally_issues
    st.session_state["df_ally_content"] = df_ally_content
    st.session_state["df_readiness_sections"] = df_readiness_sections
    st.session_state["df_sga"] = df_sga
    checklist_sums = load_checklist_data()
    df_assess = load_assessment_data()


# Page Wrapper Functions
def page_faculty_overview():
    view_faculty_overview(df_aut, df_spr, checklist_sums, df_assess)

def page_school_dashboard():
    # `freshness` is built in the sidebar block below, which runs before nav.run().
    view_school_dashboard(df_aut, df_spr, checklist_sums, df_assess, data_freshness=freshness)

def page_module_report():
    view_module_report(df_aut, df_spr, checklist_sums, df_assess, load_checklist_data)

def page_resources_and_support():
    tabs_list = ["💡 Help & Support", "❓ FAQs", "💬 App Feedback", "📋 Release Changelog"]
    if is_dla_or_admin:
        tabs_list.append("💻 Developer Guide")

    tabs = st.tabs(tabs_list)

    with tabs[0]:
        view_help()
    with tabs[1]:
        view_faq()
    with tabs[2]:
        view_feedback()
    with tabs[3]:
        view_changelog()

    if is_dla_or_admin:
        with tabs[4]:
            view_developer_guide()

def page_admin():
    view_admin_panel(df_aut, df_spr, checklist_sums, df_assess)

def page_audit_portal():
    view_audit_portal(df_aut, df_spr, checklist_sums, df_assess, load_checklist_data)

# Define st.Page objects
pg_about = st.Page(view_about, title="Welcome", icon=":material/home:")
pg_faculty = st.Page(page_faculty_overview, title="Faculty Overview", icon=":material/account_balance:")
pg_school = st.Page(page_school_dashboard, title="School Dashboard", icon=":material/dashboard:")
pg_module = st.Page(page_module_report, title="Module report", icon=":material/receipt_long:")
pg_audit = st.Page(page_audit_portal, title="Audit Portal", icon=":material/fact_check:")
pg_resources = st.Page(page_resources_and_support, title="Resources & Support", icon=":material/info:")
pg_admin = st.Page(page_admin, title="Admin Panel", icon=":material/settings:")

# Store page objects in session state for cross-page navigation
st.session_state.pg_module = pg_module
st.session_state.pg_audit = pg_audit
st.session_state.pg_school = pg_school

# Build Navigation array for routing
pages_list = [pg_about]
if can_view_faculty:
    pages_list.append(pg_faculty)
if can_view_school_dashboard:
    pages_list.append(pg_school)
pages_list.append(pg_module)
if can_audit:
    pages_list.append(pg_audit)
pages_list.append(pg_resources)

if is_admin or has_limited_admin:
    pages_list.append(pg_admin)

nav = st.navigation(pages_list, position="hidden")

# --- CUSTOM SIDEBAR LAYOUT ---
with st.sidebar:
    st.title("FoSS Digital Learning Review Portal")

    import_dates = load_last_import_dates()
    freshness_sources = [('sits', 'SITS'), ('bb', 'Blackboard Template Alignment'), ('ally', 'Ally'), ('leganto', 'Leganto')]
    if can_view_sga(user_caps):
        freshness_sources.append(('sga', 'SGAs'))
    freshness = ", ".join(
        f"{label} ({fmt_report_date(import_dates.get(key)) if import_dates.get(key) else 'no data'})"
        for key, label in freshness_sources
    )

    # Semester Selector placed at the top (above main navigation)
    st.radio(
        "Select Semester", 
        ["Autumn", "Spring", "All year"], 
        key="select_semester_widget",
        index=["Autumn", "Spring", "All year"].index(st.session_state.semester) if st.session_state.semester in ["Autumn", "Spring", "All year"] else 0,
        on_change=update_semester,
        help="Active semester filter for school and module-level data."
    )

    # Collapsed: the five import dates took a third of the sidebar on a
    # laptop screen, and are only wanted occasionally. One line per source
    # inside, so they read better than the old comma-joined caption.
    with st.expander("📅 Data last imported", expanded=False):
        for key, label in freshness_sources:
            stamp = fmt_report_date(import_dates.get(key)) if import_dates.get(key) else 'no data'
            st.caption(f"**{label}:** {stamp}")

    st.divider()

    st.caption("Main")
    st.page_link(pg_about)
    if can_view_faculty:
        st.page_link(pg_faculty)
    if can_view_school_dashboard:
        st.page_link(pg_school)
    st.page_link(pg_module)
    if can_audit:
        st.page_link(pg_audit)
    st.page_link(pg_resources)

    if is_admin or has_limited_admin:
        st.caption("Admin/Developer")
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
