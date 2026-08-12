import streamlit as st
import pandas as pd
import datetime
import logging
from processing import (
    get_module_mapping, FACULTY_SCHOOLS, readiness_prefill_for_module,
    resolve_active_row, compute_spot_check_agreement, CURRENT_ACADEMIC_YEAR,
)
from database import (
    get_active_audit_fields,
    get_audit_responses,
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
        school_context_badge = f" <span style='font-size: 16px; vertical-align: middle; background-color: rgba(59, 130, 246, 0.1); color: #3b82f6; padding: 4px 10px; border-radius: 12px; margin-left: 12px; border: 1px solid rgba(59, 130, 246, 0.2);'>Context: {st.session_state.saved_school}</span>"
        st.markdown(f"### VLE Audit Portal{school_context_badge}", unsafe_allow_html=True)
        combined_options = [opt for opt in combined_options if opt.startswith(st.session_state.saved_school)]
    else:
        st.markdown("### VLE Audit Portal")
        # Optional multi-tenant school filter to focus without siloing
        if st.session_state.saved_school != "All":
            filter_by_school = st.checkbox(f"Focus on my school ({st.session_state.saved_school})", value=True, key="ap_focus_school")
            if filter_by_school:
                combined_options = [opt for opt in combined_options if opt.startswith(st.session_state.saved_school)]
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

        col1, col2 = st.columns([2, 1])
        with col1:
            if url:
                st.markdown(f"🔗 [Open in Blackboard]({url})")
            else:
                st.caption("⚠️ VLE link not found")
        with col2:
            st.markdown(f"**Status:** {sa_status}", help="")

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

            col_draft, col_submit, col_revert = st.columns(3)
            with col_draft:
                save_draft = st.form_submit_button("💾 Save Draft", use_container_width=True, disabled=masquerading)
            with col_submit:
                save_submit = st.form_submit_button("✅ Submit Audit", use_container_width=True, disabled=masquerading)
            with col_revert:
                # Only enabled once Submitted - reverts audit_status alone,
                # without re-saving the checklist answers above (unlike Save
                # Draft/Submit Audit, which always save the whole form). A
                # dedicated, clearly-labelled action rather than relying on
                # advisors to know Save Draft can also move status backward.
                revert_draft = st.form_submit_button(
                    "↩️ Revert to Draft", use_container_width=True,
                    disabled=masquerading or audit_status != 'submitted',
                    help="Sets this module back to Draft without changing any answers."
                         if audit_status == 'submitted'
                         else "Only available once a module has been Submitted.")

            if (save_draft or save_submit or revert_draft) and not masquerading:
                timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                try:
                    if revert_draft:
                        save_audit_response(selected_code, 'audit_status', 'draft', username_upper, timestamp)
                        action = "reverted to draft"
                    else:
                        for fid, val in responses_input.items():
                            save_audit_response(selected_code, fid, str(val), username_upper, timestamp)

                        save_audit_response(selected_code, 'notes_to_lead', module_notes_val, username_upper, timestamp)
                        save_audit_response(selected_code, 'auditor_notes', auditor_notes_val, username_upper, timestamp)

                        status = 'submitted' if save_submit else 'draft'
                        save_audit_response(selected_code, 'audit_status', status, username_upper, timestamp)
                        action = "submitted" if save_submit else "saved as draft"

                        # If this module was flagged for spot-check by the person
                        # saving it, the first save closes it out - comparing what
                        # they just answered against the suggestion frozen at the
                        # moment they flagged it. A save by someone other than the
                        # flagger (e.g. covering an absence) leaves it pending, so
                        # the agreement rate stays a measure of the flagger's own
                        # judgement, not whoever happened to save the module.
                        # Reverting to draft doesn't count as this kind of save,
                        # so it deliberately skips this block.
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
