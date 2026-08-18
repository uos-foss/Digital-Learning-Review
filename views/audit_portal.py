import streamlit as st
import pandas as pd
import datetime
import logging
from processing import (
    get_module_mapping, FACULTY_SCHOOLS, readiness_prefill_for_module,
    resolve_active_row, compute_spot_check_agreement, CURRENT_ACADEMIC_YEAR,
    compute_audit_verdict, parse_user_schools, format_user_schools,
    module_matches_user_schools,
)
from database import (
    get_active_audit_fields,
    get_audit_responses,
    get_audit_response_history,
    save_audit_response,
    get_spot_checks_for_user,
    get_pending_spot_check,
    mark_spot_check_checked,
)
from masquerade import is_masquerading

def view_audit_portal(df_aut, df_spr, checklist_sums, df_assess=None):
    user_caps = st.session_state.get("capabilities", [])
    if "edit_checklist" not in [c.lower() for c in user_caps]:
        st.error("Access Denied: You do not have permission to access the Audit Portal.")
        st.stop()

    user_role = str(st.session_state.get("user_role", "")).strip().upper()
    is_dla_or_admin = user_role in ("ADMIN", "DLA")

    module_mapping = get_module_mapping(df_aut, df_spr)
    combined_options = sorted([f"{code} - {name}" for code, name in module_mapping.items()])

    schools_list = list(FACULTY_SCHOOLS)

    only_own_school = any(c.lower() == "view_school" for c in user_caps) and not any(c.lower() == "view_all" for c in user_caps)

    if only_own_school:
        user_schools = parse_user_schools(st.session_state.saved_school)
        school_context_badge = f" <span style='font-size: 16px; vertical-align: middle; background-color: rgba(59, 130, 246, 0.1); color: #3b82f6; padding: 4px 10px; border-radius: 12px; margin-left: 12px; border: 1px solid rgba(59, 130, 246, 0.2);'>Context: {format_user_schools(user_schools)}</span>"
        st.markdown(f"### VLE Audit Portal{school_context_badge}", unsafe_allow_html=True)
        combined_options = [opt for opt in combined_options if module_matches_user_schools(opt, user_schools)]
    else:
        st.markdown("### VLE Audit Portal")
        # Optional multi-tenant school filter to focus without siloing
        user_schools = parse_user_schools(st.session_state.saved_school)
        if user_schools != ["All"]:
            label = format_user_schools(user_schools)
            filter_by_school = st.checkbox(f"Focus on my school{'s' if len(user_schools) > 1 else ''} ({label})", value=True, key="ap_focus_school")
            if filter_by_school:
                combined_options = [opt for opt in combined_options if module_matches_user_schools(opt, user_schools)]
            else:
                selected_school = st.selectbox(
                    "Select School to Focus",
                    ["All Schools"] + schools_list,
                    index=0,
                    key="ap_school_select",
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
                key="ap_school_select_all",
                help="Filter the module selection list by a specific school."
            )
            if selected_school != "All Schools":
                combined_options = [opt for opt in combined_options if opt.startswith(selected_school)]

    username_upper = str(st.session_state.get("username", "")).strip().upper()
    pending_spot_checks = (get_spot_checks_for_user(username_upper, status='pending')
                           if username_upper else pd.DataFrame())
    if not pending_spot_checks.empty:
        with st.expander(f"🎯 Your Spot-Checks ({len(pending_spot_checks)} pending)", expanded=True):
            st.caption(
                "Modules you flagged for spot-check on the School Dashboard. Open "
                "one and complete the checklist as normal - saving it records "
                "whether your answers matched what the Blackboard Template data "
                "suggested when you flagged it.")
            for _, sc_row in pending_spot_checks.iterrows():
                sc_code = sc_row['module_code']
                sc_name = module_mapping.get(sc_code, sc_code)
                sc_c1, sc_c2 = st.columns([4, 1])
                with sc_c1:
                    st.write(f"**{sc_code}** — {sc_name}  ·  flagged {sc_row['flagged_on']}")
                with sc_c2:
                    if st.button("Open", key=f"sc_open_{sc_row['id']}", use_container_width=True):
                        st.session_state.selected_module_code = sc_code
                        st.rerun()

    if 'selected_module_code' not in st.session_state:
        st.session_state.selected_module_code = ""

    current_idx = 0
    if st.session_state.selected_module_code:
        for i, opt in enumerate(combined_options):
            if opt.startswith(st.session_state.selected_module_code + " -"):
                current_idx = i + 1
                break

    def on_module_change():
        if st.session_state.ap_unified_search:
            st.session_state.selected_module_code = st.session_state.ap_unified_search.split(" - ")[0]
        else:
            st.session_state.selected_module_code = ""

    st.selectbox(
        "Select Module to Audit",
        options=[""] + combined_options,
        index=current_idx,
        key="ap_unified_search",
        on_change=on_module_change
    )

    selected_code = st.session_state.selected_module_code
    if selected_code:
        active_row = resolve_active_row(selected_code, df_aut, df_spr)
        readiness_prefill = readiness_prefill_for_module(active_row)

        url = str(active_row.get('URL', '')).strip() if active_row is not None else ""
        if url == 'nan':
            url = ""

        active_fields = get_active_audit_fields()
        prev_responses = get_audit_responses(selected_code)

        audit_status = prev_responses.get('audit_status', {}).get('value', '')
        if audit_status == 'submitted':
            sa_status = "✅ Submitted"
        elif audit_status == 'draft':
            sa_status = "📝 Draft"
        else:
            sa_status = "❌ Not Started"

        # As-of-last-save, not live from unsaved checkbox state - matches the
        # existing sa_status/"Last updated" caption below, which is also a
        # snapshot of the last save rather than the in-progress form.
        flat_prev = {fid: r.get('value') for fid, r in prev_responses.items()}
        verdict = compute_audit_verdict(active_fields, flat_prev)

        col1, col2 = st.columns([2, 1])
        with col1:
            if url:
                st.markdown(f"🔗 [Open in Blackboard]({url})")
            else:
                st.caption("⚠️ VLE link not found")
        with col2:
            st.markdown(
                f"**Audit Status:** {sa_status}",
                help="Whether a Digital Learning Advisor has reviewed and submitted this checklist.")

        # "Audit Status" (workflow stage, above) and "Readiness Outcome"
        # (below) are deliberately two separate labelled lines, not one -
        # they answer different questions. Status says whether a human has
        # signed this off; Outcome is computed straight from the gating
        # fields' current values and can be Ready/Not Ready even on a module
        # nobody has submitted yet (e.g. auto-suggested from readiness data).
        # Wording matches views/module_report.py exactly.
        verdict_help = ("Computed automatically from gating checklist items - "
                         "independent of whether a DLA has submitted the audit.")
        if verdict == 'ready':
            st.markdown("🟢 **Readiness Outcome: Ready**", help=verdict_help)
        elif verdict == 'not_ready':
            st.markdown("🔴 **Readiness Outcome: Not Ready**", help=verdict_help)
        elif verdict == 'blank':
            st.markdown("⚪ **Readiness Outcome: Blank** (gating items not yet assessed)", help=verdict_help)

        last_updated = None
        last_auditor = None
        if prev_responses:
            ts_vals = [r['timestamp'] for r in prev_responses.values() if r['timestamp']]
            auditor_vals = [r['auditor'] for r in prev_responses.values() if r['auditor']]
            if ts_vals: last_updated = max(ts_vals)
            if auditor_vals: last_auditor = auditor_vals[-1]

        if last_updated:
            st.caption(f"Last updated: {last_updated} by {last_auditor}")
        else:
            st.caption("No submissions yet")

        with st.expander("🕘 Change History", expanded=False):
            history = get_audit_response_history(selected_code, limit=20)
            if not history:
                st.caption("No recorded changes yet.")
            else:
                field_labels = {f['id']: f['label'] for f in active_fields}
                for h in history:
                    label = field_labels.get(h['field_id'], h['field_id'])
                    st.caption(f"**{label}**: `{h['old_value']}` → `{h['new_value']}`  ·  {h['changed_by']}, {h['changed_at']}")

        st.markdown("---")

        with st.form("audit_portal_checklist_form"):
            responses_input = {}

            if not active_fields:
                st.warning("No active audit fields are defined. Contact an administrator.")
            else:
                for field in active_fields:
                    fid = field['id']
                    label = field['label']
                    ftype = field['field_type']
                    prev_val = prev_responses.get(fid, {}).get('value', None)

                    if ftype == 'boolean':
                        suggestion = readiness_prefill.get(fid)
                        if prev_val is not None:
                            def_val = str(prev_val).upper() == 'TRUE'
                        elif suggestion is not None:
                            def_val = suggestion['suggested']
                        else:
                            def_val = False
                        tooltip = f"📋 Blackboard Template: {suggestion['evidence_text']}" if suggestion is not None else "N/A"
                        responses_input[fid] = st.checkbox(label, value=def_val, help=tooltip, key=f"ap_chk_{selected_code}_{fid}")

            st.markdown("---")

            prev_module_notes = prev_responses.get('notes_to_lead', {}).get('value', '')
            module_notes_val = st.text_area(
                "Notes for Module Lead",
                value=prev_module_notes,
                placeholder="Share observations, recommendations, or next steps...",
                key=f"ap_lead_notes_{selected_code}"
            )

            prev_auditor_notes = prev_responses.get('auditor_notes', {}).get('value', '')
            auditor_notes_val = st.text_area(
                "🔒 Internal Notes",
                value=prev_auditor_notes,
                help="Not visible to module leads.",
                placeholder="Add internal context or reminders...",
                key=f"ap_auditor_notes_{selected_code}"
            )

            masquerading = is_masquerading()
            if masquerading:
                st.info("🎭 Masquerade mode is view-only — switch back to your own account to save changes.")

            # Audit status is a one-way progression: Not Started -> Draft ->
            # Submitted, and never goes backwards. There is deliberately no
            # "revert to draft" action.
            #
            # Submitting does NOT lock the audit, because it can't: modules are
            # built just-in-time all year, so a September audit is legitimately
            # out of date by January, and a spot-check flagged on an
            # already-submitted module has to be recordable. What Submitted
            # actually means is "complete enough to count" - it is the gate
            # processing.py's faculty compliance table uses to decide which
            # modules feed the pass rate. Re-saving a submitted audit revises
            # it in place and it stays Submitted; going back to Draft would
            # only mean "less complete than before", which is never what an
            # advisor editing a finished audit intends. The Change History
            # expander above is what makes those revisions accountable.
            is_submitted = audit_status == 'submitted'

            if is_submitted:
                save_draft = False
                save_submit = st.form_submit_button(
                    "✅ Update Audit", use_container_width=True, disabled=masquerading,
                    help="Saves your changes. This module stays Submitted and keeps "
                         "counting toward faculty figures; every change is recorded "
                         "in Change History.")
            else:
                col_draft, col_submit = st.columns(2)
                with col_draft:
                    save_draft = st.form_submit_button(
                        "💾 Save Draft", use_container_width=True, disabled=masquerading,
                        help="Saves your progress without marking the audit complete. "
                             "Draft audits are excluded from faculty compliance figures.")
                with col_submit:
                    save_submit = st.form_submit_button(
                        "✅ Submit Audit", use_container_width=True, disabled=masquerading,
                        help="Marks this audit complete. It starts counting toward "
                             "faculty compliance figures, and stays editable afterwards.")

            if (save_draft or save_submit) and not masquerading:
                timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                try:
                    for fid, val in responses_input.items():
                        save_audit_response(selected_code, fid, str(val), username_upper, timestamp)

                    save_audit_response(selected_code, 'notes_to_lead', module_notes_val, username_upper, timestamp)
                    save_audit_response(selected_code, 'auditor_notes', auditor_notes_val, username_upper, timestamp)

                    status = 'submitted' if save_submit else 'draft'
                    save_audit_response(selected_code, 'audit_status', status, username_upper, timestamp)
                    if save_submit:
                        action = "updated" if is_submitted else "submitted"
                    else:
                        action = "saved as draft"

                    # If this module was flagged for spot-check by the person
                    # saving it, the first save closes it out - comparing what
                    # they just answered against the suggestion frozen at the
                    # moment they flagged it. A save by someone other than the
                    # flagger (e.g. covering an absence) leaves it pending, so
                    # the agreement rate stays a measure of the flagger's own
                    # judgement, not whoever happened to save the module.
                    pending_sc = get_pending_spot_check(selected_code, CURRENT_ACADEMIC_YEAR)
                    if pending_sc and pending_sc.get('flagged_by') == username_upper:
                        agreement = compute_spot_check_agreement(
                            pending_sc.get('data_verdict_snapshot'), responses_input)
                        mark_spot_check_checked(
                            selected_code, CURRENT_ACADEMIC_YEAR, timestamp,
                            agreement['agreed'], agreement['total'],
                            notes=f"Closed via Audit Portal save on {timestamp}.")
                        logging.info(
                            "🎯 Spot-check closed for '%s' by '%s': %d/%d fields agreed with the data.",
                            selected_code, username_upper, agreement['agreed'], agreement['total'])

                    st.cache_data.clear()
                    logging.info(f"✅ Audit {action} for '{selected_code}' by '{username_upper}'.")
                    st.success(f"Audit {action}!")
                    st.rerun()
                except Exception as e:
                    logging.error(f"❌ Error saving audit for '{selected_code}': {e}")
                    st.error(f"Error saving: {e}")
