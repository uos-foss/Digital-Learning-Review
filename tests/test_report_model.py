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


# --- School Dashboard --------------------------------------------------------

def test_score_shows_the_stage_until_a_course_has_content():
    assert report_model.score_or_stage(
        {"Content Maturity": "In progress", "Ally Overall": 0.953}) == "95.3%"
    assert report_model.score_or_stage(
        {"Content Maturity": "Not yet built", "Ally Overall": 1.0}) == "Not started"
    assert report_model.score_or_stage({"Content Maturity": "Empty"}) == "Empty"
    assert report_model.score_or_stage({"Content Maturity": ""}) == "—"
    # In progress but no score: the stage, not a blank.
    assert report_model.score_or_stage({"Content Maturity": "In progress"}) == "In progress"


def test_a_dla_answer_outranks_leganto_in_the_reading_list_cell():
    row = {"Leganto Missing": True, "Leganto List Status": ""}
    assert report_model.reading_list_display(row, True) == "✅ DLA confirmed"
    assert report_model.reading_list_display(row, False) == "❌ DLA: not done"
    assert report_model.reading_list_display(row, None) == "❌ Missing"
    assert report_model.reading_list_display({"Leganto List Status": "Published"}, None) == "✅ Published"
    assert report_model.reading_list_display({"Leganto List Status": "Mixed"}, None) == "📝 Draft"
    # In neither export: no signal, but still something to act on.
    assert report_model.reading_list_display({}, None) == "❌ Missing"


def _school_frame():
    base = {"Module name": "Mod", "Mod. lead": "ADA LOVELACE", "UG/ PG/ Other": "UG Level 2",
            "Ally Enabled": True, "Ally Severe": 0, "Ally Major": 0, "Ally Overall": 0.9,
            "Template Sections": {}, "Leganto Missing": False, "Leganto List Status": "Published"}
    return pd.DataFrame([
        {**base, "New module code": "TST002", "Content Maturity": "Not yet built"},
        {**base, "New module code": "TST001", "Content Maturity": "In progress", "Ally Overall": 0.8,
         "SGA Attributes": 2},
    ])


def _school(**kw):
    args = dict(spot_check_status={"TST001": "checked"}, fix_claims_by_module={},
                active_fields=[], can_view_sga=False)
    args.update(kw)
    summaries = {"TST001": {"Actionable Items": 3, "Responses": {}},
                 "TST002": {"Actionable Items": 1, "Responses": {}}}
    return report_model.build_school("TST", "Autumn", _school_frame(), summaries, **args)


def test_headline_figures_use_the_shared_rules():
    labels = {label: value for label, value, _ in _school()["headline"]}
    assert labels["Total modules"] == "2"
    assert labels["Modules with no activity"] == "1"       # the template-only course
    assert labels["Average Ally score"] == "80.0%"          # built courses only
    assert labels["Outstanding actionable items"] == "4"


def test_modules_are_sorted_and_carry_their_cells():
    modules = _school()["modules"]
    assert [m["code"] for m in modules] == ["TST001", "TST002"]
    first = modules[0]
    assert first["lead"] == "Ada Lovelace" and first["level"] == "UG2"
    assert first["score"] == "80.0%" and first["items"] == 3
    assert first["spot_check"] == "✅ Checked" and modules[1]["spot_check"] == ""
    assert modules[1]["score"] == "Not started"


def test_the_sga_column_needs_the_capability_and_an_import():
    assert _school()["show_sga"] is False
    assert _school(can_view_sga=True)["show_sga"] is True
    frame = _school_frame().drop(columns=["SGA Attributes"])
    no_import = report_model.build_school(
        "TST", "Autumn", frame, {}, spot_check_status={}, fix_claims_by_module={},
        active_fields=[], can_view_sga=True)
    assert no_import["show_sga"] is False


def test_the_matrix_has_one_row_per_module_and_aligned_cells():
    matrix = _school()["matrix"]
    assert [r["code"] for r in matrix["rows"]] == ["TST001", "TST002"]
    assert matrix["columns"][-1] == "Accessibility"
    assert all(len(r["cells"]) == len(matrix["columns"]) for r in matrix["rows"])


def test_ally_snapshot_date_accepts_a_series_or_a_dict():
    # The Streamlit page passes a pandas Series, Django a dict. `row or {}`
    # raised "truth value of a Series is ambiguous" on the Series.
    checked = {"Ally Last Checked": "2026-10-01"}
    for row in (pd.Series(checked), checked):
        assert report_model.ally_snapshot_date(row, {}) == "01-10-2026"
    assert report_model.ally_snapshot_date(None, {"ally": "2026-10-05"}) == "05-10-2026"


def test_date_from_filename_reads_a_day_first_date_or_gives_none():
    import datetime
    from processing import date_from_filename
    assert date_from_filename("Ally export 09-10-2026.csv") == datetime.date(2026, 10, 9)
    assert date_from_filename("readiness_9-1-26.csv") == datetime.date(2026, 1, 9)
    # Day first: 03-04 is 3 April, not 4 March.
    assert date_from_filename("leganto 03-04-2026.csv") == datetime.date(2026, 4, 3)
    for none in ("export.csv", "", None, "report 31-31-2026.csv"):
        assert date_from_filename(none) is None


# --- School Dashboard: Spot-Check Comments and Reported Fixes ---------------

def _comments_frame():
    return pd.DataFrame([
        # Re-flagged module: two rows, newest flag first, one comment.
        {"id": 3, "module_code": "TST001", "status": "pending", "flagged_by": "ann",
         "flagged_on": "2026-10-10 09:00:00", "checked_by": None, "checked_on": None,
         "comment": " Fixed the contacts\nand the outline ", "comment_by": "bob",
         "comment_on": "2026-10-05 10:00:00"},
        {"id": 1, "module_code": "TST001", "status": "checked", "flagged_by": "ann",
         "flagged_on": "2026-09-01 09:00:00", "checked_by": "bob", "checked_on": None,
         "comment": " Fixed the contacts\nand the outline ", "comment_by": "bob",
         "comment_on": "2026-10-05 10:00:00"},
        {"id": 2, "module_code": "TST002", "status": "pending", "flagged_by": "ann",
         "flagged_on": "2026-10-11 09:00:00", "checked_by": None, "checked_on": None,
         "comment": "", "comment_by": None, "comment_on": None},
        {"id": 4, "module_code": "TST003", "status": "checked", "flagged_by": "cat",
         "flagged_on": "2026-09-02 09:00:00", "checked_by": "bob", "checked_on": None,
         "comment": "Later note", "comment_by": "dan", "comment_on": "2026-10-09 10:00:00"},
    ])


def test_comments_one_card_per_module_newest_comment_first():
    out = report_model.build_spot_check_comments(
        _comments_frame(), {"TST001": "Alpha"}, [])
    assert [c["code"] for c in out["cards"]] == ["TST003", "TST001", "TST002"]
    assert out["flagged"] == 3 and out["with_comment"] == 2 and out["without_comment"] == 1
    assert out["label"] == "Additional Comments"
    first_flag = next(c for c in out["cards"] if c["code"] == "TST001")
    assert first_flag["status"] == "pending"      # the most recent flag is kept
    assert first_flag["name"] == "Alpha"


def test_comments_label_follows_audit_fields():
    out = report_model.build_spot_check_comments(
        _comments_frame(), {}, [{"id": "comments", "label": "Advisor remarks"}])
    assert out["label"] == "Advisor remarks"


def test_comments_filters():
    cards = report_model.build_spot_check_comments(_comments_frame(), {}, [])["cards"]
    shown = report_model.filter_comment_cards(cards)
    assert [c["code"] for c in shown] == ["TST003", "TST001"]     # empties hidden
    assert len(report_model.filter_comment_cards(cards, include_empty=True)) == 3
    assert [c["code"] for c in report_model.filter_comment_cards(cards, status="checked")] == ["TST003"]
    assert [c["code"] for c in report_model.filter_comment_cards(cards, search="CONTACTS")] == ["TST001"]
    assert [c["code"] for c in report_model.filter_comment_cards(
        cards, search="tst003", include_empty=True)] == ["TST003"]


def test_comments_empty_frame():
    out = report_model.build_spot_check_comments(pd.DataFrame(), {}, [])
    assert out["cards"] == [] and out["flagged"] == 0


def test_reported_fixes_rows_and_counts():
    fixes = pd.DataFrame([
        {"module_code": "TST001", "field_id": "contacts_complete", "claimed_by": "login1",
         "claimed_on": "2026-10-10 09:00:00", "note": "Done", "submitter_name": "a@x.ac.uk",
         "checked_on": "2026-10-11 09:00:00", "checked_by": "bob", "checked": True},
        {"module_code": "TST002", "field_id": "learning_materials", "claimed_by": "login2",
         "claimed_on": "2026-10-12 09:00:00", "note": None, "submitter_name": None,
         "checked_on": None, "checked_by": None, "checked": False},
    ])
    out = report_model.build_reported_fixes(
        fixes, {"TST001": "Alpha"}, [{"id": "learning_materials", "label": "Learning Materials"}])
    assert out["awaiting"] == 1 and out["checked"] == 1
    done, waiting = out["rows"]
    assert done["reporter"] == "a@x.ac.uk" and done["checked_on"] != "" and done["name"] == "Alpha"
    assert waiting["reporter"] == "login2" and waiting["note"] == "" and waiting["checked_on"] == ""
    assert waiting["section"] == "Learning Materials"
    assert report_model.build_reported_fixes(pd.DataFrame(), {}, [])["rows"] == []


# --- School Dashboard: Ally Analytics ---------------------------------------

def _ally_school():
    return pd.DataFrame([
        {"New module code": "TST001", "Module name": "Alpha", "Mod. lead": "ADA LOVELACE",
         "Content Maturity": "In progress", "Ally Overall": 0.619, "Ally Files": 0.4,
         "Ally WYSIWYG": 0.98, "Total Files": 87, "Ally WYSIWYG Items": 47,
         "Ally Severe": 9, "Ally Major": 101, "Ally Minor": 84, "Ally Students": 51},
        {"New module code": "TST002", "Module name": "Beta", "Mod. lead": "",
         "Content Maturity": "Not yet built", "Ally Overall": 1.0, "Ally Files": 1.0,
         "Ally WYSIWYG": 1.0, "Total Files": 2, "Ally WYSIWYG Items": 3,
         "Ally Severe": 0, "Ally Major": 0, "Ally Minor": 0, "Ally Students": 0},
    ])


def _ally_issues():
    return pd.DataFrame([
        {"module_code": "TST001", "check_name": "PDFImageOnly", "severity": 1, "items": 24},
        {"module_code": "TST001", "check_name": "ImageNoAlt", "severity": 2, "items": 10},
        {"module_code": "TST002", "check_name": "ImageNoAlt", "severity": 2, "items": 4},
        {"module_code": "OTHER9", "check_name": "ImageNoAlt", "severity": 2, "items": 99},
    ])


def test_maturity_note_only_when_under_half_started():
    half = _ally_school()                                    # 1 of 2 started
    assert report_model.maturity_note(half) == ""
    low = pd.concat([half, half.assign(**{"New module code": "X"}).iloc[1:]])   # 1 of 3
    note = report_model.maturity_note(low)
    assert note.startswith("1 of 3 modules have content beyond their template. ")
    assert report_model.maturity_note(pd.DataFrame()) == ""


def test_ally_analytics_scopes_issues_to_the_school_and_counts_items():
    out = report_model.build_ally_analytics(_ally_school(), _ally_issues())
    by_issue = {r["items"]: r for r in out["profile"]}
    assert sorted(by_issue) == [14, 24] or sorted(by_issue) == [24, 14]   # OTHER9's 99 excluded
    assert out["profile"][0]["severity"] == "Severe"                      # severity first
    assert max(r["bar"] for r in out["profile"]) == 100
    first = out["modules"][0]
    assert first["code"] == "TST001" and first["overall"] == "61.9%" and first["lead"] == "Ada Lovelace"
    assert first["matching"] is None and not out["filters_active"]


def test_ally_analytics_filters_narrow_the_table_and_ignore_junk():
    out = report_model.build_ally_analytics(_ally_school(), _ally_issues(), severities=["Severe"])
    assert out["filters_active"] and [m["code"] for m in out["modules"]] == ["TST001"]
    assert out["modules"][0]["matching"] == 24
    assert all(r["severity"] == "Severe" for r in out["profile"])
    junk = report_model.build_ally_analytics(
        _ally_school(), _ally_issues(), severities=["bogus"], issues=["nope"])
    assert not junk["filters_active"] and len(junk["modules"]) == 2
    both = report_model.build_ally_analytics(
        _ally_school(), _ally_issues(), issues=[out_label for out_label in
                                                 report_model.build_ally_analytics(
                                                     _ally_school(), _ally_issues())["issue_options"]][:1])
    assert both["filters_active"] and both["modules"]


def test_ally_analytics_without_issue_data():
    out = report_model.build_ally_analytics(_ally_school(), pd.DataFrame())
    assert not out["has_issue_data"] and out["profile"] == [] and len(out["modules"]) == 2


# --- The Blackboard item tree ------------------------------------------------

def test_tree_guides_follow_siblings_and_depth():
    def row(depth, kind="section"):
        return {"kind": kind, "depth": depth}
    rows = [row(0), row(1), row(1), row(2), row(2), row(1), row(0), row(1)]
    rows.insert(5, {"kind": "note", "depth": 1})              # a note is not a tree node
    out = report_model.add_tree_guides(rows)
    shapes = [(r["depth"], r.get("tree")) for r in out if r["kind"] != "note"]
    assert shapes[0] == (0, None) and shapes[6] == (0, None)
    assert shapes[1][1] == {"cont": [], "last": False}        # first of three children
    assert shapes[3][1] == {"cont": [True], "last": False}    # its parent has a sibling after it
    assert shapes[4][1] == {"cont": [True], "last": True}     # last grandchild, line above still runs on
    assert shapes[5][1] == {"cont": [], "last": True}         # last child of the first heading
    assert shapes[7][1] == {"cont": [], "last": True}         # the second heading's only child
    # the note sits under a depth-1 item with another depth-1 item still to come, so the
    # level-1 line runs through it and it draws no elbow of its own
    assert out[5]["tree"] == {"cont": [True], "last": True}


def test_tree_guides_empty_and_flat():
    assert report_model.add_tree_guides([]) == []
    flat = report_model.add_tree_guides([{"kind": "section", "depth": 0}] * 3)
    assert all("tree" not in r for r in flat)
