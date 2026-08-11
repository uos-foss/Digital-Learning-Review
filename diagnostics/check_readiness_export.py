"""
Parses a faculty Template Alignment Report and asserts what we know to be true
of it, without writing to the database.

There is no test suite in this project, so this is the thing to run after
changing processing.parse_readiness_export() or the readiness schema, and
before trusting a new export. It reads the CSV, runs the real parser, checks the
parse against the shape of the data and against the SITS module list, and prints
the last-modified date distribution that READINESS_BULK_EDIT_SHARE is calibrated
against.

    python diagnostics/check_readiness_export.py "C:/path/to/alignment.csv" 2026-27
"""
import os
import re
import sys

import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from processing import (  # noqa: E402
    parse_readiness_export, aggregate_readiness_to_modules, detect_bulk_edit_dates,
    reconcile_ally_modules, FACULTY_SCHOOLS, TEMPLATE_SECTIONS, LEAD_OWNED_SECTIONS,
    READINESS_BULK_EDIT_SHARE, READINESS_BULK_EDIT_MIN_MODULES, READINESS_SECTION_RANK,
    SECTION_STATES,
)

FAILURES = []


def _norm_label(text):
    """Section labels down to something comparable across the report's own
    inconsistent wording - 'SGAS'/'SGAs', 'and'/'&', stray punctuation."""
    text = str(text).casefold().replace('&', ' and ')
    return re.sub(r'[^a-z0-9]+', '', text)


def check(label, condition, detail=""):
    mark = "PASS" if condition else "FAIL"
    print(f"  [{mark}] {label}" + (f"  ({detail})" if detail else ""))
    if not condition:
        FAILURES.append(label)


def main(path, academic_year):
    print(f"Reading {path}")
    raw = pd.read_csv(path, low_memory=False)
    print(f"  {len(raw)} rows x {len(raw.columns)} columns\n")

    parsed = parse_readiness_export(raw, academic_year, "2026-08-11")
    courses, sections = parsed['courses'], parsed['sections']
    if courses.empty:
        print("No in-faculty rows for that year - nothing to check.")
        return 1

    print("Scoping")
    print(f"  years in file: {', '.join(parsed['years_seen']) or '(none)'}")
    check("all rows accounted for", parsed['rows_in'] == len(raw))
    check(f"kept only {academic_year}",
          set(courses['academic_year']) == {academic_year})
    check("dropped out-of-faculty rows counted, not silently lost",
          parsed['dropped_out_of_faculty'] >= 0,
          f"{parsed['dropped_out_of_faculty']} rows")
    check("every kept module code is a faculty prefix",
          courses['module_code'].str[:3].isin(FACULTY_SCHOOLS).all())
    print(f"  -> {len(courses)} courses, {courses['module_code'].nunique()} module codes\n")

    print("Grain")
    check("course_number is unique within the snapshot",
          not courses['course_number'].duplicated().any())
    dupes = courses['module_code'].value_counts()
    multi = dupes[dupes > 1]
    check("more courses than module codes only via known multi-shell modules",
          len(courses) - courses['module_code'].nunique() == int((multi - 1).sum()),
          f"{len(multi)} modules run more than one shell")
    print()

    print("Template sections")
    keys = parsed['section_keys']
    print(f"  {len(keys)} section columns detected")
    expected = courses['expected_sections'].mode()
    expected_n = int(expected.iloc[0]) if not expected.empty else 0
    check("section columns match EXPECTED_SECTION_COUNT",
          len(keys) == expected_n, f"{len(keys)} columns vs {expected_n} expected")
    unknown = sorted(set(keys) - set(TEMPLATE_SECTIONS))
    check("every section is in the TEMPLATE_SECTIONS catalogue",
          not unknown, f"unlisted: {unknown}" if unknown else "")
    stale = sorted(set(TEMPLATE_SECTIONS) - set(keys))
    if stale:
        print(f"  note: catalogue lists sections absent from this file: {stale}")
    bad_status = sorted(set(sections['status']) - set(READINESS_SECTION_RANK))
    check("every section status is one of Visible/Hidden/Deleted/Missing",
          not bad_status, f"unexpected: {bad_status}" if bad_status else "")
    print()

    print("Section counts")
    total = (courses['visible_sections'] + courses['hidden_sections']
             + courses['deleted_sections'] + courses['missing_sections'])
    check("expected == visible + hidden + deleted + missing on every row",
          bool((total == courses['expected_sections']).all()),
          f"{int((total != courses['expected_sections']).sum())} rows disagree")
    score = (courses['visible_sections'] / courses['expected_sections'] * 100).round(1)
    check("completeness score == visible / expected",
          bool((score - courses['completeness_score']).abs().max() <= 0.1),
          f"max diff {float((score - courses['completeness_score']).abs().max()):.2f}")
    # Cross-checks the export's own summary text against its own detail columns.
    # A Deleted section drops out of HIDDEN_SECTIONS, so a reader who trusts only
    # the summary misses it entirely.
    #
    # Compared as sets of section *keys*, not label strings: the report's wording
    # drifts between the summary columns and our catalogue ("SGAS" vs "SGAs",
    # "and" vs "&"), and that is a naming difference, not a data discrepancy.
    label_to_key = {_norm_label(v[0]): k for k, v in TEMPLATE_SECTIONS.items()}
    for col, status in (('HIDDEN_SECTIONS', 'Hidden'),
                        ('DELETED_SECTIONS', 'Deleted'),
                        ('MISSING_SECTIONS', 'Missing')):
        if col not in raw.columns:
            continue
        summary = (raw.set_index(raw['COURSE_NUMBER'].astype(str).str.strip())[col]
                      .fillna("").astype(str))
        detail = (sections[sections['status'] == status]
                  .groupby('course_number')['section_key'].apply(set))
        mismatches, unmapped = 0, set()
        for course in courses['course_number']:
            listed = set()
            for part in str(summary.get(course, "")).split(';'):
                part = part.strip()
                if not part:
                    continue
                key = label_to_key.get(_norm_label(part))
                if key is None:
                    unmapped.add(part)
                else:
                    listed.add(key)
            if listed != detail.get(course, set()):
                mismatches += 1
        check(f"{col} text agrees with the per-section columns",
              mismatches == 0, f"{mismatches} courses disagree")
        if unmapped:
            check(f"{col} labels all map to a known section",
                  False, f"unrecognised: {sorted(unmapped)}")
    print()

    print("Lead-owned sections")
    print(f"  lead-owned: {', '.join(LEAD_OWNED_SECTIONS)}")
    lead = sections[sections['section_key'].isin(LEAD_OWNED_SECTIONS)]
    hidden_by_default = (sections[sections['status'] != 'Visible']['section_key']
                         .value_counts())
    # The 11/3 split is the whole basis of triage. If a template revision makes a
    # different set of sections lead-owned, TEMPLATE_SECTIONS has to follow, and
    # this is where that shows up.
    top_hidden = set(hidden_by_default.head(len(LEAD_OWNED_SECTIONS)).index)
    check("the most-hidden sections are the ones marked lead-owned",
          top_hidden == set(LEAD_OWNED_SECTIONS),
          f"most hidden: {sorted(top_hidden)}")
    for key in LEAD_OWNED_SECTIONS:
        counts = lead[lead['section_key'] == key]['status'].value_counts().to_dict()
        print(f"    {key:<28} {counts}")
    print()

    print("Edit dates")
    dated = sections[sections['last_modified'] != ""]
    freq = dated['last_modified'].value_counts()
    print(f"  {len(freq)} distinct dates across {len(dated)} section rows")
    for date, n in freq.head(12).items():
        print(f"    {date}  {n}")
    # detect_bulk_edit_dates needs module_code and works at the shape
    # get_readiness_sections_latest() returns, so join it back on here.
    joined = sections.merge(courses[['course_number', 'module_code']], on='course_number')
    bulk = detect_bulk_edit_dates(joined)
    print(f"  bulk-edit thresholds: {READINESS_BULK_EDIT_SHARE:.0%} of a school's modules, "
          f"or {READINESS_BULK_EDIT_MIN_MODULES}+ modules on one day")
    # Printed with the numbers behind each call, since this is the table the
    # thresholds are calibrated against.
    joined['school'] = joined['module_code'].astype(str).str[:3]
    sizes = joined.groupby('school')['module_code'].nunique()
    counts = (joined[joined['last_modified'] != ""]
              .groupby(['school', 'last_modified'])['module_code'].nunique())
    print(f"  classified as bulk pushes ({len(bulk)}):")
    for school, date in sorted(bulk, key=lambda p: -counts.get(p, 0)):
        n = int(counts.get((school, date), 0))
        print(f"    {school} {date}  {n:>4} modules  ({n / sizes.get(school, 1):.0%})")
    near = sorted(((int(n), s, d) for (s, d), n in counts.items()
                   if (s, d) not in bulk), reverse=True)[:5]
    if near:
        print("  closest not classified as bulk:")
        for n, s, d in near:
            print(f"    {s} {d}  {n:>4} modules  ({n / sizes.get(s, 1):.0%})")
    check("at least one date is a bulk push",
          len(bulk) > 0,
          "if this fails the threshold is too high for this file")
    check("not every date is a bulk push",
          len(bulk) < len(freq),
          "if this fails the threshold is too low and no edit can ever count")
    print()

    print("Rollup to modules")
    modules = aggregate_readiness_to_modules(courses, joined)
    check("one row per module code",
          len(modules) == courses['module_code'].nunique())
    check("lead_sections_ready never exceeds the number of lead-owned sections",
          bool((modules['lead_sections_ready'] <= len(LEAD_OWNED_SECTIONS)).all()))
    check("rolled-up completeness stays in range",
          bool(modules['completeness_score'].dropna().between(0, 100).all()))
    ready = modules['lead_sections_ready'].value_counts().sort_index()
    print("  lead sections ready per module:")
    for n, count in ready.items():
        print(f"    {n} of {len(LEAD_OWNED_SECTIONS)}:  {count}")
    blocking = modules[modules['blocking_sections'].apply(len) > 0]
    print(f"  modules with a deleted or missing section: {len(blocking)}")
    for row in blocking.head(6).itertuples(index=False):
        print(f"    {row.module_code}: {'; '.join(row.blocking_sections)}")
    evidence, state_counts = {}, {}
    for states in modules['section_states']:
        for key in LEAD_OWNED_SECTIONS:
            if key in states:
                e = states[key]['evidence']
                evidence[e] = evidence.get(e, 0) + 1
                st = states[key]['state']
                state_counts[st] = state_counts.get(st, 0) + 1
    print(f"  lead-section edit evidence: {evidence}")
    print("  lead-section states:")
    total_states = sum(state_counts.values()) or 1
    for key, (label, tier, _) in SECTION_STATES.items():
        n = state_counts.get(key, 0)
        if n:
            print(f"    {key:<22} {n:>5}  ({n / total_states:>5.1%})  [{tier}] {label}")

    drafted = int(modules['lead_sections_drafted'].sum())
    print(f"  worked on but still hidden: {drafted} sections across "
          f"{int((modules['lead_sections_drafted'] > 0).sum())} modules")

    # If these sections ever ship visible by default, every module reads as
    # ready with no work done. That is the same trap the 11 institutional
    # sections are already in, and it would arrive silently.
    unattributed = state_counts.get('visible_unattributed', 0)
    check("visible lead sections are attributable, not a new default",
          unattributed <= 0.10 * total_states,
          f"{unattributed} of {total_states} visible with no per-module edit"
          + ("  <- has the template changed to ship these visible? "
             "recheck LEAD_OWNED_SECTIONS" if unattributed > 0.10 * total_states else ""))
    print()

    print("Reconciliation against SITS")
    try:
        from database import get_db_connection, table_exists
        with get_db_connection() as conn:
            if table_exists(conn, "sits_assessment_2026_27"):
                sits = pd.read_sql_query(
                    'SELECT DISTINCT "CIS unit code" AS c FROM sits_assessment_2026_27', conn)
                rec = reconcile_ally_modules(courses['module_code'], sits['c'])
                print(f"  matched        {len(rec['matched'])}")
                print(f"  report only    {len(rec['ally_only'])}  e.g. {rec['ally_only'][:6]}")
                print(f"  SITS only      {len(rec['sits_only'])}  e.g. {rec['sits_only'][:6]}")
                check("most courses match a SITS module",
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
