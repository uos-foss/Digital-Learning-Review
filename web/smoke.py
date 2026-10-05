"""
Repeatable smoke check for the spike. Reads the real shared database and
renders real pages, which is the point: it proves the joins to existing data,
not mocks.

    cd web
    ../.venv-django/Scripts/python smoke.py        # Windows
    ../.venv-django/bin/python smoke.py            # Linux

Read-only on the shared database. It does create one local user
('spike-smoke') in Django's own SQLite file, which is gitignored.

The pure-logic tests in tests/ run under pytest instead. They are kept apart
on purpose: pytest-django builds throwaway test databases, which would be
empty of the unmanaged tables these pages read.
"""

import os
import sys

import django


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "dlr.settings")
    django.setup()

    from django.contrib.auth.models import User
    from django.test import Client
    from django.test.utils import setup_test_environment

    import database
    import pandas as pd
    from modules import loaders

    setup_test_environment()
    failures = []

    def check(label, condition, detail=""):
        print(f"{'PASS' if condition else 'FAIL'}  {label}{(' - ' + detail) if detail else ''}")
        if not condition:
            failures.append(label)

    # 1. The shared database is readable, and a module code exists to test with.
    with database.get_db_connection() as conn:
        codes = pd.read_sql_query(
            "SELECT DISTINCT [CIS unit code] AS c FROM sits_assessment_2026_27 "
            "ORDER BY c LIMIT 1", conn)["c"].tolist()
    check("SITS table readable", bool(codes), f"first code {codes[0] if codes else 'none'}")
    if not codes:
        sys.exit(1)
    code = codes[0]

    # 2. The row contract and the findings pipeline, unchanged from Streamlit.
    row, findings = loaders.load_findings(code)
    check("module row built", row is not None)
    check("findings produced", findings is not None,
          f"{len(findings)} findings, "
          f"{sum(1 for f in findings if f.get('state') == 'pending')} pending")
    check("template sections present", isinstance(row.get("Template Sections"), dict),
          f"{len(row.get('Template Sections') or {})} sections")

    # 3. Unmanaged models read through the router.
    from auditdata.models import AuditField
    field_count = AuditField.objects.using("audit").filter(is_active=1).count()
    check("audit_fields via ORM", field_count > 0, f"{field_count} active fields")

    # 4. Pages render, including the HTMX fragment and the chart.
    user, _ = User.objects.get_or_create(username="spike-smoke")
    client = Client()
    client.force_login(user)

    report = client.get(f"/modules/{code}/")
    body = report.content.decode("utf-8", "replace")
    check("report page renders", report.status_code == 200, f"HTTP {report.status_code}")
    check("actions panel present", "Actions" in body)

    fragment = client.get(f"/modules/{code}/accessibility/")
    frag_body = fragment.content.decode("utf-8", "replace")
    check("htmx fragment renders", fragment.status_code == 200)
    check("plotly chart rendered", "Plotly.newPlot" in frag_body
          or "No Ally score" in frag_body)

    # 5. Unknown module is a 404, and anonymous access is redirected to sign in.
    check("unknown module is 404",
          client.get("/modules/ZZZ999/").status_code == 404)
    anon = Client().get(f"/modules/{code}/")
    check("anonymous redirected to sign in", anon.status_code == 302,
          anon.get("Location", ""))

    print()
    if failures:
        print(f"{len(failures)} check(s) failed: {', '.join(failures)}")
        sys.exit(1)
    print("All checks passed.")


if __name__ == "__main__":
    main()
