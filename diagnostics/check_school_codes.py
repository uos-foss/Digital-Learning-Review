"""
Checks that every module code in the database is normalised, and that
processing.school_of() agrees with the raw prefix slices it replaced.

Written when ~20 copies of the "first three characters" rule were replaced by
`school_of()` / `school_series()` / `is_faculty_code()` on 05-10-2026. Those
copies disagreed about normalisation: some sliced the raw value, some
uppercased and stripped first. The helpers always normalise, which is only a
no-op while the stored codes are already stripped and uppercase. This asserts
that, so a future import that writes ' edc004 ' is caught here rather than by
a school quietly losing modules from its totals.

    python diagnostics/check_school_codes.py

Read-only. Exits non-zero on failure.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd  # noqa: E402

import database  # noqa: E402
from processing import (FACULTY_SCHOOLS, is_faculty_code, school_of,  # noqa: E402
                        school_series)

# Tables holding module codes, and the candidate column names across them.
TABLES = [
    'sits_assessment_2026_27', 'ally_courses', 'readiness_courses',
    'leganto_lists', 'leganto_nolist', 'sga_mappings', 'audit_responses',
    'spot_checks', 'main_vle_audit_aut', 'main_vle_audit_spr',
    'inactive_modules', 'blackboard_links', 'module_lead_overrides',
]
CODE_COLUMNS = ['module_code', 'course_code', 'CIS unit code', 'New module code']

FAILURES = []


def check(label, condition, detail=""):
    print(f"{'PASS' if condition else 'FAIL'}  {label}{f' - {detail}' if detail else ''}")
    if not condition:
        FAILURES.append(label)


def code_columns():
    """Every (table, column, Series of codes) pair present in the database."""
    found = []
    with database.get_db_connection() as conn:
        for table in TABLES:
            if not database.table_exists(conn, table):
                continue
            cols = [row[1] for row in conn.execute(f"PRAGMA table_info({table})")]
            col = next((c for c in CODE_COLUMNS if c in cols), None)
            if col is None:
                continue
            codes = pd.read_sql_query(
                f"SELECT [{col}] AS code FROM {table}", conn)['code']
            found.append((table, col, codes.dropna().astype(str)))
    return found


def main():
    columns = code_columns()
    check("code columns found", bool(columns), f"{len(columns)} tables")
    if not columns:
        sys.exit(1)

    total = 0
    unnormalised = {}
    mismatches = {}
    outside = {}

    for table, col, codes in columns:
        total += len(codes)

        odd = codes[codes != codes.str.strip().str.upper()]
        if not odd.empty:
            unnormalised[f"{table}.{col}"] = list(odd.unique())[:5]

        # The helper against the raw slice each old call site used.
        helper = school_series(codes)
        raw_slice = codes.str[:3]
        upper_slice = codes.astype(str).str[:3].str.upper()
        if not helper.equals(raw_slice) or not helper.equals(upper_slice):
            differing = codes[helper != raw_slice]
            mismatches[f"{table}.{col}"] = list(differing.unique())[:5]

        # Scalar and vectorised forms must agree with each other.
        sample = codes.head(500)
        if any(school_of(c) != school_series(pd.Series([c])).iloc[0] for c in sample):
            mismatches[f"{table}.{col} (scalar)"] = ["school_of disagrees with school_series"]

        # is_faculty_code against the isin() it replaced.
        if not is_faculty_code(codes).equals(raw_slice.isin(FACULTY_SCHOOLS)):
            outside[f"{table}.{col}"] = list(
                codes[~is_faculty_code(codes)].unique())[:5]

    check("every stored code is already stripped and uppercase",
          not unnormalised, str(unnormalised) if unnormalised else f"{total} codes")
    check("school_series matches the raw prefix slice it replaced",
          not mismatches, str(mismatches) if mismatches else "")
    check("is_faculty_code matches the isin() it replaced",
          not outside, str(outside) if outside else "")

    check("school_of handles blanks and missing values",
          school_of(None) == '' and school_of('') == ''
          and school_of(float('nan')) == '' and school_of(' edc004 ') == 'EDC',
          "None/''/NaN give '', ' edc004 ' gives EDC")

    print()
    if FAILURES:
        print(f"{len(FAILURES)} check(s) failed: {', '.join(FAILURES)}")
        sys.exit(1)
    print("All checks passed.")


if __name__ == "__main__":
    main()
