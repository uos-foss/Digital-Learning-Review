import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import logging
import re
import html
from processing import (
    get_module_mapping,
    FACULTY_SCHOOLS,
    CURRENT_ACADEMIC_YEAR,
    summarise_ally_issues,
    summarise_ally_issue_categories,
    TEMPLATE_SECTIONS,
    LEAD_OWNED_SECTIONS,
    TEMPLATE_SECTION_TREE,
    SECTION_STATES,
    INSTITUTION_MAPPED_FIELD_IDS,
    derive_module_findings,
    readiness_manual_override,
    compute_audit_verdict,
    fmt_report_date,
    fmt_report_datetime,
    readiness_evidence_words,
    readiness_created_date,
    resolve_active_row,
    parse_user_schools,
    format_user_schools,
    module_matches_user_schools,
)
from database import (
    get_active_audit_fields,
    get_audit_responses,
    save_audit_response,
    get_pending_spot_check,
    get_last_import_dates,
)


@st.cache_data(ttl=300)
def _load_last_import_dates():
    return get_last_import_dates()

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

# Colour used for each worklist tier - shared between the health banner (via
# the presence of severe items) and the unified worklist below it.
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


def _ally_band(score):
    for threshold, colour, level, description in ALLY_BANDS:
        if score >= threshold:
            return colour, level, description
    return ALLY_BANDS[-1][1:]


# Fixed pixel width for the three accessibility gauges - see the sizing note
# in _score_gauge's docstring for why this is fixed rather than responsive.
GAUGE_WIDTH = 220


def _score_gauge(label, score, sub, is_template=False):
    """One of the three surface scores, as a Plotly gauge indicator.

    Hand-rolled SVG gauges kept misaligning inside Streamlit's markdown
    sanitizer (track/value arcs and labels drifting out of sync across
    reruns) - go.Indicator is a proven, purpose-built gauge renderer instead
    of fighting that.

    is_template flags a course that's still its rolled-over template - the
    score itself is Ally's real, unmodified figure (no credibility weighting,
    see module docstring below), but the gauge renders grey rather than in
    its score-band colour, since the maturity banner above already explains
    why and colouring it as a real result would overstate it.

    Rendered at a fixed pixel size rather than `use_container_width=True`.
    Two problems traced back to that responsiveness, not to anything about
    the gauge itself: Plotly's Indicator sizes its number relative to the
    trace's rendered box at draw time, so (a) a size pinned in the Python code
    stops matching that box the moment the column is narrower than what it
    was tuned at, clipping the number against neighbouring columns, and (b)
    leaving the size unset for Plotly to compute automatically instead reads
    whatever box size the DOM reports at that instant - on first render,
    before Streamlit's flex layout has settled, that can be near-zero, so the
    number draws invisibly small and stays that way until something (like a
    manual browser resize) fires Plotly's own resize handler and forces a
    recompute against the now-correct box. Three small gauges never needed to
    fill a wide page's full column width anyway, so fixing the box size in
    pixels removes the dependency behind both bugs at once and caps how far
    they spread out on a wide screen.
    """
    has_score = score is not None and pd.notna(score)
    colour = "#6B7280" if (is_template or not has_score) else _ally_band(float(score))[0]
    value = float(score) * 100 if has_score else 0
    r, g, b = int(colour[1:3], 16), int(colour[3:5], 16), int(colour[5:7], 16)
    bgcolour = f"rgba({r},{g},{b},0.12)"

    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=value,
        number={'suffix': "%", 'font': {'size': 26, 'color': colour}} if has_score
               else {'valueformat': '', 'suffix': "--", 'font': {'size': 26, 'color': colour}},
        title={'text': label, 'font': {'size': 12, 'color': colour}},
        gauge={
            'axis': {'range': [0, 100], 'visible': False},
            'bar': {'color': colour, 'thickness': 1},
            'bgcolor': bgcolour,
            'borderwidth': 0,
            'shape': "angular",
        },
    ))
    fig.update_layout(
        width=GAUGE_WIDTH,
        height=140,
        margin=dict(l=20, r=20, t=40, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        font={'color': '#6B7280'},
    )
    return fig, has_score, sub


def _render_ally_card(selected_code, active_row, ally_profile, ally_categories):
    """
    The module's accessibility profile: scores, trend, and the issues behind
    them, all in one place.

    Shows Ally's three scores as Ally reports them. The portal used to display
    a single locally credibility-weighted figure instead, which pulled thin
    courses toward 50% and so disagreed with the score the module lead sees in
    Blackboard. What that weighting was really groping at - is there enough
    here to judge? - is now answered directly by the item counts and the
    content maturity banner.

    The issue list used to live in a page-level worklist shared with
    checklist and Leganto gaps. It now lives here instead, so the
    Accessibility column is self-contained - everything Ally in one place,
    rather than split between a score card and a separate outstanding-items
    section.
    """
    with st.container():
        if active_row is None:
            st.info("No Ally accessibility data is available for this module.")
            return

        maturity = str(active_row.get('Content Maturity', 'No data') or 'No data')
        overall = active_row.get('Ally Overall')
        files_score = active_row.get('Ally Files')
        wysiwyg_score = active_row.get('Ally WYSIWYG')
        n_files = int(active_row.get('Total Files', 0) or 0)
        n_wysiwyg = int(active_row.get('Ally WYSIWYG Items', 0) or 0)
        shells = int(active_row.get('Ally Shells', 0) or 0)
        last_checked = str(active_row.get('Ally Last Checked', '') or '')

        if maturity == "No data" or (n_files == 0 and n_wysiwyg == 0 and shells == 0):
            st.info(
                f"No Ally record for this module in {CURRENT_ACADEMIC_YEAR}. That usually "
                "means it has no Blackboard course, or its course is filed under a "
                "different code — ask a Digital Learning Advisor to check if this looks wrong.")
            return

        last_scanned_date = pd.to_datetime(last_checked, errors='coerce').strftime('%d-%m-%Y') if last_checked else "—"
        # The whole-table import date (get_last_import_dates()['ally'], the
        # same figure the sidebar's "Latest data from" caption shows) - not
        # this module's own last_checked/snapshot row, which Ally's
        # unchanged-course skip (database.save_ally_snapshot) can leave
        # sitting on an earlier date than the import that just ran, if this
        # particular course had nothing new to report.
        snapshot_date = fmt_report_date(_load_last_import_dates().get('ally')) or last_scanned_date
        url = str(active_row.get('URL', '') or '')
        _render_ally_intro(url, snapshot_date)

        # 1. Maturity banner - only for states that need explaining. "In
        # progress" is the common case and is already obvious from the
        # gauges being non-zero, so it doesn't get its own banner; "Not yet
        # built"/"Empty" do, since a high score there would otherwise read as
        # real accessibility compliance rather than an unbuilt template.
        if maturity != "In progress":
            colour, icon, note = ALLY_MATURITY_NOTE.get(maturity, ALLY_MATURITY_NOTE["No data"])
            display_maturity = "Not started" if maturity == "Not yet built" else maturity
            note += f" · Last scanned {last_scanned_date}"
            st.markdown(
                f"""<div style="border-left:4px solid {colour};background-color:{colour}0D;
                            padding:8px 12px;border-radius:4px;margin-bottom:12px;">
                    <b style="color:{colour};">{icon} {display_maturity}</b>
                    <span style="color:#6B7280;font-size:13px;"> — {note}</span>
                </div>""", unsafe_allow_html=True)

        # 2. The three scores, each with the volume of content behind it.
        # Greyed out for a template/empty course - the number is real (Ally's
        # own, unmodified) but isn't an accessibility result worth reading in
        # colour yet.
        is_template = maturity in ("Not yet built", "Empty")
        c1, c2, c3 = st.columns(3)
        for col, tile_label, tile_score, tile_sub, tile_key in (
            (c1, "Overall", overall, f"{n_files + n_wysiwyg} items", "overall"),
            (c2, "Files", files_score, f"{n_files} file{'' if n_files == 1 else 's'}", "files"),
            (c3, "Page Content", wysiwyg_score,
             f"{n_wysiwyg} document{'' if n_wysiwyg == 1 else 's'}", "wysiwyg"),
        ):
            fig, _, sub_text = _score_gauge(tile_label, tile_score, tile_sub, is_template)
            with col:
                st.plotly_chart(fig, use_container_width=False,
                                config={'displayModeBar': False}, key=f"gauge_{selected_code}_{tile_key}")
                st.markdown(
                    f"<div style='text-align:center;font-size:11px;color:#6B7280;margin-top:-16px;'>{sub_text}</div>",
                    unsafe_allow_html=True)

        if not active_row.get('Ally Enabled', True):
            st.warning("⚠️ Ally is switched off for this course, so students get no "
                       "alternative formats and the module lead sees no feedback.")

        st.caption(
            "Need help? "
            "[Digital accessibility guidance](https://staff.sheffield.ac.uk/digital-accessibility) · "
            "[Making content accessible with Ally](https://staff.sheffield.ac.uk/blackboard/ally)")

        st.markdown("---")
        _render_ally_issues(ally_categories, ally_profile, is_template)


def _ally_issue_profile(selected_code):
    """This module's Ally issues, ranked worst-first. Empty frame if none."""
    df_issues = st.session_state.get("df_ally_issues", pd.DataFrame())
    if df_issues is None or df_issues.empty:
        return pd.DataFrame()

    mine = df_issues[df_issues['module_code'].astype(str).str.strip().str.upper()
                     == str(selected_code).strip().upper()]
    return summarise_ally_issues(mine)


def _ally_issue_categories(selected_code):
    """This module's Ally issues rolled up to ALLY_CATEGORIES. Empty frame if none."""
    df_issues = st.session_state.get("df_ally_issues", pd.DataFrame())
    if df_issues is None or df_issues.empty:
        return pd.DataFrame()

    mine = df_issues[df_issues['module_code'].astype(str).str.strip().str.upper()
                     == str(selected_code).strip().upper()]
    return summarise_ally_issue_categories(mine)


def _render_health_banner(ally_profile, pending_count, leganto_missing, has_audit,
                           leganto_draft=False, leganto_items=0, active_row=None,
                           leganto_status='', leganto_draft_items=0):
    """
    A short, neutral summary of what's outstanding across Ally, the checklist,
    Leganto and the Blackboard template - the one place these add up to a single
    picture.

    Deliberately factual rather than evaluative: this reports what's open, not
    a score or grade for the module or its lead. Individual items can say
    "severe" (that's actionable information), but the banner never reads as an
    alarm - amber at most, never red, and a plain reassuring line when there's
    nothing outstanding.
    """
    severe = ally_profile[ally_profile['severity_label'] == 'Severe'] if not ally_profile.empty else ally_profile
    major = ally_profile[ally_profile['severity_label'] == 'Major'] if not ally_profile.empty else ally_profile

    bullets = []
    if len(severe):
        items = int(severe['items'].sum())
        bullets.append(f"{len(severe)} severe accessibility issue type{'s' if len(severe) != 1 else ''} "
                       f"({items} item{'s' if items != 1 else ''})")
    if len(major):
        items = int(major['items'].sum())
        bullets.append(f"{len(major)} major accessibility issue type{'s' if len(major) != 1 else ''} "
                       f"({items} item{'s' if items != 1 else ''})")
    if pending_count:
        bullets.append(f"{pending_count} checklist item{'s' if pending_count != 1 else ''} outstanding")

    # Template alignment. Stated as a count of sections not yet visible to
    # students, which is a fact about the course, rather than as the vendor's
    # "Non-Compliant" banding, which reads as a verdict on the lead.
    if active_row is not None:
        outstanding = active_row.get('Lead Sections Outstanding') or []
        drafted = active_row.get('Drafted Sections') or []
        blocking = active_row.get('Template Blocking') or []
        if len(outstanding):
            total = int(active_row.get('Lead Sections Total') or len(LEAD_OWNED_SECTIONS))
            bullets.append(f"{len(outstanding)} of {total} module template section"
                           f"{'s' if total != 1 else ''} not yet visible to students")
        # Called out separately: the work exists, it just needs releasing, and
        # that is a far smaller ask than the bullet above implies on its own.
        if len(drafted):
            n = len(drafted)
            bullets.append(f"{n} of those {'has' if n == 1 else 'have'} been "
                           f"worked on and only needs making visible "
                           f"({', '.join(drafted)})")
        if len(blocking):
            n = len(blocking)
            bullets.append(f"{n} template section{'s' if n != 1 else ''} "
                           f"{'have' if n != 1 else 'has'} been deleted from or "
                           f"{'are' if n != 1 else 'is'} missing in the Blackboard course")

    if leganto_missing:
        bullets.append("no Leganto reading list connected")
    elif leganto_status == 'Mixed':
        # Distinct from plain Draft below - a Mixed module already has most
        # or all of its items published on at least one course shell, and
        # "still in Draft" alone would misreport that as nothing published.
        bullets.append(f"reading list partly published in Leganto "
                       f"({leganto_draft_items} of {leganto_items} item{'s' if leganto_items != 1 else ''} "
                       f"still in Draft)")
    elif leganto_draft:
        bullets.append(f"reading list still in Draft in Leganto ({leganto_items} item{'s' if leganto_items != 1 else ''})")
    if not has_audit:
        bullets.append("not yet audited by a Digital Learning Advisor")

    if not bullets:
        colour, icon, text = "#047857", "✅", "Nothing outstanding right now."
    else:
        colour, icon = "#F59E0B", "📋"
        text = "; ".join(bullets) + "."

    st.markdown(
        f"""<div style="border-left:4px solid {colour};background-color:{colour}0D;
                    padding:8px 12px;border-radius:4px;margin-bottom:12px;">
            <span style="color:{colour};font-weight:600;">{icon}</span>
            <span style="color:#374151;font-size:13px;"> {text}</span>
        </div>""", unsafe_allow_html=True)


def _render_data_reliability_block(active_row, has_audit=False):
    """
    What this report is based on and what it does/doesn't show, condensed
    from the "Data Reliability and Audit Rationale" section of the Help page.

    Two versions, gated on has_audit: a data-driven module has only the
    automated snapshots behind it, so the explanation carries the caveats
    that come with that (snapshot staleness, quantitative-only measurement,
    false negatives). Once a Digital Learning Advisor has actually recorded
    an audit or spot-check for this module, their verdict is the evidence
    the report is really resting on (see readiness_manual_override()) and
    those data caveats no longer apply the same way, so the message is a
    short, different one rather than the same caveats plus a footnote.

    Placed once, near the top, above both tabs: it's context for everything
    below, not something specific to Accessibility or Module Checks alone.
    The ingestion date line is always visible - the fuller explanation is
    collapsed, since most readers only need it once.
    """
    ally_date = fmt_report_date(active_row.get('Ally Last Checked')) if active_row is not None else ""
    readiness_date = fmt_report_date(active_row.get('Readiness Snapshot')) if active_row is not None else ""
    leganto_date = fmt_report_date(active_row.get('Leganto Snapshot')) if active_row is not None else ""

    st.caption(
        f"📅 Data last refreshed — Ally: {ally_date or '—'} · "
        f"Template Alignment: {readiness_date or '—'} · "
        f"Reading list: {leganto_date or '—'}")

    with st.expander("ℹ️ About this report"):
        if has_audit:
            st.markdown(
                "This report has been generated using data evidence and also "
                "manually spot-checked by a Digital Learning Advisor.")
        else:
            st.markdown(
                "This module report has been generated using data evidence. "
                "The combination of data from different sources gives us a "
                "reasonably good picture of the readiness of this module. "
                "The data used is:\n\n"
                f"* **Template alignment** data, last ingested at {readiness_date or '—'}. "
                "This tells us about the visibility and whether or not "
                "Blackboard template items have been edited.\n"
                f"* **Ally Accessibility** data, last ingested at {ally_date or '—'}. "
                "This is the Ally report for your module and shows the "
                "accessibility of files and Blackboard content across your module.\n"
                f"* **Leganto (reading lists)** data, last ingested at {leganto_date or '—'}. "
                "This tells us whether the module has a reading list and if it "
                "has been published or is in draft.\n\n"
                "There are a few caveats for a data-driven report:\n\n"
                "* Snapshot data is used, so the report may not be perfectly up-to-date.\n"
                "* The data is purely quantitative, so while it can tell us if an "
                "item has been edited, it cannot speak to the quality of the item.\n"
                "* The data may flag false negatives - e.g. if a Blackboard item "
                "has been deleted then legitimately replaced, it may still flag as deleted.")


def _render_ally_issue_card(row):
    """One Ally issue type, in the same card shape as checklist items."""
    icon, where = SURFACE_WORDS.get(row['surface'], ("📄", ""))
    colour = TIER_COLOUR.get(row['severity_label'], "#6B7280")
    st.markdown(
        f"""<div style="border-left: 4px solid {colour}; background-color: {colour}05; padding: 12px 16px; margin-bottom: 12px; border-radius: 4px; border-top: 1px solid {colour}0D; border-right: 1px solid {colour}0D; border-bottom: 1px solid {colour}0D;">
            <span style="background:{colour}1A;color:{colour};font-size:10px;
                         font-weight:700;padding:2px 6px;border-radius:4px;
                         text-transform:uppercase;">{row['severity_label']}</span>
            <h4 style="margin: 6px 0 6px 0; color: #1F2937; font-size: 15px; font-weight: 600;">{row['label']}</h4>
            <div style="margin: 0; color: #4B5563; font-size: 14px; line-height: 1.5;">
                {row['items']} item(s) · {icon} {where}. {row['advice']}
            </div>
        </div>""", unsafe_allow_html=True)


def _render_actions_panel(actions):
    """
    Every outstanding item on this module - checklist, Leganto, Ally and
    template readiness findings alike - as one consolidated bullet list in a
    single amber panel, styled identically regardless of source.

    Previously each source rendered its own way: checklist/Leganto items as
    individually bordered cards, template-mapped fields as a separate
    warning banner above them, Ally findings not shown here at all despite
    already counting toward Actionable Items on School Dashboard -
    different visual languages (and one silent omission) answering the same
    "what do I need to do" question read as mixed, inconsistent signals to
    a module lead. One list, one style. Richly-displayed template readiness
    (the Blackboard Template cards to the left of this panel) and Ally (its
    own Accessibility tab) are still shown in full elsewhere too - this
    panel duplicates them on purpose, the same way it does for readiness,
    so the badge and this list can never disagree about what's outstanding.
    Callers only ever pass already-filtered pending 'checklist' | 'leganto'
    | 'ally' | 'readiness' findings.

    Free text a DLA typed into a 'text' audit field ('custom' type) is
    html.escape()d before interpolation - it must never be trusted as raw
    HTML, or a note containing "<script>..." would execute for anyone who
    opens this module's report. This does mean a custom observation's own
    markdown (bold, links) no longer renders as formatting here, in exchange
    for everything living in one real HTML list instead of separate
    st.markdown() calls that cannot actually nest inside one styled panel.
    """
    if not actions:
        st.success("✅ Nothing outstanding right now.")
        return

    items_html = []
    for item in actions:
        if item['type'] == 'custom':
            label = html.escape(item.get('category') or 'Custom Observation')
            combined = '\n'.join(
                p for p in (item.get('label', '').strip(), item.get('description', '').strip()) if p)
            description = html.escape(combined).replace('\n', '<br/>')
        elif item['type'] == 'boolean':
            label = item.get('label', '')
            description = item.get('description', '')
        else:
            continue

        li = f'<li style="margin-bottom:12px;"><strong>{label}</strong>'
        if description:
            li += f'<br/><span style="color:#6B7280;font-size:13px;">{description}</span>'
        li += '</li>'
        items_html.append(li)

    st.markdown(
        '<div style="border-left:4px solid #F59E0B; background-color:rgba(245,158,11,0.06); '
        'border-radius:4px; padding:14px 16px 2px 16px;">'
        '<ul style="margin:0; padding-left:18px;">'
        + ''.join(items_html) +
        '</ul></div>',
        unsafe_allow_html=True)


def _render_ally_category_card(row):
    """One accessibility issue category: what kind of thing it is, roughly
    how much of it, and why it matters. Deliberately no per-check detail or
    fix instructions here - see _render_ally_issues's docstring for why."""
    colour = TIER_COLOUR.get(row['severity_label'], "#6B7280")
    items_word = "item" if row['items'] == 1 else "items"
    checks_word = "issue type" if row['checks'] == 1 else "issue types"
    st.markdown(
        f"""<div style="border-left: 4px solid {colour}; background-color: {colour}05; padding: 12px 16px; margin-bottom: 12px; border-radius: 4px; border-top: 1px solid {colour}0D; border-right: 1px solid {colour}0D; border-bottom: 1px solid {colour}0D;">
            <h4 style="margin: 0 0 4px 0; color: #1F2937; font-size: 15px; font-weight: 600;">{row['icon']} {row['title']}</h4>
            <div style="color: #6B7280; font-size: 12px; margin-bottom: 8px;">{row['items']} {items_word} across {row['checks']} {checks_word}</div>
            <div style="color: #4B5563; font-size: 14px; line-height: 1.5;">{row['why']}</div>
        </div>""", unsafe_allow_html=True)


def _render_ally_intro(url, snapshot_date):
    """Sets expectations for the whole Accessibility column before the reader
    hits a single score: this is a snapshot, not a live view, and their own
    Ally Accessibility Report in Blackboard is the up-to-date, file-level
    source. Placed at the top rather than after the gauges/issue list -
    the caveat matters most before someone has already drawn a conclusion
    from the numbers below it, not after.

    snapshot_date is the whole-table Ally import date, not this course's own
    last_checked/snapshot row - a course whose Ally data hasn't moved since
    the previous import is skipped by database.save_ally_snapshot()'s
    change detection, so its own dates can lag behind an import that just
    ran and would otherwise make a freshly-imported report read as stale.

    Styled as a "#### heading" + st.caption() subtitle, the same pairing
    the Blackboard Template block uses for its own intro (see
    _render_template_sections) - not a bordered card, just the plain
    heading/caption pattern the rest of this page's section intros use."""
    st.markdown("#### How to use this Accessibility Report")
    st.caption(
        f"This report is based on an institutional data snapshot from {snapshot_date}. "
        "It shows the Ally accessibility report for this module at the time of the "
        "snapshot; it is not live.")
    st.caption(
        "The scores below are the familiar RAG-rated scores for Files (material "
        "you've uploaded), Page Content (Blackboard Ultra documents) and the Overall "
        "score, along with a summary of the kinds of accessibility issues found.")
    st.caption(
        "This is simply a summary, not a replacement for your Ally course report - "
        "for a more detailed and up-to-date view of accessibility in your module, and "
        "to see which files are affected, always use the Ally Accessibility Report in "
        "Blackboard (Books & Course Tools > Ally Accessibility Report).")
    if url:
        st.markdown(f"[Open this course in Blackboard]({url})")


def _render_issue_cards(rows):
    """Cards for an iterable of per-check issue rows, with a tier subheading
    whenever the severity changes from the previous row."""
    current_tier = None
    for _, row in rows.iterrows():
        if row['severity_label'] != current_tier:
            current_tier = row['severity_label']
            st.markdown(f"**{current_tier}**")
        _render_ally_issue_card(row)


def _render_ally_issues(ally_categories, ally_profile, is_template=False):
    """
    What kinds of accessibility problems Ally found on this module, and why
    they matter - written for the module lead reading their own report, not
    for a DLA auditing it.

    Lives inside the Accessibility column, directly below the score tiles -
    scores and the issues behind them are one picture, not two separate page
    sections a reader has to reconcile by hand.

    Deliberately does not try to be a fix-it list. A module lead's own Ally
    Course Report in Blackboard already links each issue to its exact file,
    previews the problem, and often fixes it in situ - a page like this
    cannot usefully compete with that, and listing 38 named checks flat used
    to bury the handful of things actually worth a lead's attention under an
    auditor's level of detail. What this page can do that Blackboard can't
    is explain once, in plain terms, why each *kind* of problem matters, and
    point at where the specifics live - see _render_ally_intro, now shown at
    the top of the column rather than here. The full per-check technical
    list (what a DLA audits against) is one click away in the expander at
    the bottom, not the thing leading the page.

    is_template distinguishes "genuinely clean" from "nothing scanned yet" -
    a zero-issue template hasn't been checked for anything, so a green
    success tick there would overstate it the same way an unqualified high
    score would.
    """
    total_items = int(ally_categories['items'].sum()) if not ally_categories.empty else 0
    if total_items == 0:
        if is_template:
            st.caption("This course still holds only its rolled-over template, so there's "
                       "nothing to report yet.")
        else:
            st.success("✅ No accessibility issues reported.")
        return

    n_categories = len(ally_categories)
    st.markdown(f"#### Summary of accessibility issues ({total_items} items across "
                f"{n_categories} area{'' if n_categories == 1 else 's'})")

    for _, row in ally_categories.iterrows():
        _render_ally_category_card(row)

    if not ally_profile.empty:
        st.markdown("")
        with st.expander(f"Full technical detail ({len(ally_profile)} issue types, for auditors)"):
            _render_issue_cards(ally_profile)


def _render_module_checks(actions, has_audit, active_row=None, responses=None,
                          leganto_missing=False, leganto_status='', leganto_items=0,
                          leganto_draft_items=0):
    """
    Blackboard Template sections and outstanding Actions, side by side: the
    detailed per-section state on the left (roughly three-quarters width),
    a single consolidated Actions list on the right (roughly a quarter) -
    two columns rather than one long stacked page, so "what's the current
    state" and "what do I need to do" read as two distinct questions with
    two distinct answers instead of interleaved down one column.

    actions is every pending checklist, Leganto, Ally and template-readiness
    finding from processing.derive_module_findings() - the single place
    that decides what counts as outstanding for every source - already
    filtered to state == 'pending'. This function only renders, it does not
    classify. There is deliberately no matching "Completed" list here any
    more - a module lead came to this tab to see what's left to do, and a
    growing list of everything already fine just pushed that further down
    the page without answering that question.
    """
    col_sections, col_actions = st.columns([3, 1])
    with col_sections:
        _render_template_sections(active_row, responses, has_audit,
                                  leganto_missing, leganto_status, leganto_items, leganto_draft_items)
    with col_actions:
        st.markdown(f"#### Actions ({len(actions)})")
        _render_actions_panel(actions)


def _render_section_card(key, state, responses, has_audit, created, leganto=None, depth=0):
    """
    One template section, as a styled card: status badge, what it means, and
    when it was last changed.

    Most of the 14 sections are institutional content a module lead never
    edits directly - an LTI link, a folder, a fixed-text page - so for them
    only visibility is actionable: edited-or-not is noise, and both the
    Visible states and both the Hidden states collapse to one message each
    (INSTITUTION_SECTION_COPY). Only the lead-owned sections (LEAD_OWNED_
    SECTIONS) keep the edited/unedited and drafted/not-started distinctions
    SECTION_STATES draws, because for them it's the whole point - real
    content a lead (or, for HOW_YOUR_FEEDBACK_SHAPES specifically, whoever
    writes it on the module's behalf) has to actually produce, where "visible
    but never edited" plausibly means untouched template placeholder text.

    Applies processing.readiness_manual_override() whenever the section has a
    mapped checklist field - not only the three lead-owned sections. That
    function is already generic (it keys off audit_field_id and responses,
    with no lead-only restriction); restricting it to lead-owned sections was
    only ever a call-site choice here, and it left sga/student_voice/
    assessment_overview/encore_link unable to show "Manually verified" even
    when a Digital Learning Advisor had recorded a real answer for them.

    Without either fix, the card could show a section as a problem ("Visible,
    unedited" or "Not started") while the Completed cards next to it show the
    same section ticked off from a real audit or read as fine everywhere else
    on the page - the contradiction that confused advisors reading a
    spot-checked module's report.

    `leganto` (only ever passed for MODULE_READING_LIST) layers the reading
    list's own Published/Draft status on top of Blackboard visibility: unlike
    every other institutional section, being visible in Blackboard is not by
    itself the finish line here - the connected list also has to be published
    in Leganto.

    The action/footer lines are dropped (`show_detail = False`) for the one
    case where they add nothing: a plain institution "Visible to students"
    with no further news. With every one of the 14 sections now a full card
    (no lead-owned/other split any more - see TEMPLATE_SECTION_TREE), a
    fully-compliant module was reading as a long scroll of cards each saying
    the same generic sentence the badge already said. Every other path here
    re-asserts `show_detail = True`, since it always has something the badge
    alone doesn't: a caution, a fault, a DLA's manual verification, or
    Reading List's Leganto status.
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

    if owner != 'lead':
        visible_copy, hidden_copy = INSTITUTION_SECTION_COPY.get(key, _INSTITUTION_DEFAULT_COPY)
        if state_key in ('visible_edited', 'visible_unedited'):
            badge, tier, action = "Visible to students", 'ok', visible_copy
            show_detail = False
        elif state_key in ('drafted_hidden', 'not_started'):
            badge, tier, action = "Hidden from students", 'action', hidden_copy

    colour = STATE_TIER_COLOUR.get(tier, "#6B7280")

    if key == 'MODULE_READING_LIST' and leganto is not None and tier == 'ok':
        status = leganto.get('status', '')
        items = int(leganto.get('items', 0) or 0)
        draft_items = int(leganto.get('draft_items', 0) or 0)
        if leganto.get('missing'):
            badge, tier = "Visible, no reading list", 'action'
            action = ("Visible to students, but Leganto shows no reading list connected to "
                      "this module. Being visible here isn't the finish line for this "
                      "section - a reading list still needs to be added and published.")
        elif status == 'Draft':
            badge, tier = "Visible, list in Draft", 'action'
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
            action = (f"Visible to students. The connected reading list is partly published in "
                      f"Leganto - {draft_items} of {items} item{'s' if items != 1 else ''} "
                      f"still in Draft, most likely on a different course shell for this "
                      f"module. Those still need publishing.")
        elif status == 'Published':
            action = "Visible to students, and the connected reading list is Published in Leganto."
        show_detail = True
        colour = STATE_TIER_COLOUR.get(tier, "#6B7280")

    manual = readiness_manual_override(audit_field_id, responses) if has_audit else None
    if manual is not None:
        data_label = SECTION_STATES.get(state_key, SECTION_STATES['unknown'])[0]
        if manual:
            badge, colour = "Manually verified complete", STATE_TIER_COLOUR['ok']
            action = "A Digital Learning Advisor has recorded this as complete in the audit."
        else:
            badge, colour = "Manually verified incomplete", STATE_TIER_COLOUR['fault']
            action = "A Digital Learning Advisor has recorded this as not yet complete in the audit."
        footer = f"Automatically detected as of the last update: {data_label}. {footer}"
        show_detail = True

    icon = CONTENT_TYPE_ICONS.get(SECTION_CONTENT_TYPE.get(key), '')
    indent = depth * 24
    # Built as one joined string, not a multi-line f-string, deliberately: a
    # blank line left where {detail_html} would sit when show_detail is False
    # makes Streamlit's markdown parser treat the raw HTML as two separate
    # blocks, and the closing </div> after that blank line prints as literal
    # text instead of closing the div - exactly the stray "</div>" that
    # showed up on every collapsed card before this.
    detail_html = (
        f'<p style="margin:4px 0 4px 0;color:#374151;font-size:12px;">{action}</p>'
        f'<p style="margin:0;color:#9CA3AF;font-size:11px;">{footer}</p>'
        if show_detail else "")

    st.markdown(
        f'<div style="border-left: 4px solid {colour}; background-color: {colour}05; '
        f'padding: 8px 12px; margin-bottom: 6px; margin-left: {indent}px; border-radius: 4px;">'
        f'<h4 style="margin:0;color:#1F2937;font-size:14px;font-weight:600;'
        f'display:flex;align-items:center;">'
        f'<span style="display:inline-block;vertical-align:middle;margin-right:10px;">{icon}</span>'
        f'<span style="flex:1;">{label}</span>'
        f'<span style="background:{colour}1A;color:{colour};font-size:10px;'
        f'font-weight:700;padding:2px 6px;border-radius:4px;text-transform:uppercase;'
        f'white-space:nowrap;margin-left:8px;">{badge}</span>'
        f'</h4>'
        f'{detail_html}'
        f'</div>', unsafe_allow_html=True)


def _render_label_node(name, depth, has_children_data):
    """
    A Learning Module heading with no readiness data of its own - only
    its contents are tracked (Assessment Information), or nothing under it
    is tracked yet at all (Learning Materials). Never a status card: there
    is no visibility state to show a badge for.
    """
    indent = depth * 24
    icon = CONTENT_TYPE_ICONS.get('learning_module', '')
    st.markdown(
        f"""<div style="margin:14px 0 6px {indent}px;">
            <span style="display:inline-block;vertical-align:middle;
                         margin-right:12px;opacity:0.6;">{icon}</span>
            <span style="font-weight:700;font-size:14px;color:#374151;">{name}</span>
        </div>""", unsafe_allow_html=True)
    if not has_children_data:
        st.markdown(
            f"""<p style="margin:0 0 8px {indent}px;color:#9CA3AF;font-size:11px;">
                Not part of the readiness data yet.</p>""", unsafe_allow_html=True)


def _render_section_tree(nodes, states, responses, has_audit, created, leganto, depth=0):
    """
    Walks processing.TEMPLATE_SECTION_TREE, rendering each node at its
    nesting depth - a status card for a tracked section, a plain heading for
    a Learning Module folder with no data of its own. Nesting mirrors where a
    lead actually finds each item in their own course menu.

    A node's own data (or lack of it) never gates its children: Assessment
    Information itself carries no state, but its three children do, and each
    is checked independently against `states`.
    """
    for node_type, value, children in nodes:
        if node_type == 'section':
            state = states.get(value)
            if state:
                _render_section_card(value, state, responses, has_audit, created,
                                     leganto=leganto if value == 'MODULE_READING_LIST' else None,
                                     depth=depth)
        else:
            _render_label_node(value, depth, has_children_data=bool(children))
        if children:
            _render_section_tree(children, states, responses, has_audit, created, leganto, depth + 1)


def _render_template_sections(active_row, responses=None, has_audit=False,
                              leganto_missing=False, leganto_status='', leganto_items=0,
                              leganto_draft_items=0):
    """
    The Blackboard template's required sections, from the faculty Template
    Alignment Report.

    Nested to match where a module lead actually finds each item in their own
    course menu (processing.TEMPLATE_SECTION_TREE) - Module Information's
    Learning Module with its contents nested beneath it, Module Reading List
    and Encore Lecture Capture as standalone top-level items, Assessment
    Information's contents nested under its own (untracked) heading, and
    University Help & Support standalone - rather than the lead/
    institution-owner split that only matters for readiness logic elsewhere.
    Every tracked section renders as a full card; there is no catch-all
    "other sections" table.

    leganto_missing/leganto_status/leganto_items are the same values the
    health banner and worklist already use - passed through so the Module
    Reading List card (the one section where Blackboard visibility isn't the
    whole story) can say whether the connected list is actually published.
    """
    if active_row is None:
        return

    states = active_row.get('Template Sections') or {}
    if not isinstance(states, dict) or not states:
        return

    created = readiness_created_date(states)
    leganto = {'missing': leganto_missing, 'status': leganto_status, 'items': leganto_items,
               'draft_items': leganto_draft_items}

    st.markdown("#### Blackboard Template")
    st.caption(
        "The following represents the structure of your Blackboard course and "
        "its measured or observed state - e.g. whether items are visible to "
        "students, have been edited, etc.")

    _render_section_tree(TEMPLATE_SECTION_TREE, states, responses, has_audit, created, leganto)


def title_case_name(name: str) -> str:
    if not name:
        return name
    words = name.split()
    title_words = []
    for word in words:
        if '-' in word:
            parts = word.split('-')
            processed_parts = []
            for part in parts:
                p = part.capitalize()
                if p.lower().startswith('mc') and len(p) > 2:
                    p = 'Mc' + p[2:].capitalize()
                elif len(p) > 2 and p[:2].upper() in ["O'", "D'", "L'"]:
                    p = p[:2].upper() + p[2:].capitalize()
                processed_parts.append(p)
            word = '-'.join(processed_parts)
        else:
            word = word.capitalize()
            if word.lower().startswith('mc') and len(word) > 2:
                word = 'Mc' + word[2:].capitalize()
            elif len(word) > 2 and word[:2].upper() in ["O'", "D'", "L'"]:
                word = word[:2].upper() + word[2:].capitalize()
        title_words.append(word)
    return ' '.join(title_words)

def view_module_report(df_aut, df_spr, checklist_sums, df_assess=None, load_checklist_data_cache=None):
    module_mapping = get_module_mapping(df_aut, df_spr)
    combined_options = sorted([f"{code} - {name}" for code, name in module_mapping.items()])

    schools_list = list(FACULTY_SCHOOLS)

    user_caps = st.session_state.get("capabilities", [])
    only_own_school = any(c.lower() == "view_school" for c in user_caps) and not any(c.lower() == "view_all" for c in user_caps)

    if only_own_school:
        user_schools = parse_user_schools(st.session_state.saved_school)
        school_context_badge = f" <span style='font-size: 16px; vertical-align: middle; background-color: rgba(59, 130, 246, 0.1); color: #3b82f6; padding: 4px 10px; border-radius: 12px; margin-left: 12px; border: 1px solid rgba(59, 130, 246, 0.2);'>Context: {format_user_schools(user_schools)}</span>"
        st.markdown(f"<h1>Module Report{school_context_badge}</h1>", unsafe_allow_html=True)
        combined_options = [opt for opt in combined_options if module_matches_user_schools(opt, user_schools)]
    else:
        st.title("Module Report")
        # Optional multi-tenant school filter to focus without siloing.
        # `context_focus_own` / `context_school` are plain session-state
        # values (never a widget's own `key=`) shared with School Dashboard's
        # and Audit Portal's equivalent controls, read here and written back
        # below. A widget's *own* state does not survive `st.switch_page()`
        # navigation in this app's st.navigation()/st.Page(function) setup,
        # so `value=`/`index=` always reseed from these plain keys rather
        # than relying on `key=` continuity across pages - see "School
        # context locking" in CLAUDE.md.
        user_schools = parse_user_schools(st.session_state.saved_school)
        if user_schools != ["All"]:
            label = format_user_schools(user_schools)
            filter_by_school = st.checkbox(
                f"Focus on my school{'s' if len(user_schools) > 1 else ''} ({label})",
                value=st.session_state.get("context_focus_own", True),
                key="rc_context_focus_own_widget",
                help="Uncheck to work in another school's context - this stays locked "
                     "across pages until you re-check this or pick your own school "
                     "again, so covering a colleague's school doesn't keep reverting "
                     "back to yours.")
            st.session_state.context_focus_own = filter_by_school
            if filter_by_school:
                combined_options = [opt for opt in combined_options if module_matches_user_schools(opt, user_schools)]
            else:
                options = ["All Schools"] + schools_list
                persisted_school = st.session_state.get("context_school")
                default_idx = options.index(persisted_school) if persisted_school in options else 0
                selected_school = st.selectbox(
                    "Select School to Focus",
                    options,
                    index=default_idx,
                    key="rc_context_school_widget",
                    help="Switch to another school's module list."
                )
                st.session_state.context_school = selected_school
                if selected_school != "All Schools":
                    combined_options = [opt for opt in combined_options if opt.startswith(selected_school)]
        else:
            # Fallback for "All Schools" users (e.g. FACULTY, and most real
            # DLA accounts - see "DLA accounts are faculty-wide" in project
            # memory) to filter module list by school. Shares `context_school`
            # with School Dashboard's and Audit Portal's equivalent fallback
            # branch, same reasoning as the checkbox branch above.
            options = ["All Schools"] + schools_list
            persisted_school = st.session_state.get("context_school")
            default_idx = options.index(persisted_school) if persisted_school in options else 0
            selected_school = st.selectbox(
                "Filter by School",
                options,
                index=default_idx,
                key="rc_school_select_all",
                help="Filter the module selection list by a specific school. This "
                     "choice is shared with School Dashboard and the Audit Portal."
            )
            st.session_state.context_school = selected_school
            if selected_school != "All Schools":
                combined_options = [opt for opt in combined_options if opt.startswith(selected_school)]

    if 'selected_module_code' not in st.session_state:
        st.session_state.selected_module_code = ""

    current_idx = 0
    if st.session_state.selected_module_code:
        for i, opt in enumerate(combined_options):
            if opt.startswith(st.session_state.selected_module_code + " -"):
                current_idx = i + 1
                break

    # A static key only applies index= on the widget's first render - once
    # Streamlit has a stored value for the key, a later rerun that changes
    # selected_module_code some other way (a jump from School Dashboard, the
    # Audit Portal's spot-check panel) leaves the dropdown showing whatever
    # it last held instead of the new module. Keying the widget by the
    # module code it should show forces a fresh widget instance whenever
    # that code changes, so index= is honoured again.
    widget_key = f"unified_search_{st.session_state.selected_module_code or 'none'}"

    def on_module_change():
        picked = st.session_state[widget_key]
        if picked:
            st.session_state.selected_module_code = picked.split(" - ")[0]
        else:
            st.session_state.selected_module_code = ""

    st.selectbox(
        "Search by Module Code or Name",
        options=[""] + combined_options,
        index=current_idx,
        key=widget_key,
        on_change=on_module_change
    )

    selected_code = st.session_state.selected_module_code

    if selected_code:
        # A persistent heading naming the module being viewed, so it's never
        # ambiguous which module the report below belongs to - e.g. after
        # jumping here from School Dashboard, without having to first check
        # the dropdown above.
        st.markdown(f"#### {selected_code} — {module_mapping.get(selected_code, selected_code)}")

        # Extract Autumn and Spring module audit rows
        aut_m = df_aut[df_aut['New module code'] == selected_code] if not df_aut.empty else pd.DataFrame()
        spr_m = df_spr[df_spr['New module code'] == selected_code] if not df_spr.empty else pd.DataFrame()

        # Determine active row for metadata
        active_row = resolve_active_row(selected_code, df_aut, df_spr)

        mod_lead = "Unknown Lead"
        ug_pg = "UG"
        url = ""

        # Leganto status feeds the checklist summary, the health banner, and
        # the unified worklist.
        leganto_missing = False
        if not aut_m.empty and 'Leganto Missing' in aut_m.columns:
            if aut_m.iloc[0]['Leganto Missing'] is True:
                leganto_missing = True
        if not spr_m.empty and 'Leganto Missing' in spr_m.columns:
            if spr_m.iloc[0]['Leganto Missing'] is True:
                leganto_missing = True

        # Draft/Published status and item count for modules that DO have a
        # list. A blank status just means this module isn't in that export -
        # not the same as 'Leganto Missing' above.
        leganto_status = str(active_row.get('Leganto List Status', '')).strip() if active_row is not None else ''
        leganto_items = int(active_row.get('Leganto List Items', 0) or 0) if active_row is not None else 0
        leganto_draft_items = int(active_row.get('Leganto Draft Items', 0) or 0) if active_row is not None else 0
        leganto_draft = leganto_status in ('Draft', 'Mixed')

        # Checklist, Leganto, Ally and readiness findings all come from one
        # place - processing.derive_module_findings() - so the worklist below,
        # the health banner's counts, and the Actionable Items badge on School
        # Dashboard / Faculty Overview can no longer disagree about what a
        # module has outstanding.
        active_fields = get_active_audit_fields()

        # checklist_sums now carries an entry for every module with ANY
        # outstanding finding - including data-only ones (Leganto, Ally,
        # readiness) that no human has looked at. 'in checklist_sums' alone
        # can no longer mean "has been audited"; a genuine audit trail always
        # carries a real auditor username, where a data-only entry is stamped
        # 'System' (see app.py::load_checklist_data()).
        sum_entry = checklist_sums.get(selected_code)
        has_audit = bool(sum_entry) and sum_entry.get('Auditor') not in (None, '', 'System')
        if sum_entry:
            responses = sum_entry.get('Responses', {})
            # Same timestamp the Audit Status line above reads, formatted the
            # same way - it was showing the raw ISO storage value, against the
            # DD-MM-YYYY convention, and the two sat on one page disagreeing
            # about how to write the same moment.
            last_updated_str = (
                f"{fmt_report_datetime(sum_entry.get('Timestamp')) or 'Unknown'}"
                f" by {sum_entry.get('Auditor', 'Unknown')}"
                if has_audit else "Never")
        else:
            responses = {}
            last_updated_str = "Never"

        findings = derive_module_findings(active_row, responses, active_fields)

        # Not gated on has_audit - a never-audited module has no responses at
        # all, so this already resolves to 'blank' correctly by itself;
        # gating on has_audit would just suppress a correct, meaningful signal.
        verdict = compute_audit_verdict(active_fields, responses)

        # Every outstanding item across sources, for the consolidated Actions
        # panel. Template-readiness and Ally findings are included here
        # (unlike the old checklist-only worklist) precisely so a
        # manually-recorded-incomplete mapped field, or a severe Ally issue,
        # still appears as an action even though its status is also shown
        # richly elsewhere (the Blackboard Template card to its left, the
        # Accessibility tab) - see "Unified module findings" in CLAUDE.md.
        actions = [f for f in findings if f['state'] == 'pending']

        # The banner's "N checklist items outstanding" bullet is checklist-only
        # - Ally, Leganto and lead-owned template readiness each already have
        # their own dedicated bullet, computed directly from active_row/
        # ally_profile. The institution-owned mapped fields (sga,
        # assessment_overview, encore_link) have no bullet of their own,
        # though, so a 'readiness' finding for one of them is counted here
        # too - otherwise a DLA manually marking one of them incomplete would
        # silently drop out of the banner now that doing so produces a
        # 'readiness' finding instead of a 'checklist' one (see "Unified
        # module findings" in CLAUDE.md). student_voice moved to the
        # lead-owned side 15-09-2026 and now gets its own signal via "Lead
        # Sections Outstanding" instead.
        checklist_pending_count = len([
            f for f in findings if f['state'] == 'pending' and (
                f['source'] == 'checklist'
                or (f['source'] == 'readiness'
                    and f.get('audit_field_id') in INSTITUTION_MAPPED_FIELD_IDS))
        ])

        ally_profile = _ally_issue_profile(selected_code)
        ally_categories = _ally_issue_categories(selected_code)

        # 1. Overview metadata + module health banner
        if active_row is not None:
            raw_mod_lead = str(active_row.get('Mod. lead', '')).strip()
            if not raw_mod_lead or raw_mod_lead.lower() == 'nan':
                mod_lead = "<span style='color: #9CA3AF;'>--</span>"
            else:
                mod_lead = title_case_name(raw_mod_lead)

            ug_pg = str(active_row.get('UG/ PG/ Other', '')).strip()
            if not ug_pg or ug_pg == 'nan':
                ug_pg = "<span style='color: #9CA3AF;'>--</span>"

            url = str(active_row.get('URL', '')).strip()
            if url == 'nan':
                url = ''

            # Data-derived / Spot check-pending / Spot checked - not the raw
            # Draft/Submitted workflow status (checklist_sums's own 'Status',
            # still used as-is elsewhere - Faculty Overview, School Dashboard,
            # calculate_dynamic_compliance_gap()'s literal "✅ Submitted"
            # check - so left untouched there). has_audit is exactly "a real
            # person has recorded an answer" already (see "Unified module
            # findings" in CLAUDE.md); a pending spot_checks row for this
            # module/year distinguishes "flagged, not yet done" from "never
            # looked at" for everything else.
            #
            # A bare "Spot checked" gave a module lead no way to tell a check
            # saved this morning from one saved last October, so the date and
            # time of the most recent saved answer is shown alongside it. That
            # is sum_entry['Timestamp'] (the latest audit_responses row for the
            # module), not spot_checks.checked_on: the label fires on has_audit,
            # which covers audits that were never flagged as a spot-check at
            # all, and a re-audit moves the response timestamp while checked_on
            # stays frozen at the original close-out. The label falls back to
            # the bare wording if that value is one of app.py's "Unknown" /
            # "Never" sentinels rather than a real timestamp.
            pending_spot_check = get_pending_spot_check(selected_code, CURRENT_ACADEMIC_YEAR)
            if has_audit:
                checked_on = fmt_report_datetime(sum_entry.get('Timestamp'))
                audit_status_label = (f"Spot checked on {checked_on}" if checked_on
                                      else "Spot checked")
            elif pending_spot_check:
                audit_status_label = "Spot check-pending"
            else:
                audit_status_label = "Data-derived"

            vle_value = (f"<a href='{url}' target='_blank' style='color:#2563EB;'>Open Module Site</a>"
                         if url else "<span style='color:#9CA3AF;'>--</span>")

            # Readiness Outcome (the data-driven gating verdict) is hidden for
            # now, per user request - compute_audit_verdict() above is left
            # in place rather than removed, since this is explicitly temporary.

            st.markdown(
                f"""<div style="border:1px solid rgba(49,51,63,0.2);border-radius:8px;
                            padding:10px 16px;margin-bottom:8px;display:flex;flex-wrap:wrap;
                            gap:6px 28px;align-items:baseline;">
                    <span><b>Module Lead:</b> {mod_lead}</span>
                    <span><b>Level:</b> {ug_pg}</span>
                    <span><b>Module Site:</b> {vle_value}</span>
                    <span title="Whether this module's report rests on data alone, has a spot-check flagged, or has been spot-checked by a Digital Learning Advisor - and, if it has, when that check was last saved."><b>Audit Status:</b> {audit_status_label}</span>
                </div>""", unsafe_allow_html=True)

        _render_health_banner(ally_profile, checklist_pending_count, leganto_missing, has_audit,
                              leganto_draft, leganto_items, active_row,
                              leganto_status, leganto_draft_items)

        _render_data_reliability_block(active_row, has_audit)

        st.markdown(" ")

        # 2. Module Checks and Readiness first - it's the actionable tab for
        # a module lead - then Accessibility Report.
        # Streamlit's default tabs are small underlined text that's easy to
        # miss below the health banner, so their labels are enlarged (the
        # standard underline style is kept). The CSS is scoped to the keyed
        # container (Streamlit adds an `st-key-<key>` class) so no other
        # st.tabs in the app are affected.
        st.markdown(
            """<style>
            .st-key-mr_report_tabs [data-baseweb="tab-list"] {
                gap: 28px;
            }
            .st-key-mr_report_tabs [data-baseweb="tab"] {
                height: auto;
                padding: 6px 2px 10px;
            }
            .st-key-mr_report_tabs [data-baseweb="tab"] p {
                font-size: 1.3rem;
            }
            .st-key-mr_report_tabs [data-baseweb="tab"][aria-selected="true"] p {
                font-weight: 600;
            }
            </style>""", unsafe_allow_html=True)

        with st.container(key="mr_report_tabs"):
            tab_checks, tab_accessibility = st.tabs(
                ["📋 Module Checks and Readiness", "♿ Accessibility Report"])

            with tab_checks:
                _render_module_checks(actions, has_audit, active_row, responses,
                                      leganto_missing, leganto_status, leganto_items, leganto_draft_items)

                comments_val = str(responses.get('comments', '') or '').strip()
                if has_audit and comments_val:
                    st.info(f"**Additional Comments:**\n\n{comments_val}")

            with tab_accessibility:
                _render_ally_card(selected_code, active_row, ally_profile, ally_categories)

        st.caption(f"Last updated: {last_updated_str}")
