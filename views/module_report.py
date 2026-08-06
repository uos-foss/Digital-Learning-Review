import streamlit as st
import pandas as pd
import datetime
import logging
import json
import re
from processing import (
    get_module_mapping,
    FACULTY_SCHOOLS,
    CURRENT_ACADEMIC_YEAR,
    summarise_ally_issues,
)
from database import (
    get_active_audit_fields,
    get_audit_responses,
    save_audit_response,
    get_comment_bank,
    update_module_lead_sqlite,
    parse_custom_observations,
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


def _ally_band(score):
    for threshold, colour, level, description in ALLY_BANDS:
        if score >= threshold:
            return colour, level, description
    return ALLY_BANDS[-1][1:]


def _score_tile(label, score, sub):
    """One of the three surface scores, or a muted tile when nothing applies."""
    if score is None or pd.isna(score):
        return f"""
        <div style="text-align:center;border-radius:10px;padding:10px 8px;
                    background-color:#6B728010;border:1px solid #6B728033;">
            <span style="font-size:10px;font-weight:700;color:#6B7280;text-transform:uppercase;
                         letter-spacing:.8px;display:block;">{label}</span>
            <h2 style="margin:0;color:#6B7280;font-size:24px;font-weight:800;">--</h2>
            <span style="font-size:11px;color:#6B7280;">{sub}</span>
        </div>"""
    colour, level, _ = _ally_band(float(score))
    return f"""
    <div style="text-align:center;border-radius:10px;padding:10px 8px;
                background-color:{colour}10;border:1px solid {colour}33;">
        <span style="font-size:10px;font-weight:700;color:{colour};text-transform:uppercase;
                     letter-spacing:.8px;display:block;">{label}</span>
        <h2 style="margin:0;color:{colour};font-size:28px;font-weight:800;">{float(score):.1%}</h2>
        <span style="font-size:11px;color:#6B7280;">{sub}</span>
    </div>"""


def _render_ally_card(selected_code, active_row):
    """
    The module's accessibility profile.

    Shows Ally's three scores as Ally reports them. The portal used to display
    a single locally credibility-weighted figure instead, which pulled thin
    courses toward 50% and so disagreed with the score the module lead sees in
    Blackboard. What that weighting was really groping at - is there enough
    here to judge? - is now answered directly by the item counts and the
    content maturity banner.

    The outstanding-issues worklist used to live inside this card. It now
    lives in the page-level unified worklist instead, alongside checklist and
    Leganto gaps, so an auditor sees one ranked list rather than three.
    """
    with st.container(border=True):
        st.subheader("🔍 Ally Accessibility",
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

        # 1. Maturity first. A template scoring 99% is not an accessibility result.
        colour, icon, note = ALLY_MATURITY_NOTE.get(maturity, ALLY_MATURITY_NOTE["No data"])
        last_scanned_date = pd.to_datetime(last_checked, errors='coerce').strftime('%d-%m-%Y') if last_checked else "—"
        note += f" · Last scanned {last_scanned_date}"
        st.markdown(
            f"""<div style="border-left:4px solid {colour};background-color:{colour}0D;
                        padding:8px 12px;border-radius:4px;margin-bottom:12px;">
                <b style="color:{colour};">{icon} {maturity}</b>
                <span style="color:#6B7280;font-size:13px;"> — {note}</span>
            </div>""", unsafe_allow_html=True)

        # 2. The three scores, each with the volume of content behind it.
        c1, c2, c3 = st.columns(3)
        c1.markdown(_score_tile("Overall", overall, f"{n_files + n_wysiwyg} items"),
                    unsafe_allow_html=True)
        c2.markdown(_score_tile("Files", files_score,
                                f"{n_files} file{'' if n_files == 1 else 's'}"),
                    unsafe_allow_html=True)
        c3.markdown(_score_tile("Ultra Documents", wysiwyg_score,
                                f"{n_wysiwyg} document{'' if n_wysiwyg == 1 else 's'}"),
                    unsafe_allow_html=True)

        if (files_score is not None and wysiwyg_score is not None
                and pd.notna(files_score) and pd.notna(wysiwyg_score)):
            gap = float(wysiwyg_score) - float(files_score)
            if abs(gap) >= 0.15:
                worse, better = ("uploaded files", "Ultra Documents") if gap > 0 \
                    else ("Ultra Documents", "uploaded files")
                st.caption(
                    f"The {worse} score {abs(gap):.0%} lower than the {better}. "
                    + ("Fixing documents means re-authoring and re-uploading them."
                       if gap > 0 else
                       "Ultra Document problems are fixable directly in the Blackboard editor."))

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


def _render_health_banner(ally_profile, pending_count, leganto_missing, has_audit):
    """
    A short, neutral summary of what's outstanding across Ally, the checklist,
    and Leganto - the one place these three add up to a single picture.

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
    if leganto_missing:
        bullets.append("no Leganto reading list connected")
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
    """One Ally issue type, as used inside the unified worklist."""
    icon, where = SURFACE_WORDS.get(row['surface'], ("📄", ""))
    colour = TIER_COLOUR.get(row['severity_label'], "#6B7280")
    st.markdown(
        f"""<div style="padding:6px 0;border-bottom:1px solid #E5E7EB;">
            <span style="background:{colour}1A;color:{colour};font-size:10px;
                         font-weight:700;padding:2px 6px;border-radius:4px;
                         text-transform:uppercase;">{row['severity_label']}</span>
            <b style="margin-left:6px;">{row['label']}</b>
            <span style="color:#6B7280;"> — {row['items']} item(s)</span><br>
            <span style="font-size:13px;color:#4B5563;">{icon} {where}. {row['advice']}</span>
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
        <h4 style="margin: 0 0 6px 0; color: #1F2937; font-size: 15px; font-weight: 600;">{title}</h4>
        <div style="margin: 0; color: #4B5563; font-size: 14px; line-height: 1.5;">{body}</div>
    </div>
    """, unsafe_allow_html=True)


def _render_unified_worklist(active_row, ally_profile, pending_items, leganto_missing, has_audit):
    """
    One severity-ranked worklist across Ally, the checklist, and Leganto.

    Replaces three separate lists (an Ally-only expander, a checklist-only
    "Actions & Recommendations" expander, and a one-line Leganto mention) with
    a single ranked list, so an auditor sees what actually needs doing without
    cross-referencing three sections by hand. Checklist items and a missing
    Leganto list don't carry their own severity today, so they sit at a fixed
    "Major" tier alongside Ally's own major-severity issues - no schema
    change, revisit if per-item severity is ever added to the checklist.
    """
    severe = ally_profile[ally_profile['severity_label'] == 'Severe'] if not ally_profile.empty else ally_profile
    major_ally = ally_profile[ally_profile['severity_label'] == 'Major'] if not ally_profile.empty else ally_profile
    minor = (ally_profile[ally_profile['severity_label'].isin(['Minor', 'Other'])]
             if not ally_profile.empty else ally_profile)

    major_checklist = list(pending_items)
    if leganto_missing:
        major_checklist.append({
            'type': 'boolean',
            'label': 'Leganto Reading List Missing',
            'description': "This module doesn't have a reading list connected in Leganto yet."
        })

    total = len(severe) + len(major_ally) + len(major_checklist) + len(minor)
    if total == 0:
        st.success("✅ Nothing outstanding right now — no accessibility issues and no open checklist items.")
        return

    with st.expander(f"Outstanding items ({total})", expanded=bool(len(severe))):
        if not has_audit:
            st.caption("This module hasn't had a Digital Learning Advisor audit yet, so checklist "
                       "items are shown as outstanding until one is completed.")

        if len(severe):
            st.markdown("**Severe**")
            for _, row in severe.iterrows():
                _render_ally_issue_card(row)

        if len(major_ally) or major_checklist:
            st.markdown("**Major**")
            for _, row in major_ally.iterrows():
                _render_ally_issue_card(row)
            for item in major_checklist:
                _render_pending_item_card(item)

        if len(minor):
            st.markdown("**Minor**")
            for _, row in minor.iterrows():
                _render_ally_issue_card(row)

        url = str(active_row.get('URL', '') or '') if active_row is not None else ''
        if url and (len(severe) or len(major_ally) or len(minor)):
            st.markdown(f"[Open this course in Blackboard]({url}) to work through its Ally report.")


def _compute_checklist_items(selected_code, checklist_sums, active_fields):
    """
    Classify each active audit field into pending/completed, read-only.

    Runs whether or not the module has been audited yet, so an unaudited
    module correctly shows every field as outstanding in the unified worklist
    rather than the checklist section going blank. Leganto is handled by the
    caller, not here - it isn't one of the active audit fields.

    Returns (pending_items, completed_items, has_audit, last_updated_str, responses).
    """
    pending_items = []
    completed_items = []

    has_audit = selected_code in checklist_sums
    last_updated_str = "Never"
    responses = {}

    if has_audit:
        sum_entry = checklist_sums[selected_code]
        responses = sum_entry.get('Responses', {})
        last_updated_str = f"{sum_entry.get('Timestamp', 'Never')} by {sum_entry.get('Auditor', 'Unknown')}"

    if active_fields:
        comment_bank = get_comment_bank()
        compliant_tag_ids = {c['id'] for c in comment_bank
                             if "Compliant" in c.get('category', '') or "No action needed" in c.get('advice', '')}
        cb_lookup = {c['id']: c for c in comment_bank}

        for field in active_fields:
            fid = field['id']
            label = field['label']
            action_label = field.get('action_label') or label
            desc = field['description']
            ftype = field['field_type']
            val = responses.get(fid, None)

            if ftype == 'boolean' or ftype == 'yes/no':
                if ftype == 'boolean':
                    is_compliant = (str(val).upper() == 'TRUE')
                else:
                    is_compliant = (str(val).upper() == 'YES')

                if is_compliant:
                    completed_items.append({'type': 'boolean', 'label': label, 'description': desc})
                else:
                    pending_items.append({'type': 'boolean', 'label': action_label, 'description': desc})
            elif ftype == 'text' and val:
                try:
                    data = json.loads(val)
                    if isinstance(data, dict):
                        tags = data.get("tags", [])
                        custom = data.get("custom", "")

                        for tag_id in tags:
                            tag_info = cb_lookup.get(tag_id)
                            if tag_info:
                                is_compliant = tag_id in compliant_tag_ids
                                target = completed_items if is_compliant else pending_items
                                target.append({
                                    'type': 'tag',
                                    'category': tag_info.get('category', 'General'),
                                    'comment': tag_info.get('comment', ''),
                                    'advice': tag_info.get('advice', ''),
                                    'resource_url': tag_info.get('resource_url', ''),
                                    'resource_text': tag_info.get('resource_text', '')
                                })
                            else:
                                pending_items.append({'type': 'legacy_tag', 'comment': str(tag_id)})

                        custom_obs_list = parse_custom_observations(custom)
                        for obs in custom_obs_list:
                            pending_items.append({
                                'type': 'custom',
                                'category': label,
                                'label': obs.get('observation', ''),
                                'description': obs.get('action', '')
                            })
                except Exception:
                    if str(val).strip():
                        custom_obs_list = parse_custom_observations(val)
                        for obs in custom_obs_list:
                            pending_items.append({
                                'type': 'custom',
                                'category': label,
                                'label': obs.get('observation', ''),
                                'description': obs.get('action', '')
                            })

    return pending_items, completed_items, has_audit, last_updated_str, responses


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
        active_row = spr_m.iloc[0] if not spr_m.empty else (aut_m.iloc[0] if not aut_m.empty else None)

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

        # Checklist and Ally data are both needed by the health banner and the
        # unified worklist, so compute them before rendering anything.
        active_fields = get_active_audit_fields()
        pending_items, completed_items, has_audit, last_updated_str, responses = \
            _compute_checklist_items(selected_code, checklist_sums, active_fields)
        if not leganto_missing:
            completed_items.append({
                'type': 'boolean',
                'label': 'Leganto Reading List: OK / Connected',
                'description': 'The module has a reading list connected in Leganto.'
            })
        ally_profile = _ally_issue_profile(selected_code)

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

            with st.container(border=True):
                c1, c2, c3, c4 = st.columns(4)
                with c1:
                    st.markdown(f"**Module Lead:**  \n{mod_lead}", unsafe_allow_html=True)
                with c2:
                    st.markdown(f"**Level:**  \n{ug_pg}", unsafe_allow_html=True)
                with c3:
                    if url:
                        st.markdown(f"**VLE Link:**  \n[Open Module Site]({url})", unsafe_allow_html=True)
                    else:
                        st.markdown("**VLE Link:**  \n<span style='color: #9CA3AF;'>--</span>", unsafe_allow_html=True)
                with c4:
                    st.markdown(f"**Checklist Status:**  \n{sa_status}", unsafe_allow_html=True)

        _render_health_banner(ally_profile, len(pending_items), leganto_missing, has_audit)

        st.markdown(" ")

        # 2. Ally accessibility profile
        _render_ally_card(selected_code, active_row)
        st.markdown("---")

        # 3. One outstanding-items worklist across Ally, the checklist, and Leganto
        _render_unified_worklist(active_row, ally_profile, pending_items, leganto_missing, has_audit)

        # 4. Checklist detail: DLA edit access, completed criteria, internal notes
        is_dla_or_admin = any(c.lower() == "edit_checklist" for c in user_caps)

        if is_dla_or_admin:
            st.info("ℹ️ **Auditor Mode**: You have permissions to audit this module. To make changes or record observations, please open the dedicated Audit Portal.")
            if st.button("✏️ Open Audit Portal to Edit Checklist", use_container_width=True, key=f"ap_redir_{selected_code}"):
                st.switch_page(st.session_state.pg_audit)

        with st.expander("View Completed Check Criteria", expanded=False):
            if not completed_items:
                st.caption("No completed checklist criteria recorded yet.")
            else:
                for item in completed_items:
                    if item['type'] == 'boolean':
                        st.markdown(f"""
                        <div style="border-left: 4px solid #10B981; background-color: rgba(16, 185, 129, 0.01); padding: 8px 12px; margin-bottom: 8px; border-radius: 4px; border-top: 1px solid rgba(16, 185, 129, 0.02); border-right: 1px solid rgba(16, 185, 129, 0.02); border-bottom: 1px solid rgba(16, 185, 129, 0.02);">
                            <span style="color: #047857; font-weight: 600; font-size: 14px;">✅ {item['label']}</span>
                        </div>
                        """, unsafe_allow_html=True)
                    elif item['type'] == 'tag':
                        st.markdown(f"""
                        <div style="border-left: 4px solid #10B981; background-color: rgba(16, 185, 129, 0.01); padding: 8px 12px; margin-bottom: 8px; border-radius: 4px; border-top: 1px solid rgba(16, 185, 129, 0.02); border-right: 1px solid rgba(16, 185, 129, 0.02); border-bottom: 1px solid rgba(16, 185, 129, 0.02);">
                            <span style="color: #047857; font-weight: 600; font-size: 14px;">✅ {item['category']} Compliant: {item['comment']}</span>
                        </div>
                        """, unsafe_allow_html=True)

        # Render confidential internal notes if user is an auditor
        if is_dla_or_admin and has_audit:
            auditor_notes = str(responses.get('auditor_notes', '')).strip()
            if auditor_notes and auditor_notes.lower() != 'none':
                st.info(f"🔒 **Auditor Notes (Internal/Auditors Only):**\n\n{auditor_notes}")

        st.caption(f"Last updated: {last_updated_str}")
