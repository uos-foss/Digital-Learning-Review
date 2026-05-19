import streamlit as st
import os
import datetime
import logging
from processing import get_module_mapping
from data_manager import (
    initialize_checklist_headers, 
    get_latest_checklist_entry, 
    append_row_to_sheet, 
    get_all_checklist_entries
)

def view_module_lead_checklist(df_aut, df_spr, load_checklist_data_cache, df_assess=None):
    st.title("✅ Module Lead Checklist")
    st.write("Use this form to self-audit your module and submit findings.")
    
    module_mapping = get_module_mapping(df_aut, df_spr)
    combined_options = sorted([f"{code} - {name}" for code, name in module_mapping.items()])
    
    schools_list = ["ALA", "ECN", "EDC", "GPL", "IJC", "MGT", "SPR"]
    
    # Optional multi-tenant school filter to focus without siloing
    if st.session_state.saved_school != "All":
        filter_by_school = st.checkbox(f"Focus on my school ({st.session_state.saved_school})", value=True, key="cl_focus_school")
        if filter_by_school:
            combined_options = [opt for opt in combined_options if opt.startswith(st.session_state.saved_school)]
        else:
            selected_school = st.selectbox(
                "Select School to Focus", 
                ["All Schools"] + schools_list,
                index=0,
                key="cl_school_select",
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
            key="cl_school_select_all",
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

    def on_cl_module_change():
        if st.session_state.cl_unified_search:
            st.session_state.selected_module_code = st.session_state.cl_unified_search.split(" - ")[0]
        else:
            st.session_state.selected_module_code = ""

    st.selectbox(
        "Search by Module Code or Name", 
        options=[""] + combined_options, 
        index=current_idx, 
        key="cl_unified_search",
        on_change=on_cl_module_change
    )

    selected_code = st.session_state.selected_module_code
    matched_name = module_mapping.get(selected_code, "")
    
    checklist_id = os.getenv("CHECKLIST_SPREADSHEET_ID")
    initialize_checklist_headers(checklist_id, "Sheet1")
    
    latest_entry = None
    if selected_code:
        latest_entry = get_latest_checklist_entry(checklist_id, "Sheet1", selected_code)

    # Integration: SITS Assessment Strategy for reference
    if selected_code and df_assess is not None and not df_assess.empty and 'CIS unit code' in df_assess.columns:
        module_assess = df_assess[df_assess['CIS unit code'] == selected_code]
        if not module_assess.empty:
            with st.expander("📝 Reference SITS Assessment Strategy", expanded=True):
                st.caption("Verify this official assessment profile matches the assessment overview displayed on your module's VLE site:")
                cols = st.columns(min(len(module_assess), 3))
                for idx, (_, row) in enumerate(module_assess.iterrows()):
                    col = cols[idx % len(cols)]
                    with col:
                        title = row.get('Assessment title', 'Assessment')
                        weight = row.get('Assessment weighting', 'N/A')
                        atype = row.get('Assessment type', 'Other')
                        wcount = row.get('Word Count', '')
                        duration = row.get('Exam duration (per hour)', '')
                        is_final = row.get('Final assessment flag', '')
                        reassess = row.get('Reassessment', '')
                        q_mark = row.get('Qualifying mark', '')
                        
                        w_str = f"{weight}%" if str(weight).strip().isdigit() else f"{weight}"
                        
                        with st.container(border=True):
                            st.markdown(f"##### **{title}**")
                            st.markdown(f"**Weighting:** `{w_str}` | **Type:** {atype}")
                            
                            details = []
                            if wcount and str(wcount).strip():
                                details.append(f"📝 {wcount} words")
                            if duration and str(duration).strip():
                                details.append(f"⏱️ {duration} hours")
                            if is_final and str(is_final).strip().lower() == 'yes':
                                details.append("🏁 Final Component")
                            if reassess and str(reassess).strip():
                                details.append(f"🔄 Reassessment: {reassess}")
                            if q_mark and str(q_mark).strip():
                                details.append(f"⚠️ Qual. Mark: {q_mark}")
                                
                            if details:
                                st.markdown("  \n".join(details))

    with st.form("checklist_form"):
        if latest_entry:
            st.info(f"Last updated: {latest_entry[0]}. Showing your previous progress below.")
        else:
            st.info(f"Auditing: **{selected_code} - {matched_name}**" if selected_code else "Please select a module above.")
        
        st.divider()
        def_q1 = latest_entry[3] == "TRUE" if latest_entry and len(latest_entry) > 3 else False
        def_q2 = latest_entry[4] == "TRUE" if latest_entry and len(latest_entry) > 4 else False
        def_q3 = latest_entry[5] == "TRUE" if latest_entry and len(latest_entry) > 5 else False
        def_q4 = latest_entry[6] == "TRUE" if latest_entry and len(latest_entry) > 6 else False
        def_comm = latest_entry[7] if latest_entry and len(latest_entry) > 7 else ""

        q1 = st.checkbox("Welcome message present?", value=def_q1)
        q2 = st.checkbox("Key staff contacts complete?", value=def_q2)
        q3 = st.checkbox("Module outline visible?", value=def_q3)
        q4 = st.checkbox("Assessment overview consistent with SITS?", value=def_q4)
        comments = st.text_area("Additional Comments", value=def_comm)
        submitted = st.form_submit_button("Submit Update")
        
        if submitted:
            if selected_code and matched_name:
                timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                row = [timestamp, selected_code, matched_name, q1, q2, q3, q4, comments]
                try:
                    append_row_to_sheet(checklist_id, "Sheet1", row)
                    load_checklist_data_cache.clear()
                    logging.info(f"✅ Self-audit checklist submitted successfully for module '{selected_code}' by user '{st.session_state.username}'.")
                    st.success(f"Audit trail updated for {selected_code}!")
                    st.balloons()
                    st.rerun()
                except Exception as e:
                    logging.error(f"❌ Error submitting self-audit checklist for module '{selected_code}' by user '{st.session_state.username}': {e}")
                    st.error(f"Error submitting checklist: {e}")
            else:
                st.warning("Please select a Module Code and Name from the dropdowns above.")

    if selected_code:
        st.divider()
        st.subheader(f"📜 Version History: {selected_code}")
        history_df = get_all_checklist_entries(checklist_id, "Sheet1", selected_code)
        if not history_df.empty:
            st.write("Below are all previous updates for this module.")
            st.dataframe(history_df.drop(columns=['Module Code', 'Module Name']), width='stretch')
        else:
            st.info("No previous history found for this module.")
