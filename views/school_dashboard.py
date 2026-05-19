import streamlit as st
import pandas as pd

def view_school_dashboard(df_aut, df_spr, checklist_sums):
    st.title("🏫 School Dashboard")
    
    schools = sorted(list(set([s.split(' ')[0] for s in ["ALA", "ECN", "EDC", "GPL", "IJC", "MGT", "SPR"]])))
    
    # If saved_school is not "All", show the focus checkbox. If unchecked, let them select another school context.
    if st.session_state.saved_school != "All":
        filter_by_school = st.checkbox(
            f"Focus on my school ({st.session_state.saved_school})", 
            value=True, 
            key="sd_focus_school",
            help="Uncheck to toggle or view other schools."
        )
        if filter_by_school:
            school = st.session_state.saved_school
        else:
            school = st.selectbox(
                "Select School to View", 
                schools, 
                index=schools.index(st.session_state.saved_school) if st.session_state.saved_school in schools else 0,
                key="sd_school_select",
                help="Select a specific school to view its dashboard."
            )
    else:
        # Fallback for "All Schools" users (e.g. FACULTY)
        school = st.selectbox(
            "Select School to View", 
            schools, 
            key="sd_school_select_all",
            help="Please select a specific school to view its dashboard."
        )
        
    semester = st.session_state.semester
    st.header(f"{school} - {semester} Semester")
    
    target_df = df_aut if semester == "Autumn" else df_spr
    
    if not target_df.empty:
        school_df = target_df[target_df['New module code'].str.startswith(school, na=False)].copy()
        
        if not school_df.empty:
            # Integration: Add self-audit status
            def get_audit_status(code):
                if code in checklist_sums:
                    return checklist_sums[code]['Status']
                return "❌ No"
            
            school_df['Self-Audited?'] = school_df['New module code'].apply(get_audit_status)
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total Modules", len(school_df))
            with col2:
                avg_ally = school_df['Ally 25/26 All'].mean() if 'Ally 25/26 All' in school_df.columns else 0
                st.metric("Avg Ally Score", f"{avg_ally:.1%}")
            with col3:
                audited_count = school_df['Self-Audited?'].apply(lambda x: x != "❌ No").sum()
                st.metric("Self-Audit Participation", f"{(audited_count / len(school_df)):.1%}")
            
            st.divider()
            st.subheader("Module Audit Status")
            display_df = school_df.copy()
            cols = ['New module code', 'Module name', 'Mod. lead']
            configs = {
                "New module code": "Module Code",
                "Module name": "Module Name",
                "Mod. lead": "Lead"
            }
            if 'Total Files' in display_df.columns:
                cols.append('Total Files')
                configs['Total Files'] = st.column_config.NumberColumn("Files", format="%d")
            if 'Ally Measured' in display_df.columns:
                display_df['Measured'] = display_df['Ally Measured'].apply(lambda x: f"{x:.1%}" if pd.notna(x) else "")
                cols.append('Measured')
                configs['Measured'] = "Measured"
            if 'Ally 25/26 All' in display_df.columns:
                display_df['Weighted'] = display_df['Ally 25/26 All'].apply(lambda x: f"{x:.1%}" if pd.notna(x) else "")
                cols.append('Weighted')
                configs['Weighted'] = "Weighted"
            if 'Ally Shift' in display_df.columns:
                display_df['Shift (Δ)'] = display_df['Ally Shift'].apply(lambda x: f"{x:+.1%}" if pd.notna(x) else "")
                cols.append('Shift (Δ)')
                configs['Shift (Δ)'] = "Shift (Δ)"
            cols.append('Self-Audited?')
            configs['Self-Audited?'] = "Audited?"
            
            if 'Leganto Missing' in display_df.columns:
                display_df['Leganto'] = display_df['Leganto Missing'].apply(lambda x: "❌ No List" if x is True else "✅ OK")
                cols.append('Leganto')
                configs['Leganto'] = "Leganto Status"
            
            clean_display_df = display_df[cols].reset_index(drop=True)
            
            selection = st.dataframe(
                clean_display_df, 
                column_config=configs, 
                width="stretch",
                hide_index=True,
                on_select="rerun",
                selection_mode="single-row",
                key="school_dashboard_dataframe"
            )
            
            # ACTION CENTER ROUTER
            if selection.selection.rows:
                row_idx = selection.selection.rows[0]
                clicked_code = clean_display_df.iloc[row_idx]['New module code']
                
                st.divider()
                st.info(f"🚀 Quick Action Launch: **{clicked_code}**")
                c1, c2 = st.columns(2)
                with c1:
                    if st.button(f"📊 Jump to Report Card", width="stretch", type="primary", key="btn_school_rc"):
                        st.session_state.selected_module_code = clicked_code
                        st.session_state.view_selection = "📋 Module Report Card"
                        st.rerun()
                with c2:
                    if st.button(f"✅ Open Lead Checklist", width="stretch", key="btn_school_cl"):
                        st.session_state.selected_module_code = clicked_code
                        st.session_state.view_selection = "✅ Module Lead Checklist"
                        st.rerun()
                st.divider()
            
            csv_school = school_df.to_csv(index=False).encode('utf-8')
            st.download_button(f"📥 Export {school} {semester} Data", csv_school, f"{school}_{semester}_audit.csv", "text/csv")
        else:
            st.warning(f"No modules found for {school} in {semester}.")
    else:
        st.error(f"Data for {semester} is not available.")
