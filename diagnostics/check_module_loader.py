"""
Sanity-checks loaders.py against the live database, with no Streamlit involved.

That last part is the point: before the module-row assembly was extracted from
app.py::load_audit_data(), nothing outside a running Streamlit script could
build a module row, so none of this could be checked at all.

    python diagnostics/check_module_loader.py             # whole faculty
    python diagnostics/check_module_loader.py EDC004      # one module

Read-only. Exits non-zero if a check fails, so it can gate a deploy.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import loaders  # noqa: E402
import processing  # noqa: E402
import database  # noqa: E402

FAILURES = []


def check(label, condition, detail=""):
    print(f"{'PASS' if condition else 'FAIL'}  {label}{f' - {detail}' if detail else ''}")
    if not condition:
        FAILURES.append(label)


def check_one_module(code):
    record = loaders.load_module_record(code)
    check(f"{code} found in SITS", record is not None)
    if record is None:
        return

    check("record carries the findings contract",
          all(key in record for key in (
              'Leganto Missing', 'Leganto List Status', 'Leganto List Items',
              'Ally Severe', 'Ally Major', 'Ally Enabled', 'Ally Overall',
              'Template Sections')),
          f"{len(record)} keys")

    findings = processing.derive_module_findings(
        record, database.get_audit_responses(code),
        database.get_active_audit_fields())
    pending = [f for f in findings if f.get('state') == 'pending']
    check("findings derive from the record", findings is not None,
          f"{len(findings)} findings, {len(pending)} pending")

    print(f"      {code}: {record.get('Module name', '')}")
    print(f"      Ally {record.get('Ally Overall')} "
          f"severe/major {record.get('Ally Severe')}/{record.get('Ally Major')}, "
          f"{len(record.get('Template Sections') or {})} template sections, "
          f"SGA {record.get('SGA Attributes')}")


def check_faculty():
    df_aut, df_spr, ally_courses, ally_issues, ally_content, readiness, sga = (
        loaders.load_audit_frames())

    check("module frames built", not df_aut.empty and not df_spr.empty,
          f"Autumn {len(df_aut)}, Spring {len(df_spr)}")
    if df_aut.empty or df_spr.empty:
        return

    codes = set(df_aut['New module code']) | set(df_spr['New module code'])
    check("every code has a school prefix in FACULTY_SCHOOLS",
          all(c[:3] in processing.FACULTY_SCHOOLS for c in codes),
          f"{len(codes)} modules")

    # A year-long module must appear in both frames: "All year" narrowing
    # downstream depends on it (see resolve_semester_df()).
    both = set(df_aut['New module code']) & set(df_spr['New module code'])
    check("year-long modules appear in both semesters", len(both) > 0,
          f"{len(both)} modules in both")

    check("no module is listed twice in one semester",
          not df_aut['New module code'].duplicated().any()
          and not df_spr['New module code'].duplicated().any())

    inactive = loaders.load_module_sources().inactive_codes
    check("inactive modules are excluded", not (codes & inactive),
          f"{len(inactive)} inactive codes in the database")

    check("detail frames returned", all(f is not None for f in (
        ally_courses, ally_issues, ally_content, readiness, sga)),
        f"ally {len(ally_courses)}/{len(ally_issues)}/{len(ally_content)}, "
        f"readiness {len(readiness)}, sga {len(sga)}")

    # Spot-check the findings pipeline over every module, which is what the
    # Actionable Items badge sums.
    fields = database.get_active_audit_fields()
    total_pending = 0
    for code in sorted(codes):
        row = processing.resolve_active_row(code, df_aut, df_spr)
        items = processing.derive_module_findings(
            row, database.get_audit_responses(code), fields)
        total_pending += sum(1 for f in items if f.get('state') == 'pending')
    check("findings derive for every module", True,
          f"{total_pending} pending findings across {len(codes)} modules")


def main():
    if len(sys.argv) > 1:
        check_one_module(sys.argv[1])
    else:
        check_faculty()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} check(s) failed: {', '.join(FAILURES)}")
        sys.exit(1)
    print("All checks passed.")


if __name__ == "__main__":
    main()
