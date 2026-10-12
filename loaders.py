"""
Assembles the module list every view is built from, with no Streamlit in it.

This is the layer between `database.py` (SQL) and `processing.py` (I/O-free
pandas): it runs the queries, hands the frames to the aggregation functions,
and builds one record per module in the shape the views and
`processing.derive_module_findings()` expect.

It used to live inside `app.py::load_audit_data()`, wrapped in
`@st.cache_data` in a module that configures Streamlit pages at import time,
so nothing but a running Streamlit script could call it. That made the module
row impossible to test and impossible to reuse: the Django spike under `web/`
had to duplicate the mapping to render a single module. Extracted 05-10-2026.

- `app.py::load_audit_data()` is now a thin `@st.cache_data` wrapper around
  `load_audit_frames()`. The caching stays in `app.py`, because that is
  Streamlit's concern, not this module's.
- `load_module_record()` builds one module's row without assembling the whole
  faculty, for a caller that only needs one.
- Nothing here touches `st.*`. Keep it that way: the point of the extraction
  is that a second front end, a script or a test can call it.

The record's keys are a contract with the views and with
`derive_module_findings()`, whose docstring lists the ones it reads. Several
are transitional aliases for views not yet moved onto the current names.
"""

import logging
from dataclasses import dataclass, field

import pandas as pd

import database
import processing
from processing import CURRENT_ACADEMIC_YEAR

# Period codes as SITS writes them. Anything unrecognised falls to Spring,
# which is the behaviour this replaced - deliberately not an error, since a
# new period code should not empty the module list.
AUTUMN_PERIODS = {'S1', 'ED1', 'N19', 'N21', 'ISS1'}
SPRING_PERIODS = {'S2', 'ED2', 'N27', 'N28', 'MDE2'}
ALL_YEAR_PERIODS = {'AY', 'FY', 'TRI', 'X4'}

LEVEL_LABELS = {
    'F': 'Foundation',
    '4': 'UG Level 1',
    '5': 'UG Level 2',
    '6': 'UG Level 3',
    '7': 'PGT',
    '8': 'PGR',
}


def map_level_value(val):
    """SITS module level to the label the views show."""
    if pd.isna(val):
        return ''
    s = str(val).strip()
    if s.lower() in ('nan', 'none', ''):
        return ''
    return LEVEL_LABELS.get(s.upper(), s)


def semester_for_period(period):
    """Autumn / Spring / All year for a SITS period code."""
    code = str(period or '').strip().upper()
    if code in AUTUMN_PERIODS:
        return 'Autumn'
    if code in SPRING_PERIODS:
        return 'Spring'
    if code in ALL_YEAR_PERIODS:
        return 'All year'
    return 'Spring'


@dataclass
class ModuleSources:
    """
    Everything needed to build module records, read once per load.

    The lookups are keyed by module code. The frames are the course-grain
    detail the views need behind the headline numbers, returned unchanged.
    """

    ref_lookup: dict = field(default_factory=dict)
    ally_map: dict = field(default_factory=dict)
    ally_issue_map: dict = field(default_factory=dict)
    leganto_lists_map: dict = field(default_factory=dict)
    leganto_missing_set: set = field(default_factory=set)
    # True when the leganto_nolist export has been imported at all. When it
    # has not, 'Leganto Missing' falls back to the legacy audit tables rather
    # than reading every module as having a list.
    leganto_nolist_available: bool = False
    blackboard_links_map: dict = field(default_factory=dict)
    readiness_map: dict = field(default_factory=dict)
    sga_map: dict = field(default_factory=dict)
    sga_loaded: bool = False
    inactive_codes: set = field(default_factory=set)

    df_ally_courses: pd.DataFrame = field(default_factory=pd.DataFrame)
    df_ally_issues: pd.DataFrame = field(default_factory=pd.DataFrame)
    df_ally_content: pd.DataFrame = field(default_factory=pd.DataFrame)
    df_readiness_sections: pd.DataFrame = field(default_factory=pd.DataFrame)
    df_sga: pd.DataFrame = field(default_factory=pd.DataFrame)

    @property
    def detail_frames(self):
        """The five frames load_audit_frames() returns after df_aut/df_spr."""
        return (self.df_ally_courses, self.df_ally_issues, self.df_ally_content,
                self.df_readiness_sections, self.df_sga)


def _index_by_module(df):
    """A module-grain frame as {module_code: {column: value}}."""
    if df is None or df.empty or 'module_code' not in df.columns:
        return {}
    return df.set_index('module_code').to_dict(orient='index')


def _upper_code_set(df, column='module_code'):
    if df is None or df.empty or column not in df.columns:
        return set()
    return set(df[column].astype(str).str.strip().str.upper())


def load_module_sources():
    """
    Every lookup and detail frame needed to build module records.

    One call does all the I/O, so build_module_record() stays pure and a
    caller assembling many modules pays for the queries once.
    """
    with database.get_db_connection() as conn:
        legacy_aut = (pd.read_sql_query("SELECT * FROM main_vle_audit_aut", conn)
                      if database.table_exists(conn, "main_vle_audit_aut") else pd.DataFrame())
        legacy_spr = (pd.read_sql_query("SELECT * FROM main_vle_audit_spr", conn)
                      if database.table_exists(conn, "main_vle_audit_spr") else pd.DataFrame())
        df_leganto_nolist = (pd.read_sql_query("SELECT * FROM leganto_nolist", conn)
                             if database.table_exists(conn, "leganto_nolist") else pd.DataFrame())
        df_blackboard_links = (pd.read_sql_query(
            "SELECT * FROM blackboard_links WHERE academic_year = ?", conn,
            params=(CURRENT_ACADEMIC_YEAR,))
            if database.table_exists(conn, "blackboard_links") else pd.DataFrame())
        df_inactive = (pd.read_sql_query("SELECT module_code FROM inactive_modules", conn)
                       if database.table_exists(conn, "inactive_modules") else pd.DataFrame())

    # Legacy audit tables, for reference columns the SITS export does not carry.
    ref_lookup = {}
    legacy_dfs = [df for df in (legacy_aut, legacy_spr) if not df.empty]
    if legacy_dfs:
        legacy_combined = pd.concat(legacy_dfs, ignore_index=True)
        if 'New module code' in legacy_combined.columns:
            legacy_combined['New module code'] = (
                legacy_combined['New module code'].astype(str).str.strip().str.upper())
            legacy_combined = legacy_combined.drop_duplicates(subset=['New module code'])
            ref_lookup = legacy_combined.set_index('New module code').to_dict(orient='index')

    blackboard_links_map = {}
    if not df_blackboard_links.empty and 'module_code' in df_blackboard_links.columns:
        links = df_blackboard_links.copy()
        links['module_code'] = links['module_code'].astype(str).str.strip().str.upper()
        blackboard_links_map = dict(zip(links['module_code'], links['blackboard_link']))

    # Ally, Leganto, readiness and SGA: course grain in the database, rolled up
    # to module grain here, never at import time. Current academic year only -
    # a prior-year snapshot shown against this year's module list is how the
    # old dashboard came to overstate what had been measured.
    df_ally_courses = database.get_ally_courses_latest(CURRENT_ACADEMIC_YEAR)
    df_ally_issues = database.get_ally_issues_latest(CURRENT_ACADEMIC_YEAR)
    df_ally_content = database.get_ally_content_latest(CURRENT_ACADEMIC_YEAR)

    df_readiness_courses = database.get_readiness_courses_latest(CURRENT_ACADEMIC_YEAR)
    df_readiness_sections = database.get_readiness_sections_latest(CURRENT_ACADEMIC_YEAR)

    sga_loaded = database.sga_imported(CURRENT_ACADEMIC_YEAR)
    df_sga = processing.explode_sga_mappings(
        database.get_sga_mappings(CURRENT_ACADEMIC_YEAR))

    return ModuleSources(
        ref_lookup=ref_lookup,
        ally_map=_index_by_module(processing.aggregate_ally_to_modules(df_ally_courses)),
        ally_issue_map=_index_by_module(
            processing.count_ally_issues_by_module(df_ally_issues)),
        leganto_lists_map=_index_by_module(processing.aggregate_leganto_to_modules(
            database.get_leganto_lists_latest(CURRENT_ACADEMIC_YEAR))),
        leganto_missing_set=_upper_code_set(df_leganto_nolist),
        leganto_nolist_available=not df_leganto_nolist.empty,
        blackboard_links_map=blackboard_links_map,
        readiness_map=_index_by_module(processing.aggregate_readiness_to_modules(
            df_readiness_courses, df_readiness_sections)),
        sga_map=_index_by_module(processing.aggregate_sga_to_modules(df_sga)),
        sga_loaded=sga_loaded,
        inactive_codes=_upper_code_set(df_inactive),
        df_ally_courses=df_ally_courses,
        df_ally_issues=df_ally_issues,
        df_ally_content=df_ally_content,
        df_readiness_sections=df_readiness_sections,
        df_sga=df_sga,
    )


def build_module_record(sits_row, sources):
    """
    One module's record, from its SITS row plus the shared lookups.

    No I/O: everything comes from `sources`. The keys are the contract the
    views and derive_module_findings() read - see the module docstring.
    """
    code = str(sits_row.get('CIS unit code', '')).strip().upper()
    ref_fields = sources.ref_lookup.get(code, {})

    ally = sources.ally_map.get(code, {})
    issue_counts_row = sources.ally_issue_map.get(code, {})

    def _score(key):
        val = pd.to_numeric(ally.get(key), errors='coerce')
        return None if pd.isna(val) else float(val)

    overall_score = _score('overall_score')
    files_score = _score('files_score')
    wysiwyg_score = _score('wysiwyg_score')

    # Leganto Missing: the dedicated export when it has been imported,
    # otherwise the legacy audit tables' own column, which may be a string.
    if not sources.leganto_nolist_available:
        leganto_missing = ref_fields.get('Leganto Missing', False)
        if str(leganto_missing).upper() in ['TRUE', '1']:
            leganto_missing = True
        elif str(leganto_missing).upper() in ['FALSE', '0', '']:
            leganto_missing = False
    else:
        leganto_missing = code in sources.leganto_missing_set

    # Reading-list status/items for modules that DO have a list. Blank status
    # means the module isn't in that export at all - not the same as
    # 'Leganto Missing' above, which is an explicit export of modules
    # confirmed to have no list.
    leganto_list = sources.leganto_lists_map.get(code, {})

    # Template alignment. 'Lead Sections Ready' is the part that discriminates:
    # the vendor completeness score restates the visible section count, and
    # after a rollover almost every module sits on the same one. Blank rather
    # than zero where the module is absent from the report, so "not measured"
    # never reads as "nothing done".
    readiness = sources.readiness_map.get(code, {})
    readiness_score = pd.to_numeric(readiness.get('completeness_score'), errors='coerce')

    sga = sources.sga_map.get(code, {})

    return {
        'New module code': code,
        'Module name': sits_row.get('Module name', ''),
        'Mod. lead': sits_row.get('Academic contact', ''),
        'Prog. lead': ref_fields.get('Prog. lead', ''),
        'UG/ PG/ Other': map_level_value(sits_row.get('Module level', '')),
        'URL': sources.blackboard_links_map.get(code, ref_fields.get('URL', '')),
        'Semester': semester_for_period(sits_row.get('Period', '')),

        # Ally's own three scores, unmodified. The credibility-weighted
        # 'Ally Weighted' this replaced was a local invention that shrank
        # small courses toward 50%, which on a rolled-over year of template
        # content moved the faculty mean by 30 points.
        'Ally Overall': overall_score,
        'Ally Files': files_score,
        'Ally WYSIWYG': wysiwyg_score,
        'Total Files': int(ally.get('total_files', 0) or 0),
        'Ally WYSIWYG Items': int(ally.get('total_wysiwyg', 0) or 0),
        'Ally Items': int(ally.get('total_items', 0) or 0),
        'Ally Students': int(ally.get('students', 0) or 0),
        'Ally Enabled': bool(ally.get('ally_enabled', 1)),
        'Ally Last Checked': ally.get('last_checked_on', ''),
        'Ally Shells': int(ally.get('shell_count', 0) or 0),
        'Content Maturity': ally.get('content_maturity', "No data"),
        'Ally Severe': int(issue_counts_row.get('severe', 0) or 0),
        'Ally Major': int(issue_counts_row.get('major', 0) or 0),
        'Ally Minor': int(issue_counts_row.get('minor', 0) or 0),

        # Transitional aliases for views not yet moved onto the names above.
        # 'Ally 25/26 All' in particular is a hardcoded year that should not
        # outlive this migration.
        'Ally Measured': files_score,
        'Ally Weighted': overall_score,
        'Ally 25/26 All': overall_score,

        'Leganto Missing': leganto_missing,
        'Leganto List Status': leganto_list.get('status', ''),
        'Leganto List Items': int(leganto_list.get('total_items', 0) or 0),
        'Leganto Draft Items': int(leganto_list.get('draft_items', 0) or 0),
        'Leganto Snapshot': leganto_list.get('snapshot_date', ''),

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
        'Lead Sections Outstanding': list(readiness.get('lead_sections_outstanding') or []),
        'Drafted Sections': list(readiness.get('drafted_sections') or []),
        'Template Blocking': list(readiness.get('blocking_sections') or []),
        'Template Sections': readiness.get('section_states') or {},
        'Readiness Snapshot': readiness.get('snapshot_date', ''),

        'SGA Attributes': int(sga.get('sga_attributes', 0)) if sources.sga_loaded else None,
        'SGA Sub-Attributes': (int(sga.get('sga_sub_attributes', 0))
                               if sources.sga_loaded else None),
        'SGA Attribute Names': sga.get('sga_attribute_names', ''),

        # Legacy audit columns, kept as reference.
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
        'Comments': ref_fields.get('Comments', ''),
    }


def assemble_module_frames(df_sits, sources):
    """
    (df_aut, df_spr) from the SITS export.

    A year-long module appears in *both* frames: that is what "All year"
    narrowing depends on downstream (see resolve_semester_df()). Inactive
    modules are dropped from both.
    """
    if df_sits.empty or 'CIS unit code' not in df_sits.columns:
        logging.warning("⚠️ sits_assessment_2026_27 is empty or missing 'CIS unit code'.")
        return pd.DataFrame(), pd.DataFrame()

    df_sits = df_sits.copy()
    df_sits['CIS unit code'] = df_sits['CIS unit code'].astype(str).str.strip().str.upper()
    unique_modules = df_sits.drop_duplicates(subset=['CIS unit code'])

    records = [build_module_record(row, sources)
               for _, row in unique_modules.iterrows()]
    df_all = pd.DataFrame(records)
    if df_all.empty:
        return pd.DataFrame(), pd.DataFrame()

    df_aut = df_all[df_all['Semester'] == 'Autumn'].copy()
    df_spr = df_all[df_all['Semester'] == 'Spring'].copy()
    df_all_year = df_all[df_all['Semester'] == 'All year'].copy()

    aut_dfs = [d for d in ([df_aut, df_all_year] if not df_all_year.empty else [df_aut])
               if not d.empty]
    spr_dfs = [d for d in ([df_spr, df_all_year] if not df_all_year.empty else [df_spr])
               if not d.empty]

    df_aut = pd.concat(aut_dfs, ignore_index=True) if aut_dfs else pd.DataFrame()
    df_spr = pd.concat(spr_dfs, ignore_index=True) if spr_dfs else pd.DataFrame()

    if sources.inactive_codes:
        if not df_aut.empty:
            df_aut = df_aut[~df_aut['New module code'].isin(sources.inactive_codes)].copy()
        if not df_spr.empty:
            df_spr = df_spr[~df_spr['New module code'].isin(sources.inactive_codes)].copy()
        logging.info(f"Filtered out {len(sources.inactive_codes)} inactive modules.")

    return df_aut, df_spr


def _legacy_frames():
    """
    The pre-SITS audit tables, for a database where the SITS import has never
    been run. Kept so a fresh or half-migrated database still shows something.
    """
    with database.get_db_connection() as conn:
        df_aut = (pd.read_sql_query("SELECT * FROM main_vle_audit_aut", conn)
                  if database.table_exists(conn, "main_vle_audit_aut") else pd.DataFrame())
        df_spr = (pd.read_sql_query("SELECT * FROM main_vle_audit_spr", conn)
                  if database.table_exists(conn, "main_vle_audit_spr") else pd.DataFrame())
    for df in (df_aut, df_spr):
        if not df.empty and 'UG/ PG/ Other' in df.columns:
            df['UG/ PG/ Other'] = df['UG/ PG/ Other'].map(map_level_value)
    return df_aut, df_spr


def load_audit_frames():
    """
    (df_aut, df_spr, ally_courses, ally_issues, ally_content,
    readiness_sections, sga) - the module list plus the course-grain detail
    frames the views read behind the headline numbers.

    Caching is the caller's business: app.py wraps this in @st.cache_data.
    """
    logging.info("📥 Constructing module list from SITS as single source of truth...")
    empty_detail = (pd.DataFrame(), pd.DataFrame(), pd.DataFrame(),
                    pd.DataFrame(), pd.DataFrame())
    try:
        with database.get_db_connection() as conn:
            if not database.table_exists(conn, "sits_assessment_2026_27"):
                logging.warning("⚠️ sits_assessment_2026_27 not found. Falling back to "
                                "legacy tables.")
                return _legacy_frames() + empty_detail
            df_sits = pd.read_sql_query("SELECT * FROM sits_assessment_2026_27", conn)

        sources = load_module_sources()
        df_aut, df_spr = assemble_module_frames(df_sits, sources)

        logging.info(f"✅ Successfully compiled SITS module list "
                     f"(Autumn: {len(df_aut)}, Spring: {len(df_spr)}).")
        return (df_aut, df_spr) + sources.detail_frames
    except Exception as e:
        logging.error(f"Error loading SITS audit data: {e}")
        return (pd.DataFrame(), pd.DataFrame()) + empty_detail


def load_module_record(code, sources=None):
    """
    One module's record, or None when the code is not in SITS for the current
    year. For a caller that needs a single module rather than the faculty -
    pass `sources` to reuse an already-loaded set of lookups.
    """
    code = str(code).strip().upper()
    with database.get_db_connection() as conn:
        if not database.table_exists(conn, "sits_assessment_2026_27"):
            return None
        df_sits = pd.read_sql_query(
            "SELECT * FROM sits_assessment_2026_27 "
            "WHERE UPPER(TRIM([CIS unit code])) = ?", conn, params=(code,))

    if df_sits.empty:
        return None

    sources = sources if sources is not None else load_module_sources()
    return build_module_record(df_sits.iloc[0], sources)


def _trail_from_rows(rows):
    """
    One module's saved audit from its audit_responses rows, as (field_id,
    value, auditor, timestamp) tuples in table order. Shared by the single
    module and whole-faculty paths so they cannot disagree.
    """
    if not rows:
        return {'responses': {}, 'last_saved': None, 'auditor': 'System',
                'has_audit': False}
    stamps = [t for _, _, _, t in rows if t]
    auditors = [a for _, _, a, _ in rows if a]
    auditor = auditors[-1] if auditors else 'Unknown'
    return {'responses': {fid: value for fid, value, _, _ in rows},
            'last_saved': max(stamps) if stamps else 'Unknown',
            'auditor': auditor,
            'has_audit': auditor not in (None, '', 'System')}


def load_audit_trail(code):
    """
    One module's saved audit, in the shapes the report reads:
    `{'responses', 'last_saved', 'auditor', 'has_audit'}`.

    `responses` is flat, {field_id: value}, which is what
    derive_module_findings() takes - not the nested rows
    database.get_audit_responses() returns. The rest mirrors what
    app.py::load_checklist_data() puts in `checklist_sums`: the latest
    timestamp, the last auditor, and `has_audit` meaning a real person saved
    an answer (a module with no rows is the data-only 'System' case, never
    audited). With rows but no auditor recorded the auditor reads 'Unknown',
    as there.
    """
    rows = database.get_audit_responses(code)
    return _trail_from_rows([(fid, r['value'], r['auditor'], r['timestamp'])
                             for fid, r in rows.items()])


def load_audit_trails():
    """{module_code: trail} for every module that has any saved answer, from
    one query rather than one per module."""
    df = database.get_all_audit_responses()
    if df.empty:
        return {}
    grouped = {}
    for rec in df[['module_code', 'field_id', 'value', 'auditor_username',
                   'timestamp']].itertuples(index=False):
        grouped.setdefault(str(rec[0]).strip().upper(), []).append(
            (rec[1], rec[2], rec[3], rec[4]))
    return {code: _trail_from_rows(rows) for code, rows in grouped.items()}


def audit_summary(row, trail, active_fields):
    """
    One module's audit status and outstanding-item count: the shape
    app.py::load_checklist_data() builds as `checklist_sums`, from the same
    full module row the module report reads.

    'Actionable Items' is the number of pending findings from
    processing.derive_module_findings(), so it agrees with the module report
    by construction. A module with no saved answers is counted on data alone
    (Leganto, Ally, readiness), with its checklist fields left out: about 1,560
    of ~1,570 modules have never been audited, and counting all eight checklist
    fields as pending for each would turn the figure into a constant. See
    "A never-audited module's checklist fields" in CLAUDE.md.
    """
    responses = trail['responses']
    audited = bool(responses)
    findings = processing.derive_module_findings(
        row, responses, active_fields if audited else [])
    pending = [f for f in findings if f['state'] == 'pending']

    audit_status = responses.get('audit_status', '')
    status = ("✅ Submitted" if audit_status == 'submitted'
              else "📝 Draft" if audit_status == 'draft' else "❌ Not Started")
    return {
        'Status': status,
        'Actionable Items': len(pending),
        'Derived Findings': [f['label'] for f in pending if f['source'] != 'checklist'],
        'Timestamp': (trail['last_saved'] if audited else "Never"),
        'Auditor': (trail['auditor'] if audited else "System"),
        'Responses': responses,
        'Comments': responses.get('comments', ''),
    }


def load_audit_summaries(rows_by_code, active_fields=None):
    """
    {module_code: audit_summary} for the module rows given
    ({code: module record}), with one audit query for the lot. The
    whole-school counterpart of app.py::load_checklist_data(), with no
    Streamlit in it.
    """
    active_fields = (active_fields if active_fields is not None
                     else database.get_active_audit_fields())
    trails = load_audit_trails()
    empty = _trail_from_rows([])
    return {code: audit_summary(row, trails.get(code, empty), active_fields)
            for code, row in rows_by_code.items()}


def load_checklist_summaries(sources=None):
    """
    The `checklist_sums` dictionary the Streamlit pages read, from the shared
    module records: {module_code: audit_summary}.

    Replaces the body of app.py::load_checklist_data(), which built its own
    lean module row (no SGA data, no Leganto draft count) and so counted a
    module's outstanding items differently from the module report. Same
    membership as before, deliberately, because some pages count the
    dictionary ("Audits Completed" is its length) or ask whether a code is in
    it: every module with any saved answer, plus every module the data alone
    flags (in the Leganto, Ally or readiness data) with at least one pending
    item. A code outside SITS still gets an entry if the data mentions it,
    built from the same sources with a bare record.
    """
    sources = sources if sources is not None else load_module_sources()
    with database.get_db_connection() as conn:
        df_sits = (pd.read_sql_query("SELECT * FROM sits_assessment_2026_27", conn)
                   if database.table_exists(conn, "sits_assessment_2026_27")
                   else pd.DataFrame())

    sits_rows = {}
    if not df_sits.empty and 'CIS unit code' in df_sits.columns:
        df_sits = df_sits.copy()
        df_sits['CIS unit code'] = df_sits['CIS unit code'].astype(str).str.strip().str.upper()
        sits_rows = {r['CIS unit code']: r for r in
                     df_sits.drop_duplicates(subset=['CIS unit code']).to_dict('records')}

    trails = load_audit_trails()
    empty = _trail_from_rows([])
    active_fields = database.get_active_audit_fields()

    # Modules the data alone can flag, so a finding is not invisible until
    # someone opens the module.
    data_codes = (sources.leganto_missing_set | set(sources.leganto_lists_map)
                  | set(sources.ally_issue_map) | set(sources.ally_map)
                  | set(sources.readiness_map))

    summaries = {}
    for code in set(trails) | data_codes:
        row = build_module_record(sits_rows.get(code, {'CIS unit code': code}), sources)
        summary = audit_summary(row, trails.get(code, empty), active_fields)
        if code in trails or summary['Actionable Items'] > 0:
            summaries[code] = summary
    return summaries
