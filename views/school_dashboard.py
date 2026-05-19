import streamlit as st
import pandas as pd
from processing import calculate_compliance_gap, is_compliant_val

def view_school_dashboard(df_aut, df_spr, checklist_sums, df_assess=None):
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
            
            # Prepare SITS assessment data for the school
            matching_assess = pd.DataFrame()
            type_counts = pd.DataFrame()
            if df_assess is not None and not df_assess.empty:
                school_codes = set(school_df['New module code'].dropna().astype(str).str.strip().str.upper())
                matching_assess = df_assess[df_assess['CIS unit code'].isin(school_codes)]
                if not matching_assess.empty:
                    type_counts = matching_assess['Assessment type'].value_counts().reset_index()
                    type_counts.columns = ['Assessment Type', 'Count']

            st.divider()
            
            # Segmented view navigation control
            view_options = ["📋 All Modules", "📊 Ally Analytics", "✅ Compliance Gap", "⚠️ Priority Action List", "📝 Assessment Types"]
            selected_view = st.segmented_control(
                "Navigate School View:", 
                options=view_options, 
                default=view_options[0], 
                key="school_nav_segmented_control",
                label_visibility="collapsed"
            )
            st.divider()
            
            if selected_view == "📋 All Modules":
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

            elif selected_view == "📊 Ally Analytics":
                st.subheader(f"Ally Score Distribution ({semester})")
                if not school_df.empty and 'Ally 25/26 All' in school_df.columns:
                    scores_series = school_df['Ally 25/26 All'].dropna()
                    if not scores_series.empty:
                        bins = [i/10.0 for i in range(11)]
                        labels = [f"{i*10}-{(i+1)*10}%" for i in range(10)]
                        
                        binned = pd.cut(scores_series, bins=bins, labels=labels, include_lowest=True)
                        dist_df = binned.value_counts().sort_index().reset_index()
                        dist_df.columns = ['Score Bracket', 'Module Count']
                        
                        st.caption("Frequency distribution of overall accessibility scores for this school.")
                        st.bar_chart(dist_df, x='Score Bracket', y='Module Count')
                        
                        # Drill Down Section
                        with st.expander("🔍 Inspect Modules in Specific Bracket"):
                            drill_options = ["Choose a bracket..."] + list(reversed(labels))
                            selected_bracket = st.selectbox("Filter list by score range:", drill_options, key="school_hist_drill_down")
                            
                            if selected_bracket != "Choose a bracket...":
                                drill_source = school_df[school_df['Ally 25/26 All'].notna()].copy()
                                drill_source['Bracket'] = pd.cut(drill_source['Ally 25/26 All'], bins=bins, labels=labels, include_lowest=True)
                                
                                bracket_matches = drill_source[drill_source['Bracket'] == selected_bracket]
                                
                                if not bracket_matches.empty:
                                    st.success(f"Found {len(bracket_matches)} modules in the {selected_bracket} range.")
                                    display_df = bracket_matches.copy()
                                    display_df['Score'] = display_df['Ally 25/26 All'].apply(lambda x: f"{x:.1%}")
                                    
                                    cols = ['New module code', 'Module name', 'Mod. lead', 'Score']
                                    existing_cols = [c for c in cols if c in display_df.columns]
                                    
                                    safe_display_df = display_df[existing_cols].sort_values('Score', ascending=False).reset_index(drop=True)
                                    
                                    selection_drill = st.dataframe(
                                        safe_display_df,
                                        width="stretch",
                                        hide_index=True,
                                        on_select="rerun",
                                        selection_mode="single-row",
                                        key="school_analytics_drill_dataframe"
                                    )
                                    
                                    if selection_drill.selection.rows:
                                        row_idx = selection_drill.selection.rows[0]
                                        clicked_code = safe_display_df.iloc[row_idx]['New module code']
                                        st.success(f"🔍 Selected Module: **{clicked_code}**")
                                        
                                        c1, c2 = st.columns(2)
                                        with c1:
                                            if st.button(f"📊 Jump to Report Card", width="stretch", type="primary", key="school_btn_drill_rc_jump"):
                                                st.session_state.selected_module_code = clicked_code
                                                st.session_state.view_selection = "📋 Module Report Card"
                                                st.rerun()
                                        with c2:
                                            if st.button(f"✅ Open Lead Checklist", width="stretch", key="school_btn_drill_cl_jump"):
                                                st.session_state.selected_module_code = clicked_code
                                                st.session_state.view_selection = "✅ Module Lead Checklist"
                                                st.rerun()
                                else:
                                    st.info(f"No modules found in the {selected_bracket} range.")
                    else:
                        st.warning("No numerical Ally scores found to distribute.")
                else:
                    st.warning("No data found for this school.")

            elif selected_view == "✅ Compliance Gap":
                st.subheader(f"Compliance Gap Analysis ({semester})")
                st.caption("Shows the percentage of modules fully meeting audit criteria across key structural areas.")
                gaps = calculate_compliance_gap(school_df)
                if gaps:
                    gap_df = pd.DataFrame(list(gaps.items()), columns=['Category', 'Compliance %'])
                    gap_df['Compliance %'] = gap_df['Compliance %'] * 100
                    
                    import altair as alt
                    chart_base = alt.Chart(gap_df).encode(
                        y=alt.Y('Category:N', 
                                sort='x', 
                                title=None,
                                axis=alt.Axis(labelLimit=500, labelFontSize=12)),
                        x=alt.X('Compliance %:Q', 
                                scale=alt.Scale(domain=[0, 100]), 
                                title="Percentage Compliant"),
                        tooltip=['Category', alt.Tooltip('Compliance %', format='.1f')]
                    )
                    
                    bars = chart_base.mark_bar(cornerRadiusEnd=5, height=28).encode(
                        color=alt.Color('Compliance %:Q', 
                                       scale=alt.Scale(scheme='redyellowgreen'), 
                                       legend=None)
                    )
                    
                    text_overlay = chart_base.mark_text(
                        align='left',
                        baseline='middle',
                        dx=6,
                        fontWeight='bold'
                    ).encode(
                        text=alt.Text('Compliance %:Q', format='.1f')
                    )
                    
                    final_chart = (bars + text_overlay).properties(
                        height=450
                    ).configure_view(
                        strokeWidth=0
                    )
                    
                    st.altair_chart(final_chart, use_container_width=True)
                else:
                    st.write("No compliance data available.")

            elif selected_view == "⚠️ Priority Action List":
                st.subheader("🎯 Focus Priority Lenses")
                st.caption("Pivoting on different risk vectors across the school.")
                
                lens = st.radio(
                    "Choose inspection criteria:",
                    ["⚠️ Low Accessibility (<70%)", "🔍 Critical Compliance Gaps", "📋 Missing Self-Audits", "📚 Missing Reading Lists"],
                    horizontal=True,
                    label_visibility="collapsed",
                    key="school_priority_lens_selector"
                )
                st.divider()

                render_df = None
                render_configs = {}
                render_status = None
                render_status_type = "info" 
                
                source_data = school_df.copy()
                
                if lens == "⚠️ Low Accessibility (<70%)":
                    filtered_df = source_data[source_data['Ally 25/26 All'] < 0.7].sort_values('Ally 25/26 All')
                    if not filtered_df.empty:
                        render_status = f"🎯 Found {len(filtered_df)} modules requiring Accessibility remediation (<70%)."
                        render_status_type = "warning"
                        filtered_df['DisplayValue'] = filtered_df['Ally 25/26 All'].apply(lambda x: f"{x:.1%}" if pd.notna(x) else "")
                        display_cols = ['New module code', 'Module name', 'Mod. lead', 'DisplayValue']
                        render_df = filtered_df[display_cols].copy()
                        render_configs = {
                            "New module code": "Code", "Module name": "Module Name",
                            "Mod. lead": "Lead", "DisplayValue": st.column_config.TextColumn("Overall Score")
                        }
                    else:
                        render_status = "No modules below the 70% Ally threshold!"
                        render_status_type = "success"

                elif lens == "🔍 Critical Compliance Gaps":
                    audit_cols = [
                        'Welcome to your module message?', 'Key staff contacts complete?', 
                        'Module outline complete?', 'How you will be assessed visible?',
                        'Skills development (SGAs) visible?', 'Accessibility statement visible?',
                        'School handbook visible?', 'Assessment overview - present and consistent with SITS',
                        'Assessment support and guidance visible to students?',
                        'University help and study support visible to students?'
                    ]
                    present_cols = [c for c in audit_cols if c in source_data.columns]
                    
                    if not present_cols:
                        render_status = "Compliance auditing data columns could not be located."
                        render_status_type = "error"
                    else:
                        compliance_scores = source_data[present_cols].copy()
                        for c in present_cols:
                            compliance_scores[c] = compliance_scores[c].apply(is_compliant_val)
                        
                        source_data['Compliant Items'] = compliance_scores.sum(axis=1)
                        max_items = len(present_cols)
                        threshold = max_items - 2 
                        
                        gap_df = source_data[source_data['Compliant Items'] < threshold].sort_values('Compliant Items')
                        
                        if not gap_df.empty:
                            render_status = f"🎯 Displaying {len(gap_df)} modules missing multiple key structural requirements."
                            render_status_type = "warning"
                            gap_df['DisplayValue'] = gap_df['Compliant Items'].apply(lambda x: f"{int(x)} / {max_items}")
                            
                            display_cols = ['New module code', 'Module name', 'Mod. lead', 'DisplayValue']
                            render_df = gap_df[display_cols].copy()
                            render_configs = {
                                "New module code": "Code", "Module name": "Module Name",
                                "Mod. lead": "Lead", "DisplayValue": "Compliance Count"
                            }
                        else:
                            render_status = "All modules meet healthy baseline structural thresholds!"
                            render_status_type = "success"

                elif lens == "📋 Missing Self-Audits":
                    def get_status(code):
                        c_str = str(code).strip()
                        return checklist_sums[c_str].get('Status', "🟡 Partial") if c_str in checklist_sums else "❌ Not Submitted"
                    
                    source_data['DisplayValue'] = source_data['New module code'].apply(get_status)
                    missing_df = source_data[source_data['DisplayValue'] != "✅ Complete"].sort_values('DisplayValue', ascending=False)
                    
                    if not missing_df.empty:
                        render_status = f"🎯 Found {len(missing_df)} modules either pending self-audit or with partial submissions."
                        render_status_type = "warning"
                        
                        display_cols = ['New module code', 'Module name', 'Mod. lead', 'DisplayValue']
                        render_df = missing_df[display_cols].copy()
                        render_configs = {
                            "New module code": "Code", "Module name": "Module Name",
                            "Mod. lead": "Lead", "DisplayValue": "Submission Status"
                        }
                    else:
                        render_status = "All currently listed modules have completed their self-audits! 🌟"
                        render_status_type = "success"

                elif lens == "📚 Missing Reading Lists":
                    if 'Leganto Missing' not in source_data.columns:
                        render_status = "Leganto configuration data not integrated yet."
                        render_status_type = "error"
                    else:
                        missing_leganto_df = source_data[source_data['Leganto Missing'] == True].copy()
                        
                        if not missing_leganto_df.empty:
                            render_status = f"🎯 Found {len(missing_leganto_df)} modules explicitly flagged as missing a Leganto list."
                            render_status_type = "warning"
                            
                            missing_leganto_df['DisplayValue'] = "Missing"
                            display_cols = ['New module code', 'Module name', 'Mod. lead', 'DisplayValue']
                            render_df = missing_leganto_df[display_cols].copy()
                            render_configs = {
                                "New module code": "Code", "Module name": "Module Name",
                                "Mod. lead": "Lead", "DisplayValue": "Status"
                            }
                        else:
                            render_status = "Zero modules are flagged as missing Leganto reading lists in the current view! 🎉"
                            render_status_type = "success"
                
                if render_status:
                    if render_status_type == "success": st.success(render_status)
                    elif render_status_type == "error": st.error(render_status)
                    else: st.warning(render_status)
                
                if render_df is not None:
                    clean_render_df = render_df.reset_index(drop=True)
                    
                    selection_priority = st.dataframe(
                        clean_render_df, 
                        column_config=render_configs, 
                        width="stretch", 
                        hide_index=True,
                        key="school_priority_lens_dataframe",
                        on_select="rerun",
                        selection_mode="single-row"
                    )
                    
                    if selection_priority.selection.rows:
                        row_idx = selection_priority.selection.rows[0]
                        clicked_code = clean_render_df.iloc[row_idx]['New module code']
                        
                        st.divider()
                        st.info(f"🚀 Launch Control: **{clicked_code}**")
                        
                        c1, c2 = st.columns(2)
                        with c1:
                            if st.button(f"📊 Jump to Module Report Card", width="stretch", type="primary", key="school_priority_btn_rc"):
                                st.session_state.selected_module_code = clicked_code
                                st.session_state.view_selection = "📋 Module Report Card"
                                st.rerun()
                        with c2:
                             if st.button(f"✅ Jump to Lead Checklist", width="stretch", key="school_priority_btn_cl"):
                                st.session_state.selected_module_code = clicked_code
                                st.session_state.view_selection = "✅ Module Lead Checklist"
                                st.rerun()
                        st.divider()

            elif selected_view == "📝 Assessment Types":
                c_left, c_right = st.columns([1, 1])
                with c_left:
                    st.subheader("Assessment Type Distribution")
                    if not type_counts.empty:
                        import altair as alt
                        pie_chart = alt.Chart(type_counts).mark_arc(innerRadius=50).encode(
                            theta=alt.Theta(field="Count", type="quantitative"),
                            color=alt.Color(field="Assessment Type", type="nominal", legend=alt.Legend(title="Type")),
                            tooltip=["Assessment Type", "Count"]
                        ).properties(
                            height=250
                        )
                        st.altair_chart(pie_chart, use_container_width=True)
                    else:
                        st.info("No SITS assessment records found for this school.")
                with c_right:
                    st.subheader("Assessment Strategy Metrics")
                    if not matching_assess.empty:
                        total_components = len(matching_assess)
                        modules_with_assess = matching_assess['CIS unit code'].nunique()
                        avg_components = total_components / modules_with_assess if modules_with_assess > 0 else 0
                        
                        exam_count = matching_assess[matching_assess['Assessment type'].str.contains('Exam', case=False, na=False)].shape[0]
                        exam_pct = exam_count / total_components if total_components > 0 else 0
                        
                        st.write(f"**Total SITS Assessment Components:** `{total_components}`")
                        st.write(f"**Modules with SITS Records:** `{modules_with_assess}` / `{len(school_df)}`")
                        st.write(f"**Average Components per Module:** `{avg_components:.1f}`")
                        st.write(f"**Exams / Centrally Scheduled:** `{exam_count}` (`{exam_pct:.1%}` of all components)")
                        
                        if not type_counts.empty:
                            most_common = type_counts.iloc[0]['Assessment Type']
                            most_common_count = type_counts.iloc[0]['Count']
                            st.write(f"**Most Common Type:** `{most_common}` (`{most_common_count}` times)")
                    else:
                        st.info("No metrics available.")

            st.divider()
            csv_school = school_df.to_csv(index=False).encode('utf-8')
            st.download_button(f"📥 Export {school} {semester} Data", csv_school, f"{school}_{semester}_audit.csv", "text/csv")
        else:
            st.warning(f"No modules found for {school} in {semester}.")
    else:
        st.error(f"Data for {semester} is not available.")
