"""
The rules both front ends read, pinned down.

Every function here is pure: data in, a verdict out, no database and no
Streamlit. That is what makes them cheap to test and what makes them
dangerous to change - the Streamlit badge, the Audit Portal's suggestions,
the Template Alignment matrices and the Django module report all read the
same answers, so a change made for one shows up in all of them.

Each test names the rule and, where the rule was corrected once already, the
date. CLAUDE.md carries the full reasoning.

Run from the repo root:

    .venv/Scripts/python -m pytest
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


def _field(field_id, label, field_type="boolean"):
    """One row of audit_fields, in the shape get_active_audit_fields() returns.

    Every key it selects is present deliberately: derive_module_findings()
    reads field['description'] directly, so a dict missing it raises rather
    than degrading, and a test helper that quietly allowed the short version
    would not be testing the same thing the app runs.
    """
    return {
        "id": field_id,
        "label": label,
        "action_label": label,
        "description": f"Whether {label} is complete.",
        "field_type": field_type,
        "is_active": 1,
        "display_order": 1,
        "is_gating": 0,
    }


class TestSectionReadyByOwnership:
    """readiness_section_is_ready() is deliberately not a bare
    `state in READINESS_READY_STATES` check: the same state means different
    things depending on who owns the section. Applying one rule to both
    (08-09-2026) would have read most of the institutional fields as not
    ready, and was caught before it shipped."""

    def test_lead_section_visible_but_unedited_is_not_ready(self):
        """The red flag the rule exists to catch: students can see it, but
        nothing shows anyone wrote it, so it may still be placeholder text."""
        assert processing.readiness_section_is_ready(
            "WELCOME_MODULE_OUTLINE", "visible_unedited") is False

    def test_institution_section_visible_but_unedited_is_ready(self):
        """Nobody was ever meant to edit these, so untouched since course
        creation is their correct resting state."""
        assert processing.readiness_section_is_ready(
            "ASSESSMENT_OVERVIEW", "visible_unedited") is True

    def test_feedback_shapes_counts_as_lead_owned(self):
        """Reclassified 15-09-2026: it ships visible like the institutional
        sections, but it is a document someone has to actually write."""
        assert processing.readiness_section_is_ready(
            "HOW_YOUR_FEEDBACK_SHAPES", "visible_unedited") is False

    def test_visible_and_edited_is_ready_either_way(self):
        for key in ("WELCOME_MODULE_OUTLINE", "ASSESSMENT_OVERVIEW"):
            assert processing.readiness_section_is_ready(key, "visible_edited") is True

    def test_drafted_hidden_is_not_ready(self):
        """Work exists, no student can see it. One click from done, but not
        done."""
        assert processing.readiness_section_is_ready(
            "WELCOME_MODULE_OUTLINE", "drafted_hidden") is False

    def test_unknown_section_takes_the_stricter_read(self):
        """A section that is not in TEMPLATE_SECTIONS must not pass silently."""
        assert processing.readiness_section_is_ready(
            "NOT_A_REAL_SECTION", "visible_unedited") is False


class TestLegantoGate:
    """leganto_blocks_reading_list(): Leganto data alone saying the reading
    list isn't done."""

    def test_no_list_at_all_blocks(self):
        assert processing.leganto_blocks_reading_list(True, "") is True

    def test_draft_blocks(self):
        assert processing.leganto_blocks_reading_list(False, "Draft") is True

    def test_mixed_blocks(self):
        assert processing.leganto_blocks_reading_list(False, "Mixed") is True

    def test_published_does_not_block(self):
        assert processing.leganto_blocks_reading_list(False, "Published") is False

    def test_blank_status_does_not_block(self):
        """A module in neither Leganto export has no evidence either way, and
        must not read as Missing."""
        assert processing.leganto_blocks_reading_list(False, "") is False
        assert processing.leganto_blocks_reading_list(False, None) is False


class TestSgaGate:
    """sga_blocks_sga_field(): 0 mapped attributes is an action, no import is
    not. Changed 30-09-2026 from informational to gating."""

    def test_zero_attributes_blocks(self):
        assert processing.sga_blocks_sga_field(0) is True

    def test_mapped_attributes_do_not_block(self):
        assert processing.sga_blocks_sga_field(3) is False

    def test_no_import_does_not_block(self):
        """None means no SGA import this year, which must never read as the
        module having no SGAs."""
        assert processing.sga_blocks_sga_field(None) is False
        assert processing.sga_blocks_sga_field(float("nan")) is False


class TestManualOverride:
    """readiness_manual_override(): a DLA's recorded answer outranks the data,
    and the absence of an answer is not an answer."""

    def test_recorded_true_wins(self):
        assert processing.readiness_manual_override(
            "welcome_outline", {"welcome_outline": "TRUE"}) is True

    def test_recorded_false_wins(self):
        assert processing.readiness_manual_override(
            "welcome_outline", {"welcome_outline": "FALSE"}) is False

    def test_never_answered_is_none_not_false(self):
        assert processing.readiness_manual_override("welcome_outline", {}) is None

    def test_blank_answer_is_none_not_false(self):
        assert processing.readiness_manual_override(
            "welcome_outline", {"welcome_outline": ""}) is None

    def test_unmapped_field_is_none(self):
        assert processing.readiness_manual_override(None, {"x": "TRUE"}) is None


class TestReadingListVerdict:
    """reading_list_verdict() reads the same answer out of checklist_sums for
    the dashboard views, so they agree with derive_module_findings()."""

    def test_recorded_answer_is_returned(self):
        sums = {"TST001": {"Responses": {processing.READING_LIST_FIELD_ID: "TRUE"}}}
        assert processing.reading_list_verdict(sums, "TST001") is True

    def test_module_with_no_entry_is_none(self):
        assert processing.reading_list_verdict({}, "TST001") is None

    def test_entry_without_an_answer_is_none(self):
        assert processing.reading_list_verdict(
            {"TST001": {"Responses": {}}}, "TST001") is None


class TestFixClaimWords:
    """fix_claim_words() is the one wording for a lead's "this is fixed",
    shared by the finding and the Blackboard Template card so they cannot
    differ."""

    def test_names_the_date_in_the_portal_format(self):
        words = processing.fix_claim_words({"claimed_on": "2026-10-01 09:30:00"})
        assert "01-10-2026" in words

    def test_includes_the_submitter_when_present(self):
        words = processing.fix_claim_words(
            {"claimed_on": "2026-10-01", "submitter_name": "a.lead@sheffield.ac.uk"})
        assert "a.lead@sheffield.ac.uk" in words

    def test_appends_the_note_when_present(self):
        words = processing.fix_claim_words(
            {"claimed_on": "2026-10-01", "note": "Unhid the section"})
        assert "Unhid the section" in words

    def test_returns_plain_text_not_markup(self):
        """The note is free text typed by a lead. This function deliberately
        does not escape it, so a caller putting it in markup has to escape it
        itself. A caller assuming otherwise would be relying on something that
        was never true."""
        words = processing.fix_claim_words(
            {"claimed_on": "2026-10-01", "note": "<b>done</b>"})
        assert "<b>done</b>" in words


class TestAlignmentRow:
    """module_alignment_status() is the single definition behind School
    Dashboard's and Faculty Overview's matrices and the Module Report's
    summary, so all three agree about one module."""

    def _cells(self, row, responses, fields, fix_claims=None):
        return dict(processing.module_alignment_status(
            row, responses, fields, fix_claims))

    def test_unanswered_field_is_a_cross(self):
        fields = [_field("learning_materials", "Learning Materials")]
        col = processing.short_field_label("learning_materials", "Learning Materials")
        assert self._cells(_row(), {}, fields)[col] == "❌"

    def test_ticked_field_is_a_tick(self):
        fields = [_field("learning_materials", "Learning Materials")]
        col = processing.short_field_label("learning_materials", "Learning Materials")
        cells = self._cells(_row(), {"learning_materials": "TRUE"}, fields)
        assert cells[col] == "✅"

    def test_reported_fix_replaces_the_cross(self):
        """Added 08-10-2026: a lead who has reported a section fixed should not
        keep seeing a cross for work they have done. The count behind
        Actionable Items still includes it, deliberately."""
        fields = [_field("learning_materials", "Learning Materials")]
        col = processing.short_field_label("learning_materials", "Learning Materials")
        claims = {"learning_materials": {"claimed_on": "2026-10-08",
                                         "submitter_name": "a.lead@sheffield.ac.uk",
                                         "note": ""}}
        assert self._cells(_row(), {}, fields, claims)[col] == "\U0001f527"

    def test_severe_issues_are_red(self):
        cells = self._cells(_row(**{"Ally Severe": 1}), {}, [])
        assert cells["Accessibility"] == "\U0001f534"

    def test_ally_switched_off_is_red(self):
        cells = self._cells(_row(**{"Ally Enabled": False}), {}, [])
        assert cells["Accessibility"] == "\U0001f534"

    def test_major_only_is_amber(self):
        cells = self._cells(_row(**{"Ally Major": 7}), {}, [])
        assert cells["Accessibility"] == "\U0001f7e0"

    def test_neither_is_green(self):
        assert self._cells(_row(), {}, [])["Accessibility"] == "\U0001f7e2"

    def test_no_score_is_white(self):
        """Nothing to judge yet is its own state, not a pass and not a fail."""
        cells = self._cells(_row(**{"Ally Overall": float("nan")}), {}, [])
        assert cells["Accessibility"] == "⚪"

    def test_untouched_template_is_white(self):
        cells = self._cells(_row(**{"Content Maturity": "Not yet built"}), {}, [])
        assert cells["Accessibility"] == "⚪"


class TestMappedFieldProducesOneFinding:
    """A checklist field mapped to a template section produces a 'readiness'
    finding only. Before 14-09-2026 both loops ran, so one real gap counted
    twice in Actionable Items and the module report's two panels disagreed on
    screen about the same section."""

    def _findings(self):
        row = _row(**{"Template Sections": {
            "WELCOME_MODULE_OUTLINE": {"state": "visible_unedited"}}})
        fields = [_field("welcome_outline", "Welcome & Module Outline")]
        return processing.derive_module_findings(row, {}, fields)

    def test_no_checklist_finding_for_a_mapped_field(self):
        assert not [f for f in self._findings()
                    if f["source"] == "checklist"
                    and f.get("field_id") == "welcome_outline"]

    def test_readiness_finding_speaks_for_it_instead(self):
        readiness = [f for f in self._findings()
                     if f["source"] == "readiness"
                     and f.get("audit_field_id") == "welcome_outline"]
        assert len(readiness) == 1
        assert readiness[0]["state"] == "pending"


# --- Ally trend --------------------------------------------------------------

def _history():
    import pandas as pd
    def row(date, course, module, files, pages, score):
        return {"snapshot_date": date, "course_id": course, "module_code": module,
                "total_files": files, "total_wysiwyg": pages, "overall_score": score}
    return pd.DataFrame([
        row("2026-08-01", "c1", "TST001", 10, 0, 1.0),
        row("2026-08-01", "c2", "TST002", 10, 0, 0.5),
        row("2026-08-01", "c9", "OTHER1", 99, 0, 0.1),
        # Later snapshot records only the course that changed.
        row("2026-09-01", "c1", "TST001", 20, 0, 0.8),
    ])


def test_ally_trend_carries_unchanged_courses_forward():
    from processing import ally_trend
    trend, message = ally_trend(_history(), ["TST001", "tst002"])
    assert message == ""
    assert list(trend["Files uploaded"]) == [20, 30]      # not 20 -> 20 (c2 dropped)
    assert list(trend["Courses"]) == [2, 2]
    assert round(trend["Overall score"].iloc[0], 3) == 0.75    # (10*1.0 + 10*0.5) / 20
    assert round(trend["Overall score"].iloc[1], 3) == round((20 * 0.8 + 10 * 0.5) / 30, 3)


def test_ally_trend_says_why_there_is_nothing_to_plot():
    import pandas as pd
    from processing import (ally_trend, ALLY_TREND_NO_HISTORY, ALLY_TREND_NO_SCHOOL,
                            ALLY_TREND_ONE_SNAPSHOT)
    assert ally_trend(pd.DataFrame(), ["TST001"]) == (None, ALLY_TREND_NO_HISTORY)
    assert ally_trend(_history().iloc[:3], ["TST001"]) == (None, ALLY_TREND_ONE_SNAPSHOT)
    assert ally_trend(_history(), ["NOPE99"]) == (None, ALLY_TREND_NO_SCHOOL)


# --- The School Dashboard's lenses -------------------------------------------

def _lens_school():
    import pandas as pd
    return pd.DataFrame([
        {"New module code": "TST001", "Module name": "Alpha", "Mod. lead": "A",
         "Content Maturity": "In progress", "Ally Overall": 0.5, "Ally Severe": 3,
         "Ally Major": 1, "Ally Students": 40, "Leganto Missing": True, "SGA Attributes": 0},
        {"New module code": "TST002", "Module name": "Beta", "Mod. lead": "B",
         "Content Maturity": "In progress", "Ally Overall": 0.99, "Ally Severe": 0,
         "Ally Major": 0, "Ally Students": 10, "Leganto Missing": True, "SGA Attributes": 4},
        {"New module code": "TST003", "Module name": "Gamma", "Mod. lead": "C",
         "Content Maturity": "Not yet built", "Ally Overall": 1.0, "Ally Severe": 0,
         "Ally Major": 0, "Ally Students": 0, "Leganto Missing": False, "SGA Attributes": None},
    ])


def test_lens_accessibility_risk_excludes_untouched_shells_and_ranks_by_harm():
    frame, note, kind = processing.lens_accessibility_risk(_lens_school())
    assert list(frame["New module code"]) == ["TST001"]        # TST002 scores 99%, TST003 unbuilt
    assert kind == "warning" and "1 module(s) not yet started are excluded" in note
    assert frame["Score"].iloc[0] == 50.0                       # numeric, not a formatted string
    assert processing.lens_accessibility_risk(None)[0] is None


def test_lens_reading_lists_respects_a_recorded_answer():
    school = _lens_school()
    frame, status, kind = processing.lens_missing_reading_lists(school, {})
    assert list(frame["New module code"]) == ["TST001", "TST002"] and kind == "warning"
    ticked = {"TST001": {"Responses": {"reading_list": True}}}
    frame, _, _ = processing.lens_missing_reading_lists(school, ticked)
    assert list(frame["New module code"]) == ["TST002"]         # a DLA's tick overrides Leganto
    assert processing.lens_missing_reading_lists(school.drop(columns=["Leganto Missing"]), {})[2] == "error"


def test_lens_no_sgas_only_flags_a_count_of_zero():
    frame, _, kind = processing.lens_no_sgas(_lens_school())
    assert list(frame["New module code"]) == ["TST001"] and kind == "warning"   # None is no evidence
    assert processing.lens_no_sgas(_lens_school().assign(**{"SGA Attributes": None}))[2] == "error"


def test_combine_lenses_ranks_by_how_many_flag_a_module():
    school = _lens_school()
    results = {
        processing.LENS_RISK: processing.lens_accessibility_risk(school),
        processing.LENS_READING: processing.lens_missing_reading_lists(school, {}),
    }
    frame, status, kind, notes = processing.combine_lenses(
        [processing.LENS_RISK, processing.LENS_READING], results)
    assert list(frame["New module code"]) == ["TST001", "TST002"]   # TST001 is flagged by both
    assert "2 modules flagged by at least one of 2 lenses (1 by all 2)" in status
    assert [n[0] for n in notes] == [processing.LENS_RISK, processing.LENS_READING]
    empty = {processing.LENS_SGA: (None, "x", "success"), processing.LENS_READING: (None, "y", "success")}
    assert processing.combine_lenses([processing.LENS_SGA, processing.LENS_READING], empty)[0] is None


# --- School names ------------------------------------------------------------

def test_school_names_come_from_the_most_common_department_name():
    rows = [
        ("GPL130", "School of Geography and Planning", 40),
        ("GPL225", "School of Geography and Planning", 30),
        ("GPL999", "A stray name", 2),                       # one odd row cannot rename a school
        ("EDC004", "School of Education", 5),
        ("ECN357", "", 9),                                   # blank names are ignored
        ("AF4F1001", "Sheffield University Management School", 7),   # legacy code, not a faculty school
        ("SCS100", "Some other faculty", 3),
    ]
    assert processing.school_names_from_rows(rows) == {
        "GPL": "School of Geography and Planning", "EDC": "School of Education"}
    assert processing.school_names_from_rows([]) == {}
