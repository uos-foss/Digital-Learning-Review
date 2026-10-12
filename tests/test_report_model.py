"""
What the module report says, pinned down.

`report_model` holds the wording and assembly that the Streamlit page, its PDF
and the Django report all read, so a change here changes all three. No
database, no Streamlit, no Django.

Run from the repo root:

    .venv/Scripts/python -m pytest
"""

import pandas as pd

import report_model
from processing import TEMPLATE_SECTION_TREE, SGA_SECTION


def _row(**overrides):
    row = {
        "New module code": "TST001", "Module name": "Test module",
        "Mod. lead": "ADA LOVELACE", "UG/ PG/ Other": "UG Level 2",
        "URL": "https://example.org/course",
        "Ally Overall": 0.95, "Ally Files": 0.9, "Ally WYSIWYG": 1.0,
        "Ally Enabled": True, "Ally Severe": 0, "Ally Major": 0,
        "Ally Last Checked": "2026-10-01", "Content Maturity": "In progress",
        "Total Files": 12, "Ally WYSIWYG Items": 4, "Ally Shells": 1,
        "Leganto Missing": False, "Leganto List Status": "", "Leganto List Items": 0,
        "Leganto Draft Items": 0, "Template Sections": {},
        "SGA Attributes": None, "SGA Sub-Attributes": None,
    }
    row.update(overrides)
    return row


def _report(row=None, **kw):
    args = dict(responses={}, has_audit=False, last_saved=None, auditor="System",
                fix_claims={}, active_fields=[], df_ally_issues=pd.DataFrame(),
                import_dates={}, can_view_sga=False, spot_check_pending=False)
    args.update(kw)
    return report_model.build_report("TST001", row or _row(), **args)


def test_audit_status_says_when_a_check_was_saved():
    assert report_model.audit_status_label(
        True, "2026-10-01 09:30:00", False) == "Spot checked on 01-10-2026 09:30:00"
    # The sentinels app.py uses where a real timestamp is missing.
    assert report_model.audit_status_label(True, "Unknown", False) == "Spot checked"
    assert report_model.audit_status_label(False, None, True) == "Spot check-pending"
    assert report_model.audit_status_label(False, None, False) == "Data-derived"


def test_a_checked_flag_does_not_read_as_pending_once_audited():
    # has_audit wins over a pending flag, as on the Streamlit page.
    assert report_model.audit_status_label(True, "2026-10-01 09:30:00", True).startswith("Spot checked on")


def test_action_items_split_custom_findings_into_label_and_description():
    items = report_model.action_items([
        {"type": "boolean", "label": "Reading list", "description": "Publish it"},
        {"type": "custom", "category": "Note", "label": "Odd thing", "description": "Fix it"},
        {"type": "custom", "label": "", "description": ""},
        {"type": "something-else", "label": "ignored"},
    ])
    assert items[0] == {"label": "Reading list", "description": "Publish it"}
    assert items[1] == {"label": "Note", "description": "Odd thing\nFix it"}
    assert items[2]["label"] == "Custom Observation"
    assert len(items) == 3


def test_sga_note_needs_the_capability_and_an_import():
    mapped = _row(**{"SGA Attributes": 3, "SGA Sub-Attributes": 1})
    assert report_model.sga_note(mapped, False) is None
    assert report_model.sga_note(_row(), True) is None  # no import yet
    assert "no graduate attributes" in report_model.sga_note(_row(**{"SGA Attributes": 0}), True)
    assert report_model.sga_note(mapped, True) == (
        "SGA tool: 3 graduate attributes mapped (1 sub-attribute).")


def test_sga_note_row_appears_even_without_readiness_data_for_the_section():
    rows = report_model.template_rows(
        TEMPLATE_SECTION_TREE, {}, {}, False, None, {}, sga_note="a note")
    notes = [r for r in rows if r["kind"] == "note"]
    assert len(notes) == 1 and notes[0]["text"] == "a note"
    # And never when none is passed, which is the PDF's case.
    assert not [r for r in report_model.template_rows(
        TEMPLATE_SECTION_TREE, {}, {}, False, None, {}) if r["kind"] == "note"]
    assert SGA_SECTION  # the row is attached to this section


def test_sections_carry_their_key_for_the_icon():
    states = {"MODULE_INFORMATION": {"state": "visible_edited", "last_modified": "2026-08-01",
                                     "evidence": "lead_edit"}}
    rows = report_model.template_rows(TEMPLATE_SECTION_TREE, states, {}, False, None, {})
    sections = [r for r in rows if r["kind"] == "section"]
    assert [r["key"] for r in sections] == ["MODULE_INFORMATION"]


def test_site_links_must_be_http():
    assert _report()["site_url"] == "https://example.org/course"
    assert _report(_row(URL="javascript:alert(1)"))["site_url"] == ""
    assert _report(_row(URL="nan"))["site_url"] == ""


def test_a_module_with_no_ally_record_says_so_rather_than_showing_zero_gauges():
    report = _report(_row(**{"Content Maturity": "No data", "Total Files": 0,
                             "Ally WYSIWYG Items": 0, "Ally Shells": 0}))
    assert "No Ally record" in report["ally"]["message"]
    assert "intro" not in report["ally"]


def test_a_template_course_gets_a_banner_and_grey_gauges():
    report = _report(_row(**{"Content Maturity": "Not yet built"}))
    banner = report["ally"]["maturity_banner"]
    assert banner["title"] == "Not started"
    assert banner["note"].endswith("Last scanned 01-10-2026")
    assert {colour for *_, colour in report["ally"]["scores"]} == {"#6B7280"}


def test_the_report_header_reads_like_the_streamlit_one():
    report = _report()
    assert report["lead"] == "Ada Lovelace"
    assert report["level"] == "UG Level 2"
    assert report["audit_status"] == "Data-derived"
    assert report["last_updated"] == "Never"
    assert report["comment"] == ""


def test_last_updated_names_the_auditor_once_audited():
    report = _report(has_audit=True, last_saved="2026-10-01 09:30:00", auditor="dla@sheffield.ac.uk")
    assert report["last_updated"] == "01-10-2026 09:30:00 by dla@sheffield.ac.uk"
    assert report["audit_status"].startswith("Spot checked on")


def test_the_advisor_comment_only_shows_on_an_audited_module():
    responses = {"comments": "Looks fine\nbut check the list"}
    assert _report(responses=responses)["comment"] == ""
    shown = _report(responses=responses, has_audit=True, last_saved="2026-10-01 09:30:00",
                    auditor="dla")["comment"]
    assert "Looks fine" in shown



def _card(key, state, **kw):
    args = dict(responses={}, has_audit=False, created=None)
    args.update(kw)
    return report_model.section_card_content(key, {"state": state, "evidence": "lead_edit",
                                                    "last_modified": "2026-08-01"}, **args)


def test_short_wording_is_empty_for_a_plain_visible_section():
    assert _card("ACCESSIBILITY_STATEMENT", "visible_edited")["short"] == ""
    assert _card("ACCESSIBILITY_STATEMENT", "visible_unedited")["short"] == ""


def test_short_wording_for_a_lead_section_says_what_is_missing():
    assert _card("WELCOME_MODULE_OUTLINE", "drafted_hidden")["short"] == "Edited but still hidden"
    assert _card("WELCOME_MODULE_OUTLINE", "visible_unedited")["short"].startswith("No edits on record")
    assert _card("ACCESSIBILITY_STATEMENT", "not_started")["short"] == "Hidden from students"


def test_a_dla_tick_reads_short_and_flags_when_the_data_disagrees():
    ticked = {"welcome_outline": "True"}
    ok = _card("WELCOME_MODULE_OUTLINE", "visible_edited", responses=ticked, has_audit=True)
    assert ok["short"] == "DLA has observed as complete"
    off = _card("WELCOME_MODULE_OUTLINE", "drafted_hidden", responses=ticked, has_audit=True)
    assert off["short"] == "DLA has observed as complete (data: hidden from students)"
    unticked = _card("WELCOME_MODULE_OUTLINE", "visible_edited",
                     responses={"welcome_outline": "False"}, has_audit=True)
    assert unticked["short"] == "DLA has observed as incomplete"


def test_the_full_wording_is_untouched_by_the_short_one():
    card = _card("WELCOME_MODULE_OUTLINE", "visible_edited",
                 responses={"welcome_outline": "True"}, has_audit=True)
    assert card["action"] == "A Digital Learning Advisor has recorded this as complete in the audit."


def test_rows_carry_a_blackboard_type():
    states = {k: {"state": "visible_edited", "evidence": "lead_edit", "last_modified": "2026-08-01"}
              for k in ("MODULE_INFORMATION", "WELCOME_MODULE_OUTLINE", "SKILLS_DEVELOPMENT_SGAS",
                        "STUDENT_VOICE", "ACCESSIBILITY_STATEMENT")}
    rows = report_model.template_rows(TEMPLATE_SECTION_TREE, states, {}, False, None, {})
    types = {r["key"]: r["type"] for r in rows if r["kind"] == "section"}
    assert types == {"MODULE_INFORMATION": "Learning module",
                     "WELCOME_MODULE_OUTLINE": "Ultra Document",
                     "SKILLS_DEVELOPMENT_SGAS": "LTI", "STUDENT_VOICE": "Folder",
                     "ACCESSIBILITY_STATEMENT": "Link"}
    assert all(r["type"] == "Learning module" for r in rows if r["kind"] == "heading")


def test_table_status_is_complete_but_the_badge_keeps_its_full_wording():
    ticked = _card("WELCOME_MODULE_OUTLINE", "visible_edited",
                   responses={"welcome_outline": "True"}, has_audit=True)
    assert ticked["short_status"] == "Complete"
    assert ticked["badge"] == "Manually verified complete"
    unticked = _card("WELCOME_MODULE_OUTLINE", "visible_edited",
                     responses={"welcome_outline": "False"}, has_audit=True)
    assert unticked["short_status"] == "Incomplete"
    # Anything not manually verified keeps its badge as the status.
    plain = _card("ACCESSIBILITY_STATEMENT", "visible_edited")
    assert plain["short_status"] == plain["badge"] == "Visible to students"
