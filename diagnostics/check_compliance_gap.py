"""
Diagnoses why calculate_dynamic_compliance_gap() (the "Template Alignment"
tab on Faculty Overview / School Dashboard) shows 0.0% for a school.

That function's denominator (total_modules) and numerator (compliant_count)
are BOTH scoped to module codes found in sits_assessment_2026_27 - a module
with a real, ticked audit response is only counted if its code also appears
in that table. This script reports, per school, how many SITS-listed modules
actually have any audit_responses row at all, and how many audited modules
are missing from SITS entirely (and so are silently excluded from the gap
calc no matter how they were answered). Run this against the real database
to tell "no audits exist for this school" apart from "audits exist but don't
overlap with SITS".

    python diagnostics/check_compliance_gap.py [school_code]

With no argument, reports on every FACULTY_SCHOOLS code.
"""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from database import get_db_connection, get_active_audit_fields  # noqa: E402
from processing import FACULTY_SCHOOLS  # noqa: E402


def main(school_codes):
    active_fields = get_active_audit_fields()
    boolean_fields = [f for f in active_fields if f['field_type'] in ('boolean', 'yes/no')]
    print(f"{len(boolean_fields)} active boolean/yes-no audit fields: "
          f"{[f['id'] for f in boolean_fields]}\n")

    with get_db_connection() as conn:
        df_sits = pd.read_sql_query("SELECT DISTINCT [CIS unit code] FROM sits_assessment_2026_27", conn)
        df_resp = pd.read_sql_query("SELECT DISTINCT module_code FROM audit_responses", conn)

    df_sits['CIS unit code'] = df_sits['CIS unit code'].astype(str).str.strip().str.upper()
    df_resp['module_code'] = df_resp['module_code'].astype(str).str.strip().str.upper()
    sits_codes = set(df_sits['CIS unit code'])
    audited_codes = set(df_resp['module_code'])

    print(f"{len(sits_codes)} distinct modules in sits_assessment_2026_27")
    print(f"{len(audited_codes)} distinct modules with at least one audit_responses row")
    print(f"{len(audited_codes - sits_codes)} audited modules NOT in sits_assessment_2026_27 "
          f"(silently excluded from the compliance gap numerator)\n")

    header = f"{'School':<8}{'SITS modules':<14}{'Audited (SITS)':<16}{'Audited (non-SITS)':<20}"
    print(header)
    print("-" * len(header))
    for school in school_codes:
        school_sits = {c for c in sits_codes if c.startswith(school)}
        school_audited_in_sits = school_sits & audited_codes
        school_audited_outside_sits = {c for c in audited_codes if c.startswith(school)} - sits_codes
        print(f"{school:<8}{len(school_sits):<14}{len(school_audited_in_sits):<16}"
              f"{len(school_audited_outside_sits):<20}")


if __name__ == "__main__":
    codes = sys.argv[1:] if len(sys.argv) > 1 else FACULTY_SCHOOLS
    main(codes)
