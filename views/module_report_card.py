import streamlit as st
from processing import get_module_mapping

def view_module_report_card(df_aut, df_spr, checklist_sums):
    st.title("📋 Module Report Card")
    
    module_mapping = get_module_mapping(df_aut, df_spr)
    combined_options = sorted([f"{code} - {name}" for code, name in module_mapping.items()])
    
    schools_list = ["ALA", "ECN", "EDC", "GPL", "IJC", "MGT", "SPR"]
    
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
        st.header(f"Report Card: {selected_code}")
        st.subheader(module_mapping.get(selected_code, "Unknown Module"))
        
        # Integration: Add Self-Audit summary
        if selected_code in checklist_sums:
            sum_entry = checklist_sums[selected_code]
            with st.expander(f"Latest Self-Audit Status: {sum_entry.get('Status', 'Yes')}", expanded=True):
                c1, c2, c3, c4 = st.columns(4)
                c1.write(f"**Welcome:** {'✅' if sum_entry['Q1'] else '❌'}")
                c2.write(f"**Staff:** {'✅' if sum_entry['Q2'] else '❌'}")
                c3.write(f"**Outline:** {'✅' if sum_entry['Q3'] else '❌'}")
                c4.write(f"**Assessment:** {'✅' if sum_entry['Q4'] else '❌'}")
                st.write(f"**Comments:** {sum_entry['Comments']}")
                st.caption(f"Last updated: {sum_entry['Timestamp']}")
        else:
            with st.expander("Latest Self-Audit Status: ❌ Incomplete", expanded=True):
                c1, c2, c3, c4 = st.columns(4)
                c1.write("**Welcome:** ❌")
                c2.write("**Staff:** ❌")
                c3.write("**Outline:** ❌")
                c4.write("**Assessment:** ❌")
                st.write("**Comments:** No self-audit submitted yet.")
                st.caption("Last updated: Never")
        
        # Integration: Add Leganto status warning
        aut_m, spr_m = df_aut[df_aut['New module code'] == selected_code], df_spr[df_spr['New module code'] == selected_code]
        
        # Check if missing in either semester record
        leganto_missing = False
        if not aut_m.empty and 'Leganto Missing' in aut_m.columns:
            if aut_m.iloc[0]['Leganto Missing'] is True:
                leganto_missing = True
        if not spr_m.empty and 'Leganto Missing' in spr_m.columns:
            if spr_m.iloc[0]['Leganto Missing'] is True:
                leganto_missing = True
                
        if leganto_missing:
            st.error("⚠️ **Action Required**: This module is currently flagged as **missing a reading list** in Leganto.")
        
        if not aut_m.empty or not spr_m.empty:
            col1, col2 = st.columns(2)
            with col1:
                st.subheader("🍂 Autumn Audit")
                if not aut_m.empty:
                    st.json(aut_m.iloc[0].to_dict())
                else:
                    st.write("No Autumn data.")
            with col2:
                st.subheader("🌱 Spring Audit")
                if not spr_m.empty:
                    st.json(spr_m.iloc[0].to_dict())
                else:
                    st.write("No Spring data.")
        else:
            st.warning("Module code not found.")
