"""
The tests the Streamlit app never had, starting where they are most useful:
the pure logic in processing.py.

These need no database and no Django. They run against processing.py directly,
which is why they belong here first - if the port stalls, these still earn
their place in the existing app.

Run from the web/ directory:

    pytest
"""

import processing


def _row(**overrides):
    """A module row in the shape derive_module_findings() documents."""
    row = {
        "New module code": "TST001",
        "Ally Overall": 0.95,
        "Ally Enabled": True,
        "Ally Severe": 0,
        "Ally Major": 0,
        "Leganto Missing": False,
        "Leganto List Status": "",
        "Leganto List Items": 0,
        "Template Sections": {},
        "SGA Attributes": None,
    }
    row.update(overrides)
    return row


def _pending(findings, source=None):
    return [f for f in findings
            if f.get("state") == "pending"
            and (source is None or f.get("source") == source)]


class TestAllyFindings:
    def test_major_only_issues_still_produce_a_finding(self):
        """
        A module with major but no severe issues must produce an Ally finding.
        Before 15-09-2026 the trigger was severe-only, so the module report's
        summary named major issue types while the Actions panel showed nothing.
        """
        findings = processing.derive_module_findings(
            _row(**{"Ally Major": 7}), {}, [])
        assert _pending(findings, "ally"), "major-only issues produced no finding"

    def test_clean_module_produces_no_ally_finding(self):
        findings = processing.derive_module_findings(_row(), {}, [])
        assert not _pending(findings, "ally")

    def test_disabled_scanning_is_a_finding(self):
        findings = processing.derive_module_findings(
            _row(**{"Ally Enabled": False}), {}, [])
        assert _pending(findings, "ally")


class TestLegantoFindings:
    def test_missing_list_is_pending(self):
        findings = processing.derive_module_findings(
            _row(**{"Leganto Missing": True}), {}, [])
        assert _pending(findings, "leganto")

    def test_draft_list_is_pending(self):
        """The badge used never to count a list stuck in Draft."""
        findings = processing.derive_module_findings(
            _row(**{"Leganto List Status": "Draft", "Leganto List Items": 12}),
            {}, [])
        assert _pending(findings, "leganto")


class TestRowContract:
    def test_empty_row_does_not_raise(self):
        """
        A module can legitimately be absent from any one dataset, so missing
        keys must degrade to "nothing from that source" rather than raising.
        """
        assert processing.derive_module_findings({}, {}, []) is not None

    def test_none_row_does_not_raise(self):
        assert processing.derive_module_findings(None, {}, []) is not None


class TestSectionStates:
    def test_edited_but_hidden_is_not_called_not_started(self):
        """
        drafted_hidden: the work exists but no student can see it. A
        status-only reading called this "not started", which was both wrong
        and insulting to whoever did the work.
        """
        state = processing.classify_section_state("Hidden", "lead_edit")
        assert state != "not_started"

    def test_bulk_edit_counts_as_edited(self):
        """lead_edit and bulk are treated identically wherever a human reads
        them, as of 08-09-2026."""
        assert (processing.classify_section_state("Hidden", "bulk")
                == processing.classify_section_state("Hidden", "lead_edit"))
