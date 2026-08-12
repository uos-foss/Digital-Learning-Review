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

__version__ = "1.19.0"

from processing import CURRENT_ACADEMIC_YEAR

# Import modularized views
from views.faculty_overview import view_faculty_overview
from views.school_dashboard import view_school_dashboard
from views.module_report import view_module_report
from views.docs import view_help, view_changelog, view_developer_guide
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
is_admin = any(c.lower() == "access_admin_panel" for c in user_caps)
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
from database import table_exists

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
            
            # Load local Leganto and Blackboard links tables if they exist
            df_leganto_local = pd.read_sql_query("SELECT * FROM leganto_nolist", conn) if table_exists(conn, "leganto_nolist") else pd.DataFrame()
            df_blackboard_links = pd.read_sql_query(
                "SELECT * FROM blackboard_links WHERE academic_year = ?", conn,
                params=(CURRENT_ACADEMIC_YEAR,)) if table_exists(conn, "blackboard_links") else pd.DataFrame()

        # Ally comes from the institutional export, at Blackboard-course grain,
        # and is rolled up to modules here. The frames are stashed for the views
        # that need the detail behind the headline score.
        from database import get_ally_courses_latest, get_ally_issues_latest, get_ally_content_latest
        from processing import aggregate_ally_to_modules, count_ally_issues_by_module

        df_ally_courses = get_ally_courses_latest(CURRENT_ACADEMIC_YEAR)
        df_ally_issues = get_ally_issues_latest(CURRENT_ACADEMIC_YEAR)
        st.session_state["df_ally_courses"] = df_ally_courses
        st.session_state["df_ally_issues"] = df_ally_issues
        st.session_state["df_ally_content"] = get_ally_content_latest(CURRENT_ACADEMIC_YEAR)

        ally_modules = aggregate_ally_to_modules(df_ally_courses)
        ally_local_map = (ally_modules.set_index('module_code').to_dict(orient='index')
                          if not ally_modules.empty else {})
        issue_counts = count_ally_issues_by_module(df_ally_issues)
        ally_issue_map = (issue_counts.set_index('module_code').to_dict(orient='index')
                          if not issue_counts.empty else {})

        # Leganto reading-list status/items, for courses that DO have a list.
        # Separate from the leganto_nolist 'missing' flag below - a module
        # absent here (not in either export) keeps today's generic wording.
        from database import get_leganto_lists_latest
        from processing import aggregate_leganto_to_modules

        leganto_lists_modules = aggregate_leganto_to_modules(get_leganto_lists_latest(CURRENT_ACADEMIC_YEAR))
        leganto_lists_map = (leganto_lists_modules.set_index('module_code').to_dict(orient='index')
                             if not leganto_lists_modules.empty else {})

        # Module readiness, from the faculty Template Alignment Report. Same
        # shape as Ally: course-grain in the database, rolled up to modules
        # here, with the long section frame stashed for the detail view.
        from database import get_readiness_courses_latest, get_readiness_sections_latest
        from processing import aggregate_readiness_to_modules

        df_readiness_courses = get_readiness_courses_latest(CURRENT_ACADEMIC_YEAR)
        df_readiness_sections = get_readiness_sections_latest(CURRENT_ACADEMIC_YEAR)
        st.session_state["df_readiness_sections"] = df_readiness_sections

        readiness_modules = aggregate_readiness_to_modules(df_readiness_courses, df_readiness_sections)
        readiness_map = (readiness_modules.set_index('module_code').to_dict(orient='index')
                         if not readiness_modules.empty else {})

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
            
            # Ally, for this academic year only. There is deliberately no
            # fallback to the legacy audit tables here: those carry 2025-26
            # figures, and showing last year's accessibility against this
            # year's module list is how the old dashboard came to overstate
            # what had been measured.
            ally = ally_local_map.get(code, {})
            issue_counts_row = ally_issue_map.get(code, {})

            def _score(key):
                val = pd.to_numeric(ally.get(key), errors='coerce')
                return None if pd.isna(val) else float(val)

            overall_score = _score('overall_score')
            files_score = _score('files_score')
            wysiwyg_score = _score('wysiwyg_score')
            files_count = int(ally.get('total_files', 0) or 0)
            wysiwyg_count = int(ally.get('total_wysiwyg', 0) or 0)
            items_count = int(ally.get('total_items', 0) or 0)
            maturity = ally.get('content_maturity', "No data")

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

            # Reading-list status/items for modules that DO have a list. Blank
            # status means the module isn't in this export at all - not the
            # same as 'Leganto Missing' above, which is a separate, explicit
            # export of modules confirmed to have no list.
            leganto_list = leganto_lists_map.get(code, {})
            leganto_list_status = leganto_list.get('status', '')
            leganto_list_items = int(leganto_list.get('total_items', 0) or 0)

            # Template alignment. 'Lead Sections Ready' is the part that
            # discriminates: the vendor completeness score restates the visible
            # section count, and after a rollover almost every module sits on the
            # same one. Blank rather than zero where the module is absent from
            # the report, so "not measured" never reads as "nothing done".
            readiness = readiness_map.get(code, {})
            readiness_score = pd.to_numeric(readiness.get('completeness_score'), errors='coerce')
            lead_outstanding = readiness.get('lead_sections_outstanding') or []
            drafted_sections = readiness.get('drafted_sections') or []
            blocking = readiness.get('blocking_sections') or []

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
                # Ally's own three scores, unmodified. The credibility-weighted
                # 'Ally Weighted' this replaced was a local invention that
                # shrank small courses toward 50%, which on a rolled-over year
                # of template content moved the faculty mean by 30 points.
                'Ally Overall': overall_score,
                'Ally Files': files_score,
                'Ally WYSIWYG': wysiwyg_score,
                'Total Files': files_count,
                'Ally WYSIWYG Items': wysiwyg_count,
                'Ally Items': items_count,
                'Ally Students': int(ally.get('students', 0) or 0),
                'Ally Enabled': bool(ally.get('ally_enabled', 1)),
                'Ally Last Checked': ally.get('last_checked_on', ''),
                'Ally Shells': int(ally.get('shell_count', 0) or 0),
                'Content Maturity': maturity,
                'Ally Severe': int(issue_counts_row.get('severe', 0) or 0),
                'Ally Major': int(issue_counts_row.get('major', 0) or 0),
                'Ally Minor': int(issue_counts_row.get('minor', 0) or 0),

                # Transitional aliases for views not yet moved onto the names
                # above. 'Ally 25/26 All' in particular is a hardcoded year that
                # should not outlive this migration.
                'Ally Measured': files_score,
                'Ally Weighted': overall_score,
                'Ally 25/26 All': overall_score,
                'Leganto Missing': leganto_missing,
                'Leganto List Status': leganto_list_status,
                'Leganto List Items': leganto_list_items,

                'Template Completeness': None if pd.isna(readiness_score) else float(readiness_score),
                'Template Alignment Status': readiness.get('alignment_status', ''),
                'Template Sections Visible': int(readiness.get('visible_sections', 0) or 0),
                'Template Sections Expected': int(readiness.get('expected_sections', 0) or 0),
                'Lead Sections Ready': (None if not readiness
                                        else int(readiness.get('lead_sections_ready', 0) or 0)),
                'Lead Sections Total': int(readiness.get('lead_sections_total', 0) or 0),
                # Worked on but still hidden - counted apart from 'not started'
                # because the remedy is only to make it visible.
                'Lead Sections Drafted': int(readiness.get('lead_sections_drafted', 0) or 0),
                'Lead Sections Not Started': int(readiness.get('lead_sections_not_started', 0) or 0),
                'Lead Sections Outstanding': list(lead_outstanding),
                'Drafted Sections': list(drafted_sections),
                'Template Blocking': list(blocking),
                'Template Sections': readiness.get('section_states') or {},
                'Readiness Snapshot': readiness.get('snapshot_date', ''),

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
        from database import (get_db_connection, get_active_audit_fields, get_comment_bank,
                              get_ally_courses_latest, get_ally_issues_latest,
                              get_leganto_lists_latest, get_readiness_courses_latest,
                              get_readiness_sections_latest)
        from processing import (count_ally_issues_by_module, aggregate_leganto_to_modules,
                                aggregate_readiness_to_modules, derive_module_findings)

        active_fields = get_active_audit_fields()
        comment_bank = get_comment_bank()

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
        ally_severe_map, ally_enabled_map = {}, {}
        try:
            issues = count_ally_issues_by_module(get_ally_issues_latest(CURRENT_ACADEMIC_YEAR))
            if not issues.empty:
                ally_severe_map = dict(zip(issues['module_code'], issues['severe']))

            df_courses = get_ally_courses_latest(CURRENT_ACADEMIC_YEAR)
            if not df_courses.empty and 'ally_enabled' in df_courses.columns:
                # A module counts as disabled if any of its shells is - same
                # rule as aggregate_ally_to_modules().
                enabled = df_courses.groupby('module_code')['ally_enabled'].min()
                ally_enabled_map = {code: bool(v) for code, v in enabled.items()}
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
                'Ally Enabled': ally_enabled_map.get(code, True),
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
                active_fields if count_checklist else [], comment_bank)
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
                          | set(ally_severe_map) | set(ally_enabled_map) | set(readiness_map))
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
        tabs_list.append("💻 Developer Guide")

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
