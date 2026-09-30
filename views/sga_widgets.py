"""
Sheffield Graduate Attributes views, shared by School Dashboard and Faculty
Overview. These views only display; the count's gating of the `sga` tick lives in
processing.derive_module_findings() (see "SGA data" in CLAUDE.md).

Both views take the semester-filtered module frame their page already built
(so a module's SGA counts ride along as 'SGA Attributes' / 'SGA
Sub-Attributes' from app.load_audit_data()) and the module x sub-attribute
frame app.py stashes in st.session_state['df_sga'].
"""
import altair as alt
import pandas as pd
import streamlit as st

from processing import (SGA_SUB_ATTRIBUTE_ROWS, SGA_THEMES, SGA_CONCENTRATION_SHARE,
                        SGA_MODULE_MANY_ATTRIBUTES, FACULTY_SCHOOLS, summarise_sga_usage)

# Categorical slots 1-3 of the reference data-viz palette, which stay
# distinguishable for colour-blind readers as a set of three.
THEME_COLOURS = ['#2a78d6', '#eb6834', '#1baf7a']


def _sga_frame():
    return st.session_state.get('df_sga', pd.DataFrame())


def _no_import(df):
    """True, after saying so, when no SGA export has been imported this year -
    the counts are None rather than 0 until then."""
    if df.empty or 'SGA Attributes' not in df.columns or df['SGA Attributes'].isna().all():
        st.info("No SGA data has been imported for this year yet. An administrator can "
                "import the SGA tool's export from Admin Panel > 📂 Data Import/Export.")
        return True
    return False


def _codes(df):
    return set(df['New module code'].dropna().astype(str).str.strip().str.upper())


def _kpis(df, usage):
    mapped = int((df['SGA Attributes'] > 0).sum())
    total = len(df)
    mapped_df = df[df['SGA Attributes'] > 0]
    many = int((df['SGA Attributes'] > SGA_MODULE_MANY_ATTRIBUTES).sum())
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Modules with SGAs", f"{mapped} of {total}",
              f"{mapped / total:.0%}" if total else None, delta_color="off")
    c2.metric("Mean attributes per module",
              f"{mapped_df['SGA Attributes'].mean():.1f}" if mapped else "—",
              help="Across modules that have any SGAs mapped, out of 12 attributes.")
    c3.metric("Sub-attributes not used", f"{int(usage['gap'].sum())} of {len(usage)}",
              help="Sub-attributes that no module here claims.")
    c4.metric(f"Modules claiming over {SGA_MODULE_MANY_ATTRIBUTES} attributes", many,
              help="Modules mapping more attributes than this may be listing everything "
                   "the module touches rather than the few it develops.")


def _usage_chart(usage):
    """Horizontal bars: share of mapped modules claiming each sub-attribute,
    coloured by theme, in catalogue order so gaps show as missing bars."""
    data = usage.assign(
        pct=usage['share'] * 100,
        flag=usage.apply(lambda r: 'Not used' if r['gap']
                         else ('Concentrated' if r['concentrated'] else ''), axis=1),
        label=usage['attribute'] + ': ' + usage['sub_attribute'])
    order = data['label'].tolist()
    base = alt.Chart(data).encode(
        y=alt.Y('label:N', sort=order, title=None,
                axis=alt.Axis(labelLimit=320, labelFontSize=11)),
        tooltip=[alt.Tooltip('attribute:N', title='Attribute'),
                 alt.Tooltip('sub_attribute:N', title='Sub-attribute'),
                 alt.Tooltip('definition:N', title='Definition'),
                 alt.Tooltip('modules:Q', title='Modules'),
                 alt.Tooltip('pct:Q', title='% of mapped modules', format='.0f'),
                 alt.Tooltip('flag:N', title='Flag')])
    bars = base.mark_bar(cornerRadiusEnd=4, height=11).encode(
        x=alt.X('pct:Q', title='% of modules with SGAs', scale=alt.Scale(domain=[0, 100])),
        color=alt.Color('theme:N', scale=alt.Scale(domain=SGA_THEMES, range=THEME_COLOURS),
                        legend=alt.Legend(title='Theme', orient='top')))
    rule = alt.Chart(pd.DataFrame({'x': [SGA_CONCENTRATION_SHARE * 100]})).mark_rule(
        strokeDash=[4, 3], color='#888').encode(x='x:Q')
    st.altair_chart((bars + rule).properties(height=len(data) * 17), width="stretch")
    st.caption(f"Dashed line: {SGA_CONCENTRATION_SHARE:.0%} of mapped modules, the point at "
               "which a sub-attribute is flagged as concentrated. Hover a bar for its definition.")


def _gap_lists(usage):
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Not claimed by any module**")
        gaps = usage[usage['gap']]
        if gaps.empty:
            st.caption("Every sub-attribute is claimed at least once.")
        else:
            for attr, grp in gaps.groupby('attribute', sort=False):
                st.markdown(f"- {attr}: {', '.join(grp['sub_attribute'])}")
    with c2:
        st.markdown("**Most concentrated**")
        conc = usage[usage['concentrated']].sort_values('share', ascending=False)
        if conc.empty:
            st.caption(f"No sub-attribute is claimed by {SGA_CONCENTRATION_SHARE:.0%} or more "
                       "of mapped modules.")
        else:
            for _, r in conc.iterrows():
                st.markdown(f"- {r['sub_attribute']} ({r['attribute']}): "
                            f"{r['modules']} modules, {r['share']:.0%}")


def _status(attrs):
    if not attrs:
        return "❌ No SGAs"
    if attrs > SGA_MODULE_MANY_ATTRIBUTES:
        return "⚠️ Claims many"
    return ""


def render_school_sga(school_df, school):
    """School Dashboard's 🎓 Graduate Attributes view."""
    st.subheader(f"Sheffield Graduate Attributes: {school}")
    if _no_import(school_df):
        return
    df = school_df.copy()
    df['SGA Attributes'] = pd.to_numeric(df['SGA Attributes'], errors='coerce').fillna(0).astype(int)
    df['SGA Sub-Attributes'] = pd.to_numeric(df['SGA Sub-Attributes'], errors='coerce').fillna(0).astype(int)
    df_sga = _sga_frame()

    levels = sorted(v for v in df['UG/ PG/ Other'].dropna().astype(str).unique() if v) \
        if 'UG/ PG/ Other' in df.columns else []
    if levels:
        chosen = st.multiselect("Level", levels, default=levels, key="sga_school_levels")
        df = df[df['UG/ PG/ Other'].isin(chosen)]
    if df.empty:
        st.warning("No modules match this filter.")
        return

    usage = summarise_sga_usage(df_sga, _codes(df))
    _kpis(df, usage)
    st.divider()

    st.markdown("#### Spread across sub-attributes")
    if usage.attrs.get('mapped_modules', 0) == 0:
        st.info("None of these modules has SGAs mapped yet.")
    else:
        _usage_chart(usage)
        _gap_lists(usage)
    st.divider()

    st.markdown("#### Modules")
    table = df.assign(Status=df['SGA Attributes'].map(_status)).sort_values('New module code')
    cols = ['New module code', 'Module name', 'Mod. lead', 'UG/ PG/ Other',
            'SGA Attributes', 'SGA Sub-Attributes', 'SGA Attribute Names', 'Status']
    table = table[[c for c in cols if c in table.columns]]
    table['Mod. lead'] = table['Mod. lead'].astype(str).str.title()
    table = table.reset_index(drop=True)
    st.caption("Select a module (tick its checkbox) to jump to its report or audit.")
    selection = st.dataframe(
        table, hide_index=True, width="stretch",
        on_select="rerun", selection_mode="single-row", key="sga_school_modules_table",
        column_config={
            'New module code': 'Module Code', 'Module name': 'Module Name',
            'Mod. lead': 'Module Lead', 'UG/ PG/ Other': 'Level',
            'SGA Attributes': st.column_config.NumberColumn('Attributes', help="Of 12."),
            'SGA Sub-Attributes': st.column_config.NumberColumn('Sub-attributes', help="Of 36."),
            'SGA Attribute Names': 'Attributes mapped',
            'Status': st.column_config.TextColumn(
                'Flag', help=f"No SGAs: nothing mapped in the SGA tool. Claims many: more "
                             f"than {SGA_MODULE_MANY_ATTRIBUTES} of 12 attributes."),
        })

    rows = [i for i in selection.selection.rows if i < len(table)]
    if rows:
        code = table.iloc[rows[0]]['New module code']
        # pg_audit is only registered for edit_checklist holders, and
        # st.switch_page raises on an unregistered page.
        can_audit = any(c.lower() == "edit_checklist"
                        for c in st.session_state.get("capabilities", []))
        st.info(f"🚀 Quick Action Launch: **{code}**")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("📊 Jump to Report Card", width="stretch", type="primary",
                         key="btn_sga_rc"):
                _jump(code, school, st.session_state.pg_module)
        with c2:
            if can_audit and st.button("✅ Open Audit Portal", width="stretch",
                                       key="btn_sga_audit"):
                _jump(code, school, st.session_state.pg_audit)


def _jump(code, school, page):
    st.session_state.selected_module_code = code
    st.session_state.context_focus_own = False
    st.session_state.context_school = school
    st.switch_page(page)


def render_faculty_sga(active_df):
    """Faculty Overview's 🎓 Graduate Attributes view."""
    st.subheader("Sheffield Graduate Attributes")
    if _no_import(active_df):
        return
    df = active_df.copy()
    df['SGA Attributes'] = pd.to_numeric(df['SGA Attributes'], errors='coerce').fillna(0).astype(int)
    df['School'] = df['New module code'].astype(str).str[:3]
    df = df[df['School'].isin(FACULTY_SCHOOLS)]
    df_sga = _sga_frame()

    usage = summarise_sga_usage(df_sga, _codes(df))
    _kpis(df, usage)
    st.divider()

    st.markdown("#### Coverage by school")
    rows, cells, themes = [], [], []
    for school in FACULTY_SCHOOLS:
        sdf = df[df['School'] == school]
        if sdf.empty:
            continue
        mapped = sdf[sdf['SGA Attributes'] > 0]
        rows.append({
            'School': school, 'Modules': len(sdf), 'With SGAs': len(mapped),
            '% with SGAs': len(mapped) / len(sdf) * 100,
            'Mean attributes': mapped['SGA Attributes'].mean() if len(mapped) else None,
            'Claims many': int((sdf['SGA Attributes'] > SGA_MODULE_MANY_ATTRIBUTES).sum()),
        })
        s_usage = summarise_sga_usage(df_sga, _codes(sdf))
        cells.append(s_usage.assign(School=school, pct=s_usage['share'] * 100))
        claims = df_sga[df_sga['module_code'].isin(_codes(sdf))] if not df_sga.empty else df_sga
        if not claims.empty:
            counts = claims['theme'].value_counts()
            for theme in SGA_THEMES:
                themes.append({'School': school, 'Theme': theme,
                               'Share': counts.get(theme, 0) / counts.sum() * 100})
    st.dataframe(
        pd.DataFrame(rows), hide_index=True, width="stretch",
        column_config={
            '% with SGAs': st.column_config.NumberColumn(format="%.0f%%"),
            'Mean attributes': st.column_config.NumberColumn(
                format="%.1f", help="Across modules with any SGAs, out of 12."),
            'Claims many': st.column_config.NumberColumn(
                help=f"Modules mapping more than {SGA_MODULE_MANY_ATTRIBUTES} of 12 attributes."),
        })

    if usage.attrs.get('mapped_modules', 0) == 0:
        st.info("No module in this semester has SGAs mapped yet.")
        return

    st.markdown("#### Sub-attribute spread by school")
    st.caption("Share of each school's mapped modules claiming each sub-attribute. Blank "
               "cells are gaps; the darkest cells are where a sub-attribute is concentrated.")
    heat = pd.concat(cells, ignore_index=True)
    heat['label'] = heat['attribute'] + ': ' + heat['sub_attribute']
    label_order = [f"{r['attribute']}: {r['sub_attribute']}" for r in SGA_SUB_ATTRIBUTE_ROWS]
    chart = alt.Chart(heat).mark_rect(stroke='white', strokeWidth=2).encode(
        x=alt.X('School:N', sort=FACULTY_SCHOOLS, title=None, axis=alt.Axis(orient='top', labelAngle=0)),
        y=alt.Y('label:N', sort=label_order, title=None, axis=alt.Axis(labelLimit=320, labelFontSize=11)),
        color=alt.condition(
            'datum.modules > 0',
            alt.Color('pct:Q', scale=alt.Scale(scheme='blues', domain=[0, 100]),
                      legend=alt.Legend(title='% of mapped modules', orient='top')),
            alt.value('#f3f3f1')),
        tooltip=[alt.Tooltip('School:N'), alt.Tooltip('attribute:N', title='Attribute'),
                 alt.Tooltip('sub_attribute:N', title='Sub-attribute'),
                 alt.Tooltip('modules:Q', title='Modules'),
                 alt.Tooltip('pct:Q', title='% of mapped modules', format='.0f')])
    st.altair_chart(chart.properties(height=len(label_order) * 18), width="stretch")

    if themes:
        st.markdown("#### Theme balance")
        st.caption("How each school's sub-attribute claims split across the three themes.")
        theme_df = pd.DataFrame(themes)
        bars = alt.Chart(theme_df).mark_bar(height=18, stroke='white', strokeWidth=2).encode(
            y=alt.Y('School:N', sort=FACULTY_SCHOOLS, title=None),
            x=alt.X('Share:Q', stack='normalize', title='Share of sub-attribute claims',
                    axis=alt.Axis(format='%')),
            color=alt.Color('Theme:N', scale=alt.Scale(domain=SGA_THEMES, range=THEME_COLOURS),
                            sort=SGA_THEMES, legend=alt.Legend(orient='top')),
            order=alt.Order('theme_order:Q'),
            tooltip=['School', 'Theme', alt.Tooltip('Share:Q', format='.0f', title='% of claims')],
        ).transform_calculate(
            theme_order=f"indexof({SGA_THEMES!r}, datum.Theme)")
        st.altair_chart(bars.properties(height=len(theme_df['School'].unique()) * 30 + 20),
                        width="stretch")
