import streamlit as st
import pandas as pd
import datetime
from processing import (calculate_module_compliance, resolve_semester_df,
                        summarise_ai_declarations, FACULTY_SCHOOLS, CURRENT_ACADEMIC_YEAR,
                        resolve_active_row, build_spot_check_snapshot,
                        parse_user_schools, format_user_schools, prepare_ally_issues)
from database import (get_all_audit_responses, get_active_audit_fields, get_ai_declarations,
                      get_ally_history, flag_module_for_spot_check, delete_spot_check,
                      get_school_spot_checks, get_spot_check_agreement_summary)
from views.ally_widgets import (
    scoreable, mean_score, render_maturity_banner, render_issue_profile,
    build_accessibility_risk_list,
)

def to_sentence_case(name: str) -> str:
    """Convert name to sentence case (capitalize first letter only)."""
    if not name or pd.isna(name):
        return ""
    name_str = str(name).strip()
    if not name_str:
        return ""
    return name_str[0].upper() + name_str[1:].lower() if len(name_str) > 0 else name_str

def view_school_dashboard(df_aut, df_spr, checklist_sums, df_assess=None):
    schools = list(FACULTY_SCHOOLS)
    
    user_caps = st.session_state.get("capabilities", [])
    only_own_school = any(c.lower() == "view_school" for c in user_caps) and not any(c.lower() == "view_all" for c in user_caps)
    # pg_audit is only registered in the navigation for holders of edit_checklist,
    # and st.switch_page raises on an unregistered page - so hide the jump button
    # from everyone else rather than letting it fail on click.
    can_audit = any(c.lower() == "edit_checklist" for c in user_caps)

    # A school handed over from the Faculty School Comparison table. Consumed
    # once, then cleared, so the user's saved_school preference is untouched.
    # Seeds the selector widgets before they are built so the controls agree
    # with the data being shown.
    drilldown_school = st.session_state.pop("drilldown_school", None)
    if drilldown_school in schools and not only_own_school:
        st.session_state.sd_focus_school = False
        st.session_state.sd_school_select = drilldown_school
        st.session_state.sd_school_select_all = drilldown_school

    if only_own_school:
        user_schools = parse_user_schools(st.session_state.saved_school)
        if len(user_schools) == 1:
            school = user_schools[0]
        else:
            # A locked user aligned with more than one school still needs to
            # pick which one to view - the dashboard shows one at a time -
            # but the options are restricted to their own schools, not the
            # full faculty list.
            school = st.selectbox(
                "Select which of your schools to view",
                user_schools,
                key="sd_school_select_locked",
            )
        school_context_badge = f" <span style='font-size: 16px; vertical-align: middle; background-color: rgba(59, 130, 246, 0.1); color: #3b82f6; padding: 4px 10px; border-radius: 12px; margin-left: 12px; border: 1px solid rgba(59, 130, 246, 0.2);'>Context: {format_user_schools(user_schools)}</span>"
        st.markdown(f"<h1>School Dashboard{school_context_badge}</h1>", unsafe_allow_html=True)
    else:
        st.title("School Dashboard")
        user_schools = parse_user_schools(st.session_state.saved_school)
        # If not faculty-wide, show the focus checkbox. If unchecked, let them select another school context.
        if user_schools != ["All"]:
            label = format_user_schools(user_schools)
            filter_by_school = st.checkbox(
                f"Focus on my school{'s' if len(user_schools) > 1 else ''} ({label})",
                value=True,
                key="sd_focus_school",
                help="Uncheck to toggle or view other schools."
            )
            if filter_by_school:
                if len(user_schools) == 1:
                    school = user_schools[0]
                else:
                    school = st.selectbox(
                        "Select which of your schools to view",
                        user_schools,
                        key="sd_school_select_focus",
                    )
            else:
                school = st.selectbox(
                    "Select School to View",
                    schools,
                    index=schools.index(user_schools[0]) if user_schools[0] in schools else 0,
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
    
    target_df = resolve_semester_df(df_aut, df_spr, semester)
    
    if not target_df.empty:
        school_df = target_df[target_df['New module code'].str.startswith(school, na=False)].copy()
        
        if not school_df.empty:
            # Integration: Add actionable items count
            def get_actionable_items(code):
                if code in checklist_sums:
                    return checklist_sums[code].get('Actionable Items', 0)
                return 0

            school_df['Actionable Items'] = school_df['New module code'].apply(get_actionable_items)
            
            # Define school codes for filtering data
            school_codes = set(school_df['New module code'].dropna().astype(str).str.strip().str.upper())

            # Prepare SITS assessment data for the school
            matching_assess = pd.DataFrame()
            type_counts = pd.DataFrame()
            if df_assess is not None and not df_assess.empty:
                matching_assess = df_assess[df_assess['CIS unit code'].isin(school_codes)]
                if not matching_assess.empty:
                    type_counts = matching_assess['Assessment type'].value_counts().reset_index()
                    type_counts.columns = ['Assessment Type', 'Count']

            st.divider()
            
            # Segmented view navigation control
            view_options = ["📋 Modules Overview", "📊 Ally Analytics", "📈 Trends", "✅ Checklist Completion", "⚠️ Priority Action List", "📝 Assessment Types", "🤖 AI in the Curriculum", "🎯 Spot-Checks"]
            selected_view = st.segmented_control(
                "Navigate School View:", 
                options=view_options, 
                default=view_options[0], 
                key="school_nav_segmented_control",
                label_visibility="collapsed"
            )
            st.divider()
            
            if selected_view == "📋 Modules Overview":
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Total Modules", len(school_df),
                              help=f"Total modules for {school} in the {semester} semester.")
                with col2:
                    no_activity = len(school_df) - len(scoreable(school_df))
                    st.metric("Modules with no activity", f"{no_activity}",
                              help="Modules that still only have the default template - no "
                                   "content added yet")
                with col3:
                    avg_ally = mean_score(school_df)
                    st.metric("Avg Ally Score", f"{avg_ally:.1%}" if avg_ally is not None else "—",
                              help="Ally's overall score, averaged across modules with content "
                                   "beyond their template only.")
                with col4:
                    total_actionable = int(school_df['Actionable Items'].sum())
                    st.metric("Outstanding Actionable Items", f"{total_actionable}",
                              help="Sum of outstanding items across all modules in this semester - "
                                   "checklist, Leganto reading lists, Ally accessibility, and "
                                   "template readiness findings combined.")

                st.subheader("Module Audit Status")
                display_df = school_df.copy()
                # Default order: the underlying query has no ORDER BY, so rows
                # otherwise land in whatever order the last sync inserted them.
                display_df = display_df.sort_values('New module code').reset_index(drop=True)
                # Apply sentence case to Module Lead names
                display_df['Mod. lead'] = display_df['Mod. lead'].apply(to_sentence_case)
                cols = ['New module code', 'Module name', 'Mod. lead']
                configs = {
                    "New module code": "Module Code",
                    "Module name": "Module Name",
                    "Mod. lead": "Module Lead"
                }
                # Shown so a DLA picking modules to spot-check can see level
                # spread at a glance - there is no Programme field anywhere
                # in the data, so that part of the spread stays on the DLA's
                # own knowledge of their school.
                if 'UG/ PG/ Other' in display_df.columns:
                    cols.append('UG/ PG/ Other')
                    configs['UG/ PG/ Other'] = "Level"
                # Ally score, qualified by how far the course has been built - an
                # untouched template scores near 100% and would otherwise read as
                # the best module in the school. One column rather than two: the
                # score only means something once a module is 'In progress', so
                # everywhere else the build stage itself is the useful value, not
                # a near-100% number sitting next to it. This mixes text and
                # percentages in the same cell by design, so it sorts as text,
                # not by score - a deliberate tradeoff of combining the two.
                if 'Ally Overall' in display_df.columns or 'Content Maturity' in display_df.columns:
                    def _score_or_stage(r):
                        maturity = r.get('Content Maturity')
                        if maturity == 'In progress':
                            v = r.get('Ally Overall')
                            if pd.notna(v):
                                return f"{v * 100:.1f}%"
                        return maturity if maturity else "—"
                    display_df['Score / Stage'] = display_df.apply(_score_or_stage, axis=1)
                    cols.append('Score / Stage')
                    configs['Score / Stage'] = st.column_config.TextColumn(
                        "Score / Build Stage",
                        help="Ally's accessibility score once a module has content "
                             "beyond its template ('In progress'); otherwise the build "
                             "stage itself, since an untouched template scores near "
                             "100% and would misread as the best module in the school.")
                cols.append('Actionable Items')
                configs['Actionable Items'] = st.column_config.NumberColumn("Actionable Items")
                
                if 'Leganto Missing' in display_df.columns:
                    def _leganto_display(r):
                        if r.get('Leganto Missing') is True:
                            return "❌ No List"
                        status = r.get('Leganto List Status', '')
                        items = r.get('Leganto List Items', 0)
                        if status == 'Published':
                            return f"✅ Published ({items})"
                        if status in ('Draft', 'Mixed'):
                            return f"📝 Draft ({items})"
                        return "✅ OK"
                    display_df['Leganto'] = display_df.apply(_leganto_display, axis=1)
                    cols.append('Leganto')
                    configs['Leganto'] = "Leganto Status"

                # Template alignment, reported as the module-lead sections only.
                # The vendor completeness score restates the visible-section
                # count and sits on the same value for most of a school after a
                # rollover, so it would sort nothing.
                if 'Lead Sections Ready' in display_df.columns:
                    def _template_display(r):
                        ready = r.get('Lead Sections Ready')
                        if ready is None or pd.isna(ready):
                            return "— No data"
                        total = int(r.get('Lead Sections Total') or 0)
                        blocking = r.get('Template Blocking') or []
                        drafted = int(r.get('Lead Sections Drafted') or 0)
                        mark = "✅" if total and ready == total else "📋"
                        if len(blocking):
                            mark = "⚠️"
                        cell = f"{mark} {int(ready)} of {total}"
                        # Surfaced here because it is the cheapest win in the
                        # school: the content exists and only needs unhiding.
                        if drafted:
                            cell += f" · 👁 {drafted} to unhide"
                        return cell
                    display_df['Template'] = display_df.apply(_template_display, axis=1)
                    cols.append('Template')
                    configs['Template'] = st.column_config.TextColumn(
                        "Template Sections",
                        help="The Blackboard template sections the module lead is "
                             "responsible for, and whether they're visible to students. "
                             "👁 marks sections already worked on but still hidden — those "
                             "only need making visible. ⚠️ marks a section deleted from or "
                             "missing in the Blackboard course.")

                # Latest spot-check status per module, fetched once for the
                # whole school rather than a query per row. A module can have
                # more than one flag over time (see purge/re-flag notes in
                # CLAUDE.md); the most recent one is what's shown.
                sc_school_df = get_school_spot_checks(school, CURRENT_ACADEMIC_YEAR)
                sc_status_by_code = {}
                if not sc_school_df.empty:
                    latest = sc_school_df.sort_values('flagged_on', ascending=False) \
                                         .drop_duplicates(subset='module_code', keep='first')
                    sc_status_by_code = dict(zip(latest['module_code'], latest['status']))

                def _spot_check_display(r):
                    status = sc_status_by_code.get(r['New module code'])
                    if status == 'pending':
                        return "⏳ Pending"
                    if status == 'checked':
                        return "✅ Checked"
                    return ""
                display_df['Spot-Check'] = display_df.apply(_spot_check_display, axis=1)
                cols.append('Spot-Check')
                configs['Spot-Check'] = st.column_config.TextColumn(
                    "Spot-Check",
                    help="⏳ Pending - flagged and waiting to be audited. ✅ Checked - "
                         "the flagger has since audited it. Blank - never flagged.")

                clean_display_df = display_df[cols].reset_index(drop=True)

                st.caption("Select one or more rows (tick the checkboxes) to jump to a "
                          "module or flag it for spot-check.")
                selection = st.dataframe(
                    clean_display_df,
                    column_config=configs,
                    width="stretch",
                    hide_index=True,
                    on_select="rerun",
                    selection_mode="multi-row",
                    key="school_dashboard_dataframe"
                )

                # ACTION CENTER ROUTER
                selected_rows = [i for i in selection.selection.rows if i < len(clean_display_df)]
                if selected_rows:
                    selected_codes = clean_display_df.iloc[selected_rows]['New module code'].tolist()

                    st.divider()
                    if len(selected_codes) == 1:
                        clicked_code = selected_codes[0]
                        st.info(f"🚀 Quick Action Launch: **{clicked_code}**")
                        c1, c2, c3 = st.columns(3)
                        with c1:
                            if st.button("📊 Jump to Report Card", width="stretch", type="primary", key="btn_school_rc"):
                                st.session_state.selected_module_code = clicked_code
                                st.switch_page(st.session_state.pg_module)
                        with c2:
                            if can_audit and st.button("✅ Open Audit Portal", width="stretch", key="btn_school_cl"):
                                st.session_state.selected_module_code = clicked_code
                                st.switch_page(st.session_state.pg_audit)
                        flag_col = c3
                    else:
                        st.info(f"🚀 {len(selected_codes)} modules selected")
                        flag_col = st.container()

                    if can_audit:
                        already_pending = [c for c in selected_codes if c in sc_status_by_code
                                          and sc_status_by_code[c] == 'pending']
                        flaggable = [c for c in selected_codes if c not in already_pending]
                        with flag_col:
                            label = (f"🎯 Flag for Spot-Check" if len(selected_codes) == 1
                                    else f"🎯 Flag {len(flaggable)} for Spot-Check")
                            if not flaggable:
                                st.button("🎯 Already flagged", width="stretch",
                                         disabled=True, key="btn_school_sc_pending",
                                         help="Every selected module already has a pending spot-check.")
                            elif st.button(label, width="stretch", key="btn_school_sc"):
                                flagger = str(st.session_state.get("username", "")).strip().upper()
                                flagged_on = datetime.date.today().strftime('%Y-%m-%d')
                                for code in flaggable:
                                    active_row = resolve_active_row(code, df_aut, df_spr)
                                    actionable = checklist_sums.get(code, {}).get('Actionable Items', 0)
                                    snapshot = build_spot_check_snapshot(active_row, actionable)
                                    flag_module_for_spot_check(
                                        code, CURRENT_ACADEMIC_YEAR, flagger, flagged_on, snapshot)
                                msg = f"Flagged {len(flaggable)} module(s) for spot-check."
                                if already_pending:
                                    msg += f" {len(already_pending)} already had a pending flag and were skipped."
                                st.success(msg)
                                # spot_checks isn't part of the cached loaders above (Actionable
                                # Items etc. are unaffected by flagging), so no st.cache_data.clear()
                                # is needed here - only a rerun to refresh the status column.
                                st.rerun()
                    st.divider()

            elif selected_view == "📊 Ally Analytics":
                st.subheader(f"Accessibility Profile — {school} ({semester})")
                render_maturity_banner(school_df)
                st.caption(
                    "Counted in content items rather than modules, because that is the "
                    "size of the job. One session on exporting tagged PDFs can clear "
                    "hundreds of items at once."
                )

                df_issues = st.session_state.get("df_ally_issues", pd.DataFrame())
                scoped_issues = prepare_ally_issues(df_issues, school_codes)

                severity_options = ["Severe", "Major", "Minor", "Other"]
                fcol1, fcol2 = st.columns(2)
                with fcol1:
                    severity_filter = st.multiselect(
                        "Filter by severity", severity_options, default=severity_options,
                        key=f"ally_severity_filter_{school}")
                if not severity_filter:
                    severity_filter = severity_options
                severity_scoped = scoped_issues[scoped_issues['severity_label'].isin(severity_filter)]
                with fcol2:
                    issue_options = sorted(severity_scoped['label'].unique())
                    issue_filter = st.multiselect(
                        "Filter by issue", issue_options, default=[],
                        key=f"ally_issue_filter_{school}",
                        help="Narrows the module table to modules carrying one or more of "
                             "the selected issues. Leave blank to include every issue at "
                             "the severities chosen on the left.")

                filters_active = set(severity_filter) != set(severity_options) or bool(issue_filter)

                chart_col, table_col = st.columns([2, 3])

                with chart_col:
                    st.markdown("##### What to fix")
                    render_issue_profile(severity_scoped, school_codes, top_n=8,
                                         key=f"school_issue_profile_{school}")

                with table_col:
                    st.markdown("##### Modules")
                    if school_df.empty or 'Ally Overall' not in school_df.columns:
                        st.warning("No Ally data found for this school.")
                    else:
                        table = school_df.copy()
                        table['_code'] = table['New module code'].astype(str).str.strip().str.upper()
                        table['Mod. lead'] = table['Mod. lead'].apply(to_sentence_case)

                        if filters_active:
                            table_issues = severity_scoped
                            if issue_filter:
                                table_issues = table_issues[table_issues['label'].isin(issue_filter)]
                            matched_items = table_issues.groupby('module_code')['items'].sum()
                            table = table[table['_code'].isin(matched_items.index)].copy()
                            table['Matching Items'] = table['_code'].map(matched_items).fillna(0).astype(int)
                            table = table.sort_values(['Matching Items', 'Ally Severe'], ascending=False)
                        else:
                            table = table.sort_values(['Ally Severe', 'Ally Major'], ascending=False)

                        if table.empty:
                            st.info("No modules match the selected filters.")
                        else:
                            show = [c for c in [
                                'New module code', 'Module name', 'Mod. lead', 'Content Maturity',
                                'Ally Overall', 'Ally Files', 'Ally WYSIWYG', 'Total Files',
                                'Ally WYSIWYG Items', 'Ally Severe', 'Ally Major', 'Ally Minor',
                                'Ally Students'] if c in table.columns]
                            configs = {
                                'New module code': "Module Code",
                                'Module name': "Module Name",
                                'Mod. lead': "Module Lead",
                                'Content Maturity': "Build Stage",
                                'Ally Overall': st.column_config.NumberColumn("Overall", format="%.1f%%"),
                                'Ally Files': st.column_config.NumberColumn("Files", format="%.1f%%"),
                                'Ally WYSIWYG': st.column_config.NumberColumn("Pages", format="%.1f%%"),
                                'Total Files': st.column_config.NumberColumn("# Files", format="%d"),
                                'Ally WYSIWYG Items': st.column_config.NumberColumn("# Pages", format="%d"),
                                'Ally Severe': st.column_config.NumberColumn("Severe", format="%d"),
                                'Ally Major': st.column_config.NumberColumn("Major", format="%d"),
                                'Ally Minor': st.column_config.NumberColumn("Minor", format="%d"),
                                'Ally Students': st.column_config.NumberColumn("Students", format="%d"),
                            }
                            if filters_active:
                                show.append('Matching Items')
                                configs['Matching Items'] = st.column_config.NumberColumn(
                                    "Matching Items",
                                    help="Content items matching the severity/issue filters "
                                         "above.")
                            st.dataframe(
                                table[show].reset_index(drop=True),
                                column_config=configs,
                                width="stretch", hide_index=True)

            elif selected_view == "📈 Trends":
                st.subheader(f"Accessibility Trends ({school})")
                try:
                    history = get_ally_history(academic_year=CURRENT_ACADEMIC_YEAR)
                except Exception:
                    history = pd.DataFrame()

                if history.empty:
                    st.info("Historical Ally data is not yet available.")
                elif history['snapshot_date'].nunique() < 2:
                    st.info(
                        "Only one Ally snapshot has been imported so far, so there is no "
                        "trend to plot yet. Import the report again after Ally next runs "
                        "and this fills in."
                    )
                else:
                    school_history = history[history['module_code'].isin(school_codes)].copy()
                    if school_history.empty:
                        st.info("No historical Ally data for this school.")
                    else:
                        school_history['items'] = (school_history['total_files']
                                                   + school_history['total_wysiwyg'])
                        grouped = school_history.groupby('snapshot_date')
                        trend = pd.DataFrame({
                            'Overall score': grouped.apply(
                                lambda g: (g['overall_score'] * g['items']).sum()
                                / max(g['items'].sum(), 1), include_groups=False),
                            'Files uploaded': grouped['total_files'].sum(),
                        })
                        trend.index = pd.to_datetime(trend.index)
                        st.markdown("**Average accessibility score over time**")
                        st.line_chart(trend['Overall score'], height=260)
                        st.markdown("**Content uploaded over time**")
                        st.line_chart(trend['Files uploaded'], height=220)
                        st.caption(
                            "A course is only re-recorded when its content actually changes, "
                            "so each point is a real movement. Early in the year the upload "
                            "line matters more than the score line."
                        )
            elif selected_view == "✅ Checklist Completion":
                st.subheader(f"Checklist Completion Analysis ({semester})")

                from processing import calculate_dynamic_compliance_gap
                gaps = calculate_dynamic_compliance_gap(school_code=school)
                
                if gaps:
                    gap_df = pd.DataFrame(list(gaps.items()), columns=['Category', '% Complete'])
                    gap_df['% Complete'] = gap_df['% Complete'] * 100

                    import altair as alt
                    chart_base = alt.Chart(gap_df).encode(
                        y=alt.Y('Category:N',
                                sort='x',
                                title=None,
                                axis=alt.Axis(labelLimit=500, labelFontSize=12)),
                        x=alt.X('% Complete:Q',
                                scale=alt.Scale(domain=[0, 100]),
                                title="% Complete"),
                        tooltip=['Category', alt.Tooltip('% Complete', format='.1f')]
                    )

                    bars = chart_base.mark_bar(cornerRadiusEnd=5, height=28).encode(
                        color=alt.Color('% Complete:Q',
                                       scale=alt.Scale(scheme='redyellowgreen'),
                                       legend=None)
                    )

                    text_overlay = chart_base.mark_text(
                        align='left',
                        baseline='middle',
                        dx=6,
                        fontWeight='bold'
                    ).encode(
                        text=alt.Text('% Complete:Q', format='.1f')
                    )

                    final_chart = (bars + text_overlay).properties(
                        height=450
                    ).configure_view(
                        strokeWidth=0
                    )

                    st.altair_chart(final_chart, use_container_width=True)
                else:
                    st.write("No checklist completion data available.")

            elif selected_view == "⚠️ Priority Action List":
                st.subheader("🎯 Focus Priority Lenses")
                st.caption("A different way to look at risk across the school's modules.")
                
                lens = st.radio(
                    "Choose inspection criteria:",
                    ["⚠️ Accessibility Risk", "🔍 Critical Checklist Gaps", "📋 Missing Audits", "📚 Missing Reading Lists"],
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

                if lens == "⚠️ Accessibility Risk":
                    render_df, render_configs, render_status, render_status_type = \
                        build_accessibility_risk_list(source_data)

                elif lens == "🔍 Critical Checklist Gaps":
                    counts, max_items = calculate_module_compliance(
                        get_all_audit_responses(), get_active_audit_fields()
                    )

                    if max_items == 0:
                        render_status = "No scorable audit fields are configured."
                        render_status_type = "error"
                    elif counts.empty:
                        render_status = "No audits submitted yet, so there are no checklist gaps to show."
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
                                "missing several key checklist items."
                            )
                            render_status_type = "warning"
                            gap_df['DisplayValue'] = gap_df['Compliant Items'].apply(lambda x: f"{int(x)} / {max_items}")

                            display_cols = ['New module code', 'Module name', 'Mod. lead', 'DisplayValue']
                            render_df = gap_df[display_cols].copy()
                            render_configs = {
                                "New module code": "Code", "Module name": "Module Name",
                                "Mod. lead": "Lead", "DisplayValue": "Items Complete"
                            }
                        elif scored_df.empty:
                            render_status = "No modules in this school have been audited yet."
                            render_status_type = "info"
                        else:
                            render_status = f"All {len(scored_df)} audited modules meet the required baseline checklist items!"
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
                        render_status = f"🎯 Found {len(missing_df)} modules either pending audit or with partial submissions."
                        render_status_type = "warning"
                        
                        display_cols = ['New module code', 'Module name', 'Mod. lead', 'DisplayValue']
                        render_df = missing_df[display_cols].copy()
                        render_configs = {
                            "New module code": "Code", "Module name": "Module Name",
                            "Mod. lead": "Lead", "DisplayValue": "Submission Status"
                        }
                    else:
                        render_status = "All currently listed modules have completed their audits! 🌟"
                        render_status_type = "success"

                elif lens == "📚 Missing Reading Lists":
                    if 'Leganto Missing' not in source_data.columns:
                        render_status = "Leganto reading-list data hasn't been imported for this school yet."
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
                                st.switch_page(st.session_state.pg_module)
                        with c2:
                            if can_audit and st.button(f"✅ Open Audit Portal", width="stretch", key="school_priority_btn_cl"):
                                st.session_state.selected_module_code = clicked_code
                                st.switch_page(st.session_state.pg_audit)
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

            elif selected_view == "🤖 AI in the Curriculum":
                st.subheader(f"AI in the Curriculum — {school}")
                st.caption(
                    "Declarations made by module leads themselves, in the separate "
                    "AI in the Curriculum Audit app."
                )

                school_codes = set(school_df['New module code'].dropna().astype(str).str.strip().str.upper())
                known_codes = set()
                for frame in (df_aut, df_spr):
                    if frame is not None and not frame.empty:
                        known_codes |= set(frame['New module code'].dropna().astype(str).str.strip().str.upper())
                summary = summarise_ai_declarations(get_ai_declarations(), school_codes, known_codes)
                per_module = summary['per_module']
                declared = summary['declared']
                in_scope = summary['in_scope']
                pct = (declared / in_scope * 100) if in_scope else 0.0

                col1, col2, col3 = st.columns(3)
                col1.metric("Modules Declared", f"{declared} / {in_scope}")
                col2.metric("Coverage", f"{pct:.1f}%")
                col3.metric(
                    "Assessments Covered",
                    int(per_module['Assessments Declared'].sum()) if not per_module.empty else 0,
                )
                st.progress(min(pct / 100, 1.0))

                st.divider()
                declared_codes = set(per_module['module_code']) if not per_module.empty else set()

                tab_missing, tab_declared = st.tabs(["📋 Awaiting Declaration", "✅ Declared"])

                with tab_missing:
                    missing = school_df[~school_df['New module code'].astype(str).str.strip().str.upper().isin(declared_codes)]
                    if missing.empty:
                        st.success("Every module in this school has a declaration.")
                    else:
                        st.warning(f"{len(missing)} module(s) have no AI declaration.")
                        st.dataframe(
                            missing[['New module code', 'Module name', 'Mod. lead']].rename(
                                columns={'New module code': 'Code', 'Module name': 'Module Name', 'Mod. lead': 'Lead'}
                            ),
                            hide_index=True,
                            width="stretch",
                        )

                with tab_declared:
                    if per_module.empty:
                        st.info("No declarations for this school yet.")
                    else:
                        names = school_df.set_index(
                            school_df['New module code'].astype(str).str.strip().str.upper()
                        )['Module name'].to_dict()
                        shown = per_module.copy()
                        shown['Module Name'] = shown['module_code'].map(names)
                        st.dataframe(
                            shown.rename(columns={'module_code': 'Code'})[
                                ['Code', 'Module Name', 'Assessments Declared', 'Gen AI Activity']
                            ],
                            hide_index=True,
                            width="stretch",
                        )

            elif selected_view == "🎯 Spot-Checks":
                st.subheader(f"Spot-Checks — {school}")
                st.caption(
                    "Modules a DLA has chosen to double-check by hand, from the module "
                    "list above - flagging is a judgement call (past experience, spread "
                    "across levels, some randomness), not an algorithm. A flagged module "
                    "closes itself out the moment its flagger saves a real audit for it "
                    "in the Audit Portal; the agreement column then shows whether their "
                    "answers matched what the Blackboard Template data was suggesting."
                )

                sc_df = get_school_spot_checks(school, CURRENT_ACADEMIC_YEAR)
                if sc_df.empty:
                    st.info(
                        "No modules flagged yet this year. Select a module in "
                        "'📋 Modules Overview' and use 🎯 Flag for Spot-Check.")
                else:
                    pending_n = int((sc_df['status'] == 'pending').sum())
                    checked_n = int((sc_df['status'] == 'checked').sum())
                    m1, m2, m3 = st.columns(3)
                    m1.metric("Flagged this year", len(sc_df))
                    m2.metric("Pending", pending_n)
                    m3.metric("Checked", checked_n)

                    agreement_summary = get_spot_check_agreement_summary(CURRENT_ACADEMIC_YEAR)
                    school_agreement = (agreement_summary[agreement_summary['school'] == school]
                                        if not agreement_summary.empty else pd.DataFrame())
                    if not school_agreement.empty:
                        row = school_agreement.iloc[0]
                        st.caption(
                            f"Agreement to date: {int(row['agreed'])} of {int(row['total'])} "
                            f"checklist answers compared ({row['agreement_pct']:.1f}%) across "
                            f"{int(row['checked'])} checked module(s).")

                    names = school_df.set_index(
                        school_df['New module code'].astype(str).str.strip().str.upper()
                    )['Module name'].to_dict()

                    def _agreement_display(r):
                        if r['status'] != 'checked':
                            return "—"
                        total = r.get('agreement_total')
                        if total in (None, 0) or pd.isna(total):
                            return "n/a"
                        return f"{int(r['agreement_agreed'])}/{int(total)}"

                    shown = sc_df.copy()
                    shown['Module Name'] = shown['module_code'].map(names)
                    shown['Status'] = shown['status'].map({'pending': '⏳ Pending', 'checked': '✅ Checked'})
                    shown['Agreement'] = shown.apply(_agreement_display, axis=1)
                    shown = shown.reset_index(drop=True)
                    # 'id' stays out of the visible table but is kept aligned by
                    # position so a selected row can be deleted by primary key.
                    sc_ids = shown['id']
                    sc_display_df = shown.rename(columns={
                        'module_code': 'Module', 'flagged_by': 'Flagged By',
                        'flagged_on': 'Flagged On', 'checked_on': 'Checked On'})[
                        ['Module', 'Module Name', 'Flagged By', 'Flagged On',
                         'Status', 'Checked On', 'Agreement']]

                    st.caption("Select a row to jump to that module, or remove its flag.")
                    sc_selection = st.dataframe(
                        sc_display_df, hide_index=True, width="stretch",
                        on_select="rerun", selection_mode="single-row",
                        key="school_dashboard_spot_check_dataframe")

                    # Streamlit keeps a dataframe's selection (by row position)
                    # in session_state across reruns even when the underlying
                    # data has since shrunk - e.g. right after this same panel
                    # deletes a row. Bounds-check before indexing rather than
                    # trusting a persisted index still fits the current table.
                    if sc_selection.selection.rows and sc_selection.selection.rows[0] < len(sc_display_df):
                        sc_row_idx = sc_selection.selection.rows[0]
                        sc_clicked_code = sc_display_df.iloc[sc_row_idx]['Module']
                        sc_clicked_status = shown.iloc[sc_row_idx]['status']
                        sc_clicked_id = int(sc_ids.iloc[sc_row_idx])
                        st.divider()
                        st.info(f"🚀 Quick Action Launch: **{sc_clicked_code}**")
                        sc_c1, sc_c2, sc_c3 = st.columns(3)
                        with sc_c1:
                            if st.button("📊 Jump to Report Card", width="stretch", type="primary",
                                        key="btn_school_sc_rc"):
                                st.session_state.selected_module_code = sc_clicked_code
                                st.switch_page(st.session_state.pg_module)
                        with sc_c2:
                            if can_audit and st.button("✅ Open Audit Portal", width="stretch",
                                                       key="btn_school_sc_ap"):
                                st.session_state.selected_module_code = sc_clicked_code
                                st.switch_page(st.session_state.pg_audit)
                        with sc_c3:
                            if can_audit:
                                # Keyed per-row (not a single shared key) so
                                # confirming removal on one row can never
                                # leave a *different* row's button
                                # pre-confirmed after switching selection -
                                # and so nothing needs resetting after delete,
                                # which Streamlit disallows once a keyed
                                # widget has rendered in the same run.
                                remove_confirm = st.checkbox(
                                    "Confirm removal", key=f"sc_remove_confirm_{sc_clicked_id}",
                                    help="Deletes this flag outright. For a checked module this "
                                         "also deletes its agreement result - re-flag it from "
                                         "'Modules Overview' afterwards to start fresh.")
                                if st.button("🗑️ Remove Flag", width="stretch",
                                            disabled=not remove_confirm, key="btn_school_sc_remove"):
                                    delete_spot_check(sc_clicked_id)
                                    st.success(f"Removed the spot-check flag for {sc_clicked_code}.")
                                    # Clear the persisted selection rather than
                                    # leaving it pointing at whatever row now
                                    # occupies the deleted one's position - a
                                    # plain del is fine here (unlike writing a
                                    # value to it) since it just drops the
                                    # widget's stored state for next run.
                                    if "school_dashboard_spot_check_dataframe" in st.session_state:
                                        del st.session_state["school_dashboard_spot_check_dataframe"]
                                    st.rerun()
                        st.divider()

            st.divider()
            csv_school = school_df.to_csv(index=False).encode('utf-8')
            st.download_button(f"📥 Export {school} {semester} Data", csv_school, f"{school}_{semester}_audit.csv", "text/csv")
        else:
            st.warning(f"No modules found for {school} in {semester}.")
    else:
        st.error(f"Data for {semester} is not available.")
