import pandas as pd
import numpy as np
import logging

# Schools that make up this faculty. Module codes are prefixed with these.
FACULTY_SCHOOLS = ["ALA", "ECN", "EDC", "GPL", "IJC", "MGT", "SPR"]

# Cut-offs for the School Comparison status badge. Placeholders until we have
# seen real faculty-wide data - retune here rather than in the view.
SCHOOL_STATUS_THRESHOLDS = {
    "ally": {"green": 75, "yellow": 50},
    "vle_compliance": {"green": 80, "yellow": 65},
}

def resolve_semester_df(df_aut, df_spr, semester):
    """
    Picks the DataFrame a view should render for the selected semester.

    Both semester frames already contain the All-year modules (app.py folds
    them into each), so "All year" is served by filtering one frame down to
    rows whose Semester is literally 'All year' - the year-long modules.

    Kept here rather than in the views so Faculty Overview and School
    Dashboard cannot drift apart on the same selection.
    """
    if semester == "Spring":
        return df_spr if df_spr is not None else pd.DataFrame()

    if semester == "All year":
        source = df_aut if df_aut is not None and not df_aut.empty else df_spr
        if source is None or source.empty or 'Semester' not in source.columns:
            return pd.DataFrame()
        return source[source['Semester'] == 'All year'].copy()

    return df_aut if df_aut is not None else pd.DataFrame()

def aggregate_faculty_stats(df_aut, df_spr):
    """
    Calculates summary statistics at the faculty level.
    """
    stats = {}
    
    # Example: Average Ally Score (using 25/26 All as the latest)
    col_name = 'Ally 25/26 All'
    
    if not df_aut.empty and col_name in df_aut.columns:
        stats['Autumn Avg Ally'] = df_aut[col_name].mean()
        stats['Autumn Module Count'] = len(df_aut)
        
    if not df_spr.empty and col_name in df_spr.columns:
        stats['Spring Avg Ally'] = df_spr[col_name].mean()
        stats['Spring Module Count'] = len(df_spr)
        
    return stats

def get_module_history(df_aut, df_spr, module_code):
    """
    Retrieves history for a single module across semesters.
    """
    # Try to find in Autumn
    aut_data = df_aut[df_aut['New module code'] == module_code] if not df_aut.empty else pd.DataFrame()
    spr_data = df_spr[df_spr['New module code'] == module_code] if not df_spr.empty else pd.DataFrame()
    
    return aut_data, spr_data

def get_module_mapping(df_aut, df_spr):
    """
    Returns a dictionary mapping module codes to module names.
    Combines data from both semesters.
    """
    mapping = {}
    
    for df in [df_aut, df_spr]:
        if not df.empty and 'New module code' in df.columns and 'Module name' in df.columns:
            # Drop rows with missing values for these columns
            temp_df = df.dropna(subset=['New module code', 'Module name'])
            for _, row in temp_df.iterrows():
                code = str(row['New module code']).strip()
                name = str(row['Module name']).strip()
                if code and name:
                    mapping[code] = name
                    
    return mapping

def is_compliant_val(val):
    """Normalizes and determines compliance for a single audit entry."""
    if pd.isna(val):
        return 0
    val_c = str(val).strip().lower()
    
    # Disqualifiers prioritize failure. If any of these are present, the item is non-compliant.
    negatives = [
        'missing', 'hidden', 'incomplete', 'empty', 'none', 
        'not edited', 'wrong place', 'not visible', 'not part of template',
        'no ' # matches 'no, yes' but safely leaves 'non-standard'
    ]
    
    if any(x in val_c for x in negatives) or val_c == 'no':
        return 0
        
    # Positive indicators - anything suggesting content or effort exists
    positives = [
        'yes', 'teaching', 'support', 'visible', 'present', 'complete', 
        'video', 'image', 'text', 'details & learning outcomes', 
        'manual', 'badging system'
    ]
    
    if any(x in val_c for x in positives):
        return 1
        
    return 0

def calculate_compliance_gap(df):
    """
    Calculates the percentage of 'Yes' (or positive indicators) for audit categories.
    """
    audit_cols = [
        'Welcome to your module message?', 
        'Key staff contacts complete?', 
        'Module outline complete?', 
        'How you will be assessed visible?',
        'Skills development (SGAs) visible?',
        'Accessibility statement visible?',
        'School handbook visible?',
        'Assessment overview - present and consistent with SITS',
        'Assessment support and guidance visible to students?',
        'University help and study support visible to students?'
    ]
    
    gaps = {}
    for col in audit_cols:
        if col in df.columns:
            # Apply logic to coerce messy text data into numeric 1s and 0s
            series_numeric = df[col].apply(is_compliant_val)
            positive_count = series_numeric.sum()
            total_count = len(df)
            gaps[col] = (positive_count / total_count) if total_count > 0 else 0

    return gaps

def calculate_module_compliance(df_responses, active_fields):
    """
    Counts compliant items per module from submitted audit responses.

    The per-module counterpart to calculate_dynamic_compliance_gap, which
    aggregates the same data per field. Kept I/O-free: callers pass in
    get_all_audit_responses() and get_active_audit_fields().

    Only boolean and yes/no fields are scored - text fields such as Additional
    Comments have no compliant/non-compliant state. Modules with no responses
    at all are absent from the result rather than scoring zero: an unaudited
    module is not a compliance gap, it is a missing audit, and belongs to the
    Missing Audits lens instead.

    Returns (DataFrame[module_code, Compliant Items], max_items).
    """
    scored = [f for f in (active_fields or []) if f.get('field_type') in ['boolean', 'yes/no']]
    max_items = len(scored)
    empty = pd.DataFrame(columns=['module_code', 'Compliant Items'])

    if max_items == 0 or df_responses is None or df_responses.empty:
        return empty, max_items

    field_ids = {f['id'] for f in scored}
    df = df_responses[df_responses['field_id'].isin(field_ids)].copy()
    if df.empty:
        return empty, max_items

    df['module_code'] = df['module_code'].astype(str).str.strip().str.upper()
    # Audit values are written as the strings 'True'/'False' by the Audit Portal.
    # is_compliant_val is for the free-text legacy columns and would read
    # 'False' as compliant, so match the strict set used by the field gap chart.
    df['compliant'] = df['value'].apply(lambda v: 1 if str(v).strip().upper() in ['TRUE', 'YES', '1'] else 0)

    counts = df.groupby('module_code')['compliant'].sum().reset_index()
    counts.columns = ['module_code', 'Compliant Items']
    return counts, max_items

def get_checklist_summaries(spreadsheet_id):
    """
    Fetches all checklist entries and returns a dictionary 
    mapping module codes to their latest audit status.
    """
    from data_manager import get_gspread_client
    import os
    client = get_gspread_client()
    try:
        spreadsheet = client.open_by_key(spreadsheet_id)
        worksheet = spreadsheet.worksheet("Sheet1")
        data = worksheet.get_all_values()
        if len(data) <= 1:
            return {}
        
        headers = data[0]
        summaries = {}
        # Iterate and keep the LATEST for each module (since they are in chronological order usually)
        for row in data[1:]:
            if len(row) > 1:
                m_code = row[1]
                q1 = row[3] == "TRUE"
                q2 = row[4] == "TRUE"
                q3 = row[5] == "TRUE"
                q4 = row[6] == "TRUE"
                
                q_states = [q1, q2, q3, q4]
                true_count = sum(q_states)
                
                if true_count == len(q_states):
                    status = "✅ Complete"
                elif true_count > 0:
                    status = "🟡 Partial"
                else:
                    status = "❌ Incomplete"

                summaries[m_code] = {
                    'Timestamp': row[0],
                    'Q1': q1,
                    'Q2': q2,
                    'Q3': q3,
                    'Q4': q4,
                    'Status': status,
                    'Comments': row[7] if len(row) > 7 else ""
                }
        return summaries
    except Exception as e:
        logging.error(f"❌ Error loading checklist summaries from Google Sheets: {e}")
        return {}

def get_updated_ally_scores(spreadsheet_id):
    """
    Fetches the updated Ally overall scores from the external Ally spreadsheet
    and returns a mapping dictionary of {clean_module_code: overall_score}.
    """
    from data_manager import get_spreadsheet_data
    try:
        ss, _ = get_spreadsheet_data(spreadsheet_id)
        sheet = ss.worksheet("Sheet1")
        data = sheet.get_all_values()
        if len(data) <= 1:
            return {}
            
        mapping = {}
        for row in data[1:]:
            if len(row) >= 8:
                # Extract clean module code, e.g., 'GPL439' from 'GPL439.A.279588'
                raw_code = str(row[1]).split('.')[0].strip().upper()
                
                # Parse total files (column index 4) and measured score (column index 7)
                files = pd.to_numeric(row[4], errors='coerce')
                if pd.isna(files) or files < 0:
                    files = 0
                    
                measured_score = pd.to_numeric(row[7], errors='coerce')
                
                if raw_code and not pd.isna(measured_score):
                    # Asymptotic Credibility Model (k=0.15, baseline=0.50)
                    credibility = 1.0 - np.exp(-0.15 * files)
                    weighted_score = credibility * measured_score + (1.0 - credibility) * 0.50
                    mapping[raw_code] = {
                        'measured': measured_score,
                        'weighted': weighted_score,
                        'files': int(files)
                    }
                    
        return mapping
    except Exception as e:
        import logging
        logging.error(f"❌ Error loading updated Ally data: {e}")
        return {}

def get_leganto_nolist_data(spreadsheet_id):
    """
    Fetches the Leganto 'no list' course codes from the external spreadsheet
    and returns a set of clean module codes.
    """
    from data_manager import get_spreadsheet_data
    try:
        ss, _ = get_spreadsheet_data(spreadsheet_id)
        # Assuming first worksheet based on inspect script
        sheet = ss.worksheets()[0] 
        data = sheet.get_all_values()
        if len(data) <= 1:
            return set()
            
        # Header row is index 0. Looking for 'Course Code' (usually index 2)
        headers = data[0]
        col_idx = -1
        for i, header in enumerate(headers):
            if 'Course Code' in str(header):
                col_idx = i
                break
        
        if col_idx == -1:
            # Fallback to expected index 2 if not found by name
            col_idx = 2
            
        no_list_codes = set()
        for row in data[1:]:
            if len(row) > col_idx:
                raw_code = str(row[col_idx]).split('.')[0].strip().upper()
                if raw_code:
                    no_list_codes.add(raw_code)
                    
        return no_list_codes
    except Exception as e:
        import logging
        logging.error(f"❌ Error loading Leganto No-List data: {e}")
        return set()

def get_assessment_data(spreadsheet_id):
    """
    Fetches the assessment data from the assessment spreadsheet
    and returns it as a pandas DataFrame.
    """
    from data_manager import get_spreadsheet_data
    try:
        ss, _ = get_spreadsheet_data(spreadsheet_id)
        sheet = ss.worksheet("All Schools 2025/26")
        data = sheet.get_all_values()
        if len(data) <= 1:
            return pd.DataFrame()
            
        headers = data[0]
        rows = data[1:]
        df = pd.DataFrame(rows, columns=headers)
        
        # Clean columns: trim whitespaces and convert code to uppercase
        if 'CIS unit code' in df.columns:
            df['CIS unit code'] = df['CIS unit code'].astype(str).str.strip().str.upper()
        if 'Module code' in df.columns:
            df['Module code'] = df['Module code'].astype(str).str.strip().str.upper()
            
        return df
    except Exception as e:
        import logging
        logging.error(f"❌ Error loading Assessment data: {e}")
        return pd.DataFrame()

def sanitize_row_data(row_data):
    """
    Defensively formats row data before writing back to Google Sheets.
    Casts all elements to strings, strips leading/trailing whitespaces,
    removes newlines, and prevents formula injection.
    """
    sanitized = []
    for item in row_data:
        if item is None or pd.isna(item):
            sanitized.append("")
            continue
            
        # Cast to string
        item_str = str(item).strip()
        
        # Prevent multiline breaking standard single-line cells
        item_str = item_str.replace('\n', ' ').replace('\r', ' ')
        
        # Prevent formula injection (unless it's an intended formula, but usually users don't write formulas from UI)
        if item_str.startswith('='):
            item_str = "'" + item_str
            
        sanitized.append(item_str)
        
    return sanitized

def calculate_dynamic_compliance_gap(school_code=None):
    """
    Calculates compliance gap metrics dynamically from active SQLite audit fields and responses.
    """
    from database import get_db_connection, get_active_audit_fields
    import pandas as pd
    
    active_fields = get_active_audit_fields()
    if not active_fields:
        return {}
        
    # We compute compliance only for boolean and yes/no audit fields
    boolean_fields = [f for f in active_fields if f['field_type'] in ['boolean', 'yes/no']]
    if not boolean_fields:
        return {}
        
    with get_db_connection() as conn:
        # Check if SITS and response tables exist
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='sits_assessment_2026_27'")
        if not cursor.fetchone():
            return {}
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='audit_responses'")
        if not cursor.fetchone():
            return {}
            
        # Get SITS unique modules
        df_sits = pd.read_sql_query("SELECT DISTINCT [CIS unit code] FROM sits_assessment_2026_27", conn)
        
        # Get active responses. Field IDs are passed as bound parameters - they
        # originate from audit_fields, which is writable via admin CSV import,
        # so they must never be interpolated into the SQL text.
        field_ids = [f['id'] for f in boolean_fields]
        placeholders = ','.join('?' * len(field_ids))
        df_resp = pd.read_sql_query(
            f"SELECT module_code, field_id, value FROM audit_responses WHERE field_id IN ({placeholders})",
            conn,
            params=field_ids,
        )
        
    if df_sits.empty:
        return {}
        
    df_sits['CIS unit code'] = df_sits['CIS unit code'].astype(str).str.strip().str.upper()
    
    # Filter modules by school if specified
    if school_code and school_code != 'All':
        df_sits = df_sits[df_sits['CIS unit code'].str.startswith(school_code, na=False)]
        
    total_modules = len(df_sits)
    if total_modules == 0:
        return {}
        
    # Calculate compliance gap for each field
    gaps = {}
    for field in boolean_fields:
        fid = field['id']
        label = field['label']
        
        # Filter responses for this field
        field_resps = df_resp[df_resp['field_id'] == fid].copy()
        field_resps['module_code'] = field_resps['module_code'].astype(str).str.strip().str.upper()
        
        # Keep only responses that correspond to our filtered modules list
        valid_codes = set(df_sits['CIS unit code'])
        field_resps = field_resps[field_resps['module_code'].isin(valid_codes)]
        
        # Count true/yes values
        compliant_count = field_resps['value'].apply(lambda x: str(x).upper() in ['TRUE', 'YES', '1']).sum()

        gaps[label] = float(compliant_count / total_modules)

    return gaps

def _status_band(value, thresholds):
    """Maps a percentage to a status band using the given green/yellow cut-offs."""
    if value is None or pd.isna(value):
        return None
    if value >= thresholds['green']:
        return 'green'
    if value >= thresholds['yellow']:
        return 'yellow'
    return 'red'

def get_school_comparison(active_df, checklist_sums):
    """
    Aggregates the active semester's modules by school for the Faculty
    School Comparison table.

    Works purely in pandas over data already held in memory - no per-school
    database queries. Note the deliberate difference from
    calculate_dynamic_compliance_gap: VLE compliance here is measured only
    across modules whose audit has been submitted, because an unaudited
    module tells us nothing about compliance. Audited coverage is returned
    alongside it so a high score off a tiny sample is visible for what it is.

    Returns (schools_df, totals) where schools_df has exactly one row per
    school - no totals row, so the table sorts cleanly and exports cleanly -
    and totals is a dict of the faculty-wide figures for display alongside it.
    VLE Compliance is None where a school has no submitted audits.
    """
    columns = ['School', 'Modules', 'Audited', 'Audited %', 'Avg Ally',
               'VLE Compliance', 'Status']
    empty_totals = {'Modules': 0, 'Audited': 0, 'Audited %': 0.0,
                    'Avg Ally': None, 'VLE Compliance': None}

    if active_df is None or active_df.empty or 'New module code' not in active_df.columns:
        return pd.DataFrame(columns=columns), empty_totals

    checklist_sums = checklist_sums or {}

    # Load the audit field definitions once, not per school.
    try:
        from database import get_active_audit_fields
        active_fields = get_active_audit_fields()
    except Exception as e:
        # Without field definitions every school reports no compliance, which
        # looks identical to "nobody has submitted yet" - so say so in the log.
        logging.error(f"❌ Could not load audit fields for school comparison: {e}")
        active_fields = []
    scored_field_ids = [f['id'] for f in active_fields
                        if f.get('field_type') in ('boolean', 'yes/no')]

    df = active_df.copy()
    df['School'] = df['New module code'].astype(str).str.strip().str.upper().str[:3]
    df = df[df['School'].isin(FACULTY_SCHOOLS)]

    if df.empty:
        return pd.DataFrame(columns=columns), empty_totals

    has_ally = 'Ally 25/26 All' in df.columns

    rows = []
    # Faculty totals are accumulated from the same per-module figures the
    # school rows use, so the total row can never drift from the rows above it.
    faculty_passed = faculty_scored = 0

    for school in FACULTY_SCHOOLS:
        school_df = df[df['School'] == school]
        module_count = len(school_df)
        if module_count == 0:
            continue

        codes = school_df['New module code'].astype(str).str.strip().str.upper()

        audited_count = 0
        passed = scored = 0
        for code in codes:
            summary = checklist_sums.get(code)
            if not summary or summary.get('Status') != "✅ Submitted":
                continue
            audited_count += 1

            responses = summary.get('Responses', {}) or {}
            for fid in scored_field_ids:
                scored += 1
                if str(responses.get(fid)).strip().upper() in ('TRUE', 'YES', '1'):
                    passed += 1

        faculty_passed += passed
        faculty_scored += scored

        avg_ally = None
        if has_ally:
            ally_mean = school_df['Ally 25/26 All'].mean()
            if pd.notna(ally_mean):
                avg_ally = float(ally_mean) * 100

        compliance = (passed / scored * 100) if scored else None
        audited_pct = (audited_count / module_count * 100) if module_count else 0.0

        bands = [_status_band(avg_ally, SCHOOL_STATUS_THRESHOLDS['ally']),
                 _status_band(compliance, SCHOOL_STATUS_THRESHOLDS['vle_compliance'])]
        bands = [b for b in bands if b is not None]
        if 'red' in bands:
            status = "❌ At Risk"
        elif 'yellow' in bands:
            status = "⚠️ Needs Support"
        elif bands:
            status = "✅ On Track"
        else:
            status = "— No Data"

        rows.append({
            'School': school,
            'Modules': module_count,
            'Audited': audited_count,
            'Audited %': audited_pct,
            'Avg Ally': avg_ally,
            'VLE Compliance': compliance,
            'Status': status,
        })

    if not rows:
        return pd.DataFrame(columns=columns), empty_totals

    result = pd.DataFrame(rows, columns=columns)

    total_modules = int(result['Modules'].sum())
    total_audited = int(result['Audited'].sum())
    faculty_ally = None
    if has_ally:
        ally_mean = df['Ally 25/26 All'].mean()
        if pd.notna(ally_mean):
            faculty_ally = float(ally_mean) * 100

    totals = {
        'Modules': total_modules,
        'Audited': total_audited,
        'Audited %': (total_audited / total_modules * 100) if total_modules else 0.0,
        'Avg Ally': faculty_ally,
        'VLE Compliance': (faculty_passed / faculty_scored * 100) if faculty_scored else None,
    }

    return result, totals
