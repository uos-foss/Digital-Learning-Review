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

__version__ = "1.15.0"

# Import modularized views
from views.faculty_overview import view_faculty_overview
from views.school_dashboard import view_school_dashboard
from views.module_report import view_module_report
from views.docs import view_help, view_changelog, view_developer_guide, view_contribute
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
is_admin = any(c.lower() == "access_admin_panel" for c in user_caps)
is_dla_or_admin = any(c.lower() in ["edit_checklist", "access_admin_panel"] for c in user_caps)
can_audit = any(c.lower() == "edit_checklist" for c in user_caps)

# Initialize session state variables
if "semester" not in st.session_state:
    st.session_state.semester = "Autumn"

def update_semester():
    st.session_state.semester = st.session_state.select_semester_widget


# Data Loading
def table_exists(conn, table_name):
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
    return cursor.fetchone() is not None

def map_level_value(val):
    if pd.isna(val):
        return ''
    s = str(val).strip()
    if s.lower() in ('nan', 'none', ''):
        return ''
    level_map = {
        'F': 'Foundation',
        '4': 'UG Level 1',
        '5': 'UG Level 2',
        '6': 'UG Level 3',
        '7': 'PGT',
        '8': 'PGR'
    }
    return level_map.get(s.upper(), s)

@st.cache_data(ttl=10)
def load_audit_data():
    logging.info("📥 Constructing module list from SITS as single source of truth...")
    try:
        from database import get_db_connection
        with get_db_connection() as conn:
            # Check if sits_assessment_2026_27 table exists in SQLite
            if not table_exists(conn, "sits_assessment_2026_27"):
                logging.warning("⚠️ sits_assessment_2026_27 table not found in database. Falling back to legacy tables.")
                df_aut = pd.read_sql_query("SELECT * FROM main_vle_audit_aut", conn) if table_exists(conn, "main_vle_audit_aut") else pd.DataFrame()
                df_spr = pd.read_sql_query("SELECT * FROM main_vle_audit_spr", conn) if table_exists(conn, "main_vle_audit_spr") else pd.DataFrame()
                for df in [df_aut, df_spr]:
                    if not df.empty and 'UG/ PG/ Other' in df.columns:
                        df['UG/ PG/ Other'] = df['UG/ PG/ Other'].map(map_level_value)
                return df_aut, df_spr

            df_sits = pd.read_sql_query("SELECT * FROM sits_assessment_2026_27", conn)
            
            # Load legacy reference tables if they exist
            legacy_aut = pd.read_sql_query("SELECT * FROM main_vle_audit_aut", conn) if table_exists(conn, "main_vle_audit_aut") else pd.DataFrame()
            legacy_spr = pd.read_sql_query("SELECT * FROM main_vle_audit_spr", conn) if table_exists(conn, "main_vle_audit_spr") else pd.DataFrame()
            
            # Load local Ally, Leganto, and Blackboard links tables if they exist
            df_ally_local = pd.read_sql_query("SELECT * FROM ally_scores", conn) if table_exists(conn, "ally_scores") else pd.DataFrame()
            st.session_state["df_ally_local"] = df_ally_local
            df_leganto_local = pd.read_sql_query("SELECT * FROM leganto_nolist", conn) if table_exists(conn, "leganto_nolist") else pd.DataFrame()
            df_blackboard_links = pd.read_sql_query("SELECT * FROM blackboard_links WHERE academic_year = '2026-27'", conn) if table_exists(conn, "blackboard_links") else pd.DataFrame()

        # Combine legacy tables to build reference lookups
        legacy_dfs = [df for df in [legacy_aut, legacy_spr] if not df.empty]
        if legacy_dfs:
            legacy_combined = pd.concat(legacy_dfs, ignore_index=True)
            if 'New module code' in legacy_combined.columns:
                legacy_combined['New module code'] = legacy_combined['New module code'].astype(str).str.strip().str.upper()
                legacy_combined = legacy_combined.drop_duplicates(subset=['New module code'])
                ref_lookup = legacy_combined.set_index('New module code').to_dict(orient='index')
            else:
                ref_lookup = {}
        else:
            ref_lookup = {}

        # Local Ally lookup
        ally_local_map = {}
        if not df_ally_local.empty and 'module_code' in df_ally_local.columns:
            df_ally_local['module_code'] = df_ally_local['module_code'].astype(str).str.strip().str.upper()
            if 'snapshot_date' in df_ally_local.columns:
                latest_ally = df_ally_local.sort_values('snapshot_date').groupby('module_code').tail(1)
            else:
                latest_ally = df_ally_local
            for _, row in latest_ally.iterrows():
                ally_local_map[row['module_code']] = {
                    'measured': row.get('measured', None),
                    'weighted': row.get('weighted', None),
                    'files': row.get('files', 0)
                }

        # Local Leganto set
        leganto_local_set = set()
        if not df_leganto_local.empty and 'module_code' in df_leganto_local.columns:
            leganto_local_set = set(df_leganto_local['module_code'].astype(str).str.strip().str.upper())

        # Local Blackboard links lookup
        blackboard_links_map = {}
        if not df_blackboard_links.empty and 'module_code' in df_blackboard_links.columns:
            df_blackboard_links['module_code'] = df_blackboard_links['module_code'].astype(str).str.strip().str.upper()
            for _, row in df_blackboard_links.iterrows():
                blackboard_links_map[row['module_code']] = row['blackboard_link']

        # Extract unique modules from SITS
        if df_sits.empty or 'CIS unit code' not in df_sits.columns:
            logging.warning("⚠️ sits_assessment_2026_27 is empty or missing 'CIS unit code' column.")
            return pd.DataFrame(), pd.DataFrame()
            
        df_sits['CIS unit code'] = df_sits['CIS unit code'].astype(str).str.strip().str.upper()
        unique_modules = df_sits.drop_duplicates(subset=['CIS unit code']).copy()

        # Build the final records
        records = []
        for _, row in unique_modules.iterrows():
            code = row['CIS unit code']
            name = row.get('Module name', '')
            lead = row.get('Academic contact', '')
            level = map_level_value(row.get('Module level', ''))
            period = str(row.get('Period', '')).strip().upper()
            
            # Map period to semester
            if period in ['S1', 'ED1', 'N19', 'N21', 'ISS1']:
                semester = 'Autumn'
            elif period in ['S2', 'ED2', 'N27', 'N28', 'MDE2']:
                semester = 'Spring'
            elif period in ['AY', 'FY', 'TRI', 'X4']:
                semester = 'All year'
            else:
                # Default to Spring for unmapped periods
                semester = 'Spring'
                
            # Retrieve legacy reference fields if they exist
            ref_fields = ref_lookup.get(code, {})
            
            # Get Ally scores (prefer local ally_scores table, fallback to legacy)
            measured_score = None
            weighted_score = None
            files_count = 0
            
            if code in ally_local_map:
                measured_score = ally_local_map[code]['measured']
                weighted_score = ally_local_map[code]['weighted']
                files_count = ally_local_map[code]['files']
            else:
                # Fallback to legacy audit row
                measured_score = ref_fields.get('Ally Measured', ref_fields.get('Ally 25/26 All', None))
                weighted_score = ref_fields.get('Ally Weighted', ref_fields.get('Ally 25/26 All', None))
                files_count = ref_fields.get('Total Files', ref_fields.get('Ally 25/26 Files', 0))

            # Cast / fallback values
            measured_score = pd.to_numeric(measured_score, errors='coerce')
            weighted_score = pd.to_numeric(weighted_score, errors='coerce')
            files_count = pd.to_numeric(files_count, errors='coerce')
            if pd.isna(measured_score): measured_score = None
            if pd.isna(weighted_score): weighted_score = None
            if pd.isna(files_count): files_count = 0

            # Get Leganto Status (prefer local leganto_nolist table, fallback to legacy)
            if df_leganto_local.empty:
                leganto_missing = ref_fields.get('Leganto Missing', False)
                # handle potential string representation
                if str(leganto_missing).upper() in ['TRUE', '1']:
                    leganto_missing = True
                elif str(leganto_missing).upper() in ['FALSE', '0', '']:
                    leganto_missing = False
            else:
                leganto_missing = code in leganto_local_set

            # Get Blackboard URL (prefer blackboard_links table, fallback to legacy)
            blackboard_url = blackboard_links_map.get(code, ref_fields.get('URL', ''))

            record = {
                'New module code': code,
                'Module name': name,
                'Mod. lead': lead,
                'Prog. lead': ref_fields.get('Prog. lead', ''),
                'UG/ PG/ Other': level,
                'URL': blackboard_url,
                'Semester': semester,
                'Ally Measured': measured_score,
                'Ally Weighted': weighted_score,
                'Ally 25/26 All': weighted_score if weighted_score is not None else measured_score,
                'Total Files': files_count,
                'Ally Shift': (weighted_score - measured_score) if (weighted_score is not None and measured_score is not None) else 0.0,
                'Leganto Missing': leganto_missing,
                
                # Include other legacy audit columns as reference
                'Available to students?': ref_fields.get('Available to students?', ''),
                'Draft': ref_fields.get('Draft', ''),
                'Published': ref_fields.get('Published', ''),
                'Encore linked and visible': ref_fields.get('Encore linked and visible', ''),
                'Learning materials structure in place': ref_fields.get('Learning materials structure in place', ''),
                'Welcome to your module message?': ref_fields.get('Welcome to your module message?', ''),
                'Key staff contacts complete?': ref_fields.get('Key staff contacts complete?', ''),
                'Module outline complete?': ref_fields.get('Module outline complete?', ''),
                'How you will be assessed visible?': ref_fields.get('How you will be assessed visible?', ''),
                'Skills development (SGAs) visible?': ref_fields.get('Skills development (SGAs) visible?', ''),
                'Accessibility statement visible?': ref_fields.get('Accessibility statement visible?', ''),
                'School handbook visible?': ref_fields.get('School handbook visible?', ''),
                'Assessment overview - present and consistent with SITS': ref_fields.get('Assessment overview - present and consistent with SITS', ''),
                'Assessment support and guidance visible to students?': ref_fields.get('Assessment support and guidance visible to students?', ''),
                'University help and study support visible to students?': ref_fields.get('University help and study support visible to students?', ''),
                'Comments': ref_fields.get('Comments', '')
            }
            records.append(record)

        df_all = pd.DataFrame(records)
        
        # Partition
        df_aut = df_all[df_all['Semester'] == 'Autumn'].copy()
        df_spr = df_all[df_all['Semester'] == 'Spring'].copy()
        df_all_year = df_all[df_all['Semester'] == 'All year'].copy()

        # All year modules run in both semesters, so include them in both lists
        aut_dfs = [df_aut, df_all_year] if not df_all_year.empty else [df_aut]
        spr_dfs = [df_spr, df_all_year] if not df_all_year.empty else [df_spr]

        # Only concat if we have dataframes to concat
        aut_dfs = [d for d in aut_dfs if not d.empty]
        spr_dfs = [d for d in spr_dfs if not d.empty]

        df_aut = pd.concat(aut_dfs, ignore_index=True) if aut_dfs else pd.DataFrame()
        df_spr = pd.concat(spr_dfs, ignore_index=True) if spr_dfs else pd.DataFrame()

        # Filter out inactive modules
        try:
            with get_db_connection() as conn:
                inactive_df = pd.read_sql_query("SELECT module_code FROM inactive_modules", conn) if table_exists(conn, "inactive_modules") else pd.DataFrame()
            if not inactive_df.empty:
                inactive_codes = set(inactive_df['module_code'].str.strip().str.upper())
                df_aut = df_aut[~df_aut['New module code'].isin(inactive_codes)].copy()
                df_spr = df_spr[~df_spr['New module code'].isin(inactive_codes)].copy()
                logging.info(f"Filtered out {len(inactive_codes)} inactive modules.")
        except Exception as e:
            logging.warning(f"Could not filter inactive modules: {e}")

        logging.info(f"✅ Successfully compiled SITS module list (Autumn: {len(df_aut)}, Spring: {len(df_spr)}).")
        return df_aut, df_spr
    except Exception as e:
        logging.error(f"Error loading SITS audit data: {e}")
        return pd.DataFrame(), pd.DataFrame()

@st.cache_data(ttl=10)
def load_checklist_data():
    logging.info("📥 Fetching dynamic audit checklist data from SQLite...")
    try:
        from database import get_db_connection, get_active_audit_fields, get_comment_bank, parse_custom_observations
        active_fields = get_active_audit_fields()
        active_field_ids = {f['id'] for f in active_fields}
        comment_bank = get_comment_bank()
        compliant_tag_ids = {c['id'] for c in comment_bank if "Compliant" in c.get('category', '') or "No action needed" in c.get('advice', '')}
        
        with get_db_connection() as conn:
            if not table_exists(conn, "audit_responses"):
                return {}
            df_resp = pd.read_sql_query("SELECT * FROM audit_responses", conn)
            
            # Fetch Leganto missing status from leganto_nolist table
            df_leganto = pd.read_sql_query("SELECT * FROM leganto_nolist", conn) if table_exists(conn, "leganto_nolist") else pd.DataFrame()
            leganto_missing_set = set()
            if not df_leganto.empty and 'module_code' in df_leganto.columns:
                leganto_missing_set = {str(code).strip().upper() for code in df_leganto['module_code']}
            
        if df_resp.empty:
            df_resp = pd.DataFrame(columns=['module_code', 'field_id', 'value', 'auditor_username', 'timestamp'])
            
        summaries = {}
        grouped = df_resp.groupby('module_code') if not df_resp.empty else []
        for m_code, group in grouped:
            m_code = str(m_code).strip().upper()
            responses = {}
            timestamps = []
            auditors = []
            
            for _, row in group.iterrows():
                fid = row['field_id']
                val = row['value']
                responses[fid] = val
                if row['timestamp']:
                    timestamps.append(row['timestamp'])
                if row['auditor_username']:
                    auditors.append(row['auditor_username'])
                    
            import json
            active_field_types = {f['id']: f['field_type'] for f in active_fields}
            
            actionable_items = 0
            for fid in active_field_ids:
                ftype = active_field_types.get(fid)
                val = responses.get(fid)
                if ftype == 'boolean':
                    if str(val).upper() != 'TRUE':
                        actionable_items += 1
                elif ftype == 'yes/no':
                    if str(val).upper() != 'YES':
                        actionable_items += 1
                elif ftype == 'text' and val:
                    try:
                        data = json.loads(val)
                        if isinstance(data, dict):
                            tags = data.get("tags", [])
                            actionable_items += len([t for t in tags if t not in compliant_tag_ids])
                            custom_list = parse_custom_observations(data.get("custom", ""))
                            actionable_items += len(custom_list)
                    except Exception:
                        pass
                        
            # Incorporate Leganto missing status
            if m_code in leganto_missing_set:
                actionable_items += 1
                        
            audit_status = responses.get('audit_status', '')
            if audit_status == 'submitted':
                status = "✅ Submitted"
            elif audit_status == 'draft':
                status = "📝 Draft"
            else:
                status = "❌ Not Started"
                
            latest_ts = max(timestamps) if timestamps else "Unknown"
            latest_auditor = auditors[-1] if auditors else "Unknown"
            
            # Pack fields for the display
            summaries[m_code] = {
                'Status': status,
                'Actionable Items': actionable_items,
                'Timestamp': latest_ts,
                'Auditor': latest_auditor,
                'Responses': responses,
                'Comments': responses.get('comments', '')
            }
            
        # Ensure modules with missing Leganto but no checklist responses are included
        for m_code in leganto_missing_set:
            if m_code not in summaries:
                summaries[m_code] = {
                    'Status': "❌ Not Started",
                    'Actionable Items': 1,
                    'Timestamp': "Never",
                    'Auditor': "System",
                    'Responses': {},
                    'Comments': ''
                }
                
        return summaries
    except Exception as e:
        logging.error(f"Error loading checklist summaries from SQLite: {e}")
        return {}

@st.cache_data(ttl=10)
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
    df_aut, df_spr = load_audit_data()
    checklist_sums = load_checklist_data()
    df_assess = load_assessment_data()


# Page Wrapper Functions
def page_faculty_overview():
    view_faculty_overview(df_aut, df_spr, checklist_sums, df_assess)

def page_school_dashboard():
    view_school_dashboard(df_aut, df_spr, checklist_sums, df_assess)

def page_module_report():
    view_module_report(df_aut, df_spr, checklist_sums, df_assess, load_checklist_data)

def page_resources_and_support():
    tabs_list = ["💡 Help & Support", "💬 App Feedback", "📋 Release Changelog"]
    if is_dla_or_admin:
        tabs_list.extend(["💻 Developer Guide", "🤝 How to Contribute"])
        
    tabs = st.tabs(tabs_list)
    
    with tabs[0]:
        view_help()
    with tabs[1]:
        view_feedback()
    with tabs[2]:
        view_changelog()
        
    if is_dla_or_admin:
        with tabs[3]:
            view_developer_guide()
        with tabs[4]:
            view_contribute()

def page_admin():
    view_admin_panel(df_aut, df_spr, checklist_sums, df_assess)

def page_audit_portal():
    view_audit_portal(df_aut, df_spr, checklist_sums, df_assess)

# Define st.Page objects
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
pages_list = []
if can_view_faculty:
    pages_list.append(pg_faculty)
pages_list.append(pg_school)
pages_list.append(pg_module)
if can_audit:
    pages_list.append(pg_audit)
pages_list.append(pg_resources)

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
    if can_audit:
        st.page_link(pg_audit)
    st.page_link(pg_resources)

    if is_admin:
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
