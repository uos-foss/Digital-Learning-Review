"""
The outstanding-item count behind the Actionable Items badge.

loaders.audit_summary() is the one place a module's count is worked out, for
the Streamlit badge (app.py::load_checklist_data()) and the Django School
Dashboard alike. These pin the two rules that decide it. No database, no
Streamlit, no Django.

Run from the repo root:  .venv/Scripts/python -m pytest
"""

import loaders

# Section states as processing.aggregate_readiness_to_modules() gives them.
_SGA_VISIBLE = {"SKILLS_DEVELOPMENT_SGAS": {
    "state": "visible_edited", "status": "Visible", "evidence": "lead_edit",
    "last_modified": "2026-08-01"}}

_FIELDS = [{"id": "sga", "label": "Skills Development", "description": "", "field_type": "boolean",
            "is_active": 1}]


def _row(**overrides):
    row = {"New module code": "TST001", "Ally Overall": 0.95, "Ally Enabled": True,
           "Ally Severe": 0, "Ally Major": 0, "Leganto Missing": False,
           "Leganto List Status": "Published", "Leganto List Items": 3,
           "Template Sections": _SGA_VISIBLE, "SGA Attributes": 3}
    row.update(overrides)
    return row


def _trail(responses=None):
    return loaders._trail_from_rows(
        [(k, v, "dla@example.org", "2026-10-01 09:00:00") for k, v in (responses or {}).items()])


def test_a_visible_sga_section_with_no_attributes_mapped_is_one_more_item():
    mapped = loaders.audit_summary(_row(), _trail(), [])
    unmapped = loaders.audit_summary(_row(**{"SGA Attributes": 0}), _trail(), [])
    assert unmapped["Actionable Items"] == mapped["Actionable Items"] + 1
    assert any("no SGAs mapped" in label for label in unmapped["Derived Findings"])


def test_no_sga_import_yet_adds_nothing():
    # None means "not imported", never "nothing mapped".
    none_yet = loaders.audit_summary(_row(**{"SGA Attributes": None}), _trail(), [])
    mapped = loaders.audit_summary(_row(), _trail(), [])
    assert none_yet["Actionable Items"] == mapped["Actionable Items"]


def test_a_never_audited_module_leaves_its_checklist_fields_out_of_the_count():
    summary = loaders.audit_summary(_row(), _trail(), _FIELDS)
    assert summary["Auditor"] == "System" and summary["Timestamp"] == "Never"
    # The same fields on an audited module do count, so the answer decides.
    audited = loaders.audit_summary(_row(), _trail({"audit_status": "draft"}), _FIELDS)
    assert audited["Status"] == "📝 Draft" and audited["Auditor"] == "dla@example.org"
    assert audited["Actionable Items"] >= summary["Actionable Items"]


def test_the_summary_has_the_shape_the_streamlit_pages_read():
    summary = loaders.audit_summary(_row(), _trail({"comments": "Fine"}), [])
    assert set(summary) >= {"Status", "Actionable Items", "Derived Findings", "Timestamp",
                            "Auditor", "Responses", "Comments"}
    assert summary["Comments"] == "Fine"
    assert summary["Responses"]["comments"] == "Fine"
