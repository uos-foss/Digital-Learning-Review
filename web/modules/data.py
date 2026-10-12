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

import database
import loaders
import processing
import report_model

from accounts.models import capabilities_of

SOURCES_TTL = 300

_cache = {"at": 0.0, "sources": None}
_lock = threading.Lock()


def _sources():
    with _lock:
        if _cache["sources"] is None or time.monotonic() - _cache["at"] > SOURCES_TTL:
            _cache["sources"] = loaders.load_module_sources()
            _cache["at"] = time.monotonic()
        return _cache["sources"]


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
