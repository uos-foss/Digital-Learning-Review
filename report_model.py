"""
What the module report says, as plain data, with no Streamlit and no Django.

The wording and verdicts behind a module report used to live inside
`views/module_report.py`, interleaved with `st.markdown()` calls, so a second
front end could only copy them. Extracted 12-10-2026 for the Django port: the
Streamlit page, its PDF export and `web/modules/` now all read these, so a
section card, the Report Summary's opening sentence or an Ally band cannot say
one thing in one place and another elsewhere.

Everything here takes data in and returns data out. Rendering - HTML, colours
as CSS, escaping - belongs to the caller. The functions that were already
shared with the PDF export (`section_card_content()`, `template_rows()`,
`ally_summary()`) moved here unchanged apart from the additive keys noted on
each; the PDF ignores keys it does not read.
"""

import pandas as pd

from processing import (
    CURRENT_ACADEMIC_YEAR,
    derive_module_findings,
    format_comment_markdown,
    mean_score,
    module_alignment_status,
    readiness_created_date,
    reading_list_verdict,
    school_of,
    scoreable,
    summarise_ally_issue_categories,
    summarise_ally_issues,
    title_case_name,
    SECTION_STATES,
    SGA_SECTION,
    TEMPLATE_SECTIONS,
    TEMPLATE_SECTION_TREE,
    fix_claim_words,
    fmt_report_date,
    fmt_report_datetime,
    readiness_evidence_words,
    readiness_manual_override,
    sga_blocks_sga_field,
)

# How each Ally score band reads to an auditor. Ally's own wording, so the
# portal and the course report agree.
ALLY_BANDS = [
    (1.0, "#047857", "Perfect", "No accessibility issues were found by the tool."),
    (0.67, "#10B981", "High", "Mostly accessible, but minor improvements are still possible."),
    (0.34, "#F59E0B", "Medium", "Somewhat accessible. Needs improvement."),
    (0.0, "#EF4444", "Low", "Severe or multiple accessibility issues."),
]

# What each maturity class means for reading the score beside it. There is no
# "Built"/"Complete" state: module leads add content just-in-time throughout
# the course, often up to the final assessment, so a content count can only
# ever show a course has started - never that it is finished.
ALLY_MATURITY_NOTE = {
    "Not yet built": ("#6B7280", "ℹ️", "This course still holds only its rolled-over template. "
                      "The accessibility score describes the template, not teaching materials."),
    "Empty": ("#6B7280", "ℹ️", "Ally has found no content in this course at all."),
    "In progress": ("#F59E0B", "🚧", "The course has content beyond its template, so the score "
                    "reflects real material - but module leads build throughout the year, "
                    "so expect it to keep moving as more goes up."),
    "No data": ("#6B7280", "—", "This module has no Ally record for the current year."),
}

# Colour used for each Ally severity tier on the accessibility issue cards.
TIER_COLOUR = {"Severe": "#EF4444", "Major": "#F59E0B", "Minor": "#6B7280"}

SURFACE_WORDS = {
    'editor': ("✏️", "Fix in the Blackboard editor"),
    'image': ("🖼️", "Fix in the browser via Ally feedback"),
    'file': ("📄", "Re-author and re-upload the file"),
}

# Template section states by tier. 'action' and 'attention' both render amber
# rather than red or grey: a section drafted and left hidden ('action') means
# somebody has done the work, and one with no edit evidence yet ('attention',
# e.g. "Not started", "Visible, unedited") is still just outstanding work, not
# a failing - only 'fault' (Deleted/Missing - actual course-creation faults)
# stays red. Only two colours are used for badges: green for genuinely done,
# amber for everything still needing a look.
STATE_TIER_COLOUR = {
    'ok': "#10B981",
    'action': "#F59E0B",
    'attention': "#F59E0B",
    'fault': "#EF4444",
}


# Card copy for sections nobody expects a module lead to edit - every section
# except the ones in LEAD_OWNED_SECTIONS. For these, edited-or-not is noise (see
# readiness_section_is_ready()): only whether it's Visible or Hidden is
# actionable, so both "edited" and "unedited" collapse to one Visible message
# and both "drafted" and "not started" collapse to one Hidden message, unlike
# lead-owned sections where that distinction is the whole point. Each entry is
# (visible_text, hidden_text); sections without an entry yet fall back to
# _INSTITUTION_DEFAULT_COPY. Filled in one section at a time as wording is
# agreed, not guessed wholesale.
INSTITUTION_SECTION_COPY = {
    'MODULE_INFORMATION': (
        "Visible to students.",
        "Hidden from students. The Learning Module should not be hidden - "
        "check and make sure it's visible."),
    'MODULE_READING_LIST': (
        "Visible to students. This is set centrally rather than written by "
        "the module lead, so being visible is all that's needed here.",
        "Hidden from students. The reading list needs to be visible to "
        "students or, if a reading list is not used, marked accordingly."),
}
_INSTITUTION_DEFAULT_COPY = (
    "Visible to students. This is set centrally rather than written by the "
    "module lead, so being visible is all that's needed here.",
    "Hidden from students. This is set centrally rather than written by the "
    "module lead, but it still needs to be visible to students.")

# Icons matching Blackboard Ultra's own course content list, so a card reads
# as "this is a folder" / "this is a link" at a glance the same way Ultra's
# own content list does. The plain outline ones (learning_module, folder,
# document, link) are fixed neutral grey regardless of the card's status
# colour - these indicate what the section *is*, not its current state. The
# LTI tools each carry their own brand mark in Blackboard rather than a
# shared generic icon, so those are approximations of the actual badges
# (colour and glyph) from the module lead's own screenshots, not literal
# traces of the originals.
_ICON_STROKE = (
    'fill="none" stroke="#6B7280" stroke-width="1.8" '
    'stroke-linecap="round" stroke-linejoin="round"')
CONTENT_TYPE_ICONS = {
    'learning_module': (
        f'<svg width="16" height="16" viewBox="0 0 24 24" {_ICON_STROKE}>'
        '<rect x="3" y="3" width="18" height="18" rx="2"/>'
        '<line x1="7" y1="8" x2="17" y2="8"/>'
        '<line x1="7" y1="12" x2="17" y2="12"/>'
        '<line x1="7" y1="16" x2="17" y2="16"/></svg>'),
    'folder': (
        f'<svg width="16" height="16" viewBox="0 0 24 24" {_ICON_STROKE}>'
        '<path d="M3 6a1 1 0 0 1 1-1h5l2 2h9a1 1 0 0 1 1 1v10a1 1 0 0 1-1 '
        '1H4a1 1 0 0 1-1-1V6z"/></svg>'),
    'document': (
        f'<svg width="16" height="16" viewBox="0 0 24 24" {_ICON_STROKE}>'
        '<path d="M14 3H6a1 1 0 0 0-1 1v16a1 1 0 0 0 1 1h12a1 1 0 0 0 '
        '1-1V8z"/><path d="M14 3v5h5"/>'
        '<line x1="8" y1="13" x2="16" y2="13"/>'
        '<line x1="8" y1="17" x2="16" y2="17"/></svg>'),
    'link': (
        f'<svg width="16" height="16" viewBox="0 0 24 24" {_ICON_STROKE}>'
        '<path d="M9 15l6-6"/>'
        '<path d="M11 6l1-1a4 4 0 0 1 6 6l-1 1"/>'
        '<path d="M13 18l-1 1a4 4 0 0 1-6-6l1-1"/></svg>'),
    # Purple "S" badge - Skills Development (SGAs) tool.
    'sga': (
        '<svg width="16" height="16" viewBox="0 0 24 24">'
        '<rect x="1" y="1" width="22" height="22" rx="5" fill="#6D28D9"/>'
        '<text x="12" y="17" text-anchor="middle" font-family="Arial, sans-serif" '
        'font-size="14" font-weight="700" fill="#ffffff">S</text></svg>'),
    # Green list badge - Module Reading List tool.
    'reading_list': (
        '<svg width="16" height="16" viewBox="0 0 24 24">'
        '<rect x="1" y="1" width="22" height="22" rx="5" fill="#127A52"/>'
        '<line x1="6" y1="8" x2="18" y2="8" stroke="#fff" stroke-width="2" stroke-linecap="round"/>'
        '<line x1="6" y1="12" x2="18" y2="12" stroke="#fff" stroke-width="2" stroke-linecap="round"/>'
        '<line x1="6" y1="16" x2="14" y2="16" stroke="#fff" stroke-width="2" stroke-linecap="round"/></svg>'),
    # Pink circle "e" badge - Encore Lecture Capture.
    'encore': (
        '<svg width="16" height="16" viewBox="0 0 24 24">'
        '<circle cx="12" cy="12" r="11" fill="#D6006F"/>'
        '<text x="12" y="17" text-anchor="middle" font-family="Georgia, serif" '
        'font-size="15" font-weight="700" font-style="italic" fill="#ffffff">e</text></svg>'),
    # Graduation cap outline - Assessment Overview.
    'assessment_cap': (
        f'<svg width="16" height="16" viewBox="0 0 24 24" {_ICON_STROKE}>'
        '<path d="M12 4 2 9l10 5 10-5-10-5z"/>'
        '<path d="M6 11.5V16c0 1.5 2.7 3 6 3s6-1.5 6-3v-4.5"/>'
        '<path d="M22 9v6"/></svg>'),
}

# Which Blackboard Ultra content type each section is, purely for the card
# icon - confirmed against the module lead's own screenshots where noted,
# best guess everywhere else pending confirmation.
SECTION_CONTENT_TYPE = {
    'MODULE_INFORMATION': 'learning_module',       # confirmed
    'WELCOME_MODULE_OUTLINE': 'document',          # guess
    'KEY_STAFF_CONTACTS': 'document',              # guess
    'SKILLS_DEVELOPMENT_SGAS': 'sga',              # confirmed
    'STUDENT_VOICE': 'folder',                     # confirmed
    'HOW_YOUR_FEEDBACK_SHAPES': 'document',        # guess
    'ACCESSIBILITY_STATEMENT': 'link',             # confirmed
    'SCHOOL_HANDBOOK': 'link',                     # confirmed
    'ASSESSMENT_OVERVIEW': 'assessment_cap',       # confirmed
    'ASSESSMENT_DETAIL': 'document',               # guess
    'ASSESSMENT_SUPPORT_GUIDANCE': 'folder',        # confirmed
    'MODULE_READING_LIST': 'reading_list',         # confirmed
    'ENCORE_LECTURE_CAPTURE': 'encore',            # confirmed
    'UNIVERSITY_HELP_SUPPORT': 'folder',           # guess
}


# One-line wording per data state, for tables. See section_card_content().
SHORT_STATE_WORDS = {
    'visible_edited': '',
    'visible_unedited': "No edits on record; may still hold placeholder text",
    'drafted_hidden': "Edited but still hidden",
    'not_started': "Not started; still the default template",
    'deleted': "Section deleted from the course",
    'missing': "Section missing from the course shell",
    'unknown': "No status in the report",
}
# A "complete" tick the data does not back up is worth flagging in the short text.
SHORT_DATA_DISAGREES = {'drafted_hidden', 'not_started', 'deleted', 'missing'}

# What each section is in Blackboard Ultra, in words, for a Type column.
CONTENT_TYPE_LABELS = {
    'learning_module': "Learning module",
    'document': "Ultra Document",
    'folder': "Folder",
    'link': "Link",
    'sga': "LTI",
    'reading_list': "LTI",
    'encore': "LTI",
    'assessment_cap': "LTI",
}


def ally_band(score):
    for threshold, colour, level, description in ALLY_BANDS:
        if score >= threshold:
            return colour, level, description
    return ALLY_BANDS[-1][1:]


def summary_intro(has_audit):
    """The Report Summary's opening sentence - shared with the PDF export."""
    if has_audit:
        return ("This report has been generated using data evidence and also "
                "manually spot-checked by a Digital Learning Advisor.")
    return ("This module report has been generated using data evidence and "
            "hasn't been verified yet by your Digital Learning Advisor. The "
            "combination of data from different sources gives us a "
            "reasonably good picture of the readiness of this module.")


def refreshed_line(active_row):
    """When each data source was last refreshed - shared with the PDF export."""
    ally_date = fmt_report_date(active_row.get('Ally Last Checked')) if active_row is not None else ""
    readiness_date = fmt_report_date(active_row.get('Readiness Snapshot')) if active_row is not None else ""
    leganto_date = fmt_report_date(active_row.get('Leganto Snapshot')) if active_row is not None else ""
    return (f"Data last refreshed: Ally {ally_date or '—'} · "
            f"Template Alignment {readiness_date or '—'} · "
            f"Reading list {leganto_date or '—'}")


def section_order():
    """TEMPLATE_SECTION_TREE section keys in the order the report shows them."""
    order = []
    def walk(nodes):
        for node_type, value, children in nodes:
            order.append(value)  # a label (Learning Materials) has a place too
            walk(children)
    walk(TEMPLATE_SECTION_TREE)
    return {k: i for i, k in enumerate(order)}


def section_card_content(key, state, responses, has_audit, created, leganto=None,
                          sga_attrs=None, fix_claims=None):
    """
    What one template section's card says - label, badge, colour, action
    and footer text - without rendering it. Shared by _render_section_card()
    and the PDF export, so the two can never describe a section differently.
    See _render_section_card() for the reasoning behind each branch.
    """
    # Unrecognised keys default to lead-owned, the stricter read, rather than
    # silently getting the lenient institution treatment below.
    label, owner, audit_field_id = TEMPLATE_SECTIONS.get(key, (key, 'lead', None))
    state_key = state.get('state', 'unknown')
    badge, tier, action = SECTION_STATES.get(state_key, SECTION_STATES['unknown'])
    footer = readiness_evidence_words(state, created)
    # Whether the action/footer lines earn their vertical space. False only
    # for the plain institution "visible, nothing more to say" case - every
    # other path below that produces real information (a caution, a fault, a
    # DLA's manual verification, Reading List's Leganto note) sets this back
    # to True, since collapsing those would hide the one thing worth reading.
    show_detail = True
    # The one-line version of action/footer for tables (the Django report).
    # The full wording above is what the Streamlit page and the PDF still show;
    # this is a second, terser rendering of the same verdict, set in step with
    # each branch below. Empty means nothing to add beyond the status.
    short = SHORT_STATE_WORDS.get(state_key, '')
    # Likewise a terser status for the table, where "Manually verified
    # complete" and the short detail beside it would say the same thing twice.
    # None means use the badge as it is.
    short_status = None

    if owner != 'lead':
        visible_copy, hidden_copy = INSTITUTION_SECTION_COPY.get(key, _INSTITUTION_DEFAULT_COPY)
        if state_key in ('visible_edited', 'visible_unedited'):
            badge, tier, action = "Visible to students", 'ok', visible_copy
            show_detail = False
            short = ''
        elif state_key in ('drafted_hidden', 'not_started'):
            badge, tier, action = "Hidden from students", 'action', hidden_copy
            short = "Hidden from students"

    colour = STATE_TIER_COLOUR.get(tier, "#6B7280")

    if key == 'MODULE_READING_LIST' and leganto is not None and tier == 'ok':
        status = leganto.get('status', '')
        items = int(leganto.get('items', 0) or 0)
        draft_items = int(leganto.get('draft_items', 0) or 0)
        if leganto.get('missing'):
            badge, tier = "Visible, no reading list", 'action'
            short = "No reading list in Leganto"
            action = ("Visible to students, but Leganto shows no reading list connected to "
                      "this module. Being visible here isn't the finish line for this "
                      "section - a reading list still needs to be added and published.")
        elif status == 'Draft':
            badge, tier = "Visible, list in Draft", 'action'
            short = f"Reading list in Draft ({items} item{'s' if items != 1 else ''})"
            action = (f"Visible to students, but the connected reading list is still in "
                      f"Draft in Leganto ({items} item{'s' if items != 1 else ''}). It needs "
                      f"publishing before students can actually use it.")
        elif status == 'Mixed':
            # A module can have more than one Blackboard course shell (see
            # "Leganto reading-list data" in CLAUDE.md), and this is the
            # visible result when they disagree - most often one cohort's
            # shell published while another's is still Draft. Naming both
            # counts matters here: without it, "Draft" alone would read as
            # nothing published yet, when what's actually true might be that
            # nearly everything is - only a handful of items on one shell
            # still need publishing.
            badge, tier = "Visible, list partly published", 'action'
            short = f"Reading list partly published ({draft_items} of {items} in Draft)"
            action = (f"Visible to students. The connected reading list is partly published in "
                      f"Leganto - {draft_items} of {items} item{'s' if items != 1 else ''} "
                      f"still in Draft, most likely on a different course shell for this "
                      f"module. Those still need publishing.")
        elif status == 'Published':
            action = "Visible to students, and the connected reading list is Published in Leganto."
            short = "Reading list published in Leganto"
        show_detail = True
        colour = STATE_TIER_COLOUR.get(tier, "#6B7280")

    if key == SGA_SECTION and tier == 'ok' and sga_blocks_sga_field(sga_attrs):
        badge, tier = "Visible, no SGAs mapped", 'action'
        short = "No SGAs mapped in the SGA tool"
        action = ("Visible to students, but the SGA tool has no graduate attributes mapped "
                  "to this module yet.")
        show_detail = True
        colour = STATE_TIER_COLOUR.get(tier, "#6B7280")

    claimed = False
    manual = readiness_manual_override(audit_field_id, responses) if has_audit else None
    if manual and key == SGA_SECTION and sga_blocks_sga_field(sga_attrs):
        manual = None  # an empty SGA mapping outranks a 'complete' tick
    if manual is not None:
        data_label = SECTION_STATES.get(state_key, SECTION_STATES['unknown'])[0]
        if manual:
            badge, colour = "Manually verified complete", STATE_TIER_COLOUR['ok']
            action = "A Digital Learning Advisor has recorded this as complete in the audit."
            short = "DLA has observed as complete"
            short_status = "Complete"
        else:
            badge, colour = "Manually verified incomplete", STATE_TIER_COLOUR['fault']
            action = "A Digital Learning Advisor has recorded this as not yet complete in the audit."
            short = "DLA has observed as incomplete"
            short_status = "Incomplete"
        footer = f"Automatically detected as of the last update: {data_label}. {footer}"
        # Worth saying only when the data disagrees with a "complete" tick.
        if manual and state_key in SHORT_DATA_DISAGREES:
            short += f" (data: {data_label.lower()})"
        show_detail = True
        claim = (fix_claims or {}).get(audit_field_id)
        if claim and not manual:
            badge, colour = "Reported fixed", STATE_TIER_COLOUR['ok']
            action = fix_claim_words(claim)
            short = action
            claimed = True

    return {'label': label, 'badge': badge, 'colour': colour, 'action': action,
            'footer': footer, 'show_detail': show_detail, 'claimed': claimed,
            'short': short, 'short_status': short_status or badge}


def template_rows(nodes, states, responses, has_audit, created, leganto, depth=0,
                  sga_attrs=None, fix_claims=None, sga_note=None):
    """TEMPLATE_SECTION_TREE flattened, walked exactly as the Streamlit page's
    _render_section_tree() walks it, with each card's wording from
    section_card_content(). Read by the PDF export and the Django report.

    Each section row also carries its `key`, for the icon. `sga_note`, when
    given, adds a 'note' row under Skills Development (SGAs) whether or not
    that section has readiness data of its own: the SGA export is a separate
    import, so the note must not vanish because the card above it did not
    render. The PDF passes none."""
    rows = []
    for node_type, value, children in nodes:
        if node_type == 'section':
            state = states.get(value)
            if state:
                card = section_card_content(
                    value, state, responses, has_audit, created,
                    leganto if value == 'MODULE_READING_LIST' else None, sga_attrs, fix_claims)
                rows.append({'kind': 'section', 'depth': depth, 'key': value,
                         'type': CONTENT_TYPE_LABELS.get(SECTION_CONTENT_TYPE.get(value), ''),
                         **card})
            if value == SGA_SECTION and sga_note:
                rows.append({'kind': 'note', 'depth': depth, 'text': sga_note})
        else:
            rows.append({'kind': 'heading', 'depth': depth, 'label': value,
                         'type': CONTENT_TYPE_LABELS['learning_module'],
                         'note': '' if children else "Not part of the readiness data yet."})
        if children:
            rows += template_rows(children, states, responses, has_audit, created,
                                  leganto, depth + 1, sga_attrs, fix_claims, sga_note)
    return rows


def ally_snapshot_date(active_row, import_dates):
    """The date the Accessibility report's data is from: the whole-table Ally
    import date (get_last_import_dates()['ally'], the figure the sidebar shows)
    in preference to this course's own last-checked date, which Ally's
    unchanged-course skip can leave on an earlier import than the one that
    just ran."""
    # active_row is a pandas Series on the Streamlit page and a dict in Django;
    # `active_row or {}` raises on a Series, so test for None explicitly.
    last_checked = str(
        ({} if active_row is None else active_row).get('Ally Last Checked', '') or '')
    return (fmt_report_date((import_dates or {}).get('ally'))
            or fmt_report_date(last_checked))


def ally_summary(active_row, ally_categories, snapshot_date):
    """The Accessibility tab's content, following the Streamlit page's
    _render_ally_card() branches. Read by the PDF export and the Django report.

    Beyond what the PDF reads it also carries `url`, `last_scanned` and
    `maturity_banner` (colour, icon, title, note) for the page's banner."""
    if active_row is None:
        return {'message': "No Ally accessibility data is available for this module."}
    maturity = str(active_row.get('Content Maturity', 'No data') or 'No data')
    n_files = int(active_row.get('Total Files', 0) or 0)
    n_wysiwyg = int(active_row.get('Ally WYSIWYG Items', 0) or 0)
    shells = int(active_row.get('Ally Shells', 0) or 0)
    if maturity == "No data" or (n_files == 0 and n_wysiwyg == 0 and shells == 0):
        return {'message': f"No Ally record for this module in {CURRENT_ACADEMIC_YEAR}. That "
                           "usually means it has no Blackboard course, or its course is filed "
                           "under a different code."}

    last_checked = str(active_row.get('Ally Last Checked', '') or '')
    last_scanned = fmt_report_date(last_checked) or "—"
    is_template = maturity in ("Not yet built", "Empty")
    maturity_line = ""
    maturity_banner = None
    if maturity != "In progress":
        colour, icon, note = ALLY_MATURITY_NOTE.get(maturity, ALLY_MATURITY_NOTE["No data"])
        shown = "Not started" if maturity == "Not yet built" else maturity
        maturity_line = f"{shown}: {note}"
        maturity_banner = {'colour': colour, 'icon': icon, 'title': shown,
                           'note': f"{note} · Last scanned {last_scanned}"}

    scores = []
    for label, key, sub in (
        ("Overall", 'Ally Overall', f"{n_files + n_wysiwyg} items"),
        ("Files", 'Ally Files', f"{n_files} file{'' if n_files == 1 else 's'}"),
        ("Page Content", 'Ally WYSIWYG',
         f"{n_wysiwyg} document{'' if n_wysiwyg == 1 else 's'}"),
    ):
        score = active_row.get(key)
        has_score = score is not None and pd.notna(score)
        colour = "#6B7280" if (is_template or not has_score) else ally_band(float(score))[0]
        scores.append((label, float(score) * 100 if has_score else None, sub, colour))

    categories = []
    if not ally_categories.empty:
        for _, row in ally_categories.iterrows():
            categories.append({'title': row['title'], 'items': row['items'],
                               'checks': row['checks'], 'why': row['why'],
                               'colour': TIER_COLOUR.get(row['severity_label'], "#6B7280")})

    return {'snapshot_date': snapshot_date, 'maturity': maturity_line, 'scores': scores,
            'disabled': not active_row.get('Ally Enabled', True),
            'categories': categories, 'is_template': is_template,
            'url': _http_url(active_row.get('URL')), 'last_scanned': last_scanned,
            'maturity_banner': maturity_banner}


def sga_note(active_row, can_view):
    """One neutral line for the Skills Development (SGAs) card: whether the SGA
    tool has any attributes mapped for this module, and how many. None when
    there is nothing to say - no SGA import yet this year, or the viewer lacks
    the SGA capability (`can_view`, from processing.can_view_sga()). A plain
    note, never amber and never in the PDF; the action itself comes from the
    section card."""
    if active_row is None or not can_view:
        return None
    attrs = pd.to_numeric(active_row.get('SGA Attributes'), errors='coerce')
    if pd.isna(attrs):
        return None
    if int(attrs) == 0:
        return "SGA tool: no graduate attributes mapped for this module yet."
    subs = int(pd.to_numeric(active_row.get('SGA Sub-Attributes'), errors='coerce') or 0)
    return (f"SGA tool: {int(attrs)} graduate attribute{'s' if attrs != 1 else ''} mapped "
            f"({subs} sub-attribute{'s' if subs != 1 else ''}).")


def audit_status_label(has_audit, last_saved, spot_check_pending):
    """Data-derived / Spot check-pending / Spot checked, with when.

    A bare "Spot checked" gave a module lead no way to tell a check saved this
    morning from one saved last October, so the date and time of the most
    recent saved answer goes beside it. `last_saved` is the latest
    audit_responses timestamp for the module, not spot_checks.checked_on: the
    label fires on has_audit, which covers audits never flagged as a
    spot-check, and a re-audit moves the response timestamp while checked_on
    stays frozen. Falls back to the bare wording if it is not a real timestamp.
    """
    if has_audit:
        checked_on = fmt_report_datetime(last_saved)
        return f"Spot checked on {checked_on}" if checked_on else "Spot checked"
    if spot_check_pending:
        return "Spot check-pending"
    return "Data-derived"


def action_items(actions):
    """Pending findings as the plain {label, description} pairs the Actions
    panel and the PDF list. Only 'boolean' and 'custom' findings have a place
    there; anything else is skipped, as it always has been.

    A 'custom' finding's label and description are free text a DLA typed, so
    they are joined into one description under the category: the caller must
    escape it (Django's autoescape does)."""
    items = []
    for a in actions:
        if a['type'] == 'custom':
            items.append({
                'label': a.get('category') or 'Custom Observation',
                'description': '\n'.join(p for p in (a.get('label', '').strip(),
                                                     a.get('description', '').strip()) if p)})
        elif a['type'] == 'boolean':
            items.append({'label': a.get('label', ''),
                          'description': a.get('description', '')})
    return items


def module_issues(df_issues, code):
    """This module's rows of an Ally issues frame, or an empty frame."""
    if df_issues is None or df_issues.empty:
        return pd.DataFrame()
    return df_issues[df_issues['module_code'].astype(str).str.strip().str.upper()
                     == str(code).strip().upper()]


def _http_url(value):
    """A link target only if it is http(s). The URLs are admin-imported, but a
    page that turns data into an href should not be one stray value away from a
    javascript: link."""
    text = _clean(value)
    return text if text.lower().startswith(("http://", "https://")) else ''


def _clean(value):
    """A SITS/legacy cell as display text: '' for blank, NaN or 'nan'."""
    text = str(value if value is not None else '').strip()
    return '' if text.lower() == 'nan' else text


def ally_issue_view(df_issues, code):
    """
    This module's Ally issues, ready to render: `categories` (what kind of
    thing is wrong and why it matters, written for the module lead) and
    `detail` (the per-check list a DLA audits against, grouped by severity
    tier). Both empty when the module has none. See the Streamlit page's
    _render_ally_issues() for why categories lead and detail is secondary.
    """
    mine = module_issues(df_issues, code)
    cats = summarise_ally_issue_categories(mine) if not mine.empty else pd.DataFrame()
    detail = summarise_ally_issues(mine) if not mine.empty else pd.DataFrame()

    categories = []
    if not cats.empty:
        for _, r in cats.iterrows():
            categories.append({
                'icon': r['icon'], 'title': r['title'], 'why': r['why'],
                'items': int(r['items']), 'checks': int(r['checks']),
                'colour': TIER_COLOUR.get(r['severity_label'], "#6B7280"),
                'items_word': "item" if r['items'] == 1 else "items",
                'checks_word': "issue type" if r['checks'] == 1 else "issue types"})

    tiers = []
    if not detail.empty:
        for _, r in detail.iterrows():
            if not tiers or tiers[-1]['name'] != r['severity_label']:
                tiers.append({'name': r['severity_label'], 'rows': [],
                              'colour': TIER_COLOUR.get(r['severity_label'], "#6B7280")})
            icon, where = SURFACE_WORDS.get(r['surface'], ("📄", ""))
            tiers[-1]['rows'].append({
                'label': r['label'], 'items': int(r['items']), 'advice': r['advice'],
                'icon': icon, 'where': where,
                'colour': TIER_COLOUR.get(r['severity_label'], "#6B7280")})
    return {'categories': categories, 'detail': tiers, 'detail_count': len(detail),
            'total_items': sum(c['items'] for c in categories), 'cat_frame': cats}


def build_report(code, row, *, responses, has_audit, last_saved, auditor, fix_claims,
                 active_fields, df_ally_issues, import_dates, can_view_sga,
                 spot_check_pending):
    """
    Everything the module report page shows, as plain data.

    The Django report renders this and nothing else, so no verdict is worked
    out in a view or a template. Every rule it applies comes from
    processing.py (findings, alignment, Ally roll-ups) or this module (card
    wording); the inputs are what the Streamlit page assembles from
    `checklist_sums`, in the shapes app.py::load_checklist_data() gives them:
    `responses` is {field_id: value}, flat; `has_audit` is a real auditor, not
    the 'System' stamp of a data-only entry (see "Unified module findings" in
    CLAUDE.md).

    Read-only by design. The fix-claim form and the PDF export are not here;
    `reported_fixed` is how a claim already made is displayed.
    """
    findings = derive_module_findings(row, responses, active_fields, fix_claims)
    pending = [f for f in findings if f['state'] == 'pending']
    open_actions = [f for f in pending if not f.get('fix_claimed')]
    claimed = [f for f in pending if f.get('fix_claimed')]

    states = row.get('Template Sections') or {}
    template = []
    if isinstance(states, dict) and states:
        template = template_rows(
            TEMPLATE_SECTION_TREE, states, responses, has_audit,
            readiness_created_date(states),
            {'missing': row.get('Leganto Missing', False),
             'status': _clean(row.get('Leganto List Status')),
             'items': int(row.get('Leganto List Items', 0) or 0),
             'draft_items': int(row.get('Leganto Draft Items', 0) or 0)},
            sga_attrs=pd.to_numeric(row.get('SGA Attributes'), errors='coerce'),
            fix_claims=fix_claims,
            sga_note=sga_note(row, can_view_sga))

    ally_issues = ally_issue_view(df_ally_issues, code)
    ally = ally_summary(row, ally_issues['cat_frame'], ally_snapshot_date(row, import_dates))
    ally['issues'] = ally_issues
    if 'snapshot_date' in ally:
        ally['intro'] = ally_intro_lines(ally['snapshot_date'])

    lead = _clean(row.get('Mod. lead'))
    if has_audit:
        last_updated = f"{fmt_report_datetime(last_saved) or 'Unknown'} by {auditor or 'Unknown'}"
    else:
        last_updated = "Never"

    return {
        'code': code,
        'school': school_of(code),
        'name': row.get('Module name', '') or code,
        'lead': title_case_name(lead) if lead else '',
        'level': _clean(row.get('UG/ PG/ Other')),
        'site_url': _http_url(row.get('URL')),
        'audit_status': audit_status_label(has_audit, last_saved, spot_check_pending),
        'has_audit': has_audit,
        'last_updated': last_updated,
        'summary': {
            'intro': summary_intro(has_audit),
            'refreshed': refreshed_line(row),
        },
        'comment': format_comment_markdown(responses.get('comments', '')) if has_audit else '',
        'actions': action_items(open_actions),
        'reported_fixed': [{'label': a.get('section_label', ''),
                            'description': a.get('description', '')} for a in claimed],
        'template': template,
        'ally': ally,
        'findings': findings,
    }


# Copy shared by both front ends, so a sentence reworded for one is reworded
# for the other. Plain text; each caller renders it its own way.
TEMPLATE_INTRO = (
    "The following represents the structure of your Blackboard course and "
    "its measured or observed state - e.g. whether items are visible to "
    "students, have been edited, etc.")
ALIGNMENT_LEGEND = (
    "✅ done · ❌ outstanding · 🔧 reported fixed, awaiting check · accessibility: "
    "🟢 good · 🟠 major issues · 🔴 severe issues · ⚪ nothing to judge yet")
NOTHING_OUTSTANDING = "Nothing outstanding right now."
ALLY_OFF_WARNING = (
    "Ally is switched off for this course, so students get no "
    "alternative formats and the module lead sees no feedback.")
ALLY_NO_ISSUES = "No accessibility issues reported."
ALLY_TEMPLATE_ONLY = (
    "This course still holds only its rolled-over template, so there's "
    "nothing to report yet.")
ALLY_HELP_LINKS = [
    ("Digital accessibility guidance", "https://staff.sheffield.ac.uk/digital-accessibility"),
    ("Making content accessible with Ally", "https://staff.sheffield.ac.uk/blackboard/ally"),
]


def ally_intro_lines(snapshot_date):
    """The three sentences that open the Accessibility report: it is a
    snapshot, what the scores are, and that the module lead's own Ally Course
    Report in Blackboard is the up-to-date, file-level source. They sit above
    the numbers because the caveat matters most before someone has drawn a
    conclusion from them."""
    return [
        f"This report is based on an institutional data snapshot from {snapshot_date}. "
        "It shows the Ally accessibility report for this module at the time of the "
        "snapshot; it is not live.",
        "The scores below are the familiar RAG-rated scores for Files (material "
        "you've uploaded), Page Content (Blackboard Ultra documents) and the Overall "
        "score, along with a summary of the kinds of accessibility issues found.",
        "This is simply a summary, not a replacement for your Ally course report - "
        "for a more detailed and up-to-date view of accessibility in your module, and "
        "to see which files are affected, always use the Ally Accessibility Report in "
        "Blackboard (Books & Course Tools > Ally Accessibility Report).",
    ]




# ---------------------------------------------------------------------------
# School Dashboard
# ---------------------------------------------------------------------------

SEMESTERS = ("Autumn", "Spring", "All year")

# Abbreviated in tables only; the full text is what is stored and shown
# elsewhere. Matches the Streamlit School Dashboard.
LEVEL_ABBREVIATIONS = {'Foundation': 'FY', 'UG Level 1': 'UG1',
                       'UG Level 2': 'UG2', 'UG Level 3': 'UG3'}


def score_or_stage(row):
    """
    The Ally score once a course is 'In progress', otherwise its build stage.

    One column rather than two: an untouched template scores near 100% and
    would otherwise read as the best module in the school, so the score only
    means something once there is content beyond it. Wording matches the
    module report's own banner ("Not started" for 'Not yet built').
    """
    maturity = row.get('Content Maturity')
    if maturity == 'In progress':
        value = row.get('Ally Overall')
        if value is not None and not pd.isna(value):
            return f"{value * 100:.1f}%"
    if not maturity:
        return "—"
    return "Not started" if maturity == "Not yet built" else maturity


def reading_list_display(row, verdict):
    """
    The reading-list cell. A DLA's recorded answer (`verdict`, from
    processing.reading_list_verdict()) overrides Leganto, which is exported
    rarely and often lags Blackboard; otherwise the Leganto status. A blank
    status means the module is in neither Leganto export: no signal either
    way, but a DLA scanning the column still has to act, so it reads as
    Missing, as it does on the Streamlit page.
    """
    if verdict is True:
        return "✅ DLA confirmed"
    if verdict is False:
        return "❌ DLA: not done"
    if row.get('Leganto Missing') == True:  # noqa: E712 - numpy.bool_ is never `is True`
        return "❌ Missing"
    status = row.get('Leganto List Status', '')
    if status == 'Published':
        return "✅ Published"
    if status in ('Draft', 'Mixed'):
        return "📝 Draft"
    if status == 'No List Expected':
        return "➖ Not needed"
    return "❌ Missing"


def spot_check_display(status):
    return {'pending': "⏳ Pending", 'checked': "✅ Checked"}.get(status, "")


def build_school(school, semester, school_df, summaries, *, spot_check_status,
                 fix_claims_by_module, active_fields, can_view_sga):
    """
    One school's dashboard as plain data: four headline figures, a table of
    its modules, and the Template Alignment matrix.

    `school_df` is the school's module records for the semester (frames from
    loaders.assemble_module_frames(), narrowed with
    processing.resolve_semester_df()); `summaries` is
    loaders.load_audit_summaries() for those modules. Nothing is decided here
    that processing.py does not already decide: the item counts come from
    derive_module_findings(), the matrix rows from module_alignment_status(),
    the averages from the same scoreable()/mean_score() the Streamlit page
    reads. Read-only: the flagging and removal actions stay in Streamlit.
    """
    school_df = school_df.sort_values('New module code').reset_index(drop=True)

    codes = [str(c).strip().upper() for c in school_df['New module code']]
    outstanding = sum(summaries.get(c, {}).get('Actionable Items', 0) for c in codes)
    average = mean_score(school_df)
    headline = [
        ("Total modules", f"{len(school_df)}",
         f"Modules for {school} in the {semester} semester."),
        ("Modules with no activity", f"{len(school_df) - len(scoreable(school_df))}",
         "Modules that still only have the default template: no content added yet."),
        ("Average Ally score", f"{average:.1%}" if average is not None else "—",
         "Ally's overall score, averaged across modules with content beyond their template only."),
        ("Outstanding actionable items", f"{outstanding}",
         "Outstanding items across these modules: checklist, Leganto reading lists, "
         "Ally accessibility and template readiness findings combined."),
    ]

    show_sga = bool(can_view_sga and 'SGA Attributes' in school_df.columns
                    and school_df['SGA Attributes'].notna().any())

    modules, matrix_rows, columns = [], [], []
    for record in school_df.to_dict('records'):
        code = str(record['New module code']).strip().upper()
        summary = summaries.get(code, {})
        responses = summary.get('Responses', {})
        lead = _clean(record.get('Mod. lead'))
        level = _clean(record.get('UG/ PG/ Other'))
        sga = record.get('SGA Attributes')
        modules.append({
            'code': code,
            'name': _clean(record.get('Module name')),
            'lead': title_case_name(lead) if lead else '',
            'level': LEVEL_ABBREVIATIONS.get(level, level),
            'score': score_or_stage(record),
            'items': summary.get('Actionable Items', 0),
            'reading_list': reading_list_display(
                record, reading_list_verdict(summaries, code)),
            'spot_check': spot_check_display(spot_check_status.get(code)),
            'sgas': '' if sga is None or pd.isna(sga) else int(sga),
        })
        cells = dict(module_alignment_status(
            record, responses, active_fields, fix_claims_by_module.get(code)))
        for label in cells:
            if label not in columns:
                columns.append(label)
        matrix_rows.append({'code': code, 'name': modules[-1]['name'],
                            'lead': modules[-1]['lead'], 'cells': cells})
    for row in matrix_rows:
        row['cells'] = [row['cells'].get(label, '') for label in columns]

    return {'school': school, 'semester': semester, 'headline': headline,
            'modules': modules, 'show_sga': show_sga,
            'matrix': {'columns': columns, 'rows': matrix_rows}}
