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
    import processing
    from modules import data

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
    row, findings = data.load_findings(code)
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
    # The smoke account is put in the DLA group, which seed_roles gives
    # view_all, because scoping is real now and an unaligned account would
    # (correctly) be refused every module below.
    from django.contrib.auth.models import Group

    user, _ = User.objects.get_or_create(username="spike-smoke")
    dla, _ = Group.objects.get_or_create(name="DLA")
    user.groups.add(dla)
    user = User.objects.get(pk=user.pk)          # drop the cached permissions
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
    #    The 404 is checked with a faculty-wide account: scoping is tested in 7.
    check("unknown module is 404",
          client.get("/modules/ZZZ999/").status_code == 404)
    anon = Client().get(f"/modules/{code}/")
    location = anon.get("Location", "")
    check("anonymous redirected to sign in",
          anon.status_code == 302 and "/accounts/login/" in location, location)

    # 6. Sign-in: the page renders, and nobody can sign themselves up.
    login_page = Client().get("/accounts/login/")
    login_body = login_page.content.decode("utf-8", "replace")
    check("sign-in page renders", login_page.status_code == 200,
          f"HTTP {login_page.status_code}")
    check("sign-in page offers Google or says why not",
          "Continue with Google" in login_body
          or "not configured on this server" in login_body)

    signup = Client().get("/accounts/signup/")
    signup_body = signup.content.decode("utf-8", "replace").lower()
    check("signup is closed", signup.status_code == 403 or "closed" in signup_body,
          f"HTTP {signup.status_code}")

    # 7. Scoping. Three accounts, same module: faculty-wide, the right school,
    # and the wrong school.
    from accounts.models import profile_for

    school = processing.school_of(code)
    other = next((s for s in processing.FACULTY_SCHOOLS if s != school), None)

    aligned, _ = User.objects.get_or_create(username="spike-aligned")
    p_aligned = profile_for(aligned)
    p_aligned.all_schools = False
    p_aligned.set_schools([school])
    p_aligned.save()

    outsider, _ = User.objects.get_or_create(username="spike-outsider")
    p_out = profile_for(outsider)
    p_out.all_schools = False
    p_out.set_schools([other] if other else [])
    p_out.save()

    aligned_client = Client()
    aligned_client.force_login(User.objects.get(pk=aligned.pk))
    outsider_client = Client()
    outsider_client.force_login(User.objects.get(pk=outsider.pk))

    check("own school sees the module",
          aligned_client.get(f"/modules/{code}/").status_code == 200,
          f"{aligned.username} aligned with {school}")
    refused = outsider_client.get(f"/modules/{code}/")
    check("other school is refused", refused.status_code == 403,
          f"{outsider.username} aligned with {other}: HTTP {refused.status_code}")
    check("the refusal covers the htmx fragment too",
          outsider_client.get(f"/modules/{code}/accessibility/").status_code == 403)
    check("faculty-wide account still sees it",
          client.get(f"/modules/{code}/").status_code == 200, "view_all via the DLA group")

    # 8. The domain rule, at the point it is actually enforced: a personal
    # Google account reaching the callback must be refused, not just
    # discouraged by the hd parameter.
    from allauth.core.exceptions import ImmediateHttpResponse
    from allauth.socialaccount.models import SocialAccount, SocialLogin
    from django.test import RequestFactory

    from accounts.adapters import SocialAccountAdapter

    def refuses(email, extra):
        login = SocialLogin(
            user=User(username=email, email=email),
            account=SocialAccount(provider="google", uid=email, extra_data=extra))
        request = RequestFactory().get("/accounts/google/login/callback/")
        try:
            SocialAccountAdapter().pre_social_login(request, login)
            return False
        except ImmediateHttpResponse:
            return True

    check("personal Google account refused",
          refuses("someone@gmail.com", {"email": "someone@gmail.com", "email_verified": True}))
    check("lookalike domain refused",
          refuses("a@notsheffield.ac.uk",
                  {"email": "a@notsheffield.ac.uk", "email_verified": True}))
    check("unverified university address refused",
          refuses("a.person@sheffield.ac.uk",
                  {"email": "a.person@sheffield.ac.uk", "email_verified": False}))
    check("verified university address allowed",
          not refuses("a.person@sheffield.ac.uk",
                      {"email": "a.person@sheffield.ac.uk", "email_verified": True}))

    print()
    if failures:
        print(f"{len(failures)} check(s) failed: {', '.join(failures)}")
        sys.exit(1)
    print("All checks passed.")


if __name__ == "__main__":
    main()
