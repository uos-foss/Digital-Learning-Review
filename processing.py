import pandas as pd
import logging
import re
import json

# Schools that make up this faculty. Module codes are prefixed with these.
FACULTY_SCHOOLS = ["ALA", "ECN", "EDC", "GPL", "IJC", "MGT", "SPR"]

# The year the portal is reporting on. Ally holds every year Blackboard has
# ever had, so reads have to say which one they want. Bump this at rollover,
# alongside the sits_assessment_* table name.
CURRENT_ACADEMIC_YEAR = "2026-27"

# Cut-offs for the School Comparison status badge. Placeholders until we have
# seen real faculty-wide data - retune here rather than in the view.
#
# The 2026-27 Ally data cannot calibrate the 'ally' band yet: with most courses
# still holding their rollover template, built ones average around 99% and every
# school lands green regardless of where the cut sits. Retune once the year has
# been authored - on the last fully taught year the schools spanned 82-93%
# overall, so 75/50 would still have separated nothing. Files score and issues
# per module discriminate far better and are the better basis when we do.
SCHOOL_STATUS_THRESHOLDS = {
    "ally": {"green": 75, "yellow": 50},
    "vle_compliance": {"green": 80, "yellow": 65},
}

# --- Ally institutional report -------------------------------------------

# Ally suffixes each issue column with a severity: Foo:1 severe, Foo:2 major,
# Foo:3 minor. LibraryReference carries no suffix - it flags library-sourced
# content rather than a defect, so it is stored but never counted as an issue.
ALLY_SEVERITY_LABELS = {1: "Severe", 2: "Major", 3: "Minor"}

# Where a problem actually gets fixed, which is what an auditor needs to know
# before advising anyone:
#   editor - the module lead fixes it in the Blackboard content editor, minutes
#   image  - answerable in the browser via Ally instructor feedback
#   file   - the source document must be re-authored and re-uploaded
ALLY_CHECKS = {
    # Severe
    "Parsable":      ("Document cannot be read by assistive technology", "file",
                      "The file is corrupt or unreadable. Re-export it from the source application and re-upload."),
    "Scanned":       ("Scanned image of text, with no real text layer", "file",
                      "A screen reader sees a picture, not words. Re-create from the original document, or run OCR."),
    "Security":      ("Document security settings block screen readers", "file",
                      "Remove the copy/extract restrictions in the PDF and re-upload."),
    "ImageSeizure":  ("Image may trigger seizures", "image",
                      "Flashing or rapidly striped image. Remove or replace it."),
    # Major
    "Tagged":        ("PDF is not tagged for reading order", "file",
                      "Export to PDF from Word or PowerPoint with 'Document structure tags' enabled, rather than printing to PDF."),
    "AlternativeText": ("Images in the document have no alternative text", "file",
                        "Add alt text to each image in the source document and re-upload."),
    "Contrast":      ("Text contrast is too low to read comfortably", "file",
                      "Darken text or lighten backgrounds in the source document to at least 4.5:1."),
    "TableHeaders":  ("Tables have no header row", "file",
                      "Mark the top row as a header row in the source document so screen readers can announce columns."),
    "HeadingsPresence": ("Document has no headings", "file",
                         "Apply real heading styles in the source document rather than bold or large text."),
    "Ocred":         ("Scanned document has been OCRed but not checked", "file",
                      "Review the OCR output for accuracy, or re-create the document from its original source."),
    "ImageContrast": ("Image contrast is too low", "image",
                      "Replace with a higher-contrast version."),
    "ImageDescription": ("Image has no description", "image",
                         "Add a description via Ally's instructor feedback, or mark it decorative."),
    "ImageDecorative": ("Image not marked decorative or described", "image",
                        "Decide whether the image carries meaning; describe it or mark it decorative."),
    "HtmlImageAlt":  ("Image on a page has no alt text", "editor",
                      "Edit the page and add alternative text to the image."),
    "HtmlObjectAlt": ("Embedded object has no alternative text", "editor",
                      "Add a text alternative, or a link to an accessible version."),
    "HtmlHeadingsPresence": ("Page has no headings", "editor",
                             "Use the editor's heading styles to structure the page."),
    "HtmlHeadingsStart": ("Page headings do not start at the top level", "editor",
                          "Start the page with a Heading 1 and work down."),
    "HtmlEmptyHeading": ("Page has an empty heading", "editor",
                         "Remove the empty heading or give it text."),
    "HtmlColorContrast": ("Text contrast on the page is too low", "editor",
                          "Use the default text colours rather than custom light ones."),
    "HtmlBrokenLink": ("Page contains a broken link", "editor",
                       "Update or remove the link."),
    "HtmlCaption":   ("Video on the page has no captions", "editor",
                      "Add captions, or link to a captioned copy."),
    "HtmlLabel":     ("Form field on the page has no label", "editor",
                      "Give each field a visible label."),
    "HtmlTdHasHeader": ("Table cells are not associated with headers", "editor",
                        "Rebuild the table with a proper header row."),
    "HtmlEmptyTableHeader": ("Table has an empty header cell", "editor",
                             "Give every header cell text."),
    # Minor
    "Title":         ("Document has no title", "file",
                      "Set the document title in the source file's properties."),
    "LanguagePresence": ("Document language is not set", "file",
                         "Set the document language in the source application so screen readers use the right voice."),
    "LanguageCorrect": ("Document language looks wrong", "file",
                        "Correct the language setting in the source document."),
    "HeadingsSequential": ("Heading levels skip a level", "file",
                           "Use headings in order without jumping from H1 to H3."),
    "HeadingsStartAtOne": ("Headings do not start at level 1", "file",
                           "Begin the document with a level 1 heading."),
    "HeadingsHigherLevel": ("A heading sits above the document's top level", "file",
                            "Reorder the heading levels so the document starts at level 1."),
    "ImageOcr":      ("Image contains text that has not been OCRed", "image",
                      "Provide the text in the page, or describe the image."),
    "HtmlTitle":     ("Page has no title", "editor", "Give the page a descriptive title."),
    "HtmlHasLang":   ("Page language is not set", "editor", "Set the page language."),
    "HtmlHeadingOrder": ("Page heading levels skip a level", "editor",
                         "Use headings in order without skipping levels."),
    "HtmlList":      ("List is not marked up as a list", "editor",
                      "Use the editor's bullet or number list buttons rather than typing dashes."),
    "HtmlDefinitionList": ("Definition list is malformed", "editor",
                           "Rebuild the list using the editor's list tools."),
    "HtmlLinkName":  ("Link text does not say where it goes", "editor",
                      "Replace 'click here' with text describing the destination."),
    "HtmlImageRedundantAlt": ("Alt text repeats nearby text", "editor",
                              "Shorten or remove the duplicated alt text."),
    # Not a defect
    "LibraryReference": ("Library-sourced content", "file",
                         "Informational only - content supplied by the Library."),
}

def ally_term_to_academic_year(term_name):
    """'Academic Year 2026-2027' -> '2026-27'. Returns '' if unparseable."""
    m = re.search(r'(\d{4})\s*[-~/]\s*(\d{2,4})', str(term_name))
    if not m:
        return ""
    start, end = m.group(1), m.group(2)
    return f"{start}-{end[-2:]}"

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

def parse_user_schools(school_value):
    """
    A user's stored School value (users.School), resolved into a list of
    codes. Most accounts hold exactly one code or the "All" sentinel, but
    some DLAs and occasionally an ML are genuinely aligned with more than one
    school, stored comma-separated (e.g. "ECN,EDC").

    "All" (or empty/None) means faculty-wide and is returned as the single
    sentinel element ["All"], not every FACULTY_SCHOOLS code, so callers can
    tell "faculty-wide" apart from "happens to be assigned every school".
    """
    raw = str(school_value).strip() if school_value else ""
    if not raw or raw.upper() == "ALL":
        return ["All"]
    codes = [c.strip().upper() for c in raw.split(",") if c.strip()]
    return codes if codes else ["All"]

def format_user_schools(schools):
    """
    Inverse of parse_user_schools - for the School badge/checkbox label and
    for writing back to users.School. "All" dominates: if present alongside
    specific codes (e.g. from a stray multiselect pick), the account is
    faculty-wide, not "All plus some schools".
    """
    if not schools or "All" in schools:
        return "All"
    return ",".join(sorted(set(s for s in schools if s)))

def module_matches_user_schools(module_code, user_schools):
    """True if a module (or 'CODE - Name' combined option string) falls
    under any of a user's assigned schools. ["All"] matches everything.
    """
    if not user_schools or "All" in user_schools:
        return True
    code = str(module_code or "")
    return any(code.startswith(s) for s in user_schools)

def aggregate_faculty_stats(df_aut, df_spr):
    """
    Calculates summary statistics at the faculty level.

    Ally averages cover only courses with content beyond their rolled-over
    template. Including the rest would report the faculty at ~99% every autumn,
    because Ally scores an untouched template almost perfectly - see
    classify_content_maturity.
    """
    stats = {}
    col_name = 'Ally Overall'

    def _avg(df):
        if df.empty or col_name not in df.columns:
            return None, 0
        if 'Content Maturity' in df.columns:
            scored = df[df['Content Maturity'] == "In progress"]
        else:
            scored = df
        values = pd.to_numeric(scored[col_name], errors='coerce').dropna()
        return (float(values.mean()) if not values.empty else None), len(scored)

    if not df_aut.empty:
        stats['Autumn Avg Ally'], stats['Autumn Scored Modules'] = _avg(df_aut)
        stats['Autumn Module Count'] = len(df_aut)

    if not df_spr.empty:
        stats['Spring Avg Ally'], stats['Spring Scored Modules'] = _avg(df_spr)
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

def resolve_active_row(code, df_aut, df_spr):
    """The module row a view should treat as canonical for one module code:
    Spring's, if the module runs in Spring, else Autumn's. Matches
    resolve_semester_df()'s own Spring-first convention. None if the module
    is in neither frame.

    Centralised because getting this precedence wrong silently changes which
    Blackboard shell's Ally/readiness/Leganto data a page shows - was
    duplicated identically in views/audit_portal.py and
    views/module_report.py before this.
    """
    aut_m = (df_aut[df_aut['New module code'] == code]
             if df_aut is not None and not df_aut.empty else pd.DataFrame())
    spr_m = (df_spr[df_spr['New module code'] == code]
             if df_spr is not None and not df_spr.empty else pd.DataFrame())
    if not spr_m.empty:
        return spr_m.iloc[0]
    if not aut_m.empty:
        return aut_m.iloc[0]
    return None

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

def parse_custom_observations(custom):
    """
    Parses a 'text'-type audit field's stored value, which can be:
    1. A JSON list of dicts: [{"observation": "...", "action": "..."}]
    2. A legacy template string: "**Observation:** ... \n\n**Action:** ..."
    3. A legacy plain text string.
    Returns a list of dicts: [{"observation": "...", "action": "..."}]

    Pure string/JSON parsing, no I/O - moved here from database.py, which
    re-exports it so nothing importing it from there breaks.
    """
    if not custom:
        return []

    if isinstance(custom, list):
        parsed = []
        for item in custom:
            if isinstance(item, dict):
                obs = str(item.get("observation", "")).strip()
                act = str(item.get("action", "")).strip()
                if obs or act:
                    parsed.append({"observation": obs, "action": act})
        return parsed

    if isinstance(custom, str):
        custom_str = custom.strip()

        if (custom_str.startswith("[") and custom_str.endswith("]")) or (custom_str.startswith("{") and custom_str.endswith("}")):
            try:
                data = json.loads(custom_str)
                if isinstance(data, list):
                    return parse_custom_observations(data)
                if isinstance(data, dict):
                    if "observation" in data or "action" in data:
                        obs = str(data.get("observation", "")).strip()
                        act = str(data.get("action", "")).strip()
                        if obs or act:
                            return [{"observation": obs, "action": act}]
            except Exception:
                pass

        if not custom_str or custom_str in ("**Observation:**", "**Observation:** \n\n**Action:**", "**Observation:**\n\n**Action:**"):
            return []

        obs_match = re.search(r'\*\*Observation:\*\*\s*(.*?)(?=\*\*Action:\*\*|$)', custom_str, re.DOTALL | re.IGNORECASE)
        action_match = re.search(r'\*\*Action:\*\*\s*(.*)', custom_str, re.DOTALL | re.IGNORECASE)

        obs = obs_match.group(1).strip() if obs_match else ""
        act = action_match.group(1).strip() if action_match else ""

        if not obs and not act:
            return [{"observation": custom_str, "action": ""}]
        return [{"observation": obs, "action": act}]

    return []

def summarise_ai_declarations(df_declarations, module_codes=None, known_codes=None):
    """
    Rolls per-assessment AI declarations up to per-module.

    The satellite AI-Audit app records one row per assessment, so a module with
    three assessments contributes three rows. The Faculty and School views want
    modules, not assessments: a module counts as declared once any of its
    assessments has been.

    `module_codes` is the set in scope for the figures - normally the SITS list
    for the selected semester or school.

    `known_codes` is every module SITS knows about, used only to classify what
    falls outside that scope. Without it a Spring module viewed in Autumn looks
    identical to a module SITS has never heard of, and the two need different
    responses: the first is routine, the second is a declaration that can never
    be reconciled and exists because the satellite offered a 2025/26 module list
    until its v1.2.0. Only the second is reported as `unmatched`. Neither is
    dropped silently.

    Kept I/O-free: callers pass in database.get_ai_declarations().

    Returns {'per_module': DataFrame, 'declared': int, 'in_scope': int,
    'unmatched': list, 'other_semester': list}.
    """
    empty = pd.DataFrame(columns=['module_code', 'Assessments Declared', 'Gen AI Activity'])
    result = {'per_module': empty, 'declared': 0, 'in_scope': 0,
              'unmatched': [], 'other_semester': []}

    scope = None
    if module_codes is not None:
        scope = {str(c).strip().upper() for c in module_codes if str(c).strip()}
        result['in_scope'] = len(scope)

    if df_declarations is None or df_declarations.empty:
        return result

    df = df_declarations.copy()
    df['module_code'] = df['module_code'].astype(str).str.strip().str.upper()
    df = df[df['module_code'] != ""]
    if df.empty:
        return result

    if scope is not None:
        outside = set(df['module_code']) - scope
        if known_codes is not None:
            known = {str(c).strip().upper() for c in known_codes if str(c).strip()}
            result['unmatched'] = sorted(outside - known)
            result['other_semester'] = sorted(outside & known)
        else:
            result['unmatched'] = sorted(outside)
        df = df[df['module_code'].isin(scope)]
    else:
        result['in_scope'] = df['module_code'].nunique()

    if df.empty:
        return result

    # "Yes" if any assessment on the module reported a Gen AI learning activity.
    gen_ai = df.groupby('module_code')['gen_ai_activity'].apply(
        lambda s: "Yes" if (s.astype(str).str.strip().str.lower() == "yes").any() else "No"
    )
    counts = df.groupby('module_code').size()

    per_module = pd.DataFrame({
        'module_code': counts.index,
        'Assessments Declared': counts.values,
    })
    per_module['Gen AI Activity'] = per_module['module_code'].map(gen_ai)

    result['per_module'] = per_module.reset_index(drop=True)
    result['declared'] = len(per_module)
    return result

def parse_ally_export(df, academic_year, snapshot_date):
    """
    Turns one Anthology Ally institutional export into the three frames that
    database.save_ally_snapshot() writes.

    The export is every Blackboard course the institution has ever had - 13k
    rows spanning a decade - so it is filtered to one academic year and to this
    faculty before anything else happens. Both counts are reported rather than
    dropped quietly, because a mis-scoped export otherwise looks like a
    successful import of the wrong year.

    The issue and content blocks are melted to long format. Ally adds new
    checks between releases, and a long table absorbs one without a migration.
    Only non-zero counts are kept: at 39 checks over ~900 courses a week, the
    zeros would be 95% of the rows.

    Kept I/O-free - the caller reads the CSV and writes the database.

    Returns {'courses', 'issues', 'content': DataFrames, 'rows_in',
    'dropped_other_years', 'dropped_out_of_faculty', 'years_seen': list}.
    """
    result = {'courses': pd.DataFrame(), 'issues': pd.DataFrame(),
              'content': pd.DataFrame(), 'rows_in': 0, 'dropped_other_years': 0,
              'dropped_out_of_faculty': 0, 'years_seen': []}
    if df is None or df.empty:
        return result

    df = df.copy()
    result['rows_in'] = len(df)

    required = ['Course code', 'Course id', 'Overall score']
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(
            "This does not look like an Ally institutional export - missing "
            + ", ".join(missing))

    # 1. Academic year. Term name is the trustworthy source, but Ally leaves it
    #    blank on some rows even for current-year courses - the year is still
    #    readable out of the free-text Course name in those cases (e.g.
    #    "(AUTUMN 2026-27)"), so fall back to that rather than dropping a course
    #    that is actually in scope.
    df['academic_year'] = df.get('Term name', "").map(ally_term_to_academic_year)
    blank_term = df['academic_year'] == ""
    if blank_term.any() and 'Course name' in df.columns:
        df.loc[blank_term, 'academic_year'] = (
            df.loc[blank_term, 'Course name'].map(ally_term_to_academic_year))
    result['years_seen'] = sorted([y for y in df['academic_year'].unique() if y], reverse=True)
    keep_year = df['academic_year'] == academic_year
    result['dropped_other_years'] = int((~keep_year).sum())
    df = df[keep_year]
    if df.empty:
        return result

    # 2. Module code, by the convention the rest of the app already uses:
    #    EDC001.A.288719 -> EDC001. The letter is a Blackboard shell
    #    discriminator, not a SITS occurrence.
    df['module_code'] = (df['Course code'].astype(str)
                         .str.split('.').str[0].str.strip().str.upper())
    df = df[df['module_code'] != ""]

    # 3. Faculty scope from the code prefix. Department name in this export is
    #    unusable as a key - it carries pre-restructure names and multi-valued
    #    entries like "Sheffield University Management School; Ultra Courses" -
    #    so it is stored for reference and never joined on.
    in_faculty = df['module_code'].str[:3].isin(FACULTY_SCHOOLS)
    result['dropped_out_of_faculty'] = int((~in_faculty).sum())
    df = df[in_faculty]
    if df.empty:
        return result

    # 4. Split the wide census blocks. Everything from the first severity-
    #    suffixed column onward is the issue block (LibraryReference sits
    #    inside it without a suffix); what lies between WYSIWYG score and that
    #    point is the content-type block. Slicing positionally rather than by a
    #    fixed list means a new Blackboard content type or a new Ally check
    #    lands in the right place on its own.
    cols = list(df.columns)
    issue_start = next((i for i, c in enumerate(cols) if ':' in str(c)), len(cols))
    try:
        content_start = cols.index('WYSIWYG score') + 1
    except ValueError:
        content_start = issue_start
    content_cols = [c for c in cols[content_start:issue_start]]
    issue_cols = [c for c in cols[issue_start:] if c not in ('academic_year', 'module_code')]

    def _num(col, default=0):
        if col not in df.columns:
            return pd.Series(default, index=df.index)
        return pd.to_numeric(df[col], errors='coerce').fillna(default)

    def _iso(col):
        """Ally writes these day-first, but exports that have been through a
        spreadsheet come back ISO. Accept both and normalise, so snapshot rows
        stay comparable and sortable."""
        if col not in df.columns:
            return pd.Series("", index=df.index)
        try:
            parsed = pd.to_datetime(df[col], format='mixed', dayfirst=True, errors='coerce')
        except (ValueError, TypeError):
            parsed = pd.to_datetime(df[col], errors='coerce')
        return parsed.dt.strftime('%Y-%m-%d %H:%M').fillna("")

    courses = pd.DataFrame({
        'course_id': df['Course id'].astype(str).str.strip(),
        'snapshot_date': snapshot_date,
        'academic_year': academic_year,
        'module_code': df['module_code'],
        'course_code': df['Course code'].astype(str).str.strip(),
        'course_name': df.get('Course name', "").astype(str).str.strip(),
        'course_url': df.get('Course url', "").astype(str).str.strip(),
        'department_name': df.get('Department name', "").astype(str).str.strip(),
        'students': _num('Number of students').astype(int),
        'ally_enabled': df.get('Ally enabled', True).astype(str).str.strip().str.upper()
                          .isin(['TRUE', '1', 'YES']).astype(int),
        'last_checked_on': _iso('Last checked on'),
        'deleted_on': _iso('Observed deleted on'),
        'total_files': _num('Total files').astype(int),
        'total_wysiwyg': _num('Total WYSIWYG').astype(int),
        'overall_score': _num('Overall score', float('nan')),
        'files_score': _num('Files score', float('nan')),
        'wysiwyg_score': _num('WYSIWYG score', float('nan')),
    })
    # One export can list the same course twice; the later row wins.
    courses = courses.drop_duplicates(subset=['course_id'], keep='last').reset_index(drop=True)

    def _melt(value_cols, name_col):
        if not value_cols:
            return pd.DataFrame(columns=['course_id', 'snapshot_date', name_col, 'items'])
        block = df[value_cols].apply(pd.to_numeric, errors='coerce').fillna(0)
        block.insert(0, 'course_id', df['Course id'].astype(str).str.strip())
        long = block.melt(id_vars='course_id', var_name=name_col, value_name='items')
        long = long[long['items'] > 0].copy()
        long['items'] = long['items'].astype(int)
        long['snapshot_date'] = snapshot_date
        return long.drop_duplicates(subset=['course_id', name_col], keep='last')

    issues = _melt(issue_cols, 'check_name')
    if not issues.empty:
        split = issues['check_name'].astype(str).str.split(':', n=1, expand=True)
        issues['check_name'] = split[0].str.strip()
        issues['severity'] = (pd.to_numeric(split[1], errors='coerce')
                              if split.shape[1] > 1 else None)
    else:
        issues['severity'] = pd.Series(dtype='float')

    content = _melt(content_cols, 'content_type')

    valid = set(courses['course_id'])
    result['courses'] = courses
    result['issues'] = issues[issues['course_id'].isin(valid)][
        ['course_id', 'snapshot_date', 'check_name', 'severity', 'items']].reset_index(drop=True)
    result['content'] = content[content['course_id'].isin(valid)][
        ['course_id', 'snapshot_date', 'content_type', 'items']].reset_index(drop=True)
    return result

# --- Leganto reading lists -------------------------------------------------

def _leganto_status(draft_lists, published_lists, list_info=""):
    """Draft/Published/Mixed from list counts, falling back to the export's
    own 'No List Expected' marker when a course has no list at all."""
    draft_lists = int(draft_lists or 0)
    published_lists = int(published_lists or 0)
    if draft_lists > 0 and published_lists > 0:
        return "Mixed"
    if published_lists > 0:
        return "Published"
    if draft_lists > 0:
        return "Draft"
    if str(list_info or "").strip():
        return "No List Expected"
    return ""

def parse_leganto_lists_export(df, academic_year, snapshot_date):
    """
    Turns the Leganto 'has a list' export into the frame
    database.save_leganto_snapshot() writes.

    Columns are `School, Course Code, Course Name, Course Term, Course List
    Info, Draft, Published, Draft, Published` - pandas resolves the repeated
    headers to `Draft, Published, Draft.1, Published.1`. The first pair is a
    count of lists in that state (normally 0/1, occasionally more where a
    course carries several lists); the second is the summed item count for
    lists in that state.

    Kept I/O-free - the caller reads the CSV and writes the database.

    Returns {'lists': DataFrame, 'rows_in', 'dropped_out_of_faculty'}.
    """
    result = {'lists': pd.DataFrame(), 'rows_in': 0, 'dropped_out_of_faculty': 0}
    if df is None or df.empty:
        return result

    df = df.copy()
    result['rows_in'] = len(df)

    required = ['Course Code', 'Draft', 'Published', 'Draft.1', 'Published.1']
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(
            "This does not look like a Leganto reading-list export - missing "
            + ", ".join(missing))

    # Module code, by the same convention as the Ally import:
    # ALA101.A.276710 -> ALA101.
    df['module_code'] = (df['Course Code'].astype(str)
                         .str.split('.').str[0].str.strip().str.upper())
    df = df[df['module_code'] != ""]

    in_faculty = df['module_code'].str[:3].isin(FACULTY_SCHOOLS)
    result['dropped_out_of_faculty'] = int((~in_faculty).sum())
    df = df[in_faculty]
    if df.empty:
        return result

    def _num(col):
        return pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)

    draft_lists = _num('Draft')
    published_lists = _num('Published')
    draft_items = _num('Draft.1')
    published_items = _num('Published.1')
    list_info = df.get('Course List Info', "").astype(str).replace('nan', '').str.strip()

    lists_df = pd.DataFrame({
        'course_code': df['Course Code'].astype(str).str.strip(),
        'snapshot_date': snapshot_date,
        'academic_year': academic_year,
        'module_code': df['module_code'],
        'course_name': df.get('Course Name', "").astype(str).str.strip(),
        'school': df.get('School', "").astype(str).str.strip(),
        'course_term': df.get('Course Term', "").astype(str).str.strip(),
        'list_info': list_info,
        'draft_lists': draft_lists,
        'published_lists': published_lists,
        'draft_items': draft_items,
        'published_items': published_items,
    })
    lists_df['status'] = [
        _leganto_status(d, p, li) for d, p, li in
        zip(lists_df['draft_lists'], lists_df['published_lists'], lists_df['list_info'])
    ]
    # One export can list the same course twice; the later row wins.
    lists_df = lists_df.drop_duplicates(subset=['course_code'], keep='last').reset_index(drop=True)

    result['lists'] = lists_df
    return result

# Uploaded-file count separates a rolled-over template from a course somebody
# has started populating, and it separates them cleanly. In 2025-26 - a fully
# taught year - only 4 of 1034 courses held 5 files or fewer, and the 10th
# percentile was 16. In 2026-27 as at August, 860 of 928 held 5 or fewer.
# Editor pages do not discriminate: the template ships ~25 of them either way.
ALLY_TEMPLATE_MAX_FILES = 5

def classify_content_maturity(total_files, total_wysiwyg, students=None):
    """
    Whether a Blackboard course still looks like its rolled-over template.

    There is deliberately no "Built" or "Complete" state. Module leads build
    just-in-time throughout the year - a module can legitimately gain content
    every week right up to its final assessment - so no file count at any
    point during the year can say a course is finished, only that it has
    started. Treating a high file count as "Built" would be a claim the data
    cannot support and would stop being true the moment the next file lands.

    Freshly rolled-over courses hold only their template - typically two files
    and a couple of dozen editor pages - and Ally scores that template at close
    to 100%. Presenting that as an accessibility result would be wrong for the
    first weeks of every year, which is the actual job of this function: gate
    the score, not grade the course.

    Deliberately based on content alone. Enrolment is far too noisy before term
    starts - in August only 101 of 928 courses had a single student, populated
    ones included - so it is left to the views to use as an impact weight
    instead. `students` is accepted and ignored so callers need not care.
    """
    files = int(total_files or 0)
    wysiwyg = int(total_wysiwyg or 0)

    if files == 0 and wysiwyg == 0:
        return "Empty"
    if files <= ALLY_TEMPLATE_MAX_FILES:
        return "Not yet built"
    return "In progress"

def aggregate_ally_to_modules(df_courses):
    """
    Rolls Blackboard courses up to modules.

    Almost every module has one course shell, but a handful run separate cohort
    shells under one code - typically an empty template beside the live taught
    course. Averaging those flatters the module, so scores are re-weighted by
    the number of content items behind them rather than by shell.

    Kept I/O-free: callers pass in database.get_ally_courses_latest().
    """
    columns = ['module_code', 'overall_score', 'files_score', 'wysiwyg_score',
               'total_files', 'total_wysiwyg', 'total_items', 'students',
               'shell_count', 'ally_enabled', 'last_checked_on', 'course_url',
               'content_maturity', 'snapshot_date']
    if df_courses is None or df_courses.empty:
        return pd.DataFrame(columns=columns)

    df = df_courses.copy()
    df['module_code'] = df['module_code'].astype(str).str.strip().str.upper()
    for col in ['total_files', 'total_wysiwyg', 'students']:
        df[col] = pd.to_numeric(df.get(col), errors='coerce').fillna(0)
    for col in ['overall_score', 'files_score', 'wysiwyg_score']:
        df[col] = pd.to_numeric(df.get(col), errors='coerce')
    df['total_items'] = df['total_files'] + df['total_wysiwyg']
    df['ally_enabled'] = pd.to_numeric(df.get('ally_enabled', 1), errors='coerce').fillna(1)

    # Weighted-average numerator/denominator per row, so the per-module ratio
    # falls out of a single groupby().sum() rather than a Python loop over each
    # module calling back into pandas per group - at faculty scale (~900
    # modules) that loop cost several seconds on every cache refresh. A row
    # whose score is missing contributes a zero weight, which is exactly what
    # excluding it from the original weighted average did.
    def _num_den(score_col, weight_col):
        weight = df[weight_col].where(df[score_col].notna(), 0.0)
        return df[score_col].fillna(0.0) * weight, weight

    ov_num, ov_den = _num_den('overall_score', 'total_items')
    fs_num, fs_den = _num_den('files_score', 'total_files')
    ws_num, ws_den = _num_den('wysiwyg_score', 'total_wysiwyg')

    tmp = pd.DataFrame({
        'module_code': df['module_code'],
        'overall_num': ov_num, 'overall_den': ov_den,
        'files_num': fs_num, 'files_den': fs_den,
        'wys_num': ws_num, 'wys_den': ws_den,
        'total_files': df['total_files'], 'total_wysiwyg': df['total_wysiwyg'],
        'total_items': df['total_items'], 'students': df['students'],
        'ally_enabled': df['ally_enabled'],
    })

    agg = tmp.groupby('module_code', sort=True).agg(
        overall_num=('overall_num', 'sum'), overall_den=('overall_den', 'sum'),
        files_num=('files_num', 'sum'), files_den=('files_den', 'sum'),
        wys_num=('wys_num', 'sum'), wys_den=('wys_den', 'sum'),
        total_files=('total_files', 'sum'), total_wysiwyg=('total_wysiwyg', 'sum'),
        total_items=('total_items', 'sum'), students=('students', 'sum'),
        shell_count=('total_files', 'size'),
        # A module counts as Ally-disabled if any of its shells is.
        ally_enabled=('ally_enabled', 'min'),
    )
    agg['overall_score'] = (agg['overall_num'] / agg['overall_den']).where(agg['overall_den'] > 0)
    agg['files_score'] = (agg['files_num'] / agg['files_den']).where(agg['files_den'] > 0)
    agg['wysiwyg_score'] = (agg['wys_num'] / agg['wys_den']).where(agg['wys_den'] > 0)

    # The shell a student is most likely to be looking at: most enrolled, then
    # most content. Used for the link and the freshness date.
    primary = (df.sort_values(['students', 'total_items'], ascending=False)
                 .groupby('module_code', sort=True).first())

    out = agg.reset_index()
    out['last_checked_on'] = primary['last_checked_on'].reindex(out['module_code']).fillna("").astype(str).values
    out['course_url'] = primary['course_url'].reindex(out['module_code']).fillna("").astype(str).values
    out['snapshot_date'] = primary['snapshot_date'].reindex(out['module_code']).fillna("").astype(str).values
    out['ally_enabled'] = out['ally_enabled'].fillna(1).astype(int)
    for col in ['total_files', 'total_wysiwyg', 'total_items', 'students', 'shell_count']:
        out[col] = out[col].astype(int)
    out['content_maturity'] = out.apply(
        lambda r: classify_content_maturity(r['total_files'], r['total_wysiwyg'], r['students']),
        axis=1)
    return out[columns]

def aggregate_leganto_to_modules(df_lists):
    """
    Rolls Leganto course-grain list records up to modules.

    A module can carry more than one course occurrence (different cohorts);
    list and item counts are summed across them and the status is re-derived
    from the summed counts, same rule as a single course row.

    Kept I/O-free: callers pass in database.get_leganto_lists_latest().
    """
    columns = ['module_code', 'status', 'draft_lists', 'published_lists',
               'draft_items', 'published_items', 'total_items', 'snapshot_date']
    if df_lists is None or df_lists.empty:
        return pd.DataFrame(columns=columns)

    df = df_lists.copy()
    df['module_code'] = df['module_code'].astype(str).str.strip().str.upper()
    for col in ['draft_lists', 'published_lists', 'draft_items', 'published_items']:
        df[col] = pd.to_numeric(df.get(col), errors='coerce').fillna(0).astype(int)

    agg = df.groupby('module_code', sort=True).agg(
        draft_lists=('draft_lists', 'sum'), published_lists=('published_lists', 'sum'),
        draft_items=('draft_items', 'sum'), published_items=('published_items', 'sum'),
        list_info=('list_info', lambda s: next((v for v in s if str(v).strip()), "")),
        snapshot_date=('snapshot_date', 'max'),
    ).reset_index()

    agg['status'] = [
        _leganto_status(d, p, li) for d, p, li in
        zip(agg['draft_lists'], agg['published_lists'], agg['list_info'])
    ]
    agg['total_items'] = agg['draft_items'] + agg['published_items']
    return agg[columns]

# --- Module readiness (template alignment) ---------------------------------

# The faculty Template Alignment Report tells us the visible/hidden/deleted/
# missing state of each required Blackboard template section, plus when each was
# last modified.
#
# `owner` is who acts when a section is wrong, which is the only thing an
# auditor needs from it:
#   lead        - the module lead, via the Audit Portal worklist
#   institution - central boilerplate that ships visible; nobody is expected to
#                 touch it, so "Visible" here carries no information at all
#   dlt         - Digital Learning Team; a Missing section means the shell was
#                 built wrong, which is a course-creation fault, not a lead one
#
# The third entry is the audit_fields.id this section answers, where one exists.
# That mapping is what lets the data pre-answer the existing checklist rather
# than sitting beside it as a separate score.
#
# Labels follow the report's own section names, so a section is called the same
# thing in the faculty report and in the portal. The one departure is "SGAs"
# rather than the report's "SGAS", to match the existing audit_fields label.
TEMPLATE_SECTIONS = {
    'MODULE_INFORMATION':          ('Module Information',                'institution', None),
    'WELCOME_MODULE_OUTLINE':      ('Welcome & Module Outline',          'lead',        'welcome_outline'),
    'KEY_STAFF_CONTACTS':          ('Key Staff Contacts',                'lead',        'contacts_complete'),
    'SKILLS_DEVELOPMENT_SGAS':     ('Skills Development: Sheffield Graduate Attributes (SGAs)',
                                                                         'institution', 'sga'),
    'STUDENT_VOICE':               ('Student Voice',                     'institution', 'student_voice'),
    'HOW_YOUR_FEEDBACK_SHAPES':    ('How Your Feedback Shapes this Module', 'institution', None),
    'ACCESSIBILITY_STATEMENT':     ('Accessibility Statement',           'institution', None),
    'SCHOOL_HANDBOOK':             ('School Handbook',                   'institution', None),
    'ASSESSMENT_OVERVIEW':         ('Assessment Overview',               'institution', 'assessment_overview'),
    'ASSESSMENT_DETAIL':           ('Assessment Detail',                 'lead',        'assessment_brief'),
    'ASSESSMENT_SUPPORT_GUIDANCE': ('Assessment Support and Guidance',   'institution', None),
    'MODULE_READING_LIST':         ('Module Reading List',               'institution', None),
    'ENCORE_LECTURE_CAPTURE':      ('Encore Lecture Capture',            'institution', 'encore_link'),
    'UNIVERSITY_HELP_SUPPORT':     ('University Help & Study Support',   'institution', None),
}

# The three sections that ship Hidden and have to be unhidden by the module
# lead. This is where all the triage signal lives: the faculty guidance states
# the 11/3 split, and the 2026-27 export bears it out - 43 of the 45 courses in
# the first excerpt sat at exactly 11 of 14 visible, which is the untouched
# post-rollover default, so the completeness score alone separates almost
# nothing. diagnostics/check_readiness_export.py re-asserts the split on every
# new file so a template change cannot silently invalidate this.
#
# Derived from the catalogue rather than written out a second time.
LEAD_OWNED_SECTIONS = tuple(k for k, v in TEMPLATE_SECTIONS.items() if v[1] == 'lead')

# Worst-wins ordering when a module carries several Blackboard shells: a section
# missing from one shell is worse than hidden in it, which is worse than
# visible. Note Deleted ranks below Hidden - somebody removed the section
# outright, and unlike Hidden it drops out of the export's own HIDDEN_SECTIONS
# summary, so it is easy to miss.
READINESS_SECTION_RANK = {'Missing': 0, 'Deleted': 1, 'Hidden': 2, 'Visible': 3}

# When a date is a same-day batch edit rather than evidence of the module
# lead's own activity. A (school, date) qualifies on EITHER test - share of
# the school, or an absolute number of modules.
#
# "Last modified is not the creation date" is NOT on its own evidence that a
# LEAD has done anything. A date this widely shared is not attributable to any
# one person from the data alone - and it is *not* safe to assume it is IT.
# Aside from the original template rollout, IT does not push bulk content
# edits. What actually produces this signature, most of the time, is
# Professional Services (PS) / school admin staff working through a batch of
# modules editing a specific section (often Key Staff Contacts) on the lead's
# behalf - real content work, just not done by the lead, and which section(s)
# get PS-edited this way varies by school. The export only gives a date, not a
# time or an editor, so a genuine IT rollout and a PS team clearing a worklist
# in one afternoon look identical here.
#
# Both tests are needed because neither works alone:
#
# - Share alone is scale-dependent, which the faculty-wide 2026-27 export made
#   obvious. The ALA batch of 23/07 touched 25 modules. In the 45-module
#   single-school excerpt this was calibrated on, that is 56% and gets flagged;
#   in the real 142-module school it is 17.6% and slips under a 20% cut. The
#   same event, the same day, two answers.
# - A count alone would flag ordinary activity in a small school.
#
# Calibrated on the faculty-wide export (911 courses, 7 schools). Excluding the
# creation date, modules touched per (school, date) ran 61, 29, 25, 24, 19, 14,
# 10, 9, 9, then 7 and below with a long tail of 34 pairs touching a single
# module. The first nine are batch operations - they also rewrite 6.5-12.8
# sections per module, where genuine one-off edits touch two or three. A floor
# of 8 sits in that gap.
#
# Erring toward flagging is the safe direction: a batch hit yields *no positive
# evidence of LEAD activity*, so over-flagging costs a human check, while
# under-flagging lets a module auto-complete on the strength of someone other
# than the lead having touched it. Re-run diagnostics/check_readiness_export.py
# on each new export - it prints the distribution and the resulting
# classification.
READINESS_BULK_EDIT_SHARE = 0.20
READINESS_BULK_EDIT_MIN_MODULES = 8

def _iso_date(series):
    """DD/MM/YYYY from the export to ISO YYYY-MM-DD for storage and sorting.

    Blank where unparseable rather than raising - a missing modification date on
    one section must not cost the whole import.
    """
    if series is None:
        return ""
    parsed = pd.to_datetime(series, dayfirst=True, errors='coerce')
    return parsed.dt.strftime('%Y-%m-%d').fillna("")

def parse_readiness_export(df, academic_year, snapshot_date):
    """
    Turns the faculty Template Alignment Report into the frames
    database.save_readiness_snapshot() writes.

    Sections are discovered from the column names rather than a fixed list:
    every column ending `_STATUS` other than `Alignment_STATUS` is a template
    section, paired with its `_LAST_MODIFIED` sibling. The template is versioned
    and gains and loses sections between years, so discovering them means a new
    template needs no code change here - only a TEMPLATE_SECTIONS entry to give
    the new section a human label.

    Kept I/O-free - the caller reads the CSV and writes the database.

    Returns {'courses', 'sections', 'rows_in', 'dropped_out_of_faculty',
    'dropped_other_years', 'years_seen', 'section_keys'}.
    """
    result = {'courses': pd.DataFrame(), 'sections': pd.DataFrame(), 'rows_in': 0,
              'dropped_out_of_faculty': 0, 'dropped_other_years': 0,
              'years_seen': [], 'section_keys': []}
    if df is None or df.empty:
        return result

    df = df.copy()
    result['rows_in'] = len(df)

    required = ['COURSE_NUMBER', 'EXPECTED_SECTION_COUNT', 'VISIBLE_SECTION_COUNT',
                'COMPLETENESS_SCORE_PERCENT', 'Alignment_STATUS']
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(
            "This does not look like a Template Alignment Report - missing "
            + ", ".join(missing))

    section_keys = [c[:-len('_STATUS')] for c in df.columns
                    if c.endswith('_STATUS') and c != 'Alignment_STATUS']
    if not section_keys:
        raise ValueError(
            "This Template Alignment Report has no per-section status columns "
            "- expected columns ending _STATUS.")
    result['section_keys'] = section_keys

    # Module code, by the same convention as the Ally and Leganto imports:
    # ALA110.A.288075 -> ALA110.
    df['module_code'] = (df['COURSE_NUMBER'].astype(str)
                         .str.split('.').str[0].str.strip().str.upper())
    df = df[df['module_code'] != ""]

    # Year comes from the file, as it does for Ally - TERM_NAME carries
    # 'Academic Year 2026-2027', the same shape as Ally's Term name.
    if 'TERM_NAME' in df.columns:
        df['_year'] = df['TERM_NAME'].map(ally_term_to_academic_year)
    else:
        df['_year'] = ""
    result['years_seen'] = sorted({y for y in df['_year'] if y})
    if result['years_seen']:
        wanted = df['_year'] == academic_year
        result['dropped_other_years'] = int((~wanted).sum())
        df = df[wanted]

    in_faculty = df['module_code'].str[:3].isin(FACULTY_SCHOOLS)
    result['dropped_out_of_faculty'] = int((~in_faculty).sum())
    df = df[in_faculty]
    if df.empty:
        return result

    # The export is a vendor file and its optional columns come and go between
    # revisions, so every accessor tolerates an absent column rather than
    # failing the whole import over one.
    def _num(col):
        if col not in df.columns:
            return pd.Series(0, index=df.index, dtype=int)
        return pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)

    def _text(col):
        if col not in df.columns:
            return pd.Series("", index=df.index, dtype=object)
        return df[col].astype(str).replace('nan', '').str.strip()

    def _date(col):
        if col not in df.columns:
            return pd.Series("", index=df.index, dtype=object)
        return _iso_date(df[col])

    courses = pd.DataFrame({
        'course_number': df['COURSE_NUMBER'].astype(str).str.strip(),
        'snapshot_date': snapshot_date,
        'academic_year': academic_year,
        'module_code': df['module_code'],
        'course_name': _text('COURSE_NAME'),
        'course_created_date': _date('COURSE_CREATED_DATE'),
        'term_name': _text('TERM_NAME'),
        'student_count': _num('STUDENT_COUNT'),
        # Level 4 of the hierarchy is the school ("School of Architecture and
        # Landscape"), which is a name rather than the 3-letter code used
        # everywhere else - kept as supplied for the import report.
        'school_name': _text('INSTITUTION_HIERARCHY_LEVEL_4'),
        'expected_sections': _num('EXPECTED_SECTION_COUNT'),
        'visible_sections': _num('VISIBLE_SECTION_COUNT'),
        'hidden_sections': _num('HIDDEN_SECTION_COUNT'),
        'deleted_sections': _num('DELETED_SECTION_COUNT'),
        'missing_sections': _num('MISSING_SECTION_COUNT'),
        'completeness_score': pd.to_numeric(df['COMPLETENESS_SCORE_PERCENT'],
                                            errors='coerce'),
        'alignment_status': _text('Alignment_STATUS'),
        'template_version': _text('TEMPLATE_VERSION_INDICATOR'),
    })
    # One export can list the same course twice; the later row wins.
    courses = courses.drop_duplicates(subset=['course_number'], keep='last').reset_index(drop=True)

    kept = set(courses['course_number'])
    frames = []
    for key in section_keys:
        status = _text(f'{key}_STATUS')
        modified = _date(f'{key}_LAST_MODIFIED')
        frames.append(pd.DataFrame({
            'course_number': df['COURSE_NUMBER'].astype(str).str.strip(),
            'snapshot_date': snapshot_date,
            'academic_year': academic_year,
            'section_key': key,
            'status': status,
            'last_modified': modified,
        }))

    sections = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if not sections.empty:
        sections = sections[sections['status'] != ""]
        sections = sections[sections['course_number'].isin(kept)]
        sections = sections.drop_duplicates(
            subset=['course_number', 'section_key'], keep='last').reset_index(drop=True)

    result['courses'] = courses
    result['sections'] = sections
    return result

def detect_bulk_edit_dates(df_sections):
    """
    Dates on which template sections changed across so many of a school's
    courses at once that the change cannot be attributed to any one person -
    lead or otherwise - from the data alone.

    The template rollout stamps a fresh last-modified date onto hundreds of
    courses on a single day, but so does Professional Services / school admin
    staff working through a batch of modules on the lead's behalf - the export
    gives only a date, no time or editor, so the two look the same here.
    Without this, "modified since the course was created" would read as
    evidence the LEAD had done something, when someone else plausibly had.

    Returns a set of (school_prefix, date) pairs. Callers treat a hit as *no
    positive evidence of lead activity*, never as negative evidence of the
    section being genuinely done - a lead may well have edited their own
    module on the same day a batch run happened, and we cannot tell.

    Deliberately computed on read rather than baked in at import, so
    READINESS_BULK_EDIT_SHARE can be retuned without re-importing - the same
    reasoning as classify_content_maturity.

    Kept I/O-free: callers pass in database.get_readiness_sections_latest().
    """
    if df_sections is None or df_sections.empty:
        return set()

    df = df_sections.copy()
    df['module_code'] = df['module_code'].astype(str).str.strip().str.upper()
    df['school'] = df['module_code'].str[:3]
    df['last_modified'] = df['last_modified'].astype(str).str.strip()
    df = df[df['last_modified'] != ""]
    if df.empty:
        return set()

    school_sizes = df.groupby('school')['module_code'].nunique()
    touched = (df.groupby(['school', 'last_modified'])['module_code']
                 .nunique().reset_index(name='modules'))
    touched['share'] = touched['modules'] / touched['school'].map(school_sizes)
    bulk = touched[(touched['share'] >= READINESS_BULK_EDIT_SHARE)
                   | (touched['modules'] >= READINESS_BULK_EDIT_MIN_MODULES)]
    return set(zip(bulk['school'], bulk['last_modified']))

def classify_edit_evidence(last_modified, created_date, is_bulk):
    """
    What a section's last-modified date is evidence of.

    'lead_edit'       - changed on a date that is neither the course creation
                        date nor a shared batch date: evidence of activity on
                        this module specifically. Cannot distinguish the lead
                        from someone else editing on their behalf on an
                        otherwise-quiet day, but at that scale there is no
                        cheaper alternative explanation.
    'bulk'            - changed only on a date many other modules also
                        changed, so the change cannot be attributed to the
                        LEAD in particular. Often genuine content work done by
                        Professional Services / admin staff on the lead's
                        behalf rather than a lead editing their own module -
                        see detect_bulk_edit_dates().
    'never_modified'  - unchanged since the course was created
    'unknown'         - no usable date

    Deliberately about the *date alone*. Whether a section is ready is the
    status; this says what the date can and cannot prove about who moved it.
    Both have to line up before the data can claim the LEAD has done anything -
    a hidden section with a lead_edit date has been worked on and still is not
    visible to students.

    'bulk' and 'never_modified' both mean *no positive evidence of LEAD
    activity*, never evidence the section itself is unfinished: a lead may well
    have edited their module on the same day a batch run happened elsewhere in
    the school, and a 'bulk' section may be genuinely complete work done by PS
    staff rather than the lead. An institutional section sitting untouched is
    separately fine, since nobody was ever expected to touch it.
    """
    modified = str(last_modified or "").strip()
    if not modified:
        return 'unknown'
    if modified == str(created_date or "").strip():
        return 'never_modified'
    if is_bulk:
        return 'bulk'
    return 'lead_edit'

# What a section's status and its edit evidence mean *together*. Neither answers
# the question alone, and the combinations are not variations on a theme - they
# call for different conversations:
#
#   label   - the student-facing fact, which is what the badge says
#   tier    - ok | attention | action | fault, for colour and ordering
#   action  - what an advisor would actually say about it
#
# 'drafted_hidden' is the one worth knowing about. In the 2026-27 export 34
# lead-owned sections had a genuine per-module edit date and were still hidden:
# the work exists and no student can see it. That is a one-click fix and nothing
# like "this has not been started", which is what a status-only reading of
# Hidden would have called it.
#
# 'visible_unattributed' is the mirror case: visible, but the only date on it is
# a batch edit or the course creation date, so nothing records anyone preparing
# it on this module specifically. Students can see it, which is what matters
# for readiness - and per Phase 4 (readiness_prefill_for_module()), it is
# also what matters for the audit checklist suggestion: "is this section done"
# is a status question, not a "did the lead personally do it" question, and a
# batch date is frequently genuine Professional Services work completed on the
# lead's behalf rather than nobody's work at all. So visible_edited and
# visible_unattributed are treated alike for suggesting a tick - the evidence
# text is what tells the advisor which one they are looking at.
#
# In the 2026-27 export only 2 lead-owned sections were visible_unattributed
# (both batch-dated), and none were visible with the course-creation date.
# That will not hold. The moment a template revision ships these three
# sections visible by default, or an availability change lands without
# touching last_modified, visible_unattributed becomes the mass default - and
# a module would read "3 of 3 ready" with no work done, exactly as the 11
# institutional sections read today. check_readiness_export.py alarms when its
# share climbs.
READINESS_READY_STATES = ('visible_edited', 'visible_unattributed')
SECTION_STATES = {
    'visible_edited': (
        "Visible to students", 'ok',
        "Visible and prepared on this module. Nothing outstanding."),
    'visible_unattributed': (
        "Visible to students", 'ok',
        "Visible to students, but nothing records anyone preparing it on this "
        "module - it may still hold template placeholder text."),
    'drafted_hidden': (
        "Hidden from students", 'action',
        "This has been worked on but is still hidden, so no student can see it. "
        "Making it visible is all that is outstanding."),
    'not_started': (
        "Not started", 'attention',
        "Still hidden and with no sign of being edited, so it is still the "
        "default template section."),
    'deleted': (
        "Deleted", 'fault',
        "This section has been removed from the course. If that was not "
        "deliberate it has to be restored."),
    'missing': (
        "Missing", 'fault',
        "This section is absent from the course shell - a course-creation "
        "fault for the Digital Learning Team rather than the module lead."),
    'unknown': (
        "Unknown", 'attention',
        "The report carries no usable status for this section."),
}

def classify_section_state(status, evidence):
    """Status and edit evidence combined into one state - see SECTION_STATES.

    Kept separate from classify_edit_evidence() because that answers "who moved
    it" and status answers "can a student see it". Both are needed: a section
    can be genuinely worked on and still invisible.
    """
    status = str(status or "").strip()
    if status == 'Missing':
        return 'missing'
    if status == 'Deleted':
        return 'deleted'
    if status == 'Visible':
        return 'visible_edited' if evidence == 'lead_edit' else 'visible_unattributed'
    if status == 'Hidden':
        return 'drafted_hidden' if evidence == 'lead_edit' else 'not_started'
    return 'unknown'

def fmt_report_date(value):
    """ISO storage to the DD-MM-YYYY the portal shows users. Blank if unusable."""
    parsed = pd.to_datetime(str(value or ""), errors='coerce')
    return "" if pd.isna(parsed) else parsed.strftime('%d-%m-%Y')

def readiness_evidence_words(state, created_date):
    """The plain sentence under a section's status, saying what the data does
    and does not show.

    Shared by the module report's Blackboard Template block and the Audit
    Portal's pre-fill caption (readiness_prefill_for_module()) so the two
    surfaces never describe the same section differently.

    Deliberately explicit about the limits. A 'Visible' section only proves
    somebody unhid it - it is not claimed as proof the content is right, and a
    'bulk' date is not claimed to be an IT job. Aside from the original
    template rollout, a same-day batch edit across many courses is usually
    Professional Services / school admin staff working through a batch of
    modules on the lead's behalf, not a central push - see
    detect_bulk_edit_dates().
    """
    modified = fmt_report_date(state.get('last_modified'))
    evidence = state.get('evidence')
    if evidence == 'never_modified':
        created = fmt_report_date(created_date) or modified
        return f"Unchanged since the course was created{f' on {created}' if created else ''}."
    if evidence == 'bulk':
        return (f"Last changed {modified}, the same day as many other courses in the "
                "school - most likely Professional Services staff working through a "
                "batch on the lead's behalf, not evidence from this module alone.")
    if evidence == 'lead_edit':
        return f"Last changed {modified}."
    return "No modification date recorded."

def aggregate_readiness_to_modules(df_courses, df_sections):
    """
    Rolls Blackboard courses up to modules for the template alignment report.

    A module can carry more than one course shell (separate cohorts), so section
    status is combined worst-wins via READINESS_SECTION_RANK: if any shell still
    hides a section, the module still hides it.

    The verdict columns describe the lead-owned sections only. The vendor's own
    completeness_score and alignment_status are carried through unmodified for
    continuity with the faculty-wide report, but they are near-constant in
    practice - see LEAD_OWNED_SECTIONS - so they describe rather than triage.

    Kept I/O-free: callers pass in database.get_readiness_courses_latest() and
    get_readiness_sections_latest().
    """
    columns = ['module_code', 'completeness_score', 'alignment_status',
               'expected_sections', 'visible_sections', 'hidden_sections',
               'deleted_sections', 'missing_sections', 'lead_sections_total',
               'lead_sections_ready', 'lead_sections_drafted',
               'lead_sections_not_started', 'lead_sections_outstanding',
               'drafted_sections', 'blocking_sections', 'section_states',
               'shell_count', 'template_version', 'snapshot_date']
    if df_courses is None or df_courses.empty:
        return pd.DataFrame(columns=columns)

    df = df_courses.copy()
    df['module_code'] = df['module_code'].astype(str).str.strip().str.upper()
    for col in ['expected_sections', 'visible_sections', 'hidden_sections',
                'deleted_sections', 'missing_sections', 'student_count']:
        df[col] = pd.to_numeric(df.get(col), errors='coerce').fillna(0).astype(int)
    df['completeness_score'] = pd.to_numeric(df.get('completeness_score'), errors='coerce')

    agg = df.groupby('module_code', sort=True).agg(
        # Worst shell wins on every count, so a module is never flattered by an
        # empty duplicate shell sitting beside the real taught course.
        expected_sections=('expected_sections', 'max'),
        visible_sections=('visible_sections', 'min'),
        hidden_sections=('hidden_sections', 'max'),
        deleted_sections=('deleted_sections', 'max'),
        missing_sections=('missing_sections', 'max'),
        completeness_score=('completeness_score', 'min'),
        shell_count=('expected_sections', 'size'),
        snapshot_date=('snapshot_date', 'max'),
    ).reset_index()

    # The shell a student is most likely to be looking at: most enrolled, then
    # most of the template visible. Sources the descriptive fields.
    primary = (df.sort_values(['student_count', 'visible_sections'], ascending=False)
                 .groupby('module_code', sort=True).first())
    for col in ['alignment_status', 'template_version']:
        agg[col] = primary[col].reindex(agg['module_code']).fillna("").astype(str).values

    section_states = _readiness_section_states(df, df_sections)
    agg['section_states'] = agg['module_code'].map(section_states).apply(
        lambda v: v if isinstance(v, dict) else {})

    def _lead_in_state(states, wanted):
        return [k for k in LEAD_OWNED_SECTIONS
                if states.get(k, {}).get('state') in wanted]

    def _labels(keys):
        return [TEMPLATE_SECTIONS.get(k, (k,))[0] for k in keys]

    def _blocking(states):
        # Deleted and Missing sections are structural faults rather than
        # unfinished work, and Deleted ones drop out of the export's own hidden
        # list, so they are surfaced separately from the lead worklist.
        return [f"{TEMPLATE_SECTIONS.get(k, (k,))[0]} ({v.get('status')})"
                for k, v in states.items()
                if v.get('status') in ('Deleted', 'Missing')]

    agg['lead_sections_total'] = len(LEAD_OWNED_SECTIONS)
    agg['lead_sections_ready'] = agg['section_states'].apply(
        lambda s: len(_lead_in_state(s, READINESS_READY_STATES)))
    # Worked on and still hidden. Counted apart from "not started" because the
    # remedy is different and much smaller: the content exists, it just needs
    # making visible.
    agg['lead_sections_drafted'] = agg['section_states'].apply(
        lambda s: len(_lead_in_state(s, ('drafted_hidden',))))
    agg['lead_sections_not_started'] = agg['section_states'].apply(
        lambda s: len(_lead_in_state(s, ('not_started',))))
    agg['lead_sections_outstanding'] = agg['section_states'].apply(
        lambda s: _labels(_lead_in_state(s, ('drafted_hidden', 'not_started',
                                             'deleted', 'missing', 'unknown'))))
    agg['drafted_sections'] = agg['section_states'].apply(
        lambda s: _labels(_lead_in_state(s, ('drafted_hidden',))))
    agg['blocking_sections'] = agg['section_states'].apply(_blocking)
    return agg[columns]

def _readiness_section_states(df_courses, df_sections):
    """
    {module_code: {section_key: {'status', 'last_modified', 'evidence'}}}.

    Status is combined worst-wins across a module's shells; last_modified takes
    the most recent, and the evidence classification is recomputed from that
    pair rather than carried over from whichever shell won.
    """
    if df_sections is None or df_sections.empty:
        return {}

    s = df_sections.copy()
    s['module_code'] = s['module_code'].astype(str).str.strip().str.upper()
    s['status'] = s['status'].astype(str).str.strip()
    s['last_modified'] = s['last_modified'].astype(str).str.strip()
    s = s[s['status'] != ""]
    if s.empty:
        return {}

    bulk_dates = detect_bulk_edit_dates(s)

    # Earliest creation date across a module's shells - the date against which
    # "never modified" is judged.
    created = {}
    if df_courses is not None and not df_courses.empty and 'course_created_date' in df_courses:
        c = df_courses[['module_code', 'course_created_date']].copy()
        c['module_code'] = c['module_code'].astype(str).str.strip().str.upper()
        c['course_created_date'] = c['course_created_date'].astype(str).str.strip()
        c = c[c['course_created_date'] != ""]
        created = c.groupby('module_code')['course_created_date'].min().to_dict()

    s['rank'] = s['status'].map(READINESS_SECTION_RANK).fillna(len(READINESS_SECTION_RANK))
    grouped = s.groupby(['module_code', 'section_key']).agg(
        rank=('rank', 'min'), last_modified=('last_modified', 'max')).reset_index()
    rank_to_status = {v: k for k, v in READINESS_SECTION_RANK.items()}

    states = {}
    for row in grouped.itertuples(index=False):
        status = rank_to_status.get(row.rank, "")
        school = row.module_code[:3]
        is_bulk = (school, row.last_modified) in bulk_dates
        evidence = classify_edit_evidence(
            row.last_modified, created.get(row.module_code, ""), is_bulk)
        states.setdefault(row.module_code, {})[row.section_key] = {
            'status': status,
            'last_modified': row.last_modified,
            'evidence': evidence,
            'state': classify_section_state(status, evidence),
        }
    return states

def summarise_ally_issues(df_issues, module_codes=None, top_n=None):
    """
    Rolls long issue rows up by check, newest-first by weight of the problem.

    `items` is the number of content items affected, so summing it across
    modules gives the size of the job rather than a count of modules with a
    complaint. LibraryReference is excluded - it marks library-sourced content,
    not a defect.

    Kept I/O-free: callers pass in database.get_ally_issues_latest().
    """
    columns = ['check_name', 'label', 'severity', 'severity_label', 'surface',
               'advice', 'items', 'modules']
    if df_issues is None or df_issues.empty:
        return pd.DataFrame(columns=columns)

    df = df_issues.copy()
    df = df[df['check_name'] != 'LibraryReference']
    if module_codes is not None:
        scope = {str(c).strip().upper() for c in module_codes if str(c).strip()}
        df = df[df['module_code'].astype(str).str.strip().str.upper().isin(scope)]
    if df.empty:
        return pd.DataFrame(columns=columns)

    df['items'] = pd.to_numeric(df['items'], errors='coerce').fillna(0)
    grouped = (df.groupby('check_name', as_index=False)
                 .agg(severity=('severity', 'min'),
                      items=('items', 'sum'),
                      modules=('module_code', 'nunique')))
    grouped['label'] = grouped['check_name'].map(lambda c: ALLY_CHECKS.get(c, (c, 'file', ''))[0])
    grouped['surface'] = grouped['check_name'].map(lambda c: ALLY_CHECKS.get(c, (c, 'file', ''))[1])
    grouped['advice'] = grouped['check_name'].map(lambda c: ALLY_CHECKS.get(c, (c, 'file', ''))[2])
    grouped['severity_label'] = grouped['severity'].map(
        lambda s: ALLY_SEVERITY_LABELS.get(int(s), "Other") if pd.notna(s) else "Other")
    grouped['items'] = grouped['items'].astype(int)

    grouped = grouped.sort_values(['severity', 'items'], ascending=[True, False])
    if top_n:
        grouped = grouped.head(top_n)
    return grouped[columns].reset_index(drop=True)

def count_ally_issues_by_module(df_issues):
    """Per-module severe/major/minor totals, for the derived actionable items."""
    columns = ['module_code', 'severe', 'major', 'minor']
    if df_issues is None or df_issues.empty:
        return pd.DataFrame(columns=columns)

    df = df_issues.copy()
    df = df[df['check_name'] != 'LibraryReference']
    if df.empty:
        return pd.DataFrame(columns=columns)

    df['module_code'] = df['module_code'].astype(str).str.strip().str.upper()
    df['items'] = pd.to_numeric(df['items'], errors='coerce').fillna(0)
    df['severity'] = pd.to_numeric(df['severity'], errors='coerce')

    out = df.pivot_table(index='module_code', columns='severity', values='items',
                         aggfunc='sum', fill_value=0)
    out = out.rename(columns={1.0: 'severe', 2.0: 'major', 3.0: 'minor'})
    for col in ['severe', 'major', 'minor']:
        if col not in out.columns:
            out[col] = 0
    return out.reset_index()[columns].astype({'severe': int, 'major': int, 'minor': int})

def reconcile_ally_modules(ally_codes, sits_codes):
    """
    Which Ally courses and SITS modules failed to meet each other.

    Roughly a twentieth of the Ally rows are programme-level or community
    shells that SITS has never heard of, and a handful of SITS modules have no
    Blackboard course at all. Both used to vanish at import; neither should.
    """
    # Not `ally_codes or []` - these arrive as Series as often as lists, and a
    # Series has no truth value.
    ally = {str(c).strip().upper() for c in (ally_codes if ally_codes is not None else []) if str(c).strip()}
    sits = {str(c).strip().upper() for c in (sits_codes if sits_codes is not None else []) if str(c).strip()}
    return {'matched': sorted(ally & sits),
            'ally_only': sorted(ally - sits),
            'sits_only': sorted(sits - ally)}

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

    has_ally = 'Ally Overall' in df.columns

    def _ally_pct(frame):
        """Mean Ally score over built courses only, as a percentage.

        Courses still holding their rolled-over template score close to 100% on
        a couple of dozen template items. Averaging those in would band every
        school green through the autumn, which is exactly the reading this
        column exists to prevent.
        """
        if not has_ally or frame.empty:
            return None
        scored = frame
        if 'Content Maturity' in frame.columns:
            scored = frame[frame['Content Maturity'] == "In progress"]
        values = pd.to_numeric(scored['Ally Overall'], errors='coerce').dropna()
        return float(values.mean()) * 100 if not values.empty else None

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

        avg_ally = _ally_pct(school_df)

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
    faculty_ally = _ally_pct(df)

    totals = {
        'Modules': total_modules,
        'Audited': total_audited,
        'Audited %': (total_audited / total_modules * 100) if total_modules else 0.0,
        'Avg Ally': faculty_ally,
        'VLE Compliance': (faculty_passed / faculty_scored * 100) if faculty_scored else None,
    }

    return result, totals

# --- Unified module findings ------------------------------------------------
#
# "What's outstanding on this module" used to be computed independently in
# three places - app.py's Actionable Items badge, module_report.py's checklist
# worklist, and module_report.py's health banner - each covering a different
# subset of sources by hand. They disagreed: the Actionable Items badge never
# counted a Leganto list stuck in Draft, never counted template readiness at
# all, and undercounted legacy free-text custom observations that the module
# report page showed as cards. This is the one place that decides "is this a
# pending or completed finding" for every source; every consumer reads from it
# instead of recomputing its own answer.
#
# Item dicts use the exact shape views/module_report.py's card renderers
# already expect (type: 'boolean'/'tag'/'legacy_tag'/'custom', with the keys
# each type needs), plus 'source' and 'state' as the only new keys - so nothing
# downstream needed new rendering code, only a new place to get the list from.

def readiness_manual_override(audit_field_id, responses):
    """
    Whether a Digital Learning Advisor's own audit answer should override a
    lead-owned template section's data-driven ready/not-ready read.

    Returns True/False - the human verdict - when the module has a real,
    recorded answer for audit_field_id; None when there is nothing to
    override with (no mapping, or the field has never been answered), in
    which case the caller falls back to the raw readiness state.

    Unconditional on whether the answer agrees with the data: once an
    advisor has recorded a verdict (a full audit, or closing out a
    spot-check - see "Spot-check flagging" in CLAUDE.md), that verdict is
    what happened, and the readiness snapshot becomes context for it rather
    than a rival source of truth that can go on contradicting it on screen.
    Before this, a module's Blackboard Template block and its own completed
    checklist cards could show the same section as both "Not started" and
    "Complete" at once - the data hadn't caught up with what the advisor had
    actually verified.
    """
    if not audit_field_id:
        return None
    val = (responses or {}).get(audit_field_id)
    if val is None or str(val).strip() == '':
        return None
    return str(val).strip().upper() == 'TRUE'


def derive_module_findings(active_row, responses, active_fields, comment_bank):
    """
    Every checklist, Leganto, Ally and template-readiness finding for one
    module, as one flat list of {'source', 'state', 'type', ...} dicts.

    'source' is 'checklist' | 'leganto' | 'ally' | 'readiness'.
    'state' is 'pending' | 'completed'.

    active_row: the module's row from df_aut/df_spr (or an equivalent dict) -
    needs 'Leganto Missing', 'Leganto List Status', 'Leganto List Items',
    'Ally Severe', 'Ally Enabled', 'Template Sections'. Missing keys degrade
    gracefully to "nothing from that source" rather than raising, since a
    module can legitimately be absent from any one of these datasets.
    responses: {field_id: value} for this module, from audit_responses.
    active_fields, comment_bank: from get_active_audit_fields() /
    get_comment_bank() - passed in rather than fetched here to keep this
    I/O-free and callable once per module without re-querying each time.

    Only Ally and readiness findings are never rendered as generic cards -
    both already have their own richer, source-specific display (the Ally
    issue breakdown, the Blackboard Template section block) - but they are
    still produced here so every consumer that only wants the *count* agrees
    with what those richer views show, which previously nothing guaranteed.
    """
    findings = []

    # --- checklist: one finding per active audit field -----------------
    if active_fields:
        compliant_tag_ids = {c['id'] for c in (comment_bank or [])
                             if "Compliant" in c.get('category', '') or "No action needed" in c.get('advice', '')}
        cb_lookup = {c['id']: c for c in (comment_bank or [])}

        for field in active_fields:
            fid = field['id']
            label = field['label']
            action_label = field.get('action_label') or label
            desc = field['description']
            ftype = field['field_type']
            val = (responses or {}).get(fid, None)

            if ftype in ('boolean', 'yes/no'):
                is_compliant = (str(val).upper() == 'TRUE' if ftype == 'boolean'
                               else str(val).upper() == 'YES')
                findings.append({
                    'source': 'checklist',
                    'state': 'completed' if is_compliant else 'pending',
                    'type': 'boolean',
                    'label': label if is_compliant else action_label,
                    'description': desc,
                })
            elif ftype == 'text' and val:
                custom_val = val
                tags = []
                try:
                    data = json.loads(val)
                    if isinstance(data, dict):
                        tags = data.get("tags", [])
                        custom_val = data.get("custom", "")
                except Exception:
                    pass  # legacy plain-text value - falls through to parse_custom_observations below

                for tag_id in tags:
                    tag_info = cb_lookup.get(tag_id)
                    if tag_info:
                        is_compliant = tag_id in compliant_tag_ids
                        findings.append({
                            'source': 'checklist',
                            'state': 'completed' if is_compliant else 'pending',
                            'type': 'tag',
                            'category': tag_info.get('category', 'General'),
                            'comment': tag_info.get('comment', ''),
                            'advice': tag_info.get('advice', ''),
                            'resource_url': tag_info.get('resource_url', ''),
                            'resource_text': tag_info.get('resource_text', ''),
                        })
                    else:
                        findings.append({
                            'source': 'checklist', 'state': 'pending',
                            'type': 'legacy_tag', 'comment': str(tag_id),
                        })

                for obs in parse_custom_observations(custom_val):
                    findings.append({
                        'source': 'checklist', 'state': 'pending',
                        'type': 'custom', 'category': label,
                        'label': obs.get('observation', ''),
                        'description': obs.get('action', ''),
                    })

    # --- leganto: at most one finding, missing/draft/published/connected -
    row = active_row if active_row is not None else {}
    leganto_missing = bool(row.get('Leganto Missing'))
    leganto_status = str(row.get('Leganto List Status', '') or '').strip()
    leganto_items = int(row.get('Leganto List Items', 0) or 0)
    leganto_draft = leganto_status in ('Draft', 'Mixed')

    if leganto_missing:
        findings.append({
            'source': 'leganto', 'state': 'pending', 'type': 'boolean',
            'label': 'Leganto Reading List Missing',
            'description': "This module doesn't have a reading list connected in Leganto yet.",
        })
    elif leganto_draft:
        findings.append({
            'source': 'leganto', 'state': 'pending', 'type': 'boolean',
            'label': 'Leganto Reading List Not Published',
            'description': (f"This module's Leganto list has {leganto_items} item"
                            f"{'s' if leganto_items != 1 else ''} but is still in Draft "
                            "- not visible to students yet."),
        })
    elif leganto_status == 'Published':
        findings.append({
            'source': 'leganto', 'state': 'completed', 'type': 'boolean',
            'label': 'Leganto Reading List: Published',
            'description': f"Published in Leganto with {leganto_items} item{'s' if leganto_items != 1 else ''}.",
        })
    else:
        findings.append({
            'source': 'leganto', 'state': 'completed', 'type': 'boolean',
            'label': 'Leganto Reading List: OK / Connected',
            'description': 'The module has a reading list connected in Leganto.',
        })

    # --- ally: two binary flags, matching the accessibility card's own
    # severe/disabled signal. Emitted only when true - nothing consumes an
    # "Ally is fine" completed finding, since the accessibility card already
    # shows that state richly.
    if int(row.get('Ally Severe', 0) or 0) > 0:
        findings.append({
            'source': 'ally', 'state': 'pending', 'type': 'boolean',
            'label': 'Severe accessibility issue found by Ally',
            'description': 'See the Accessibility Issues card for detail and advice.',
        })
    if row.get('Ally Enabled') is False:
        findings.append({
            'source': 'ally', 'state': 'pending', 'type': 'boolean',
            'label': 'Ally is switched off for this course',
            'description': 'Accessibility scanning is disabled, so no score is available.',
        })

    # --- readiness: one finding per lead-owned section (ready or not), plus
    # any institutional section that is deleted or missing. Institutional
    # sections that are simply hidden are not findings at all - see
    # TEMPLATE_SECTIONS and SECTION_STATES for why.
    section_states = row.get('Template Sections') or {}
    for key, sec in section_states.items():
        info = TEMPLATE_SECTIONS.get(key)
        if info is None:
            continue
        section_label, owner, audit_field_id = info
        state_key = sec.get('state', 'unknown')
        badge, tier, action = SECTION_STATES.get(state_key, SECTION_STATES['unknown'])

        if owner == 'lead':
            manual = readiness_manual_override(audit_field_id, responses)
            is_ready = manual if manual is not None else (state_key in READINESS_READY_STATES)
            findings.append({
                'source': 'readiness',
                'state': 'completed' if is_ready else 'pending',
                'type': 'boolean',
                'label': f"{section_label}: {badge}",
                'description': action,
                'audit_field_id': audit_field_id,
                'manual_override': manual,
            })
        elif state_key in ('deleted', 'missing'):
            findings.append({
                'source': 'readiness', 'state': 'pending', 'type': 'boolean',
                'label': f"{section_label}: {badge}",
                'description': action,
                'audit_field_id': audit_field_id,
            })

    return findings

    return result, totals

def compute_audit_verdict(active_fields, responses):
    """
    Ready / Not Ready / Blank verdict for one module, from whichever
    audit_fields carry is_gating=1: 'blank' if any gating field has no saved
    response yet (checked first - blank wins even if another gating field is
    already answered false), 'not_ready' if any gating field's value isn't
    the compliant one, else 'ready'. Returns None if no field is currently
    flagged is_gating, so the feature is a no-op until an admin opts a field
    in via the Audit Field Manager - no field ids are assumed here.

    active_fields: list of dicts as returned by get_audit_fields()/
    get_active_audit_fields() - needs 'id', 'field_type', 'is_gating'.
    responses: {field_id: value_string} - the same flat shape
    derive_module_findings() takes, not get_audit_responses()'s
    {field_id: {'value':...}} shape; callers holding the latter must flatten
    it first.
    """
    gating_fields = [f for f in (active_fields or [])
                      if f.get('is_gating') and f.get('field_type') in ('boolean', 'yes/no')]
    if not gating_fields:
        return None

    for f in gating_fields:
        if (responses or {}).get(f['id']) is None:
            return 'blank'

    for f in gating_fields:
        val = (responses or {}).get(f['id'])
        is_compliant = (str(val).upper() == 'TRUE' if f['field_type'] == 'boolean'
                        else str(val).upper() == 'YES')
        if not is_compliant:
            return 'not_ready'

    return 'ready'

def readiness_created_date(states):
    """Approximate course creation date from the section states themselves:
    any lead-owned section whose evidence is 'never_modified' has a
    last_modified equal to the course's creation date, since that is the only
    way 'never_modified' can be reached. Returns None if no such section is
    present (e.g. every lead-owned section has already been touched).
    """
    for key in LEAD_OWNED_SECTIONS:
        state = states.get(key, {})
        if state.get('evidence') == 'never_modified':
            return state.get('last_modified')
    return None

def readiness_prefill_for_module(active_row):
    """
    Audit Portal checklist suggestions for one module, from the same section
    states derive_module_findings() already classifies.

    Returns {audit_field_id: {'suggested': bool, 'evidence_text': str,
    'section_key': str}} - one entry per TEMPLATE_SECTIONS section that maps
    to an audit field (7 of 14 sections today; the rest have no audit_fields
    counterpart and are not suggested on at all).

    'suggested' is True whenever the section is Visible (state in
    READINESS_READY_STATES). This is a status question - "can a student see
    it" - not a "did the lead do this personally" question, and applies alike
    to the 3 lead-owned fields and the 4 institution-owned-but-mapped ones: a
    batch-dated lead-owned section is frequently genuine work by someone other
    than the lead (see READINESS_READY_STATES), and institutional sections
    were never the lead's to edit in the first place. evidence_text still
    names which case it is, so the advisor is never just told "checked" with
    no reason.

    A module with no readiness data at all (active_row is None, or has no
    'Template Sections') returns an empty dict. Callers must treat a missing
    audit_field_id as "no suggestion, use the ordinary default" - never as
    "suggest unticked" - so the Audit Portal degrades to today's blank-form
    behaviour outside the readiness data's coverage.
    """
    row = active_row if active_row is not None else {}
    states = row.get('Template Sections') or {}
    if not isinstance(states, dict) or not states:
        return {}

    created = readiness_created_date(states)
    prefill = {}
    for key, sec in states.items():
        info = TEMPLATE_SECTIONS.get(key)
        if info is None:
            continue
        _label, _owner, audit_field_id = info
        if not audit_field_id:
            continue
        prefill[audit_field_id] = {
            'suggested': sec.get('state', 'unknown') in READINESS_READY_STATES,
            'evidence_text': readiness_evidence_words(sec, created),
            'section_key': key,
        }
    return prefill

def build_spot_check_snapshot(active_row, actionable_items):
    """
    The frozen record of what the data said about a module at the moment a
    DLA flagged it for spot-check: readiness_prefill_for_module()'s
    suggestions plus the Actionable Items count, as JSON for
    database.flag_module_for_spot_check().

    Comparing an advisor's later Audit Portal answers against this rather
    than against live data means agreement is measured against what they
    were actually shown when they chose the module, not against whatever
    the data has since become.
    """
    return json.dumps({
        'actionable_items': int(actionable_items or 0),
        'prefill': readiness_prefill_for_module(active_row),
    })

def compute_spot_check_agreement(data_verdict_snapshot, saved_responses):
    """
    Diffs a spot-check's frozen snapshot (from build_spot_check_snapshot())
    against what the DLA who flagged it actually saved for the module - one
    comparison per readiness-mapped field the module had a suggestion for.

    saved_responses: {audit_field_id: value}, the same shape
    database.get_audit_responses() values come in - value truthy-compared as
    'TRUE' (case-insensitive), so both the string form used for storage and
    a raw Python bool from an in-memory checkbox work identically.

    A field the snapshot had a suggestion for but that is missing from
    saved_responses (e.g. the audit field has since been deactivated) is
    excluded rather than counted as disagreement - there is no signal to
    compare, and silently counting it would understate agreement for a
    reason that has nothing to do with whether the advisor agreed with the
    data.

    Returns {'agreed': int, 'total': int, 'detail': [...]}. 'total' is 0
    (never None) when the module had no mapped-field suggestions at all -
    callers must treat that as "nothing measurable", not divide by it.
    """
    try:
        snapshot = json.loads(data_verdict_snapshot) if data_verdict_snapshot else {}
    except (TypeError, ValueError):
        snapshot = {}
    prefill = snapshot.get('prefill') or {}
    saved_responses = saved_responses or {}

    detail = []
    for field_id, suggestion in prefill.items():
        if field_id not in saved_responses:
            continue
        suggested = bool(suggestion.get('suggested'))
        actual = str(saved_responses[field_id]).strip().upper() == 'TRUE'
        detail.append({
            'audit_field_id': field_id,
            'suggested': suggested,
            'actual': actual,
            'agreed': actual == suggested,
        })

    return {'agreed': sum(1 for d in detail if d['agreed']),
            'total': len(detail), 'detail': detail}
