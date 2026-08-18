import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import datetime
import logging
import re
from processing import (
    get_module_mapping,
    FACULTY_SCHOOLS,
    CURRENT_ACADEMIC_YEAR,
    summarise_ally_issues,
    TEMPLATE_SECTIONS,
    LEAD_OWNED_SECTIONS,
    SECTION_STATES,
    derive_module_findings,
    compute_audit_verdict,
    fmt_report_date,
    readiness_evidence_words,
    readiness_created_date,
    resolve_active_row,
)
from database import (
    get_active_audit_fields,
    get_audit_responses,
    save_audit_response,
    get_comment_bank,
    update_module_lead_sqlite,
    get_ally_history,
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

# Colour used for each worklist tier - shared between the health banner (via
# the presence of severe items) and the unified worklist below it.
TIER_COLOUR = {"Severe": "#EF4444", "Major": "#F59E0B", "Minor": "#6B7280"}

SURFACE_WORDS = {
    'editor': ("✏️", "Fix in the Blackboard editor"),
    'image': ("🖼️", "Fix in the browser via Ally feedback"),
    'file': ("📄", "Re-author and re-upload the file"),
}

# Template section states by tier. 'action' is amber rather than red on purpose:
# a section drafted and left hidden is the most actionable thing on the page,
# but it means somebody has done the work, so it must not read as a failing.
STATE_TIER_COLOUR = {
    'ok': "#10B981",
    'action': "#F59E0B",
    'attention': "#6B7280",
    'fault': "#EF4444",
}


def _ally_band(score):
    for threshold, colour, level, description in ALLY_BANDS:
        if score >= threshold:
            return colour, level, description
    return ALLY_BANDS[-1][1:]


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
        height=140,
        margin=dict(l=20, r=20, t=40, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        font={'color': '#6B7280'},
    )
    return fig, has_score, sub


def _render_ally_card(selected_code, active_row, ally_profile):
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
        st.subheader("Accessibility Report",
                     help="Ally's own scores for this course, from the most recent "
                          "institutional export. Files and editor pages are scored "
                          "separately because they are fixed in completely different ways.")

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
                "means it has no Blackboard course, or its course sits under a different "
                "code — the Admin Panel's Ally import reports both.")
            return

        # 1. Maturity banner - only for states that need explaining. "In
        # progress" is the common case and is already obvious from the
        # gauges being non-zero, so it doesn't get its own banner; "Not yet
        # built"/"Empty" do, since a high score there would otherwise read as
        # real accessibility compliance rather than an unbuilt template.
        last_scanned_date = pd.to_datetime(last_checked, errors='coerce').strftime('%d-%m-%Y') if last_checked else "—"
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
            (c3, "Ultra Documents", wysiwyg_score,
             f"{n_wysiwyg} document{'' if n_wysiwyg == 1 else 's'}", "wysiwyg"),
        ):
            fig, _, sub_text = _score_gauge(tile_label, tile_score, tile_sub, is_template)
            with col:
                st.plotly_chart(fig, use_container_width=True,
                                config={'displayModeBar': False}, key=f"gauge_{selected_code}_{tile_key}")
                st.markdown(
                    f"<div style='text-align:center;font-size:11px;color:#6B7280;margin-top:-16px;'>{sub_text}</div>",
                    unsafe_allow_html=True)

        if not active_row.get('Ally Enabled', True):
            st.warning("⚠️ Ally is switched off for this course, so students get no "
                       "alternative formats and the module lead sees no feedback.")

        _render_ally_trend(selected_code)

        st.caption(
            "ℹ️ Ally figures come from periodic institutional exports and can lag the "
            "live course. The module's own Ally Course Report inside Blackboard is "
            "always current.")

        st.caption(
            "Need help? "
            "[Digital accessibility guidance](https://staff.sheffield.ac.uk/digital-accessibility) · "
            "[Making content accessible with Ally](https://staff.sheffield.ac.uk/blackboard/ally)")

        st.markdown("---")
        _render_ally_issues(ally_profile, active_row, is_template)


def _ally_issue_profile(selected_code):
    """This module's Ally issues, ranked worst-first. Empty frame if none."""
    df_issues = st.session_state.get("df_ally_issues", pd.DataFrame())
    if df_issues is None or df_issues.empty:
        return pd.DataFrame()

    mine = df_issues[df_issues['module_code'].astype(str).str.strip().str.upper()
                     == str(selected_code).strip().upper()]
    return summarise_ally_issues(mine)


def _render_ally_trend(selected_code):
    """Score over the stored snapshots, when there is more than one."""
    try:
        history = get_ally_history(str(selected_code).strip().upper(), CURRENT_ACADEMIC_YEAR)
    except Exception as exc:
        logging.warning(f"Could not load Ally history for {selected_code}: {exc}")
        return

    if history.empty or history['snapshot_date'].nunique() < 2:
        return

    # Snapshots are only stored when a course changes, so every point here is a
    # real movement rather than a repeated reading.
    series = (history.groupby('snapshot_date')
                     .apply(lambda g: (g['overall_score'] * (g['total_files'] + g['total_wysiwyg'])).sum()
                                      / max((g['total_files'] + g['total_wysiwyg']).sum(), 1),
                            include_groups=False)
                     .rename("Overall score"))
    st.markdown("**Accessibility over time**")
    st.line_chart(series, height=140)
    st.caption("Each point is a snapshot in which this course's content actually changed.")


def _render_health_banner(ally_profile, pending_count, leganto_missing, has_audit,
                           leganto_draft=False, leganto_items=0, active_row=None):
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
                           f"{'are' if n != 1 else 'is'} missing in the course shell")

    if leganto_missing:
        bullets.append("no Leganto reading list connected")
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


def _render_pending_item_card(item):
    """One outstanding checklist-origin item, as used inside the unified worklist."""
    if item['type'] == 'boolean':
        title = f"📌 {item['label']}"
        body = f"{item['description']}"
    elif item['type'] == 'tag':
        title = f"📌 {item['category']}"
        body = f"<strong>Observation:</strong> {item['comment']}"
        if item['advice']:
            body += f"<br/><br/><strong>Action:</strong> {item['advice']}"
        if item['resource_url']:
            label_link = item['resource_text'] if item['resource_text'] else "Useful Link / Signpost"
            body += (f"<br/><br/>🔗 <strong>Resource:</strong> "
                     f"<a href='{item['resource_url']}' target='_blank' "
                     f"style='color: #2563EB; text-decoration: underline;'>{label_link}</a>")
    elif item['type'] == 'legacy_tag':
        title = "📌 Legacy Observation"
        body = f"<strong>Observation:</strong> {item['comment']}"
    elif item['type'] == 'custom':
        title_text = item.get('label', '').strip() or item.get('category', 'Custom Observation')
        title = f"📌 {title_text}"
        body = item.get('description', '')
        body = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', body).replace('\n', '<br/>')
    else:
        return

    st.markdown(f"""
    <div style="border-left: 4px solid #F59E0B; background-color: rgba(245, 158, 11, 0.02); padding: 12px 16px; margin-bottom: 12px; border-radius: 4px; border-top: 1px solid rgba(245, 158, 11, 0.05); border-right: 1px solid rgba(245, 158, 11, 0.05); border-bottom: 1px solid rgba(245, 158, 11, 0.05);">
        <span style="background:{TIER_COLOUR['Major']}1A;color:{TIER_COLOUR['Major']};font-size:10px;
                     font-weight:700;padding:2px 6px;border-radius:4px;text-transform:uppercase;">Major</span>
        <h4 style="margin: 6px 0 6px 0; color: #1F2937; font-size: 15px; font-weight: 600;">{title}</h4>
        <div style="margin: 0; color: #4B5563; font-size: 14px; line-height: 1.5;">{body}</div>
    </div>
    """, unsafe_allow_html=True)


def _render_ally_issues(ally_profile, active_row, is_template=False):
    """
    Ally's accessibility issues, ranked by severity.

    Lives inside the Accessibility column, directly below the score tiles -
    scores and the issues behind them are one picture, not two separate page
    sections a reader has to reconcile by hand.

    is_template distinguishes "genuinely clean" from "nothing scanned yet" -
    a zero-issue template hasn't been checked for anything, so a green
    success tick there would overstate it the same way an unqualified high
    score would.
    """
    severe = ally_profile[ally_profile['severity_label'] == 'Severe'] if not ally_profile.empty else ally_profile
    major = ally_profile[ally_profile['severity_label'] == 'Major'] if not ally_profile.empty else ally_profile
    minor = (ally_profile[ally_profile['severity_label'].isin(['Minor', 'Other'])]
             if not ally_profile.empty else ally_profile)

    total = len(severe) + len(major) + len(minor)
    if total == 0:
        if is_template:
            st.caption("This course still holds only its rolled-over template, so there's "
                       "nothing to report yet.")
        else:
            st.success("✅ No accessibility issues reported.")
        return

    st.markdown(f"#### Accessibility Issues ({total})")

    if len(severe):
        st.markdown("**Severe**")
        for _, row in severe.iterrows():
            _render_ally_issue_card(row)

    if len(major):
        st.markdown("**Major**")
        for _, row in major.iterrows():
            _render_ally_issue_card(row)

    if len(minor):
        st.markdown("**Minor**")
        for _, row in minor.iterrows():
            _render_ally_issue_card(row)

    url = str(active_row.get('URL', '') or '') if active_row is not None else ''
    if url:
        st.markdown(f"[Open this course in Blackboard]({url}) to work through its Ally report.")


def _render_module_checks(pending_items, completed_items, has_audit, active_row=None):
    """
    Checklist, Leganto and Blackboard template readiness, outstanding items
    first then completed.

    Everything that isn't Ally accessibility - the module-lead-facing
    checklist, the Leganto reading-list gap/status, and the template section
    states - lives in this one column so "what's left to sort out on this
    module" and "what's already done" read together instead of across two
    page-halves.

    pending_items/completed_items already carry both checklist and Leganto
    findings - both come from processing.derive_module_findings(), the single
    place that decides what counts as outstanding for every source, so this
    function only renders, it does not classify.

    The template block is reported separately from the generic worklist rather
    than folded into it: those states are observations from an export, and a
    checklist item still means something a Digital Learning Advisor recorded.
    """
    st.subheader("Module Checks and Readiness")

    _render_template_sections(active_row)

    st.markdown(f"#### Outstanding ({len(pending_items)})")
    if not pending_items:
        st.success("✅ Nothing outstanding right now.")
    else:
        if not has_audit:
            st.caption("This module hasn't had a Digital Learning Advisor audit yet, so checklist "
                       "items are shown as outstanding until one is completed.")
        for item in pending_items:
            _render_pending_item_card(item)

    st.markdown(f"#### Completed ({len(completed_items)})")
    if not completed_items:
        st.caption("No completed checklist criteria recorded yet.")
    else:
        for item in completed_items:
            if item['type'] == 'boolean':
                st.markdown(f"""
                <div style="border-left: 4px solid #10B981; background-color: rgba(16, 185, 129, 0.02); padding: 12px 16px; margin-bottom: 12px; border-radius: 4px; border-top: 1px solid rgba(16, 185, 129, 0.05); border-right: 1px solid rgba(16, 185, 129, 0.05); border-bottom: 1px solid rgba(16, 185, 129, 0.05);">
                    <span style="background:#10B9811A;color:#047857;font-size:10px;
                                 font-weight:700;padding:2px 6px;border-radius:4px;text-transform:uppercase;">Complete</span>
                    <h4 style="margin: 6px 0 0 0; color: #1F2937; font-size: 15px; font-weight: 600;">✅ {item['label']}</h4>
                </div>
                """, unsafe_allow_html=True)
            elif item['type'] == 'tag':
                st.markdown(f"""
                <div style="border-left: 4px solid #10B981; background-color: rgba(16, 185, 129, 0.02); padding: 12px 16px; margin-bottom: 12px; border-radius: 4px; border-top: 1px solid rgba(16, 185, 129, 0.05); border-right: 1px solid rgba(16, 185, 129, 0.05); border-bottom: 1px solid rgba(16, 185, 129, 0.05);">
                    <span style="background:#10B9811A;color:#047857;font-size:10px;
                                 font-weight:700;padding:2px 6px;border-radius:4px;text-transform:uppercase;">Complete</span>
                    <h4 style="margin: 6px 0 0 0; color: #1F2937; font-size: 15px; font-weight: 600;">✅ {item['category']} Compliant: {item['comment']}</h4>
                </div>
                """, unsafe_allow_html=True)


def _render_template_sections(active_row):
    """
    The Blackboard template's required sections, from the faculty Template
    Alignment Report.

    Lead-owned sections first and in full, because those are the three that ship
    hidden and carry all the signal. The other eleven ship visible and nobody is
    expected to touch them, so "Visible" there says nothing - they are collapsed
    behind an expander and shown only so a deleted or missing one is findable.
    """
    if active_row is None:
        return

    states = active_row.get('Template Sections') or {}
    if not isinstance(states, dict) or not states:
        return

    snapshot = fmt_report_date(active_row.get('Readiness Snapshot'))
    ready = active_row.get('Lead Sections Ready')
    total = int(active_row.get('Lead Sections Total') or len(LEAD_OWNED_SECTIONS))
    created = readiness_created_date(states)

    st.markdown("#### Blackboard Template")
    st.caption(
        f"{int(ready or 0)} of {total} module-lead sections visible to students"
        + (f" · as at {snapshot}" if snapshot else ""))

    for key in LEAD_OWNED_SECTIONS:
        state = states.get(key)
        if not state:
            continue
        label = TEMPLATE_SECTIONS.get(key, (key,))[0]
        badge, tier, action = SECTION_STATES.get(
            state.get('state', 'unknown'), SECTION_STATES['unknown'])
        colour = STATE_TIER_COLOUR.get(tier, "#6B7280")
        st.markdown(
            f"""<div style="border-left: 4px solid {colour}; background-color: {colour}05;
                        padding: 10px 14px; margin-bottom: 8px; border-radius: 4px;">
                <span style="background:{colour}1A;color:{colour};font-size:10px;
                             font-weight:700;padding:2px 6px;border-radius:4px;
                             text-transform:uppercase;">{badge}</span>
                <h4 style="margin:6px 0 4px 0;color:#1F2937;font-size:15px;
                           font-weight:600;">{label}</h4>
                <p style="margin:0 0 4px 0;color:#374151;font-size:12px;">{action}</p>
                <p style="margin:0;color:#9CA3AF;font-size:11px;">
                    {readiness_evidence_words(state, created)}</p>
            </div>""", unsafe_allow_html=True)

    others = [(k, v) for k, v in states.items() if k not in LEAD_OWNED_SECTIONS]
    if others:
        problem = [k for k, v in others if v.get('status') in ('Deleted', 'Missing')]
        title = (f"Other template sections ({len(others)}) — "
                 f"{len(problem)} deleted or missing" if problem
                 else f"Other template sections ({len(others)})")
        with st.expander(title):
            st.caption(
                "These ship visible in the template and no one is expected to edit "
                "them, so 'Visible' here is the default rather than evidence of work.")
            rows = [{
                'Section': TEMPLATE_SECTIONS.get(k, (k,))[0],
                'Status': v.get('status', ''),
                'Last changed': fmt_report_date(v.get('last_modified')) or "—",
            } for k, v in others]
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


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
        school_context_badge = f" <span style='font-size: 16px; vertical-align: middle; background-color: rgba(59, 130, 246, 0.1); color: #3b82f6; padding: 4px 10px; border-radius: 12px; margin-left: 12px; border: 1px solid rgba(59, 130, 246, 0.2);'>Context: {st.session_state.saved_school}</span>"
        st.markdown(f"<h1>Module Report{school_context_badge}</h1>", unsafe_allow_html=True)
        combined_options = [opt for opt in combined_options if opt.startswith(st.session_state.saved_school)]
    else:
        st.title("Module Report")
        # Optional multi-tenant school filter to focus without siloing
        if st.session_state.saved_school != "All":
            filter_by_school = st.checkbox(f"Focus on my school ({st.session_state.saved_school})", value=True, key="rc_focus_school")
            if filter_by_school:
                combined_options = [opt for opt in combined_options if opt.startswith(st.session_state.saved_school)]
            else:
                selected_school = st.selectbox(
                    "Select School to Focus",
                    ["All Schools"] + schools_list,
                    index=0,
                    key="rc_school_select",
                    help="Switch to another school's module list."
                )
                if selected_school != "All Schools":
                    combined_options = [opt for opt in combined_options if opt.startswith(selected_school)]
        else:
            # Fallback for "All Schools" users (e.g. FACULTY) to filter module list by school
            selected_school = st.selectbox(
                "Filter by School",
                ["All Schools"] + schools_list,
                index=0,
                key="rc_school_select_all",
                help="Filter the module selection list by a specific school."
            )
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

    def on_module_change():
        if st.session_state.unified_search:
            st.session_state.selected_module_code = st.session_state.unified_search.split(" - ")[0]
        else:
            st.session_state.selected_module_code = ""

    st.selectbox(
        "Search by Module Code or Name",
        options=[""] + combined_options,
        index=current_idx,
        key="unified_search",
        on_change=on_module_change
    )

    selected_code = st.session_state.selected_module_code

    if selected_code:
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
        leganto_draft = leganto_status in ('Draft', 'Mixed')

        # Checklist, Leganto, Ally and readiness findings all come from one
        # place - processing.derive_module_findings() - so the worklist below,
        # the health banner's counts, and the Actionable Items badge on School
        # Dashboard / Faculty Overview can no longer disagree about what a
        # module has outstanding.
        active_fields = get_active_audit_fields()
        comment_bank = get_comment_bank()

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
            last_updated_str = (f"{sum_entry.get('Timestamp', 'Never')} by {sum_entry.get('Auditor', 'Unknown')}"
                                if has_audit else "Never")
        else:
            responses = {}
            last_updated_str = "Never"

        findings = derive_module_findings(active_row, responses, active_fields, comment_bank)

        # Not gated on has_audit - a never-audited module has no responses at
        # all, so this already resolves to 'blank' correctly by itself;
        # gating on has_audit would just suppress a correct, meaningful signal.
        verdict = compute_audit_verdict(active_fields, responses)

        # The generic worklist column only ever showed checklist and Leganto
        # findings - Ally and template readiness already have their own
        # richer, source-specific displays (the accessibility card, the
        # Blackboard Template block) and are not duplicated here.
        pending_items = [f for f in findings if f['source'] in ('checklist', 'leganto') and f['state'] == 'pending']
        completed_items = [f for f in findings if f['source'] in ('checklist', 'leganto') and f['state'] == 'completed']

        # The banner's "N checklist items outstanding" bullet is checklist-only
        # - Ally, Leganto and template readiness each already have their own
        # dedicated bullet, computed directly from active_row/ally_profile so
        # nothing here needs to be filtered out of a combined count.
        checklist_pending_count = len(
            [f for f in findings if f['source'] == 'checklist' and f['state'] == 'pending'])

        ally_profile = _ally_issue_profile(selected_code)

        is_dla_or_admin = any(c.lower() == "edit_checklist" for c in user_caps)

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

            sa_status = checklist_sums.get(selected_code, {}).get('Status', "❌ No Submission")

            vle_value = (f"<a href='{url}' target='_blank' style='color:#2563EB;'>Open Module Site</a>"
                         if url else "<span style='color:#9CA3AF;'>--</span>")

            # A pass/fail verdict is evaluative, unlike the health banner
            # below (deliberately factual/neutral) - kept as its own clearly
            # separate, distinctly-labelled span rather than folded into it.
            # "Audit Status"/"Readiness Outcome" wording matches audit_portal.py
            # exactly - the two pages used to say "Checklist Status"/"Module
            # Readiness" here vs "Status"/"Outcome" there for the same two
            # concepts (workflow stage vs data-driven gating verdict).
            verdict_labels = {'ready': ("🟢", "Ready"), 'not_ready': ("🔴", "Not Ready"), 'blank': ("⚪", "Blank")}
            verdict_html = ""
            if verdict:
                v_icon, v_text = verdict_labels[verdict]
                verdict_html = (
                    f'<span title="Computed automatically from gating checklist items - '
                    f'independent of whether a DLA has submitted the audit."><b>Readiness Outcome:</b> '
                    f'{v_icon} {v_text}</span>')

            st.markdown(
                f"""<div style="border:1px solid rgba(49,51,63,0.2);border-radius:8px;
                            padding:10px 16px;margin-bottom:8px;display:flex;flex-wrap:wrap;
                            gap:6px 28px;align-items:baseline;">
                    <span><b>Module Lead:</b> {mod_lead}</span>
                    <span><b>Level:</b> {ug_pg}</span>
                    <span><b>VLE Link:</b> {vle_value}</span>
                    <span title="Whether a Digital Learning Advisor has reviewed and submitted this checklist."><b>Audit Status:</b> {sa_status}</span>
                    {verdict_html}
                </div>""", unsafe_allow_html=True)

        if is_dla_or_admin:
            st.caption("🔎 Auditor Mode — you can record observations for this module in the Audit Portal (see sidebar).")

        _render_health_banner(ally_profile, checklist_pending_count, leganto_missing, has_audit,
                              leganto_draft, leganto_items, active_row)

        st.markdown(" ")

        # 2. Two source-scoped columns: everything Ally on the left,
        # everything checklist/Leganto (outstanding and completed together)
        # on the right. gap="large" gives real visual separation - the
        # default gap alone reads as one continuous block on wide screens.
        col_accessibility, col_checks = st.columns(2, gap="large")

        with col_accessibility:
            _render_ally_card(selected_code, active_row, ally_profile)

        with col_checks:
            _render_module_checks(pending_items, completed_items, has_audit, active_row)

        # Render confidential internal notes if user is an auditor
        if is_dla_or_admin and has_audit:
            auditor_notes = str(responses.get('auditor_notes', '')).strip()
            if auditor_notes and auditor_notes.lower() != 'none':
                st.info(f"🔒 **Auditor Notes (Internal/Auditors Only):**\n\n{auditor_notes}")

        st.caption(f"Last updated: {last_updated_str}")
