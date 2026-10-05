"""
The data the pages need, from the shared loader at the repo root.

This replaces the duplicated module-row mapping the spike started with:
`loaders.py` at the repo root now owns that assembly, and the Streamlit app
reads the same function (`app.py::load_audit_data()` is a thin cached wrapper
around it). One mapping, two front ends, no drift.

Nothing here is Django-specific except where it lives. Writes still belong in
`database.save_audit_response()` so both front ends record an audit
identically.
"""

from __future__ import annotations

import database
import loaders
import processing


def load_module_row(code: str) -> dict | None:
    """One module's row, or None when the code is not in SITS this year."""
    return loaders.load_module_record(code)


def load_findings(code: str):
    """
    (row, findings) for one module.

    The findings come from processing.derive_module_findings(), unchanged.
    That one call being all a new front end needs is the whole point of the
    spike.
    """
    row = loaders.load_module_record(code)
    if row is None:
        return None, []

    findings = processing.derive_module_findings(
        row,
        database.get_audit_responses(code),
        database.get_active_audit_fields(),
    )
    return row, findings
