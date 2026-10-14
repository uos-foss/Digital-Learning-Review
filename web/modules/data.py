"""
The data the pages need, from the shared loader at the repo root.

`loaders.py` owns the module-row mapping and `report_model.build_report()`
owns what the report says, so nothing here decides anything: it fetches, hands
over, and returns plain data for a template. Writes still belong in
`database.py` so both front ends record an audit identically.

The module sources (the Ally, Leganto, readiness and SGA lookups, about a
second to build) are cached in-process for `SOURCES_TTL` seconds, the same
five minutes `app.py`'s `@st.cache_data(ttl=300)` gives the Streamlit side. It
is a safety net against re-reading on every tab click, not an invalidation
scheme: an import run from the Admin Panel shows here within the TTL. What a
DLA has saved (the audit, fix claims, spot-checks) is read fresh each request,
so it never lags.
"""

from __future__ import annotations

import threading
import time

import pandas as pd

import database
import loaders
import processing
import report_model

from accounts.models import capabilities_of

SOURCES_TTL = 300

_cache = {"at": 0.0, "sources": None, "frames": None}
_lock = threading.Lock()


def _loaded():
    """(sources, (df_aut, df_spr)), rebuilt at most every SOURCES_TTL seconds.
    The frames are every module's record, which a school page needs and a
    single module report does not, so they are built on first use."""
    with _lock:
        if _cache["sources"] is None or time.monotonic() - _cache["at"] > SOURCES_TTL:
            _cache.update(sources=loaders.load_module_sources(), frames=None,
                          at=time.monotonic())
        return _cache["sources"]


def _sources():
    return _loaded()


def _frames():
    sources = _loaded()
    with _lock:
        if _cache["frames"] is None:
            with database.get_db_connection() as conn:
                df_sits = pd.read_sql_query("SELECT * FROM sits_assessment_2026_27", conn)
            _cache["frames"] = loaders.assemble_module_frames(df_sits, sources)
        return _cache["frames"]


def load_module_row(code: str) -> dict | None:
    """One module's row, or None when the code is not in SITS this year."""
    return loaders.load_module_record(code, _sources())


def load_report(code: str, user) -> dict | None:
    """
    The whole module report for one module, or None when the code is not in
    SITS for the current year. `user` only decides which optional pieces they
    may see (the SGA note).
    """
    code = str(code).strip().upper()
    sources = _sources()
    row = loaders.load_module_record(code, sources)
    if row is None:
        return None

    trail = loaders.load_audit_trail(code)
    return report_model.build_report(
        code, row,
        responses=trail["responses"],
        has_audit=trail["has_audit"],
        last_saved=trail["last_saved"],
        auditor=trail["auditor"],
        fix_claims=database.get_active_fix_claims(code),
        active_fields=database.get_active_audit_fields(),
        df_ally_issues=sources.df_ally_issues,
        import_dates=database.get_last_import_dates(),
        can_view_sga=processing.can_view_sga(capabilities_of(user)),
        spot_check_pending=bool(
            database.get_pending_spot_check(code, processing.CURRENT_ACADEMIC_YEAR)),
    )


def _school_frame(school: str, semester: str) -> pd.DataFrame:
    """One school's module records for a semester."""
    df_aut, df_spr = _frames()
    target = processing.resolve_semester_df(df_aut, df_spr, semester)
    if target is None or target.empty:
        return pd.DataFrame(columns=["New module code"])
    return target[processing.school_series(target["New module code"]) == school]


def load_school_trend(school: str, semester: str):
    """Trends for one school: (frame or None, message), see
    processing.ally_trend(). The history is read fresh; it is small."""
    codes = _school_frame(school, semester)["New module code"]
    return processing.ally_trend(
        database.get_ally_history(academic_year=processing.CURRENT_ACADEMIC_YEAR), codes)


def load_school_ally(school: str, semester: str, severities, issues) -> dict:
    """Ally Analytics for one school and semester (see report_model). The
    module records are cached with the sources; the issue rows come from the
    same cached sources, so an import shows within the TTL."""
    return report_model.build_ally_analytics(
        _school_frame(school, semester), _sources().df_ally_issues,
        severities=severities, issues=issues)


def load_school(school: str, semester: str, user) -> dict:
    """
    One school's dashboard for a semester, as plain data (see
    report_model.build_school()). Module records are cached with the sources;
    everything a DLA can change (audit answers, fix claims, spot-checks) is
    read fresh, so it never lags.
    """
    school_df = _school_frame(school, semester)

    rows = {str(r["New module code"]).strip().upper(): r
            for r in school_df.to_dict("records")}
    active_fields = database.get_active_audit_fields()
    summaries = loaders.load_audit_summaries(rows, active_fields)

    spot_checks = database.get_school_spot_checks(school, processing.CURRENT_ACADEMIC_YEAR)
    spot_status = {}
    if not spot_checks.empty:
        latest = (spot_checks.sort_values("flagged_on", ascending=False)
                  .drop_duplicates(subset="module_code", keep="first"))
        spot_status = {str(c).strip().upper(): s
                       for c, s in zip(latest["module_code"], latest["status"])}

    claims = {str(c).strip().upper(): v
              for c, v in database.get_all_active_fix_claims().items()}

    return report_model.build_school(
        school, semester, school_df, summaries,
        spot_check_status=spot_status, fix_claims_by_module=claims,
        active_fields=active_fields,
        can_view_sga=processing.can_view_sga(capabilities_of(user)))


def _school_names(school: str) -> dict:
    """Module code to name for one school, across both semesters."""
    names = {}
    for frame in _frames():
        if frame is None or frame.empty:
            continue
        mine = frame[processing.school_series(frame["New module code"]) == school]
        for code, name in zip(mine["New module code"], mine["Module name"]):
            names.setdefault(str(code).strip().upper(), name)
    return names


def load_school_comments(school: str) -> dict:
    """Spot-Check Comments for one school (see report_model). Read fresh."""
    return report_model.build_spot_check_comments(
        database.get_spot_check_comments(school, processing.CURRENT_ACADEMIC_YEAR),
        _school_names(school), database.get_active_audit_fields())


def fixes_enabled(school: str) -> bool:
    """Reported Fixes is rolled out school by school (feature_schools)."""
    return database.feature_enabled_for(processing.FIX_CLAIM_FEATURE, school)


def load_school_fixes(school: str) -> dict:
    """Reported Fixes for one school (see report_model). Read fresh."""
    return report_model.build_reported_fixes(
        database.get_fix_claims_for_school(school),
        _school_names(school), database.get_active_audit_fields())
