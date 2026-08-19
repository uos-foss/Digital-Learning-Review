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

from processing import summarise_ally_issues

# Maturity classes whose scores are worth reporting. See
# processing.classify_content_maturity for how a course lands in one - there
# is no "Built" class to include here, because a file count can only ever
# show a course has started, never that it is finished.
SCOREABLE_MATURITY = ("In progress",)

MATURITY_ORDER = ["In progress", "Not yet built", "Empty", "No data"]
SURFACE_LABELS = {
    'editor': "Fix in the Blackboard editor",
    'image': "Fix in the browser via Ally feedback",
    'file': "Re-author and re-upload the file",
}


def scoreable(df):
    """The rows whose Ally score means something. Empty frame in, empty out."""
    if df is None or df.empty or 'Content Maturity' not in df.columns:
        return pd.DataFrame()
    return df[df['Content Maturity'].isin(SCOREABLE_MATURITY)]


def mean_score(df, column='Ally Overall'):
    """Mean of a score column across built courses only, or None."""
    subset = scoreable(df)
    if subset.empty or column not in subset.columns:
        return None
    values = pd.to_numeric(subset[column], errors='coerce').dropna()
    return float(values.mean()) if not values.empty else None


def render_maturity_banner(df):
    """A one-line honesty statement about how much of the scope has content
    beyond its template yet."""
    if df is None or df.empty or 'Content Maturity' not in df.columns:
        return
    counts = df['Content Maturity'].value_counts()
    started = int(counts.get("In progress", 0))
    total = int(len(df))
    if total and started / total < 0.5:
        st.info(
            f"📋 **{started} of {total} modules have content beyond their template.** "
            "Accessibility scores below cover only those; the rest are reported as "
            "build progress instead, because scoring an empty template says nothing "
            "about the module."
        )


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
    The accessibility priority list, ranked by harm rather than by score.

    Replaces a flat "below 70%" cut, which ranked a module with four students
    above one with four hundred and — now that the year rolls over with every
    course at template content — would have been swamped by untouched shells
    scoring 99%. Untouched shells are excluded outright: there is nothing to
    remediate in a course nobody has started populating yet.

    Returns (DataFrame, column_config, status_message, status_type) so the
    School and Faculty views can render it however they already do.
    """
    if df is None or df.empty:
        return None, {}, "No modules in scope.", "info"

    scope = scoreable(df)
    skipped = len(df) - len(scope)
    if scope.empty:
        return (None, {},
                "No courses have content beyond their template yet, so there is nothing "
                "to remediate. Build progress is the thing to watch at this stage.", "info")

    work = scope.copy()
    work['_severe'] = pd.to_numeric(work.get('Ally Severe'), errors='coerce').fillna(0)
    work['_major'] = pd.to_numeric(work.get('Ally Major'), errors='coerce').fillna(0)
    work['_students'] = pd.to_numeric(work.get('Ally Students'), errors='coerce').fillna(0)
    work['_score'] = pd.to_numeric(work.get('Ally Overall'), errors='coerce')

    at_risk = work[(work['_severe'] > 0) | (work['_major'] > 0) | (work['_score'] < 0.7)]
    if at_risk.empty:
        return (None, {},
                f"No accessibility risks found across {len(scope)} module(s) with content.",
                "success")

    # Severe first, then how many students meet it, then how much major work sits
    # behind it. Score alone is a poor ranking: a module can score well overall
    # and still hide an unreadable scanned document.
    at_risk = at_risk.sort_values(['_severe', '_students', '_major'], ascending=False)
    at_risk['Score'] = at_risk['_score'].apply(lambda x: f"{x:.1%}" if pd.notna(x) else "")
    at_risk['Severe'] = at_risk['_severe'].astype(int)
    at_risk['Major'] = at_risk['_major'].astype(int)
    at_risk['Students'] = at_risk['_students'].astype(int)

    cols = [c for c in ['New module code', 'Module name', 'Mod. lead',
                        'Severe', 'Major', 'Students', 'Score'] if c in at_risk.columns]
    configs = {
        "New module code": "Code", "Module name": "Module Name", "Mod. lead": "Lead",
        "Severe": st.column_config.NumberColumn("Severe", format="%d",
                                                help="Content items that block access outright."),
        "Major": st.column_config.NumberColumn("Major", format="%d"),
        "Students": st.column_config.NumberColumn("Students", format="%d"),
        "Score": st.column_config.TextColumn("Ally Overall"),
    }
    note = f"🎯 {len(at_risk)} module(s) with content need accessibility work, worst first."
    if skipped:
        note += f" {skipped} module(s) not yet started are excluded."
    return at_risk[cols].reset_index(drop=True), configs, note, "warning"
    st.caption("Severe issues are unreadable scans, corrupt files, documents locked "
               "against screen readers, and images that can trigger seizures. These "
               "block access outright rather than making it harder.")
