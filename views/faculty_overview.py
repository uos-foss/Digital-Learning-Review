import streamlit as st
import pandas as pd
import altair as alt
from processing import (aggregate_faculty_stats, calculate_module_compliance,
                        get_school_comparison, resolve_semester_df, summarise_ai_declarations,
                        FACULTY_SCHOOLS)
from database import get_all_audit_responses, get_active_audit_fields, get_ai_declarations
from views.ally_widgets import (
    scoreable, render_maturity_banner, render_maturity_breakdown,
    render_issue_profile, build_accessibility_risk_list,
)

def view_faculty_overview(df_aut, df_spr, checklist_sums, df_assess=None):
    st.title("🏛️ Faculty Overview")

    # pg_audit is only added to the navigation when the user holds edit_checklist,
    # and st.switch_page raises on a page that is not registered - so the button
    # that jumps there must be hidden from everyone else, not just fail on click.
    user_caps = st.session_state.get("capabilities", [])
    can_audit = any(c.lower() == "edit_checklist" for c in user_caps)

    # Determine active data based on chosen semester
    semester = st.session_state.get('semester', 'Autumn')
    active_df = resolve_semester_df(df_aut, df_spr, semester)
    
    stats = aggregate_faculty_stats(df_aut, df_spr)
    
    def _ally_metric(value, scored, total):
        """Ally averages cover modules with content beyond their template only,
        so the count is part of the number - '92% of 41' is honest where a
        bare '92%' is not."""
        if value is None:
            return "—", f"No modules with content yet ({total} modules in scope)."
        return f"{value:.1%}", f"Across {scored} module(s) with content beyond the template."

    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("Autumn Modules", stats.get('Autumn Module Count', 0))
    with col2:
        val, note = _ally_metric(stats.get('Autumn Avg Ally'),
                                 stats.get('Autumn Scored Modules', 0),
                                 stats.get('Autumn Module Count', 0))
        st.metric("Autumn Avg Ally", val, help=note)
    with col3:
        st.metric("Spring Modules", stats.get('Spring Module Count', 0))
    with col4:
        val, note = _ally_metric(stats.get('Spring Avg Ally'),
                                 stats.get('Spring Scored Modules', 0),
                                 stats.get('Spring Module Count', 0))
        st.metric("Spring Avg Ally", val, help=note)
    with col5:
        st.metric("Audits Completed", len(checklist_sums))

    st.divider()
    
    # ABSOLUTE LOCKDOWN ROUTER: Uses robust native widget for 100% reliable state linkage across reloads.
    # Also enables true lazy-loading, increasing app speed by not calculating inactive views!
    # "📝 Assessment Types" and "🤖 AI in the Curriculum" are temporarily
    # disabled - add them back to this list to restore. Their view code below
    # is untouched.
    view_options = ["🏫 School Comparison", "📊 Ally Analytics", "✅ Compliance Gap", "⚠️ Priority Action List"]
    
    selected_view = st.segmented_control(
        "Navigate View:", 
        options=view_options, 
        default=view_options[0], 
        key="faculty_nav_segmented_control",
        label_visibility="collapsed"
    )
    st.divider()
    
    if selected_view == "🏫 School Comparison":
        st.subheader(f"School Comparison ({semester})")
        st.caption(
            "VLE Compliance is measured across **submitted audits only** - read it "
            "alongside the Audited column, since a high score on a small sample is "
            "not the same as a school in good shape."
        )

        comparison_df, faculty_totals = get_school_comparison(active_df, checklist_sums)

        if comparison_df.empty:
            st.warning(f"No school data available for {semester}.")
        else:
            display_df = comparison_df.copy()
            display_df['Audited'] = display_df.apply(
                lambda r: f"{int(r['Audited'])} ({r['Audited %']:.0f}%)", axis=1
            )
            for col in ['Avg Ally', 'VLE Compliance']:
                display_df[col] = display_df[col].apply(
                    lambda x: f"{x:.1f}%" if pd.notna(x) else "—"
                )
            display_df = display_df.drop(columns=['Audited %'])

            # [STABILITY FIX]: Streamlit's selection engine requires monotonic indices.
            display_df = display_df.reset_index(drop=True)

            selection_schools = st.dataframe(
                display_df,
                column_config={
                    "School": "School",
                    "Modules": st.column_config.NumberColumn("Modules"),
                    "Audited": "Audited",
                    "Avg Ally": "Avg Ally",
                    "VLE Compliance": "VLE Compliance",
                    "Status": "Status",
                },
                width="stretch",
                hide_index=True,
                on_select="rerun",
                selection_mode="single-row",
                key="faculty_school_comparison_dataframe"
            )

            # Faculty-wide figures sit outside the table so the table stays
            # purely schools - sortable and exportable without a totals row
            # masquerading as an eighth school.
            def _fmt_pct(value):
                return f"{value:.1f}%" if value is not None and pd.notna(value) else "—"

            st.markdown("##### **Faculty Totals**")
            t1, t2, t3, t4 = st.columns(4)
            with t1:
                st.metric("Modules", faculty_totals['Modules'])
            with t2:
                st.metric("Audited", f"{faculty_totals['Audited']} ({faculty_totals['Audited %']:.0f}%)")
            with t3:
                st.metric("Avg Ally", _fmt_pct(faculty_totals['Avg Ally']))
            with t4:
                st.metric("VLE Compliance", _fmt_pct(faculty_totals['VLE Compliance']))

            # Drill-down: hand the chosen school to the School Dashboard for one render.
            if selection_schools.selection.rows:
                row_idx = selection_schools.selection.rows[0]
                clicked_school = display_df.iloc[row_idx]['School']

                st.divider()
                st.info(f"🚀 Launch Control: **{clicked_school}**")
                if st.button(f"🏫 Open {clicked_school} School Dashboard",
                             width="stretch", type="primary",
                             key="faculty_school_comparison_drilldown"):
                    st.session_state.drilldown_school = clicked_school
                    st.switch_page(st.session_state.pg_school)
                st.divider()

            csv_schools = comparison_df.to_csv(index=False).encode('utf-8')
            st.download_button(
                "📥 Download School Comparison (CSV)",
                csv_schools,
                f"faculty_school_comparison_{semester.lower()}.csv",
                "text/csv",
                key="faculty_school_comparison_downloader"
            )

    elif selected_view == "📊 Ally Analytics":
        st.subheader(f"Faculty Accessibility Profile ({semester})")
        render_maturity_banner(active_df)

        df_issues = st.session_state.get("df_ally_issues", pd.DataFrame())
        faculty_codes = set(active_df['New module code'].dropna().astype(str).str.strip().str.upper()) \
            if not active_df.empty else set()

        ally_tabs = st.tabs([
            "🔧 Issue league table", "🏗️ Build-out tracker",
            "🏫 By school", "📈 Score distribution", "🩺 Coverage",
        ])

        with ally_tabs[0]:
            st.markdown("##### The faculty's accessibility workload, largest first")
            st.caption(
                "Measured in content items affected, not modules. This is the list a "
                "faculty accessibility plan should be built from: the top few checks "
                "account for most of the work, and each has a single fix."
            )
            profile = render_issue_profile(df_issues, faculty_codes, top_n=15,
                                           key="faculty_issue_profile")
            if profile is not None and not profile.empty:
                by_surface = profile.groupby('surface')['items'].sum()
                s1, s2, s3 = st.columns(3)
                s1.metric("Fixable in the editor", f"{int(by_surface.get('editor', 0)):,}",
                          help="Module leads can clear these in Blackboard in minutes.")
                s2.metric("Fixable via Ally feedback", f"{int(by_surface.get('image', 0)):,}",
                          help="Image descriptions, answerable in the browser.")
                s3.metric("Needs the file re-authored", f"{int(by_surface.get('file', 0)):,}",
                          help="Documents must be corrected at source and re-uploaded.")

        with ally_tabs[1]:
            st.markdown("##### How much of the faculty's provision has content yet")
            render_maturity_breakdown(active_df)
            if not active_df.empty and 'Content Maturity' in active_df.columns:
                by_school = active_df.copy()
                by_school['School'] = by_school['New module code'].astype(str).str[:3]
                pivot = (by_school.pivot_table(index='School', columns='Content Maturity',
                                               values='New module code', aggfunc='count',
                                               fill_value=0))
                st.markdown("**By school**")
                st.dataframe(pivot, width="stretch")
                st.caption(
                    "Early in the year this is the faculty accessibility story. A school "
                    "whose courses are still templates in week 3 needs a conversation "
                    "about building them, not about alt text."
                )

        with ally_tabs[2]:
            st.markdown("##### Severity load by school")
            if active_df.empty:
                st.info("No data for this semester.")
            else:
                per_school = active_df.copy()
                per_school['School'] = per_school['New module code'].astype(str).str[:3]
                built_only = scoreable(per_school)
                if built_only.empty:
                    st.info("No courses with content yet, so there is no severity load to show.")
                else:
                    summary = built_only.groupby('School').agg(
                        Modules=('New module code', 'count'),
                        Students=('Ally Students', 'sum'),
                        Severe=('Ally Severe', 'sum'),
                        Major=('Ally Major', 'sum'),
                        Minor=('Ally Minor', 'sum'),
                    ).reset_index()
                    summary['Major per module'] = (summary['Major'] / summary['Modules']).round(1)
                    summary['Avg Ally'] = built_only.groupby('School')['Ally Overall'].mean().values
                    st.dataframe(
                        summary,
                        column_config={
                            'Avg Ally': st.column_config.NumberColumn("Avg Ally", format="%.1f%%"),
                            'Students': st.column_config.NumberColumn("Students", format="%d"),
                        },
                        width="stretch", hide_index=True)
                    st.bar_chart(summary, x='School', y='Major per module', height=280,
                                 color='#F59E0B')
                    st.caption("Major issues per module with content beyond its template. "
                               "This normalises for school size, so a small school with a "
                               "heavy load is still visible.")

        with ally_tabs[3]:
            st.markdown("##### Where modules with content sit on the scale")
            scores_series = pd.to_numeric(
                scoreable(active_df).get('Ally Overall'), errors='coerce').dropna() \
                if not active_df.empty else pd.Series(dtype=float)
            if scores_series.empty:
                st.info(
                    "No modules with content yet to distribute. This chart fills in as "
                    "module leads upload materials."
                )
            else:
                bins = [i / 10.0 for i in range(11)]
                labels = [f"{i*10}-{(i+1)*10}%" for i in range(10)]
                binned = pd.cut(scores_series, bins=bins, labels=labels, include_lowest=True)
                dist_df = binned.value_counts().sort_index().reset_index()
                dist_df.columns = ['Score Bracket', 'Module Count']
                st.bar_chart(dist_df, x='Score Bracket', y='Module Count')

                with st.expander("🔍 Inspect modules in a specific bracket"):
                    drill_options = ["Choose a bracket..."] + list(reversed(labels))
                    selected_bracket = st.selectbox("Filter list by score range:",
                                                    drill_options, key="fac_hist_drill_down")
                    if selected_bracket != "Choose a bracket...":
                        drill_source = scoreable(active_df).copy()
                        drill_source = drill_source[drill_source['Ally Overall'].notna()]
                        drill_source['Bracket'] = pd.cut(drill_source['Ally Overall'],
                                                         bins=bins, labels=labels,
                                                         include_lowest=True)
                        matches = drill_source[drill_source['Bracket'] == selected_bracket]
                        if matches.empty:
                            st.info(f"No modules in the {selected_bracket} range.")
                        else:
                            st.success(f"Found {len(matches)} modules in {selected_bracket}.")
                            show = matches.copy()
                            show['Score'] = show['Ally Overall'].apply(lambda x: f"{x:.1%}")
                            cols = [c for c in ['New module code', 'Module name', 'Mod. lead',
                                                'Score', 'Ally Severe', 'Ally Major']
                                    if c in show.columns]
                            safe_df = show[cols].reset_index(drop=True)
                            selection = st.dataframe(
                                safe_df, width="stretch", hide_index=True,
                                on_select="rerun", selection_mode="single-row",
                                key="faculty_ally_drill_dataframe")
                            if selection.selection.rows:
                                idx = selection.selection.rows[0]
                                clicked_code = safe_df.iloc[idx]['New module code']
                                st.success(f"🔍 Selected Module: **{clicked_code}**")
                                c1, c2 = st.columns(2)
                                with c1:
                                    if st.button("📊 Jump to Report Card", width="stretch",
                                                 type="primary", key="fac_btn_drill_rc_jump"):
                                        st.session_state.selected_module_code = clicked_code
                                        st.switch_page(st.session_state.pg_module)
                                with c2:
                                    if can_audit and st.button("✅ Open Audit Portal",
                                                               width="stretch",
                                                               key="fac_btn_drill_cl_jump"):
                                        st.session_state.selected_module_code = clicked_code
                                        st.switch_page(st.session_state.pg_audit)

        with ally_tabs[4]:
            st.markdown("##### Is the data telling us the truth?")
            df_courses = st.session_state.get("df_ally_courses", pd.DataFrame())
            if df_courses.empty:
                st.info("No Ally courses loaded. Import the institutional report from the "
                        "Admin Panel.")
            else:
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Courses tracked", f"{len(df_courses):,}")
                disabled = int((pd.to_numeric(df_courses['ally_enabled'],
                                              errors='coerce').fillna(1) == 0).sum())
                c2.metric("Ally switched off", f"{disabled:,}",
                          help="Students get no alternative formats on these courses and "
                               "the module lead sees no feedback.")
                deleted = int((df_courses['deleted_on'].astype(str).str.strip() != "").sum())
                c3.metric("Observed deleted", f"{deleted:,}")

                checked = pd.to_datetime(df_courses['last_checked_on'], errors='coerce')
                if checked.notna().any():
                    stale = int((checked.max() - checked).dt.days.gt(30).sum())
                    c4.metric("Not scanned in 30+ days", f"{stale:,}",
                              help="Ally rescans courses on its own schedule, so some rows "
                                   "in any export are months old.")
                    st.caption(
                        f"Most recent Ally scan in this data: "
                        f"{checked.max().strftime('%d-%m-%Y')}. Scores describe the course "
                        "as Ally last saw it, not as it stands right now."
                    )

    elif selected_view == "✅ Compliance Gap":
        st.subheader(f"Compliance Gap Analysis ({semester})")

        from processing import calculate_dynamic_compliance_gap
        gaps = calculate_dynamic_compliance_gap(school_code='All')
        
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
            ["⚠️ Accessibility Risk", "🔍 Critical Compliance Gaps", "📋 Missing Audits", "📚 Missing Reading Lists"],
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
            
            if lens == "⚠️ Accessibility Risk":
                render_df, render_configs, render_status, render_status_type = \
                    build_accessibility_risk_list(source_data)

            elif lens == "🔍 Critical Compliance Gaps":
                counts, max_items = calculate_module_compliance(
                    get_all_audit_responses(), get_active_audit_fields()
                )

                if max_items == 0:
                    render_status = "No scorable audit fields are configured."
                    render_status_type = "error"
                elif counts.empty:
                    render_status = "No audits submitted yet, so there are no compliance gaps to show."
                    render_status_type = "info"
                else:
                    source_data['MatchCode'] = source_data['New module code'].astype(str).str.strip().str.upper()
                    scored_df = source_data.merge(
                        counts, left_on='MatchCode', right_on='module_code', how='inner'
                    )

                    threshold = max_items - 2
                    gap_df = scored_df[scored_df['Compliant Items'] < threshold].sort_values('Compliant Items')

                    if not gap_df.empty:
                        render_status = (
                            f"🎯 Displaying {len(gap_df)} of {len(scored_df)} audited modules "
                            "missing multiple key structural requirements."
                        )
                        render_status_type = "warning"
                        gap_df['DisplayValue'] = gap_df['Compliant Items'].apply(lambda x: f"{int(x)} / {max_items}")

                        display_cols = ['New module code', 'Module name', 'Mod. lead', 'DisplayValue']
                        render_df = gap_df[display_cols].copy()
                        render_configs = {
                            "New module code": "Code", "Module name": "Module Name",
                            "Mod. lead": "Lead", "DisplayValue": "Compliance Count"
                        }
                    elif scored_df.empty:
                        render_status = "No modules in this semester have been audited yet."
                        render_status_type = "info"
                    else:
                        render_status = f"All {len(scored_df)} audited modules meet healthy baseline structural thresholds!"
                        render_status_type = "success"

            elif lens == "📋 Missing Audits":
                def get_status(code):
                    c_str = str(code).strip()
                    return checklist_sums[c_str].get('Status', "❌ Not Audited") if c_str in checklist_sums else "❌ Not Audited"
                def get_actions(code):
                    c_str = str(code).strip()
                    return checklist_sums[c_str].get('Actionable Items', 0) if c_str in checklist_sums else 0
                
                source_data['DisplayValue'] = source_data['New module code'].apply(get_status)
                source_data['Actionable Items'] = source_data['New module code'].apply(get_actions)
                
                missing_df = source_data[source_data['DisplayValue'] != "✅ Audited"].sort_values('DisplayValue', ascending=False)
                
                if not missing_df.empty:
                    render_status = f"🎯 Found {len(missing_df)} modules pending audit."
                    render_status_type = "warning"
                    
                    display_cols = ['New module code', 'Module name', 'Mod. lead', 'DisplayValue', 'Actionable Items']
                    render_df = missing_df[display_cols].copy()
                    render_configs = {
                        "New module code": "Code", "Module name": "Module Name",
                        "Mod. lead": "Lead", "DisplayValue": "Audit Status",
                        "Actionable Items": st.column_config.NumberColumn("Actionable Items")
                    }
                else:
                    render_status = "All currently listed modules have completed their audits! 🌟"
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
                            st.switch_page(st.session_state.pg_module)
                    with c2:
                        if can_audit and st.button(f"✅ Open Audit Portal", width="stretch"):
                            st.session_state.selected_module_code = clicked_code
                            st.switch_page(st.session_state.pg_audit)
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

    elif selected_view == "📝 Assessment Types":
        st.subheader(f"Assessment Analysis ({semester})")
        
        # Sub-navigation for SITS Assessment view
        sub_view = st.radio(
            "Analysis View:",
            ["🌐 Overall Distribution", "🏫 Compare Schools"],
            horizontal=True,
            label_visibility="collapsed",
            key="assessment_analysis_sub_nav"
        )
        st.write("---")
        
        if df_assess is not None and not df_assess.empty:
            # Get active codes
            active_codes = set(active_df['New module code'].dropna().astype(str).str.strip().str.upper())
            matching_assess = df_assess[df_assess['CIS unit code'].isin(active_codes)].copy()
            
            if not matching_assess.empty:
                # Add School column based on CIS unit code prefix
                schools_list = set(FACULTY_SCHOOLS)
                matching_assess['School'] = matching_assess['CIS unit code'].astype(str).str[:3].str.upper()
                matching_assess = matching_assess[matching_assess['School'].isin(schools_list)]
                
                if sub_view == "🌐 Overall Distribution":
                    st.markdown("##### **Overall Assessment Type Distribution**")
                    st.caption("Distribution of assessment types across all active modules in SITS for this semester.")
                    type_counts = matching_assess['Assessment type'].value_counts().reset_index()
                    type_counts.columns = ['Assessment Type', 'Count']
                    
                    # Render using Altair donut chart
                    pie_chart = alt.Chart(type_counts).mark_arc(innerRadius=60).encode(
                        theta=alt.Theta(field="Count", type="quantitative"),
                        color=alt.Color(field="Assessment Type", type="nominal", legend=alt.Legend(title="Assessment Type")),
                        tooltip=["Assessment Type", "Count"]
                    ).properties(
                        height=400
                    )
                    st.altair_chart(pie_chart, use_container_width=True)
                    
                    # Also display a nice summary table
                    with st.expander("Detailed Breakdown", expanded=False):
                        st.dataframe(type_counts, width="stretch", hide_index=True)
                        
                elif sub_view == "🏫 Compare Schools":
                    st.markdown("##### **Compare Assessment Types Across Schools**")
                    st.caption("Compare how different schools design their assessment strategies (exams, coursework, etc.) for active modules.")
                    
                    # Toggle for Absolute vs Normalized
                    compare_mode = st.segmented_control(
                        "Chart Type:",
                        options=["Absolute Counts", "Normalized Percentages"],
                        default="Absolute Counts",
                        key="compare_schools_chart_type"
                    )
                    
                    comparison_data = matching_assess.groupby(['School', 'Assessment type']).size().reset_index(name='Count')
                    comparison_data.columns = ['School', 'Assessment Type', 'Count']
                    
                    if compare_mode == "Absolute Counts":
                        bar_chart = alt.Chart(comparison_data).mark_bar().encode(
                            x=alt.X('School:N', title='School', axis=alt.Axis(labelAngle=0)),
                            y=alt.Y('Count:Q', title='Number of Assessment Components'),
                            color=alt.Color('Assessment Type:N', legend=alt.Legend(title="Assessment Type")),
                            tooltip=['School', 'Assessment Type', 'Count']
                        ).properties(
                            height=400
                        )
                    else:
                        bar_chart = alt.Chart(comparison_data).mark_bar().encode(
                            x=alt.X('School:N', title='School', axis=alt.Axis(labelAngle=0)),
                            y=alt.Y('Count:Q', stack='normalize', axis=alt.Axis(format='%'), title='Percentage of Assessments'),
                            color=alt.Color('Assessment Type:N', legend=alt.Legend(title="Assessment Type")),
                            tooltip=['School', 'Assessment Type', 'Count']
                        ).properties(
                            height=400
                        )
                        
                    st.altair_chart(bar_chart, use_container_width=True)
                    
                    with st.expander("School Comparison Data Table", expanded=False):
                        # Pivot table for a nice cross-tabulation display
                        crosstab = pd.crosstab(matching_assess['School'], matching_assess['Assessment type'])
                        st.dataframe(crosstab, width="stretch")
            else:
                st.info("No matching SITS assessment data found for this semester's modules.")
        else:
            st.warning("SITS Assessment data is not loaded or is empty.")

    elif selected_view == "🤖 AI in the Curriculum":
        st.subheader(f"AI in the Curriculum ({semester})")
        st.caption(
            "Declarations made by module leads in the AI in the Curriculum Audit, "
            "a separate app that shares this portal's database. Leads complete "
            "these themselves, unlike the VLE audit."
        )

        declarations = get_ai_declarations()
        active_codes = set(active_df['New module code'].dropna().astype(str).str.strip().str.upper())
        # Every module SITS knows about, so a declaration for a module that runs
        # in the other semester is not mistaken for one SITS has never heard of.
        known_codes = set()
        for frame in (df_aut, df_spr):
            if frame is not None and not frame.empty:
                known_codes |= set(frame['New module code'].dropna().astype(str).str.strip().str.upper())
        summary = summarise_ai_declarations(declarations, active_codes, known_codes)

        if declarations.empty:
            st.info(
                "No declarations have been submitted yet. They will appear here as "
                "module leads complete the AI in the Curriculum Audit."
            )
        else:
            per_module = summary['per_module']
            declared = summary['declared']
            in_scope = summary['in_scope']
            pct = (declared / in_scope * 100) if in_scope else 0.0

            col1, col2, col3 = st.columns(3)
            col1.metric("Modules Declared", f"{declared} / {in_scope}")
            col2.metric("Coverage", f"{pct:.1f}%")
            col3.metric("Assessments Covered", int(per_module['Assessments Declared'].sum()) if not per_module.empty else 0)

            st.progress(min(pct / 100, 1.0))

            if summary['other_semester']:
                st.caption(
                    f"{len(summary['other_semester'])} further module(s) have declarations "
                    f"but run in the other semester: {', '.join(summary['other_semester'])}."
                )

            if summary['unmatched']:
                st.warning(
                    f"⚠️ {len(summary['unmatched'])} module(s) have declarations but do not "
                    f"appear in SITS at all, so they are excluded from every figure here: "
                    f"{', '.join(summary['unmatched'])}. The satellite app offered a 2025/26 "
                    "module list until its v1.2.0, so these are real submissions against "
                    "modules that no longer exist — they need reconciling, not ignoring."
                )

            st.divider()
            st.markdown("##### **Coverage by School**")

            if per_module.empty:
                st.info("No declarations match modules in this semester.")
            else:
                declared_codes = set(per_module['module_code'])
                rows = []
                for school in FACULTY_SCHOOLS:
                    school_codes = {c for c in active_codes if c.startswith(school)}
                    if not school_codes:
                        continue
                    n_declared = len(school_codes & declared_codes)
                    rows.append({
                        "School": school,
                        "Modules": len(school_codes),
                        "Declared": n_declared,
                        "Coverage": f"{(n_declared / len(school_codes) * 100):.1f}%",
                        "_pct": n_declared / len(school_codes) * 100,
                    })

                if rows:
                    df_schools = pd.DataFrame(rows).sort_values("_pct", ascending=False)
                    st.dataframe(
                        df_schools[["School", "Modules", "Declared", "Coverage"]],
                        hide_index=True,
                        width="stretch",
                    )

                gen_ai_yes = int((per_module['Gen AI Activity'] == "Yes").sum())
                st.caption(
                    f"{gen_ai_yes} of {len(per_module)} declared modules report a Gen AI "
                    "engaged learning activity."
                )

                with st.expander("Declared modules", expanded=False):
                    st.dataframe(
                        per_module.rename(columns={'module_code': 'Module Code'}),
                        hide_index=True,
                        width="stretch",
                    )
