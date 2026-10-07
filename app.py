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

__version__ = "1.33.1"

from processing import CURRENT_ACADEMIC_YEAR, fmt_report_date, can_view_sga

# Import modularized views
from views.faculty_overview import view_faculty_overview
from views.school_dashboard import view_school_dashboard
from views.module_report import view_module_report
from views.docs import view_about, view_help, view_faq, view_changelog, view_developer_guide
from views.feedback import view_feedback
from views.admin_panel import view_admin_panel
from views.audit_portal import view_audit_portal
from masquerade import is_masquerading, stop_masquerade, clear_masquerade_state
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

    That count is produced by processing.derive_module_findings(), the same
    function the module report page uses to build its own worklist and health
    banner, so the badge and the page can no longer disagree about what a
    module has outstanding. Previously each computed its own answer by hand:
    the badge never counted a Leganto list stuck in Draft, never counted
    template readiness at all, and undercounted legacy free-text custom
    observations the module report page showed as cards.
    """
    logging.info("📥 Fetching dynamic audit checklist data from SQLite...")
    try:
        from database import (get_db_connection, get_active_audit_fields,
                              get_ally_courses_latest, get_ally_issues_latest,
                              get_leganto_lists_latest, get_readiness_courses_latest,
                              get_readiness_sections_latest)
        from processing import (count_ally_issues_by_module, aggregate_leganto_to_modules,
                                aggregate_readiness_to_modules, aggregate_ally_to_modules,
                                derive_module_findings)

        active_fields = get_active_audit_fields()

        with get_db_connection() as conn:
            if not table_exists(conn, "audit_responses"):
                return {}
            df_resp = pd.read_sql_query("SELECT * FROM audit_responses", conn)

            df_leganto_nolist = (pd.read_sql_query("SELECT * FROM leganto_nolist", conn)
                                 if table_exists(conn, "leganto_nolist") else pd.DataFrame())
            leganto_missing_set = set()
            if not df_leganto_nolist.empty and 'module_code' in df_leganto_nolist.columns:
                leganto_missing_set = {str(code).strip().upper() for code in df_leganto_nolist['module_code']}

        # Leganto list status/items - draft lists were never reaching this
        # badge before, only the missing flag was.
        leganto_lists_map = {}
        try:
            llm = aggregate_leganto_to_modules(get_leganto_lists_latest(CURRENT_ACADEMIC_YEAR))
            if not llm.empty:
                leganto_lists_map = llm.set_index('module_code').to_dict(orient='index')
        except Exception as e:
            logging.warning(f"Could not load Leganto list status: {e}")

        # Ally severity counts and enabled/disabled, at module grain - matches
        # what the module report page's Ally card and 'Ally Severe'/'Ally
        # Enabled' columns already show, rather than a separate computation.
        ally_severe_map, ally_major_map, ally_enabled_map, ally_overall_map = {}, {}, {}, {}
        try:
            issues = count_ally_issues_by_module(get_ally_issues_latest(CURRENT_ACADEMIC_YEAR))
            if not issues.empty:
                ally_severe_map = dict(zip(issues['module_code'], issues['severe']))
                ally_major_map = dict(zip(issues['module_code'], issues['major']))

            df_courses = get_ally_courses_latest(CURRENT_ACADEMIC_YEAR)
            if not df_courses.empty and 'ally_enabled' in df_courses.columns:
                # A module counts as disabled if any of its shells is - same
                # rule as aggregate_ally_to_modules().
                enabled = df_courses.groupby('module_code')['ally_enabled'].min()
                ally_enabled_map = {code: bool(v) for code, v in enabled.items()}

            # Same module-grain weighted score the report/dashboard show, so
            # a severe-issue finding's description can quote the same number
            # rather than a locally re-derived one.
            ally_modules = aggregate_ally_to_modules(df_courses)
            if not ally_modules.empty:
                ally_overall_map = dict(zip(ally_modules['module_code'], ally_modules['overall_score']))
        except Exception as e:
            logging.warning(f"Could not derive Ally findings: {e}")

        # Template readiness - previously not reaching this badge at all.
        readiness_map = {}
        try:
            rc = get_readiness_courses_latest(CURRENT_ACADEMIC_YEAR)
            rs = get_readiness_sections_latest(CURRENT_ACADEMIC_YEAR)
            rm = aggregate_readiness_to_modules(rc, rs)
            if not rm.empty:
                readiness_map = rm.set_index('module_code').to_dict(orient='index')
        except Exception as e:
            logging.warning(f"Could not load readiness data: {e}")

        def module_row(code):
            """The subset of columns derive_module_findings() needs, in the
            same shape app.py's own module records use."""
            leg = leganto_lists_map.get(code, {})
            rd = readiness_map.get(code, {})
            return {
                'Leganto Missing': code in leganto_missing_set,
                'Leganto List Status': leg.get('status', ''),
                'Leganto List Items': leg.get('total_items', 0),
                'Ally Severe': ally_severe_map.get(code, 0),
                'Ally Major': ally_major_map.get(code, 0),
                'Ally Enabled': ally_enabled_map.get(code, True),
                'Ally Overall': ally_overall_map.get(code),
                'Template Sections': rd.get('section_states', {}),
            }

        def summarise(m_code, responses, timestamps, auditors, count_checklist):
            """One summary dict. count_checklist=False for modules with no
            audit_responses row at all, so a never-audited module's checklist
            fields do not suddenly count toward the badge the first time they
            are read - that has always been the badge's behaviour, and this
            refactor fixes concrete gaps (readiness, Leganto Draft, legacy
            free-text observations) without also changing that."""
            findings = derive_module_findings(
                module_row(m_code), responses,
                active_fields if count_checklist else [])
            pending = [f for f in findings if f['state'] == 'pending']

            audit_status = responses.get('audit_status', '')
            if audit_status == 'submitted':
                status = "✅ Submitted"
            elif audit_status == 'draft':
                status = "📝 Draft"
            else:
                status = "❌ Not Started"

            return {
                'Status': status,
                'Actionable Items': len(pending),
                'Derived Findings': [f['label'] for f in pending if f['source'] != 'checklist'],
                'Timestamp': max(timestamps) if timestamps else "Unknown" if count_checklist else "Never",
                'Auditor': (auditors[-1] if auditors else "Unknown") if count_checklist else "System",
                'Responses': responses,
                'Comments': responses.get('comments', ''),
            }

        if df_resp.empty:
            df_resp = pd.DataFrame(columns=['module_code', 'field_id', 'value', 'auditor_username', 'timestamp'])

        summaries = {}
        grouped = df_resp.groupby('module_code') if not df_resp.empty else []
        for m_code, group in grouped:
            m_code = str(m_code).strip().upper()
            responses, timestamps, auditors = {}, [], []
            for _, row in group.iterrows():
                responses[row['field_id']] = row['value']
                if row['timestamp']:
                    timestamps.append(row['timestamp'])
                if row['auditor_username']:
                    auditors.append(row['auditor_username'])
            summaries[m_code] = summarise(m_code, responses, timestamps, auditors, count_checklist=True)

        # Modules where the data alone has found something but nobody has
        # audited yet still need to appear, or the finding is invisible until
        # someone opens the module.
        external_codes = (leganto_missing_set | set(leganto_lists_map)
                          | set(ally_severe_map) | set(ally_major_map)
                          | set(ally_enabled_map) | set(readiness_map))
        for m_code in external_codes:
            if m_code in summaries:
                continue
            entry = summarise(m_code, {}, [], [], count_checklist=False)
            if entry['Actionable Items'] > 0:
                summaries[m_code] = entry

        return summaries
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

    if is_masquerading():
        st.warning(
            f"🎭 Viewing as **{st.session_state.username}** "
            f"({st.session_state.user_role}, {st.session_state.saved_school}) — "
            f"changes are disabled.",
            icon="🎭"
        )
        if st.button("↩️ Return to my account", key="exit_masquerade_btn", use_container_width=True):
            stop_masquerade()
        st.divider()

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
        clear_masquerade_state()
        st.session_state.logged_in = False
        st.session_state.saved_school = "All"
        st.session_state.username = ""
        st.session_state.logged_out_this_session = True
        st.session_state.logout_pending = True

    st.button(f"Logout - {role}", on_click=handle_logout, use_container_width=True)
    st.caption(f"Portal Version: v{__version__}")

# Run navigation
nav.run()
