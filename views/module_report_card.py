import streamlit as st
import pandas as pd
from processing import get_module_mapping

def view_module_report_card(df_aut, df_spr, checklist_sums, df_assess=None):
    st.title("📋 Module Report Card")
    
    module_mapping = get_module_mapping(df_aut, df_spr)
    combined_options = sorted([f"{code} - {name}" for code, name in module_mapping.items()])
    
    schools_list = ["ALA", "ECN", "EDC", "GPL", "IJC", "MGT", "SPR"]
    
    user_caps = st.session_state.get("capabilities", [])
    only_own_school = any(c.lower() == "view only own school" for c in user_caps)
    
    if only_own_school:
        st.info(f"Locked to school context: **{st.session_state.saved_school}**")
        combined_options = [opt for opt in combined_options if opt.startswith(st.session_state.saved_school)]
    else:
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
        
        st.header(f"Report Card: {selected_code}")
        st.subheader(module_mapping.get(selected_code, "Unknown Module"))
        
        # 1. Overview Metadata Header Card
        if active_row is not None:
            mod_lead = active_row.get('Mod. lead', 'Unknown Lead')
            prog_lead = active_row.get('Prog. lead', 'Unknown Lead')
            ug_pg = active_row.get('UG/ PG/ Other', 'UG')
            url = active_row.get('URL', '')
            
            with st.container(border=True):
                c1, c2, c3, c4 = st.columns(4)
                with c1:
                    st.markdown(f"**👤 Module Lead:**  \n{mod_lead}")
                with c2:
                    st.markdown(f"**🎓 Programme Lead:**  \n{prog_lead}")
                with c3:
                    st.markdown(f"**📚 Level:**  \n{ug_pg}")
                with c4:
                    if url:
                        st.markdown(f"**🔗 VLE Link:**  \n[Open Module Site 🌐]({url})")
                    else:
                        st.markdown("**🔗 VLE Link:**  \n*No URL configured*")
        
        # Check Leganto status
        leganto_missing = False
        if not aut_m.empty and 'Leganto Missing' in aut_m.columns:
            if aut_m.iloc[0]['Leganto Missing'] is True:
                leganto_missing = True
        if not spr_m.empty and 'Leganto Missing' in spr_m.columns:
            if spr_m.iloc[0]['Leganto Missing'] is True:
                leganto_missing = True
                
        # 2. Row of KPI metrics
        st.markdown(" ")
        col_m1, col_m2, col_m3, col_m4 = st.columns(4)
        ally_score = None
        ally_files = 0
        
        if active_row is not None:
            ally_score = active_row.get('Ally 25/26 All', None)
            if pd.isna(ally_score):
                ally_score = active_row.get('Ally Weighted', None)
            if pd.isna(ally_score):
                ally_score = active_row.get('Ally Measured', None)
                
            ally_files = active_row.get('Total Files', 0)
            if pd.isna(ally_files) or ally_files == 0:
                ally_files = active_row.get('Ally 25/26 Files', 0)
                
        with col_m1:
            if pd.notna(ally_score):
                st.metric("VLE Ally Score", f"{float(ally_score):.1%}")
            else:
                st.metric("VLE Ally Score", "N/A")
                
        with col_m2:
            st.metric("Total Files Uploaded", f"{int(ally_files) if pd.notna(ally_files) else 0}")
            
        with col_m3:
            leg_status = "❌ Missing List" if leganto_missing else "✅ OK / Connected"
            st.metric("Leganto Reading List", leg_status)
            
        with col_m4:
            sa_status = checklist_sums.get(selected_code, {}).get('Status', "❌ No Submission")
            st.metric("Self-Audit Status", sa_status)
            
        if leganto_missing:
            st.error("⚠️ **Action Required**: This module is currently flagged as **missing a reading list** in Leganto.")
            
        st.markdown("---")
        
        # 3. Integration: Add Self-Audit summary
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
        
        # 4. Integration: SITS Assessment Strategy
        if df_assess is not None and not df_assess.empty and 'CIS unit code' in df_assess.columns:
            module_assess = df_assess[df_assess['CIS unit code'] == selected_code]
            if not module_assess.empty:
                with st.expander("📝 SITS Assessment Strategy", expanded=True):
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
                                st.markdown(f"#### **{title}**")
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
            else:
                with st.expander("📝 SITS Assessment Strategy", expanded=False):
                    st.info("No SITS assessment strategy records found for this module.")
                    
        # 5. Redesigned Auditor VLE Checklists (Autumn vs Spring Tabs)
        st.markdown("### 📋 Auditor VLE Reviews")
        if not aut_m.empty or not spr_m.empty:
            tab1, tab2 = st.tabs(["🍂 Autumn Audit Details", "🌱 Spring Audit Details"])
            
            checklist_items = [
                ("Welcome to your module message?", "Welcome Message"),
                ("Key staff contacts complete?", "Staff Contacts"),
                ("Module outline complete?", "Module Outline"),
                ("How you will be assessed visible?", "Assessment Docs Visible"),
                ("Assessment overview - present and consistent with SITS", "SITS Assessment Alignment"),
                ("Assessment support and guidance visible to students?", "Assessment Support"),
                ("Accessibility statement visible?", "Accessibility Statement"),
                ("School handbook visible?", "School Handbook"),
                ("Learning materials structure in place", "Learning Materials Structure"),
                ("University help and study support visible to students?", "Study Support"),
                ("Student voice visible and convenor's report added", "Student Voice"),
                ("Skills development (SGAs) visible?", "Skills Development"),
                ("All course material is organised into folders within 'Learning Materials'", "Organised in Folders"),
                ("All course material is provided in an accessible electronic format", "Accessible Formats"),
            ]
            
            def format_audit_value(val):
                if pd.isna(val) or str(val).strip() == "":
                    return "⚪ *Not Audited*"
                val_str = str(val).strip()
                from processing import is_compliant_val
                if is_compliant_val(val):
                    return f"✅ {val_str}"
                else:
                    return f"❌ {val_str}"
                    
            def render_audit_details(df):
                if df.empty:
                    st.info("No audit record found for this semester.")
                    return
                
                row = df.iloc[0]
                
                col_a, col_b = st.columns(2)
                half = len(checklist_items) // 2
                
                with col_a:
                    for col_key, label in checklist_items[:half]:
                        val = row.get(col_key, None)
                        st.markdown(f"**{label}:** {format_audit_value(val)}")
                        
                with col_b:
                    for col_key, label in checklist_items[half:]:
                        val = row.get(col_key, None)
                        st.markdown(f"**{label}:** {format_audit_value(val)}")
                        
                # Display comments or improvements
                comments = row.get('Comments', None)
                if pd.isna(comments) or str(comments).strip() == "":
                    comments = row.get('Comments / improvements needed', None)
                    
                if pd.notna(comments) and str(comments).strip() != "":
                    st.markdown(" ")
                    st.info(f"💬 **Auditor Comments:**  \n{str(comments).strip()}")
            
            with tab1:
                render_audit_details(aut_m)
            with tab2:
                render_audit_details(spr_m)
        else:
            st.warning("No audit records found for this module code.")
