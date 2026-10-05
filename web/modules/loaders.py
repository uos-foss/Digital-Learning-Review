"""
Assembles one module's row in the shape `processing.derive_module_findings()`
expects, without importing Streamlit.

**This file is the spike's main finding, and it is a problem to fix rather
than a pattern to copy.** The row contract is documented in
`derive_module_findings()`'s own docstring ('Leganto Missing', 'Leganto List
Status', 'Leganto List Items', 'Ally Severe', 'Ally Major', 'Ally Enabled',
'Ally Overall', 'Template Sections', 'SGA Attributes'), but the code that
*builds* that row lives inside `app.py::load_audit_data()`, which is wrapped
in `@st.cache_data` and sits in a module that configures Streamlit pages at
import time. Django cannot call it, so the mapping below repeats it for one
module.

Two copies of that mapping is exactly the drift risk that keeping both front
ends in one repo is meant to avoid. Before porting any further page, extract
the row assembly out of `app.py` into a Streamlit-free loader at the repo root
that both front ends import, and delete the duplication here. The pieces it
needs - `database.get_*_latest()` and `processing.aggregate_*_to_modules()` -
are already free of Streamlit; only the assembly is trapped.

Everything else here is a genuine reuse: findings, aggregation and the
section-state model all come from `processing.py` unchanged.
"""

from __future__ import annotations

import pandas as pd

import database
import processing
from processing import CURRENT_ACADEMIC_YEAR


def _first(frame: pd.DataFrame, code: str) -> dict:
    """The row for one module code from a module-grain frame, or {}."""
    if frame is None or frame.empty or "module_code" not in frame.columns:
        return {}
    match = frame[frame["module_code"].astype(str).str.upper() == code]
    return {} if match.empty else match.iloc[0].to_dict()


def load_module_row(code: str) -> dict | None:
    """
    One module's row, or None when the code is not in SITS for the current year.

    Mirrors app.py::load_audit_data()'s per-module mapping. See the module
    docstring: this duplication is temporary by design.
    """
    code = str(code).strip().upper()

    with database.get_db_connection() as conn:
        sits = pd.read_sql_query(
            "SELECT * FROM sits_assessment_2026_27 WHERE UPPER(TRIM("
            "[CIS unit code])) = ?",
            conn,
            params=(code,),
        )
        nolist = pd.read_sql_query(
            "SELECT module_code FROM leganto_nolist", conn
        ) if database.table_exists(conn, "leganto_nolist") else pd.DataFrame()

    if sits.empty:
        return None

    sits_row = sits.iloc[0].to_dict()

    # Ally: course grain in the database, rolled up to modules on read.
    ally = _first(
        processing.aggregate_ally_to_modules(
            database.get_ally_courses_latest(CURRENT_ACADEMIC_YEAR)),
        code,
    )
    issues = _first(
        processing.count_ally_issues_by_module(
            database.get_ally_issues_latest(CURRENT_ACADEMIC_YEAR)),
        code,
    )

    # Leganto: status and item count for modules that do have a list. Absence
    # from both exports means blank status, never 'Missing' - see CLAUDE.md.
    leganto = _first(
        processing.aggregate_leganto_to_modules(
            database.get_leganto_lists_latest(CURRENT_ACADEMIC_YEAR)),
        code,
    )
    missing_codes = set()
    if not nolist.empty:
        missing_codes = set(nolist["module_code"].astype(str).str.strip().str.upper())

    # Template Alignment Report.
    readiness = _first(
        processing.aggregate_readiness_to_modules(
            database.get_readiness_courses_latest(CURRENT_ACADEMIC_YEAR),
            database.get_readiness_sections_latest(CURRENT_ACADEMIC_YEAR)),
        code,
    )

    # SGA counts are None, not 0, until a year has been imported, so that
    # "no data" never reads as "no SGAs mapped".
    sga_loaded = database.sga_imported(CURRENT_ACADEMIC_YEAR)
    sga = _first(
        processing.aggregate_sga_to_modules(
            processing.explode_sga_mappings(
                database.get_sga_mappings(CURRENT_ACADEMIC_YEAR))),
        code,
    ) if sga_loaded else {}

    overall = ally.get("overall_score")

    return {
        "New module code": code,
        "Module name": sits_row.get("Module name", ""),
        "Module Lead": sits_row.get("Academic contact", ""),
        # Every view derives the school from the code's first three letters.
        # A school_of() helper belongs in processing.py - there are ~16 copies
        # of this slice across the Streamlit app.
        "School": code[:3],
        "Ally Overall": overall,
        "Ally Enabled": bool(ally.get("ally_enabled", 1)),
        "Ally Severe": int(issues.get("severe", 0) or 0),
        "Ally Major": int(issues.get("major", 0) or 0),
        "Leganto Missing": code in missing_codes,
        "Leganto List Status": leganto.get("status", ""),
        "Leganto List Items": leganto.get("total_items", 0),
        "Template Sections": readiness.get("section_states") or {},
        "SGA Attributes": int(sga.get("sga_attributes", 0)) if sga_loaded else None,
    }


def load_findings(code: str):
    """
    (row, findings) for one module. The findings come from
    processing.derive_module_findings(), unchanged - the whole point of the
    spike is that this one call is all a new front end needs.
    """
    row = load_module_row(code)
    if row is None:
        return None, []

    responses = database.get_audit_responses(code)
    active_fields = database.get_active_audit_fields()
    findings = processing.derive_module_findings(row, responses, active_fields)
    return row, findings
