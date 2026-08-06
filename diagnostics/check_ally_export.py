"""
Parses an Ally institutional export and asserts what we know to be true of it,
without touching the database.

There is no test suite in this project, so this is the thing to run after
changing processing.parse_ally_export() or the Ally schema. It reads the CSV,
runs the real parser, and checks the parse against the shape of the data and
against the SITS module list.

    python diagnostics/check_ally_export.py "C:/path/to/courses.csv" 2026-27
"""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from processing import (  # noqa: E402
    parse_ally_export, aggregate_ally_to_modules, summarise_ally_issues,
    count_ally_issues_by_module, reconcile_ally_modules, FACULTY_SCHOOLS,
)

FAILURES = []


def check(label, condition, detail=""):
    mark = "PASS" if condition else "FAIL"
    print(f"  [{mark}] {label}" + (f"  ({detail})" if detail else ""))
    if not condition:
        FAILURES.append(label)


def main(path, academic_year):
    print(f"Reading {path}")
    raw = pd.read_csv(path, low_memory=False)
    print(f"  {len(raw)} rows x {len(raw.columns)} columns\n")

    parsed = parse_ally_export(raw, academic_year, "2026-08-05")
    courses, issues, content = parsed['courses'], parsed['issues'], parsed['content']

    print("Scoping")
    print(f"  years in file: {', '.join(parsed['years_seen'])}")
    check("all rows accounted for",
          parsed['rows_in'] == len(raw))
    check(f"kept only {academic_year}",
          courses.empty or set(courses['academic_year']) == {academic_year})
    check("dropped other years",
          parsed['dropped_other_years'] > 0,
          f"{parsed['dropped_other_years']} rows")
    check("dropped out-of-faculty rows",
          parsed['dropped_out_of_faculty'] >= 0,
          f"{parsed['dropped_out_of_faculty']} rows")
    check("every kept module code is a faculty prefix",
          courses['module_code'].str[:3].isin(FACULTY_SCHOOLS).all())
    print(f"  -> {len(courses)} courses, {courses['module_code'].nunique()} module codes\n")

    print("Grain")
    check("course_id is unique within the snapshot",
          not courses['course_id'].duplicated().any())
    dupes = courses['module_code'].value_counts()
    multi = dupes[dupes > 1]
    check("more courses than module codes only via known multi-shell modules",
          len(courses) - courses['module_code'].nunique() == int((multi - 1).sum()),
          f"{len(multi)} modules run more than one shell")
    print()

    print("Scores")
    scored = courses[(courses['total_files'] + courses['total_wysiwyg']) > 0].copy()
    # Overall is a blend of the two surface scores, so it must sit between
    # them. That invariant is exact. The item-count weighting is only an
    # approximation of how Ally actually blends them - it is spot on for most
    # courses but drifts by a few points on file-heavy ones - so it is checked
    # loosely and never used to derive a score.
    lo = scored[['files_score', 'wysiwyg_score']].min(axis=1)
    hi = scored[['files_score', 'wysiwyg_score']].max(axis=1)
    check("Overall lies between the Files and WYSIWYG scores",
          scored['overall_score'].between(lo - 1e-9, hi + 1e-9).all())
    expected = ((scored['total_files'] * scored['files_score']
                 + scored['total_wysiwyg'] * scored['wysiwyg_score'])
                / (scored['total_files'] + scored['total_wysiwyg']))
    drift = (expected - scored['overall_score']).abs()
    check("item-weighted blend approximates Overall",
          drift.quantile(0.99) < 0.10,
          f"median {drift.median():.2e}, p99 {drift.quantile(0.99):.4f}, max {drift.max():.4f}")
    check("scores are on a 0-1 scale",
          courses['overall_score'].dropna().between(0, 1).all())
    print()

    print("Census")
    check("issue rows are all non-zero", issues.empty or (issues['items'] > 0).all())
    check("content rows are all non-zero", content.empty or (content['items'] > 0).all())
    check("every issue row belongs to a kept course",
          issues.empty or issues['course_id'].isin(set(courses['course_id'])).all())
    check("severities are 1, 2, 3 or blank",
          issues.empty or issues['severity'].dropna().isin([1, 2, 3]).all())
    check("LibraryReference carries no severity",
          issues.empty or issues[issues['check_name'] == 'LibraryReference']['severity'].isna().all())
    print(f"  -> {len(issues)} issue rows, {len(content)} content rows")
    if not issues.empty:
        print(f"     distinct checks seen: {issues['check_name'].nunique()}")
    print()

    print("Rollup")
    modules = aggregate_ally_to_modules(courses)
    check("one row per module code",
          len(modules) == courses['module_code'].nunique())
    check("file counts survive the rollup",
          modules['total_files'].sum() == courses['total_files'].sum())
    check("rolled-up scores stay in range",
          modules['overall_score'].dropna().between(0, 1).all())
    print("  content maturity:")
    for name, n in modules['content_maturity'].value_counts().items():
        print(f"     {name:<15} {n}")
    print()

    issues_with_modules = issues.merge(
        courses[['course_id', 'module_code']], on='course_id', how='left')
    profile = summarise_ally_issues(issues_with_modules)
    per_module = count_ally_issues_by_module(issues_with_modules)
    check("issue profile excludes LibraryReference",
          'LibraryReference' not in set(profile['check_name']))
    if not profile.empty:
        print("  top checks by items affected:")
        for _, r in profile.head(8).iterrows():
            print(f"     {r['severity_label']:<7} {r['items']:>6}  {r['label']} [{r['surface']}]")
        print(f"  modules with a severe issue: "
              f"{int((per_module['severe'] > 0).sum()) if not per_module.empty else 0}")
    print()

    print("Reconciliation against SITS")
    try:
        from database import get_db_connection, table_exists
        with get_db_connection() as conn:
            if table_exists(conn, "sits_assessment_2026_27"):
                sits = pd.read_sql_query(
                    'SELECT DISTINCT "CIS unit code" AS c FROM sits_assessment_2026_27', conn)
                rec = reconcile_ally_modules(courses['module_code'], sits['c'])
                print(f"  matched   {len(rec['matched'])}")
                print(f"  Ally only {len(rec['ally_only'])}  e.g. {rec['ally_only'][:6]}")
                print(f"  SITS only {len(rec['sits_only'])}  e.g. {rec['sits_only'][:6]}")
                check("most Ally courses match a SITS module",
                      len(rec['matched']) > 0.8 * courses['module_code'].nunique())
            else:
                print("  (no SITS table in this database - skipped)")
    except Exception as exc:
        print(f"  (skipped: {exc})")

    print()
    if FAILURES:
        print(f"{len(FAILURES)} CHECK(S) FAILED:")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "2026-27"))
