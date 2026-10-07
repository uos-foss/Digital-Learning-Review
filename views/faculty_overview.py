import streamlit as st
import pandas as pd
import altair as alt
from processing import (aggregate_faculty_stats, calculate_module_compliance,
                        calculate_dynamic_compliance_gap, get_school_comparison,
                        resolve_semester_df, summarise_ai_declarations, summarise_ai_modules,
                        AI_FLAG_OPTIONS, school_of,
                        FACULTY_SCHOOLS, CURRENT_ACADEMIC_YEAR, reading_list_verdict,
                        can_view_sga, parse_user_schools,
                        module_alignment_status, format_comment_markdown, fmt_report_date, school_series)
from database import (get_all_audit_responses, get_active_audit_fields, get_ai_declarations,
                      get_ally_history, get_spot_checks_for_schools, get_spot_check_comments,
                      get_all_active_fix_claims)
from views.ally_widgets import (
    scoreable, mean_score, render_maturity_banner, render_maturity_breakdown,
    render_issue_profile, build_accessibility_risk_list,
)
from views.school_dashboard import to_title_case, comment_field_label


def _with_school_column(df):
    """Tags each row with its School (from the module code prefix), scoped to
    FACULTY_SCHOOLS - the same convention get_school_comparison() uses."""
    if df is None or df.empty or 'New module code' not in df.columns:
        return df if df is not None else pd.DataFrame()
    out = df.copy()
    out['School'] = school_series(out['New module code'])
    return out[out['School'].isin(FACULTY_SCHOOLS)]


def _school_filter(default_schools):
    """Shared school-scoping widget for the faculty-wide tables below. Reused
    across tabs under one key (only one tab's code runs per rerun, since
    st.segmented_control lazy-loads the rest), so a school selection made on
    one tab carries over to the next."""
    return st.multiselect(
        "Schools", FACULTY_SCHOOLS,
        default=st.session_state.get("faculty_overview_school_filter", default_schools),
        key="faculty_overview_school_filter",
        help="Scopes this table to the chosen school(s). Defaults to your own "
             "school(s) - widen it to see more of the faculty."
    )


def _quick_action_launch(code, school, can_audit, key_prefix):
    st.divider()
    st.info(f"🚀 Quick Action Launch: **{code}**")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("📊 Jump to Report Card", width="stretch", type="primary",
                     key=f"{key_prefix}_rc"):
            st.session_state.selected_module_code = code
            st.session_state.context_focus_own = False
            st.session_state.context_school = school
            st.switch_page(st.session_state.pg_module)
    with c2:
        if can_audit and st.button("✅ Open Audit Portal", width="stretch",
                                    key=f"{key_prefix}_audit"):
            st.session_state.selected_module_code = code
            st.session_state.context_focus_own = False
            st.session_state.context_school = school
            st.switch_page(st.session_state.pg_audit)
    st.divider()


def view_faculty_overview(df_aut, df_spr, checklist_sums, df_assess=None):
    st.title("🏛️ Faculty Overview")

    # pg_audit is only added to the navigation when the user holds edit_checklist,
    # and st.switch_page raises on a page that is not registered - so the button
    # that jumps there must be hidden from everyone else, not just fail on click.
    # Same applies to pg_school and view_school_dashboard.
    user_caps = st.session_state.get("capabilities", [])
    can_audit = any(c.lower() == "edit_checklist" for c in user_caps)
    can_view_school_dashboard = any(c.lower() == "view_school_dashboard" for c in user_caps)
    is_admin = any(c.lower() == "access_admin_panel" for c in user_caps)
    show_sga = can_view_sga(user_caps)

    # Determine active data based on chosen semester
    semester = st.session_state.get('semester', 'Autumn')
    active_df = resolve_semester_df(df_aut, df_spr, semester)
    active_df_scoped = _with_school_column(active_df)
    semester_codes = (
        set(active_df['New module code'].dropna().astype(str).str.strip().str.upper())
        if not active_df.empty else set())

    # Default school scope for the faculty-wide tables below: the viewer's
    # own school(s), same as School Dashboard's "Focus on my school(s)"
    # default - widen from there to see more of the faculty.
    user_schools = parse_user_schools(st.session_state.get('saved_school'))
    default_schools = list(FACULTY_SCHOOLS) if user_schools == ["All"] \
        else [s for s in user_schools if s in FACULTY_SCHOOLS] or list(FACULTY_SCHOOLS)

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
    # "📝 Assessment Types" is temporarily disabled - add it back to this list
    # to restore. Its view code below is untouched.
    view_options = ["📋 All Modules", "🏫 School Comparison", "✅ Template Alignment",
                     "📊 Ally Analytics", "📈 Trends", "⚠️ Priority Action List",
                     "🎯 Spot-Checks", "💬 Spot-Check Comments",
                     "🤖 AI in the Curriculum"]
    if not is_admin:
        view_options = [v for v in view_options
                         if v not in ("📊 Ally Analytics", "📈 Trends", "⚠️ Priority Action List")]

    selected_view = st.segmented_control(
        "Navigate View:",
        options=view_options,
        default=view_options[0],
        key="faculty_nav_segmented_control",
        label_visibility="collapsed"
    )
    st.divider()

    if selected_view == "📋 All Modules":
        st.subheader(f"All Modules ({semester})")
        chosen_schools = _school_filter(default_schools)
        scope_df = active_df_scoped[active_df_scoped['School'].isin(chosen_schools)] \
            if not active_df_scoped.empty and chosen_schools else pd.DataFrame()

        if not chosen_schools:
            st.info("Choose at least one school above to see its modules.")
        elif scope_df.empty:
            st.warning(f"No modules found for the selected school(s) in {semester}.")
        else:
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                st.metric("Total Modules", len(scope_df),
                          help=f"Total modules for the selected school(s) in the {semester} semester.")
            with c2:
                no_activity = len(scope_df) - len(scoreable(scope_df))
                st.metric("Modules with no activity", f"{no_activity}",
                          help="Modules that still only have the default template - no "
                               "content added yet")
            with c3:
                avg_ally = mean_score(scope_df)
                st.metric("Avg Ally Score", f"{avg_ally:.1%}" if avg_ally is not None else "—",
                          help="Ally's overall score, averaged across modules with content "
                               "beyond their template only.")
            with c4:
                total_actionable = int(scope_df['New module code'].apply(
                    lambda c: checklist_sums.get(c, {}).get('Actionable Items', 0)).sum())
                st.metric("Outstanding Actionable Items", f"{total_actionable}",
                          help="Sum of outstanding items across the shown modules - "
                               "checklist, Leganto reading lists, Ally accessibility, and "
                               "template readiness findings combined.")

            st.subheader("Module Audit Status")
            display_df = scope_df.copy().sort_values(['School', 'New module code']).reset_index(drop=True)
            display_df['Mod. lead'] = display_df['Mod. lead'].apply(to_title_case)
            cols = ['School', 'New module code', 'Module name', 'Mod. lead']
            configs = {
                "School": "School",
                "New module code": "Module Code",
                "Module name": "Module Name",
                "Mod. lead": "Module Lead"
            }
            if 'UG/ PG/ Other' in display_df.columns:
                _level_abbrev = {
                    'Foundation': 'FY',
                    'UG Level 1': 'UG1',
                    'UG Level 2': 'UG2',
                    'UG Level 3': 'UG3',
                }
                display_df['UG/ PG/ Other'] = display_df['UG/ PG/ Other'].apply(
                    lambda v: _level_abbrev.get(v, v))
                cols.append('UG/ PG/ Other')
                configs['UG/ PG/ Other'] = "Level"

            if 'Ally Overall' in display_df.columns or 'Content Maturity' in display_df.columns:
                def _score_or_stage(r):
                    maturity = r.get('Content Maturity')
                    if maturity == 'In progress':
                        v = r.get('Ally Overall')
                        if pd.notna(v):
                            return f"{v * 100:.1f}%"
                    if not maturity:
                        return "—"
                    return "Not started" if maturity == "Not yet built" else maturity
                display_df['Score / Stage'] = display_df.apply(_score_or_stage, axis=1)
                cols.append('Score / Stage')
                configs['Score / Stage'] = st.column_config.TextColumn(
                    "Ally Score",
                    help="Ally's accessibility score once a module has content "
                         "beyond its template ('In progress'); otherwise the build "
                         "stage itself, since an untouched template scores near "
                         "100% and would misread as the best module in its school.")

            display_df['Actionable Items'] = display_df['New module code'].apply(
                lambda c: checklist_sums.get(c, {}).get('Actionable Items', 0))
            cols.append('Actionable Items')
            configs['Actionable Items'] = st.column_config.NumberColumn(
                "Actionable Items",
                help="Outstanding items for this module - checklist, Leganto "
                     "reading lists, Ally accessibility, and template readiness "
                     "findings combined.")

            if 'Leganto Missing' in display_df.columns:
                def _leganto_display(r):
                    # A DLA's recorded answer overrides Leganto, which is
                    # exported rarely and often lags Blackboard.
                    verdict = reading_list_verdict(checklist_sums, r.get('New module code'))
                    if verdict is True:
                        return "✅ DLA confirmed"
                    if verdict is False:
                        return "❌ DLA: not done"
                    if r.get('Leganto Missing') == True:  # noqa: E712
                        return "❌ Missing"
                    status = r.get('Leganto List Status', '')
                    if status == 'Published':
                        return "✅ Published"
                    if status in ('Draft', 'Mixed'):
                        return "📝 Draft"
                    if status == 'No List Expected':
                        return "➖ Not needed"
                    return "❌ Missing"
                display_df['Leganto'] = display_df.apply(_leganto_display, axis=1)
                cols.append('Leganto')
                configs['Leganto'] = st.column_config.TextColumn(
                    "Reading List",
                    help="DLA confirmed / DLA: not done - a Digital Learning "
                         "Advisor's audit answer, which overrides Leganto. "
                         "Otherwise the Leganto status: Published/Draft - list "
                         "status in Leganto. Not needed - Leganto's own export "
                         "confirms no list is expected for this course. Missing - "
                         "no list found, or the module doesn't yet appear in "
                         "either Leganto export.")

            if show_sga and 'SGA Attributes' in display_df.columns \
                    and display_df['SGA Attributes'].notna().any():
                cols.append('SGA Attributes')
                configs['SGA Attributes'] = st.column_config.NumberColumn(
                    "SGAs",
                    help="Sheffield Graduate Attributes mapped in the SGA tool, "
                         "out of 12. 0 means none mapped.")

            sc_scope_df = get_spot_checks_for_schools(chosen_schools, CURRENT_ACADEMIC_YEAR)
            sc_status_by_code = {}
            if not sc_scope_df.empty:
                latest = sc_scope_df.sort_values('flagged_on', ascending=False) \
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
                     "audited this year, whether it was flagged first or a DLA "
                     "submitted an audit for it unprompted. Blank - neither.")

            clean_display_df = display_df[cols].reset_index(drop=True)
            st.caption("Select a row to jump to that module's report or audit.")
            selection = st.dataframe(
                clean_display_df, hide_index=True, width="stretch",
                on_select="rerun", selection_mode="single-row",
                key="faculty_all_modules_dataframe")

            selected_rows = [i for i in selection.selection.rows if i < len(clean_display_df)]
            if selected_rows:
                row = clean_display_df.iloc[selected_rows[0]]
                _quick_action_launch(row['New module code'], row['School'], can_audit,
                                      "fac_all_modules")

            st.download_button(
                "📥 Download All Modules (CSV)",
                clean_display_df.to_csv(index=False).encode('utf-8'),
                f"faculty_all_modules_{semester.lower()}.csv", "text/csv",
                key="faculty_all_modules_downloader")

    elif selected_view == "🏫 School Comparison":
        st.subheader(f"School Comparison ({semester})")
        st.caption(
            "VLE Compliance is measured across **submitted audits only** - read it "
            "alongside the Audited column, since a high score on a small sample is "
            "not the same as a school in good shape. Template Alignment % reads "
            "every module's template/readiness data instead, audited or not - the "
            "two can disagree, and that's worth a second look either way."
        )

        comparison_df, faculty_totals = get_school_comparison(active_df, checklist_sums)

        if comparison_df.empty:
            st.warning(f"No school data available for {semester}.")
        else:
            # A second, data-driven compliance reading, one DB-backed call per
            # school. Deliberately not folded into get_school_comparison()
            # itself, which stays pandas-only over in-memory data per
            # processing.py's I/O-free convention - calculate_dynamic_
            # compliance_gap() does its own queries, and only runs when this
            # tab is open (segmented_control already lazy-loads the rest).
            def _template_alignment_pct(school):
                gaps = calculate_dynamic_compliance_gap(school_code=school, module_codes=semester_codes)
                return (sum(gaps.values()) / len(gaps) * 100) if gaps else None
            comparison_df['Template Alignment %'] = comparison_df['School'].apply(_template_alignment_pct)

            display_df = comparison_df.copy()
            display_df['Audited'] = display_df.apply(
                lambda r: f"{int(r['Audited'])} ({r['Audited %']:.0f}%)", axis=1
            )
            for col in ['Avg Ally', 'VLE Compliance', 'Template Alignment %']:
                display_df[col] = display_df[col].apply(
                    lambda x: f"{x:.1f}%" if pd.notna(x) else "—"
                )
            display_df = display_df[['School', 'Modules', 'Audited', 'Avg Ally',
                                      'VLE Compliance', 'Template Alignment %', 'Status']]

            # [STABILITY FIX]: Streamlit's selection engine requires monotonic indices.
            display_df = display_df.reset_index(drop=True)

            selection_schools = st.dataframe(
                display_df,
                column_config={
                    "School": "School",
                    "Modules": st.column_config.NumberColumn("Modules"),
                    "Audited": "Audited",
                    "Avg Ally": "Avg Ally",
                    "VLE Compliance": st.column_config.TextColumn(
                        "VLE Compliance", help="Submitted audits only."),
                    "Template Alignment %": st.column_config.TextColumn(
                        "Template Alignment %",
                        help="Every module in the school, from template/readiness "
                             "data - not dependent on an audit having been submitted."),
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

            total_gaps = calculate_dynamic_compliance_gap(school_code='All', module_codes=semester_codes)
            faculty_template_alignment = (
                sum(total_gaps.values()) / len(total_gaps) * 100) if total_gaps else None

            st.markdown("##### **Faculty Totals**")
            t1, t2, t3, t4, t5 = st.columns(5)
            with t1:
                st.metric("Modules", faculty_totals['Modules'])
            with t2:
                st.metric("Audited", f"{faculty_totals['Audited']} ({faculty_totals['Audited %']:.0f}%)")
            with t3:
                st.metric("Avg Ally", _fmt_pct(faculty_totals['Avg Ally']))
            with t4:
                st.metric("VLE Compliance", _fmt_pct(faculty_totals['VLE Compliance']))
            with t5:
                st.metric("Template Alignment %", _fmt_pct(faculty_template_alignment))

            # Drill-down: hand the chosen school to the School Dashboard for one render.
            if selection_schools.selection.rows:
                row_idx = selection_schools.selection.rows[0]
                clicked_school = display_df.iloc[row_idx]['School']

                st.divider()
                st.info(f"🚀 Launch Control: **{clicked_school}**")
                if can_view_school_dashboard:
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
                by_school['School'] = school_series(by_school['New module code'])
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
                per_school['School'] = school_series(per_school['New module code'])
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

    elif selected_view == "✅ Template Alignment":
        st.subheader(f"Template Alignment Analysis ({semester})")
        st.caption(
            "How ready each part of the Blackboard template is across the "
            "faculty's modules."
        )

        gaps = calculate_dynamic_compliance_gap(school_code='All', module_codes=semester_codes)

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

        st.divider()
        st.markdown("#### Item-by-item status")
        chosen_schools = _school_filter(default_schools)
        matrix_scope_df = active_df_scoped[active_df_scoped['School'].isin(chosen_schools)] \
            if not active_df_scoped.empty and chosen_schools else pd.DataFrame()

        active_fields = get_active_audit_fields()
        boolean_fields = [f for f in active_fields if f['field_type'] in ('boolean', 'yes/no')]

        if not chosen_schools:
            st.info("Choose at least one school above to see the item-by-item matrix.")
        elif not boolean_fields or matrix_scope_df.empty:
            st.info("No checklist item data available for the selected school(s).")
        else:
            st.caption(
                "A detailed view of the status of Blackboard template items "
                "across the selected schools' modules. ✅ done · ❌ outstanding · 🔧 reported fixed, awaiting check · "
                "accessibility: 🟢 good · 🟠 major issues · 🔴 severe issues · ⚪ nothing to judge yet."
            )
            all_fix_claims = get_all_active_fix_claims()
            matrix_rows = []
            for _, r in matrix_scope_df.iterrows():
                code = r['New module code']
                active_row = r.to_dict()
                responses = checklist_sums.get(code, {}).get('Responses', {})
                row = {
                    'School': r.get('School', ''),
                    'Module Code': code,
                    'Module Name': r.get('Module name', ''),
                    'Module Lead': to_title_case(r.get('Mod. lead', '')),
                }
                row.update(module_alignment_status(
                    active_row, responses, active_fields,
                    all_fix_claims.get(str(code).strip().upper())))
                matrix_rows.append(row)

            matrix_df = pd.DataFrame(matrix_rows).sort_values(
                ['School', 'Module Code']).reset_index(drop=True)
            st.caption("Select a row (tick the checkbox) to jump to that module's report or audit.")
            matrix_selection = st.dataframe(
                matrix_df, hide_index=True, width="stretch",
                on_select="rerun", selection_mode="single-row",
                key="faculty_template_alignment_matrix")

            selected_matrix_rows = [i for i in matrix_selection.selection.rows if i < len(matrix_df)]
            if selected_matrix_rows:
                row = matrix_df.iloc[selected_matrix_rows[0]]
                _quick_action_launch(row['Module Code'], row['School'], can_audit,
                                      "fac_template_matrix")

    elif selected_view == "📈 Trends":
        st.subheader("Faculty Accessibility Trends")
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
            faculty_codes = set(active_df_scoped['New module code'].dropna().astype(str)
                                 .str.strip().str.upper()) if not active_df_scoped.empty else set()
            faculty_history = history[history['module_code'].isin(faculty_codes)].copy()
            if faculty_history.empty:
                st.info("No historical Ally data for the faculty's modules.")
            else:
                faculty_history['School'] = school_series(faculty_history['module_code'])
                faculty_history['items'] = (faculty_history['total_files']
                                            + faculty_history['total_wysiwyg'])

                grouped = faculty_history.groupby('snapshot_date')
                trend = pd.DataFrame({
                    'Overall score': grouped.apply(
                        lambda g: (g['overall_score'] * g['items']).sum()
                        / max(g['items'].sum(), 1), include_groups=False),
                    'Files uploaded': grouped['total_files'].sum(),
                })
                trend.index = pd.to_datetime(trend.index)
                st.markdown("**Average accessibility score over time (faculty-wide)**")
                st.line_chart(trend['Overall score'], height=260)
                st.markdown("**Content uploaded over time (faculty-wide)**")
                st.line_chart(trend['Files uploaded'], height=220)
                st.caption(
                    "A course is only re-recorded when its content actually changes, "
                    "so each point is a real movement. Early in the year the upload "
                    "line matters more than the score line."
                )

                st.divider()
                st.markdown("**By school**")
                by_school = faculty_history.groupby(['snapshot_date', 'School']).apply(
                    lambda g: pd.Series({
                        'Overall score': (g['overall_score'] * g['items']).sum()
                                          / max(g['items'].sum(), 1),
                    }), include_groups=False).reset_index()
                by_school['snapshot_date'] = pd.to_datetime(by_school['snapshot_date'])
                school_chart = alt.Chart(by_school).mark_line(point=True).encode(
                    x=alt.X('snapshot_date:T', title=None),
                    y=alt.Y('Overall score:Q', title="Overall score",
                            scale=alt.Scale(domain=[0, 1])),
                    color=alt.Color('School:N', legend=alt.Legend(title="School")),
                    tooltip=['School', 'snapshot_date:T',
                             alt.Tooltip('Overall score:Q', format='.1%')]
                ).properties(height=350)
                st.altair_chart(school_chart, width="stretch")
                st.caption("Compares each school's accessibility trajectory over time.")

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
                    # A DLA's tick overrides Leganto - not an action any more.
                    missing_leganto_df = missing_leganto_df[[
                        reading_list_verdict(checklist_sums, c) is not True
                        for c in missing_leganto_df['New module code']]]

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

    elif selected_view == "🎯 Spot-Checks":
        st.subheader("Spot-Checks — Faculty-wide")
        st.caption(
            "A read-only, faculty-wide view of what DLAs have flagged for spot-check "
            "this year. Flagging and removing flags stays on each school's own "
            "Spot-Checks tab in School Dashboard - a flag belongs to the school it "
            "was raised in, not to whoever raised it."
        )
        chosen_schools = _school_filter(default_schools)

        if not chosen_schools:
            st.info("Choose at least one school above to see its spot-checks.")
        else:
            sc_df = get_spot_checks_for_schools(chosen_schools, CURRENT_ACADEMIC_YEAR)
            if sc_df.empty:
                st.info("No modules flagged yet this year for the selected school(s).")
            else:
                sc_df = sc_df.copy()
                sc_df['School'] = school_series(sc_df['module_code'])

                pending_n = int((sc_df['status'] == 'pending').sum())
                checked_n = int((sc_df['status'] == 'checked').sum())
                m1, m2, m3 = st.columns(3)
                m1.metric("Flagged this year", len(sc_df))
                m2.metric("Pending", pending_n)
                m3.metric("Checked", checked_n)

                st.markdown("**By school**")
                by_school = sc_df.groupby(['School', 'status']).size().unstack(fill_value=0)
                for status_col in ('pending', 'checked'):
                    if status_col not in by_school.columns:
                        by_school[status_col] = 0
                by_school = by_school.rename(
                    columns={'pending': 'Pending', 'checked': 'Checked'})[['Pending', 'Checked']]
                st.dataframe(by_school.reset_index(), hide_index=True, width="stretch")

                # Module names, faculty-wide and both semesters - spot-checks
                # span the whole academic year, same reasoning as School
                # Dashboard's own year_names.
                year_df = _with_school_column(pd.concat(
                    [df for df in (df_aut, df_spr) if df is not None and not df.empty]))
                year_df = year_df[year_df['School'].isin(chosen_schools)] if not year_df.empty else year_df
                year_names = {}
                if not year_df.empty:
                    year_names = (year_df.assign(
                            _code=year_df['New module code'].astype(str).str.strip().str.upper())
                        .dropna(subset=['Module name'])
                        .drop_duplicates('_code')
                        .set_index('_code')['Module name'].to_dict())

                comments_label = comment_field_label()
                comment_frames = [get_spot_check_comments(s, CURRENT_ACADEMIC_YEAR)
                                   for s in chosen_schools]
                comment_frames = [f for f in comment_frames if not f.empty]
                comments_by_module = {}
                if comment_frames:
                    all_comments = pd.concat(comment_frames)
                    comments_by_module = {
                        str(c).strip().upper(): str(v or '').strip()
                        for c, v in zip(all_comments['module_code'], all_comments['comment'])}

                shown = sc_df.copy()
                shown['Module Name'] = shown['module_code'].map(
                    lambda c: year_names.get(str(c).strip().upper(), ""))
                shown['Status'] = shown['status'].map({'pending': '⏳ Pending', 'checked': '✅ Checked'})
                shown[comments_label] = shown['module_code'].map(
                    lambda c: comments_by_module.get(str(c).strip().upper(), ""))

                sc_filter = st.radio(
                    "Show", ["All", "Pending", "Checked"], horizontal=True,
                    key="faculty_sc_status_filter")
                if sc_filter != "All":
                    shown = shown[shown['status'] == sc_filter.lower()]
                shown = shown.sort_values('flagged_on', ascending=False).reset_index(drop=True)

                sc_display_df = shown.rename(columns={
                    'module_code': 'Module', 'checked_on': 'Checked On'})[
                    ['School', 'Module', 'Module Name', 'Status', 'Checked On', comments_label]]

                st.caption("Select a row to jump to that module, or to manage its flag on "
                           "that school's own Spot-Checks tab.")
                selection = st.dataframe(
                    sc_display_df, hide_index=True, width="stretch",
                    on_select="rerun", selection_mode="single-row",
                    column_config={
                        comments_label: st.column_config.TextColumn(comments_label, width="medium"),
                    },
                    key="faculty_spot_checks_dataframe")

                selected_rows = [i for i in selection.selection.rows if i < len(sc_display_df)]
                if selected_rows:
                    row = sc_display_df.iloc[selected_rows[0]]
                    st.divider()
                    st.info(f"🚀 Quick Action Launch: **{row['Module']}**")
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        if st.button("📊 Jump to Report Card", width="stretch", type="primary",
                                     key="fac_sc_rc"):
                            st.session_state.selected_module_code = row['Module']
                            st.session_state.context_focus_own = False
                            st.session_state.context_school = row['School']
                            st.switch_page(st.session_state.pg_module)
                    with c2:
                        if can_audit and st.button("✅ Open Audit Portal", width="stretch",
                                                    key="fac_sc_audit"):
                            st.session_state.selected_module_code = row['Module']
                            st.session_state.context_focus_own = False
                            st.session_state.context_school = row['School']
                            st.switch_page(st.session_state.pg_audit)
                    with c3:
                        if can_view_school_dashboard and st.button(
                                f"🏫 Manage on {row['School']} Spot-Checks", width="stretch",
                                key="fac_sc_manage"):
                            st.session_state.drilldown_school = row['School']
                            st.switch_page(st.session_state.pg_school)
                    st.divider()

                st.download_button(
                    "📥 Download Spot-Checks (CSV)",
                    sc_display_df.to_csv(index=False).encode('utf-8'),
                    "faculty_spot_checks.csv", "text/csv",
                    key="faculty_spot_checks_downloader")

    elif selected_view == "💬 Spot-Check Comments":
        comments_label = comment_field_label()
        st.subheader("Spot-Check Comments — Faculty-wide")
        st.caption(
            f'What advisors wrote in "{comments_label}" when they audited spot-checked '
            "modules across the selected school(s), most recent first. Each comment is "
            "the module's current audit answer, so revising an audit changes what "
            "appears here."
        )
        chosen_schools = _school_filter(default_schools)

        if not chosen_schools:
            st.info("Choose at least one school above to see its spot-check comments.")
        else:
            comment_frames = [get_spot_check_comments(s, CURRENT_ACADEMIC_YEAR)
                               for s in chosen_schools]
            comment_frames = [f for f in comment_frames if not f.empty]
            sc_comments = pd.concat(comment_frames) if comment_frames else pd.DataFrame()

            if sc_comments.empty:
                st.info("No modules flagged yet this year for the selected school(s).")
            else:
                sc_comments = sc_comments.copy()
                sc_comments['School'] = school_series(sc_comments['module_code'])
                sc_comments['comment'] = (sc_comments['comment'].fillna('')
                                          .astype(str).str.strip())
                # One row per module - see School Dashboard's identical
                # reasoning for this drop_duplicates (a module can be
                # re-flagged within a year; only its latest flag's comment
                # matters here since there's only one comment to read).
                sc_comments = sc_comments.drop_duplicates(subset='module_code', keep='first')
                has_comment = sc_comments['comment'] != ""

                m1, m2, m3 = st.columns(3)
                m1.metric("Modules flagged this year", len(sc_comments))
                m2.metric("With a comment", int(has_comment.sum()))
                m3.metric("No comment yet", int((~has_comment).sum()),
                          help="Usually a flag nobody has audited yet, since the "
                               "comment is written in the Audit Portal.")

                f1, f2, f3 = st.columns([2, 1, 1])
                with f1:
                    comment_search = st.text_input(
                        "Search", key="fac_sc_comment_search",
                        placeholder="Module code, school, or any word in a comment")
                with f2:
                    comment_status = st.selectbox(
                        "Flag status", ["All", "Checked", "Pending"],
                        key="fac_sc_comment_status")
                with f3:
                    show_uncommented = st.checkbox(
                        "Include no-comment flags", value=False,
                        key="fac_sc_comment_show_empty")

                filtered_comments = sc_comments
                if not show_uncommented:
                    filtered_comments = filtered_comments[filtered_comments['comment'] != ""]
                if comment_status != "All":
                    filtered_comments = filtered_comments[
                        filtered_comments['status'] == comment_status.lower()]
                needle = comment_search.strip().lower()
                if needle:
                    filtered_comments = filtered_comments[
                        filtered_comments['module_code'].astype(str).str.lower().str.contains(needle)
                        | filtered_comments['School'].astype(str).str.lower().str.contains(needle)
                        | filtered_comments['comment'].str.lower().str.contains(needle)]

                filtered_comments = filtered_comments.sort_values(
                    'comment_on', ascending=False, na_position='last')

                if filtered_comments.empty:
                    st.info("No spot-check comments match those filters.")
                else:
                    st.caption(f"Showing {len(filtered_comments)} of "
                               f"{len(sc_comments)} flagged module(s).")

                    year_df = _with_school_column(pd.concat(
                        [df for df in (df_aut, df_spr) if df is not None and not df.empty]))
                    year_names = {}
                    if not year_df.empty:
                        year_names = (year_df.assign(
                                _code=year_df['New module code'].astype(str).str.strip().str.upper())
                            .dropna(subset=['Module name'])
                            .drop_duplicates('_code')
                            .set_index('_code')['Module name'].to_dict())

                    for _, comment_row in filtered_comments.iterrows():
                        code = str(comment_row['module_code']).strip().upper()
                        module_name = year_names.get(code, "")
                        module_name = ("" if pd.isna(module_name) else str(module_name).strip())
                        status_badge = ("✅ Checked" if comment_row['status'] == 'checked'
                                        else "⏳ Pending")
                        with st.container(border=True):
                            heading = f"**{comment_row['School']} · {code}**"
                            if module_name:
                                heading += f" · {module_name}"
                            st.markdown(f"{heading} · {status_badge}")

                            body = format_comment_markdown(comment_row['comment'])
                            if body:
                                st.markdown(body)
                            else:
                                st.caption("Nothing written against this module yet.")

                            trail = []
                            author = str(comment_row.get('comment_by') or '').strip()
                            written_on = fmt_report_date(comment_row.get('comment_on'))
                            if body and author:
                                trail.append(f"Audited by {author}"
                                             + (f" on {written_on}" if written_on else ""))
                            flagged_by = str(comment_row.get('flagged_by') or '').strip()
                            flagged_on = fmt_report_date(comment_row.get('flagged_on'))
                            if flagged_by:
                                trail.append(f"Flagged by {flagged_by}"
                                             + (f" on {flagged_on}" if flagged_on else ""))
                            if trail:
                                st.caption(" · ".join(trail))

                    export_comments = filtered_comments[
                        ['School', 'module_code', 'status', 'comment', 'comment_by', 'comment_on',
                         'flagged_by', 'flagged_on', 'checked_by', 'checked_on']]
                    st.download_button(
                        "📥 Export Spot-Check Comments",
                        export_comments.to_csv(index=False).encode('utf-8'),
                        "faculty_spot_check_comments.csv", "text/csv",
                        key="fac_sc_comments_export")

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
                matching_assess['School'] = school_series(matching_assess['CIS unit code'])
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

            st.divider()
            st.markdown("##### **Module Status**")
            status_school = st.selectbox(
                "School:", ["All Schools"] + list(FACULTY_SCHOOLS), key="ai_status_school")
            in_school = (lambda code: status_school == "All Schools" or school_of(code) == status_school)
            declared_codes = set(per_module['module_code']) if not per_module.empty else set()

            status_view = st.radio(
                "View:", ["Pending (Incomplete)", "Completed"], horizontal=True,
                label_visibility="collapsed", key="ai_status_view")

            if status_view == "Pending (Incomplete)":
                pending = active_df.dropna(subset=['New module code']).copy()
                pending['New module code'] = pending['New module code'].astype(str).str.strip().str.upper()
                pending = pending.drop_duplicates(subset=['New module code'])
                pending = pending[~pending['New module code'].isin(declared_codes)]
                pending = pending[pending['New module code'].map(in_school)]
                if pending.empty:
                    st.success("All modules have a declaration.")
                else:
                    st.caption(f"{len(pending)} module(s) awaiting a declaration.")
                    st.dataframe(
                        pending[['New module code', 'Module name', 'Mod. lead']].rename(
                            columns={'New module code': 'Module Code', 'Module name': 'Module Title',
                                     'Mod. lead': 'Lead'}),
                        hide_index=True,
                        width="stretch",
                    )
            else:
                completed = declarations[
                    declarations['module_code'].isin(active_codes)
                    & declarations['module_code'].map(in_school)]
                module_status = summarise_ai_modules(completed, df_assess)
                if module_status.empty:
                    st.info("No completed modules for this selection.")
                else:
                    picked = st.multiselect(
                        "Only show modules flagged with:", AI_FLAG_OPTIONS, key="ai_status_flags",
                        help="Policy gap: AI could do most or all of an assessment but its stated "
                             "position is 'not permitted' or 'no clear position'.")
                    if picked:
                        module_status = module_status[
                            module_status['Flags'].apply(lambda f: any(p in f for p in picked))]
                    st.caption(
                        f"{len(module_status)} module(s). Highest = the most severe answer across the "
                        "module's assessments. Weighted exposure = share of the module's assessment "
                        "weighting where AI could undertake most or all of the work.")
                    st.dataframe(module_status, hide_index=True, width="stretch")
                    st.download_button(
                        "⬇️ Download summary (CSV)",
                        module_status.to_csv(index=False).encode("utf-8"),
                        file_name="ai_curriculum_module_summary.csv", mime="text/csv")
