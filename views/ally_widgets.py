"""
Shared Ally rendering used by both the School Dashboard and Faculty Overview.

Kept in one place because the two views answer the same questions at different
scopes, and they used to drift apart whenever one was edited.

The rule these widgets exist to enforce: a score is only reported for courses
with content beyond their rolled-over template - a couple of files and a
couple of dozen editor pages - because Ally scores that template at close to
100%. Averaging those in would report the faculty as near-perfect every
autumn, before anyone has taught anything. There is no "finished" state:
module leads build just-in-time throughout the year, so nothing here ever
claims a course is complete, only that it has moved past its template.
"""
import altair as alt
import pandas as pd
import streamlit as st

from processing import (  # noqa: F401 - the first three re-exported for the views
    SCOREABLE_MATURITY, mean_score, scoreable, summarise_ally_issues,
    lens_accessibility_risk)

from report_model import SURFACE_LABELS, maturity_note

MATURITY_ORDER = ["In progress", "Not yet built", "Empty", "No data"]


def render_maturity_banner(df):
    """A one-line honesty statement about how much of the scope has content
    beyond its template yet."""
    note = maturity_note(df)
    if note:
        headline, rest = note.split(". ", 1)
        st.info(f"📋 **{headline}.** {rest}")


def render_maturity_breakdown(df, caption=None):
    """How much of the scope has moved past its template, as a bar chart."""
    if df is None or df.empty or 'Content Maturity' not in df.columns:
        st.info("No Ally data for this scope.")
        return
    counts = (df['Content Maturity'].value_counts()
              .reindex(MATURITY_ORDER).dropna().astype(int).reset_index())
    counts.columns = ['Stage', 'Modules']
    st.bar_chart(counts, x='Stage', y='Modules', color='#2563EB', height=260)
    st.caption(caption or
               "A course moves to 'In progress' once it holds more than a handful of "
               "uploaded files - rolled-over shells ship with about two. There is no "
               "'Built' stage: module leads add content throughout the course, often "
               "right up to the final assessment, so a file count can only show a "
               "course has started, never that it is finished.")


def render_issue_profile(df_issues, module_codes, top_n=12, key="issue_profile"):
    """
    Which accessibility problems dominate this scope, by items affected.

    Counted in content items rather than modules, because that is the size of
    the actual job: one workshop on PDF tagging can clear hundreds of items.
    """
    if df_issues is None or df_issues.empty:
        # No issue rows anywhere is almost always "nothing imported yet", not a
        # clean bill of health, and the two must not read the same.
        st.info("No Ally issue data has been imported yet. Load the institutional "
                "report from the Admin Panel.")
        return pd.DataFrame()

    profile = summarise_ally_issues(df_issues, module_codes=module_codes, top_n=top_n)
    if profile.empty:
        st.success("✅ Ally has found no accessibility issues in this scope.")
        return profile

    chart_df = profile[['label', 'items', 'severity_label', 'modules', 'surface', 'advice']].copy()
    chart_df['surface'] = chart_df['surface'].map(lambda s: SURFACE_LABELS.get(s, ''))
    chart_df.columns = ['Issue', 'Items affected', 'Severity', 'Modules affected',
                         'Where it gets fixed', 'What to do']

    # st.bar_chart (a thin Altair wrapper) truncates long category labels to a
    # fixed pixel width with no way to override it - full-sentence issue names
    # were unreadable. Built directly in Altair instead so labelLimit can be
    # lifted and the row order (severity first, then items affected) preserved
    # rather than re-sorted alphabetically. The explanation that used to live
    # in a separate expander below is folded into the tooltip instead, so the
    # detail sits on the bar it describes rather than in a second lookup.
    issue_order = chart_df['Issue'].tolist()
    chart = (
        alt.Chart(chart_df)
        .mark_bar()
        .encode(
            y=alt.Y('Issue:N', sort=issue_order, title=None,
                    axis=alt.Axis(labelLimit=1000, labelFontSize=12, labelPadding=8)),
            x=alt.X('Items affected:Q'),
            color=alt.Color('Severity:N',
                             scale=alt.Scale(
                                 domain=["Severe", "Major", "Minor", "Other"],
                                 range=["#7F1D1D", "#DC2626", "#F97316", "#EAB308"]),
                             legend=alt.Legend(title=None)),
            tooltip=['Issue', 'Severity', 'Items affected', 'Modules affected',
                     'Where it gets fixed', 'What to do'],
        )
        .properties(height=max(320, 34 * len(chart_df)))
    )
    st.altair_chart(chart, use_container_width=True)
    return profile


def build_accessibility_risk_list(df):
    """
    The accessibility priority list, ranked by harm rather than by score. The
    rule is processing.lens_accessibility_risk(), shared with the Django
    alignment page; this adds the Streamlit column configs.

    Returns (DataFrame, column_config, status_message, status_type) so the
    School and Faculty views can render it however they already do.
    """
    at_risk, note, status_type = lens_accessibility_risk(df)
    if at_risk is None:
        return None, {}, note, status_type
    # Left numeric and formatted by column_config rather than pre-formatted into
    # a string: st.dataframe sorts a text column lexicographically, which puts
    # "9.1%" above "94.9%" the moment a reader clicks the header. Same bug, and
    # the same fix, as the Ally Score column in views/school_dashboard.py.
    configs = {
        "New module code": "Code", "Module name": "Module Name", "Mod. lead": "Lead",
        "Severe": st.column_config.NumberColumn("Severe", format="%d",
                                                help="Content items that block access outright."),
        "Major": st.column_config.NumberColumn("Major", format="%d"),
        "Students": st.column_config.NumberColumn("Students", format="%d"),
        "Score": st.column_config.NumberColumn("Ally Overall", format="%.1f%%"),
    }
    return at_risk, configs, note, status_type
