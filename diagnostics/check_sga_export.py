"""
Parses an SGA tool export and reports what an import would do, without
touching the database.

Run it against every new export before importing, and to re-tune the
SGA_CONCENTRATION_SHARE / SGA_MODULE_MANY_ATTRIBUTES thresholds in
processing.py: it prints the attributes-per-module distribution and how often
each sub-attribute is claimed.

    python diagnostics/check_sga_export.py "C:/path/to/sga_export.csv"
"""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from processing import (  # noqa: E402
    parse_sga_export, explode_sga_mappings, aggregate_sga_to_modules, summarise_sga_usage,
    SGA_CONCENTRATION_SHARE, SGA_MODULE_MANY_ATTRIBUTES, CURRENT_ACADEMIC_YEAR,
    school_series,
)

FAILURES = []


def check(label, condition, detail=""):
    mark = "PASS" if condition else "FAIL"
    print(f"  [{mark}] {label}" + (f"  ({detail})" if detail else ""))
    if not condition:
        FAILURES.append(label)


def main(path):
    print(f"Reading {path}")
    raw = pd.read_csv(path, dtype=str, keep_default_na=False)
    print(f"  {len(raw)} rows x {len(raw.columns)} columns")
    print(f"  Years in file: {sorted(raw['Year'].unique()) if 'Year' in raw else 'no Year column'}\n")

    parsed = parse_sga_export(raw)
    mappings = parsed['mappings']

    print("Scope")
    check(f"Rows kept for {CURRENT_ACADEMIC_YEAR}", not mappings.empty,
          f"{parsed['rows_in']} read, {parsed['dropped_wrong_year']} other years, "
          f"{parsed['dropped_out_of_faculty']} outside faculty")
    check("Every name matches the SGA framework", not parsed['unknown'],
          f"{len(parsed['unknown'])} problem(s)")
    for u in parsed['unknown'][:40]:
        print(f"      {u['module_code']}: '{u['value']}' under '{u['attribute']}' - {u['problem']}")
    if mappings.empty:
        return

    long = explode_sga_mappings(mappings)
    modules = aggregate_sga_to_modules(long)
    print(f"\n{len(modules)} modules, {len(mappings)} attribute rows, "
          f"{len(long)} module x sub-attribute claims")
    print(f"  Calendar codes: {mappings['calendar_code'].value_counts().to_dict()}")
    multi = mappings.groupby('module_code')['calendar_code'].nunique()
    print(f"  Modules listed under more than one calendar code: {int((multi > 1).sum())}")

    print("\nAttributes per module (of 12)")
    dist = modules['sga_attributes'].value_counts().sort_index()
    for n, count in dist.items():
        flag = "  <- claims many" if n > SGA_MODULE_MANY_ATTRIBUTES else ""
        print(f"  {n:>2}: {count:>4}{flag}")

    print("\nSub-attribute claims (share of mapped modules)")
    usage = summarise_sga_usage(long, modules['module_code'])
    for _, r in usage.iterrows():
        flag = " GAP" if r['gap'] else (" CONCENTRATED" if r['concentrated'] else "")
        print(f"  {r['attribute'][:30]:<30} {r['sub_attribute']:<24} "
              f"{r['modules']:>4}  {r['share']:>5.0%}{flag}")
    print(f"\n  Thresholds: concentrated >= {SGA_CONCENTRATION_SHARE:.0%}, "
          f"claims many > {SGA_MODULE_MANY_ATTRIBUTES} attributes")

    by_school = modules.assign(school=school_series(modules['module_code'])).groupby('school')
    print("\nBy school: modules with SGAs, mean attributes")
    for school, grp in by_school:
        print(f"  {school}: {len(grp):>4}  {grp['sga_attributes'].mean():.1f}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    main(sys.argv[1])
    print(f"\n{len(FAILURES)} check(s) failed." if FAILURES else "\nAll checks passed.")
    sys.exit(1 if FAILURES else 0)
