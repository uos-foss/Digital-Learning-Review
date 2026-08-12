import streamlit as st
import pandas as pd
import datetime
import logging
from processing import get_module_mapping, FACULTY_SCHOOLS, readiness_prefill_for_module
from database import (
    get_active_audit_fields,
    get_audit_responses,
    save_audit_response
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
        aut_m = df_aut[df_aut['New module code'] == selected_code] if not df_aut.empty else pd.DataFrame()
        spr_m = df_spr[df_spr['New module code'] == selected_code] if not df_spr.empty else pd.DataFrame()
        active_row = spr_m.iloc[0] if not spr_m.empty else (aut_m.iloc[0] if not aut_m.empty else None)
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
                    desc = field['description']
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
                        responses_input[fid] = st.checkbox(label, value=def_val, help=desc, key=f"ap_chk_{selected_code}_{fid}")
                        if suggestion is not None:
                            st.caption(f"📋 Blackboard Template: {suggestion['evidence_text']}")

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

            col_draft, col_submit = st.columns(2)
            with col_draft:
                save_draft = st.form_submit_button("💾 Save Draft", use_container_width=True, disabled=masquerading)
            with col_submit:
                save_submit = st.form_submit_button("✅ Submit Audit", use_container_width=True, disabled=masquerading)

            if (save_draft or save_submit) and not masquerading:
                timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                username_upper = str(st.session_state.get("username", "")).strip().upper()
                try:
                    for fid, val in responses_input.items():
                        save_audit_response(selected_code, fid, str(val), username_upper, timestamp)

                    save_audit_response(selected_code, 'notes_to_lead', module_notes_val, username_upper, timestamp)
                    save_audit_response(selected_code, 'auditor_notes', auditor_notes_val, username_upper, timestamp)

                    status = 'submitted' if save_submit else 'draft'
                    save_audit_response(selected_code, 'audit_status', status, username_upper, timestamp)

                    st.cache_data.clear()
                    action = "submitted" if save_submit else "saved as draft"
                    logging.info(f"✅ Audit {action} for '{selected_code}' by '{username_upper}'.")
                    st.success(f"Audit {action}!")
                    st.rerun()
                except Exception as e:
                    logging.error(f"❌ Error saving audit for '{selected_code}': {e}")
                    st.error(f"Error saving: {e}")
