import streamlit as st
import pandas as pd
import altair as alt
from processing import aggregate_faculty_stats, calculate_compliance_gap, is_compliant_val

def view_faculty_overview(df_aut, df_spr, checklist_sums):
    st.title("🏛️ Faculty Overview")
    
    # Determine active data based on chosen semester
    semester = st.session_state.get('semester', 'Autumn')
    active_df = df_spr if semester == "Spring" else df_aut
    
    stats = aggregate_faculty_stats(df_aut, df_spr)
    
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("Autumn Modules", stats.get('Autumn Module Count', 0))
    with col2:
        st.metric("Autumn Avg Ally", f"{stats.get('Autumn Avg Ally', 0):.1%}")
    with col3:
        st.metric("Spring Modules", stats.get('Spring Module Count', 0))
    with col4:
        st.metric("Spring Avg Ally", f"{stats.get('Spring Avg Ally', 0):.1%}")
    with col5:
        st.metric("Self-Audits Done", len(checklist_sums))

    st.divider()
    
    # ABSOLUTE LOCKDOWN ROUTER: Uses robust native widget for 100% reliable state linkage across reloads.
    # Also enables true lazy-loading, increasing app speed by not calculating inactive views!
    view_options = ["📊 Ally Analytics", "✅ Compliance Gap", "⚠️ Priority Action List"]
    
    selected_view = st.segmented_control(
        "Navigate View:", 
        options=view_options, 
        default=view_options[0], 
        key="faculty_nav_segmented_control",
        label_visibility="collapsed"
    )
    st.divider()
    
    if selected_view == "📊 Ally Analytics":
        st.subheader(f"Ally Score Distribution ({semester})")
        if not active_df.empty and 'Ally 25/26 All' in active_df.columns:
            # Drop empty scores for accurate statistical bucketing
            scores_series = active_df['Ally 25/26 All'].dropna()
            if not scores_series.empty:
                # Create 10% bracket bins from 0.0 to 1.0
                bins = [i/10.0 for i in range(11)]
                labels = [f"{i*10}-{(i+1)*10}%" for i in range(10)]
                
                # Compute counts per bin
                binned = pd.cut(scores_series, bins=bins, labels=labels, include_lowest=True)
                dist_df = binned.value_counts().sort_index().reset_index()
                dist_df.columns = ['Score Bracket', 'Module Count']
                
                st.caption("Frequency distribution of overall accessibility scores across the active semester.")
                st.bar_chart(dist_df, x='Score Bracket', y='Module Count')
                
                # Drill Down Section
                with st.expander("🔍 Inspect Modules in Specific Bracket"):
                    # Reverse labels so high scores appear first in dropdown
                    drill_options = ["Choose a bracket..."] + list(reversed(labels))
                    selected_bracket = st.selectbox("Filter list by score range:", drill_options, key="hist_drill_down")
                    
                    if selected_bracket != "Choose a bracket...":
                        # Isolate relevant rows safely
                        drill_source = active_df[active_df['Ally 25/26 All'].notna()].copy()
                        drill_source['Bracket'] = pd.cut(drill_source['Ally 25/26 All'], bins=bins, labels=labels, include_lowest=True)
                        
                        bracket_matches = drill_source[drill_source['Bracket'] == selected_bracket]
                        
                        if not bracket_matches.empty:
                            st.success(f"Found {len(bracket_matches)} modules in the {selected_bracket} range.")
                            
                            # Format score nicely for display
                            display_df = bracket_matches.copy()
                            display_df['Score'] = display_df['Ally 25/26 All'].apply(lambda x: f"{x:.1%}")
                            
                            cols = ['New module code', 'Module name', 'Mod. lead', 'Score']
                            existing_cols = [c for c in cols if c in display_df.columns]
                            
                            # [STABILITY FIX]: Streamlit 1.50+ strictly enforces monotonic indices for Interactive Selection.
                            # Resetting guaranteed sequential indices allows active routing to ignite.
                            safe_display_df = display_df[existing_cols].sort_values('Score', ascending=False).reset_index(drop=True)
                            
                            selection_drill = st.dataframe(
                                safe_display_df,
                                width="stretch",
                                hide_index=True,
                                on_select="rerun",
                                selection_mode="single-row",
                                key="analytics_drill_dataframe"
                            )
                            
                            # Action Handler for Row Clicks
                            if selection_drill.selection.rows:
                                row_idx = selection_drill.selection.rows[0]
                                clicked_code = safe_display_df.iloc[row_idx]['New module code']
                                
                                st.success(f"🔍 Selected Module: **{clicked_code}**")
                                if st.button(f"📋 View Report Card for {clicked_code}", width="stretch"):
                                    st.session_state.selected_module_code = clicked_code
                                    st.session_state.view_selection = "📋 Module Report Card"
                                    st.rerun()
                        else:
                            st.info(f"No modules found in the {selected_bracket} range.")
            else:
                st.warning("No numerical Ally scores found to distribute.")
        else:
            st.warning(f"No data found for {semester}.")

    elif selected_view == "✅ Compliance Gap":
        st.subheader(f"Compliance Gap Analysis ({semester})")
        st.caption("Shows the percentage of modules fully meeting audit criteria across key structural areas.")
        gaps = calculate_compliance_gap(active_df)
        if gaps:
            gap_df = pd.DataFrame(list(gaps.items()), columns=['Category', 'Compliance %'])
            gap_df['Compliance %'] = gap_df['Compliance %'] * 100
            
            # Build high-fidelity interactive Altair chart
            chart_base = alt.Chart(gap_df).encode(
                y=alt.Y('Category:N', 
                        sort='x', # Sort lowest compliance to top visually
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
            
            st.altair_chart(final_chart, width="stretch")
        else:
            st.write("No compliance data available.")

    elif selected_view == "⚠️ Priority Action List":
        st.subheader("🎯 Focus Priority Lenses")
        st.caption("Pivoting on different risk vectors across the faculty.")
        
        # Static selector anchors the UI interaction
        lens = st.radio(
            "Choose inspection criteria:",
            ["⚠️ Low Accessibility (<70%)", "🔍 Critical Compliance Gaps", "📋 Missing Self-Audits", "📚 Missing Reading Lists"],
            horizontal=True,
            label_visibility="collapsed",
            key="priority_lens_selector"
        )
        st.divider()

        # Container variables for STATIC structure rendering downstream
        render_df = None
        render_configs = {}
        render_status = None
        render_status_type = "info" 
        
        if active_df.empty:
            st.warning("No data available to analyze.")
        else:
            source_data = active_df.copy()
            
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
            
            # 1. Output singular status indicator 
            if render_status:
                if render_status_type == "success": st.success(render_status)
                elif render_status_type == "error": st.error(render_status)
                else: st.warning(render_status)
            
            # 2. Output singular dataframe anchored to key
            if render_df is not None:
                # [STABILITY FIX]: Enforce 100% unique linear indices required for modern selection engine trigger
                clean_render_df = render_df.reset_index(drop=True)
                
                selection_priority = st.dataframe(
                    clean_render_df, 
                    column_config=render_configs, 
                    width="stretch", 
                    hide_index=True,
                    key="master_priority_lens_dataframe",
                    on_select="rerun",
                    selection_mode="single-row"
                )
                
                # Action Handler for Selection Jump-Link
                if selection_priority.selection.rows:
                    row_idx = selection_priority.selection.rows[0]
                    clicked_code = clean_render_df.iloc[row_idx]['New module code']
                    
                    st.divider()
                    st.info(f"🚀 Launch Control: **{clicked_code}**")
                    
                    c1, c2 = st.columns(2)
                    with c1:
                        if st.button(f"📊 Jump to Module Report Card", width="stretch", type="primary"):
                            st.session_state.selected_module_code = clicked_code
                            st.session_state.view_selection = "📋 Module Report Card"
                            st.rerun()
                    with c2:
                         if st.button(f"✅ Jump to Lead Checklist", width="stretch"):
                            st.session_state.selected_module_code = clicked_code
                            st.session_state.view_selection = "✅ Module Lead Checklist"
                            st.rerun()
                    st.divider()
                
                # 3. Output singular download statically anchored to key
                csv = render_df.to_csv(index=False).encode('utf-8')
                dl_filename = f"faculty_priority_export.csv"
                st.download_button(
                    "📥 Download List (CSV)", 
                    csv, 
                    dl_filename, 
                    "text/csv",
                    key="master_priority_lens_downloader" 
                )
