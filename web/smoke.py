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

    # 2. The row contract, unchanged from Streamlit.
    row = data.load_module_row(code)
    check("module row built", row is not None)
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
    check("actions panel present", "Actions (" in body)
    check("header present", "Audit Status" in body)
    check("template tab is the default", "Blackboard item" in body)
    acc = client.get(f"/modules/{code}/?tab=accessibility").content.decode("utf-8", "replace")
    check("accessibility tab renders", "Plotly.newPlot" in acc or "No Ally record" in acc)
    check("an unknown tab falls back to the template tab",
          "Blackboard item" in client.get(f"/modules/{code}/?tab=nonsense").content.decode("utf-8", "replace"))

    # The report is built from the shared rules, so its counts must equal what
    # derive_module_findings() says directly, with the inputs the Streamlit
    # page uses. Compared on every module with an audit trail as well as this
    # one: the shapes of `responses` are where a port goes quietly wrong.
    import loaders

    def cross_check(module_code):
        built = data.load_report(module_code, user)
        row_ = loaders.load_module_record(module_code, data._sources())
        trail = loaders.load_audit_trail(module_code)
        direct = processing.derive_module_findings(
            row_, trail["responses"], database.get_active_audit_fields(),
            database.get_active_fix_claims(module_code))
        pending = [f for f in direct if f["state"] == "pending"]
        shown = len(built["actions"]) + len(built["reported_fixed"])
        # The panel lists boolean and custom findings only, as the Streamlit one does.
        listable = [f for f in pending if f["type"] in ("boolean", "custom")]
        return shown == len(listable), (shown, len(listable))

    with database.get_db_connection() as conn:
        audited = [r[0] for r in conn.execute(
            "SELECT DISTINCT module_code FROM audit_responses LIMIT 25").fetchall()]
    bad = [(c, cross_check(c)[1]) for c in [code] + audited if not cross_check(c)[0]]
    check("report actions match derive_module_findings()", not bad,
          f"{len(audited) + 1} modules compared" + (f"; differ: {bad[:3]}" if bad else ""))

    from modules.templatetags.report_extras import markdown_html
    rendered = str(markdown_html("**Note** <script>alert(1)</script>\n\nSecond"))
    check("advisor comment is escaped before it is marked up",
          "<script>" not in rendered and "<strong>Note</strong>" in rendered
          and rendered.count("<p>") == 2, rendered)

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
    check("the sign-in page has a password field for local accounts",
          'name="password"' in login_page.content.decode("utf-8", "replace"))
    local, _ = User.objects.get_or_create(username="spike-local")
    local.set_password("spike-local-pw")
    local.save()
    check("a local account can sign in with a password",
          Client().post("/accounts/login/", {"login": "spike-local",
                                              "password": "spike-local-pw"}).status_code == 302)
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
    check("faculty-wide account still sees it",
          client.get(f"/modules/{code}/").status_code == 200, "view_all via the DLA group")

    # 7b. The School Dashboard, with the same scoping as the module report.
    sd = client.get(f"/schools/{school}/")
    sd_body = sd.content.decode("utf-8", "replace")
    check("school dashboard renders", sd.status_code == 200, f"HTTP {sd.status_code}")
    listed = data.load_school(school, "Autumn", user)["modules"]
    check("school dashboard lists modules and links to their reports",
          "Outstanding actionable items" in sd_body and bool(listed)
          and f"/modules/{listed[0]['code']}/" in sd_body, f"{len(listed)} modules")
    check("template alignment view renders",
          "Accessibility" in client.get(f"/schools/{school}/?view=alignment")
          .content.decode("utf-8", "replace"))
    check("an unknown semester falls back instead of failing",
          client.get(f"/schools/{school}/?semester=Winter").status_code == 200)
    sc = client.get(f"/schools/{school}/?view=comments&empty=1&status=bogus&q=%3Cb%3E")
    check("spot-check comments view renders and survives odd filters",
          sc.status_code == 200 and "Spot-Check Comments" in sc.content.decode("utf-8", "replace"))
    from modules.templatetags.report_extras import markdown_html
    rendered = str(markdown_html(
        "**b**\n\n- x\n\n<script>alert(1)</script> [j](javascript:alert(1))"))
    check("comment markdown renders and typed HTML and javascript: links stay inert",
          "<strong>b</strong>" in rendered and "<li>x</li>" in rendered
          and "<script>" not in rendered and 'href="javascript' not in rendered, rendered)
    comments = data.load_school_comments(school)
    check("every flagged module appears once in the comments view",
          len({c["code"] for c in comments["cards"]}) == len(comments["cards"]),
          f"{comments['flagged']} flagged")
    fx = client.get(f"/schools/{school}/?view=fixes&show=bogus")
    check("reported fixes view renders, or falls back when not rolled out",
          fx.status_code == 200
          and (data.fixes_enabled(school) == ("Awaiting check" in fx.content.decode("utf-8", "replace")
                                              or "No fixes have been reported" in fx.content.decode("utf-8", "replace"))))
    check("own school sees its dashboard",
          aligned_client.get(f"/schools/{school}/").status_code == 200)
    ml_page = aligned_client.get(f"/schools/{school}/?view=comments").content.decode("utf-8", "replace")
    ml_matrix = aligned_client.get(f"/schools/{school}/?view=alignment").content.decode("utf-8", "replace")
    check("a module lead gets the modules list only, whatever view is asked for",
          "Outstanding actionable items" in ml_page and "Spot-Check Comments" not in ml_page
          and "Template Alignment" not in ml_matrix and "Reported Fixes" not in ml_page
          and "<th>Spot-check</th>" in ml_page)
    ml_home = aligned_client.get("/")
    check("signing in sends a one-school account straight to its school",
          ml_home.status_code == 302 and ml_home.url == f"/schools/{school}/", str(ml_home.url))
    check("a faculty-wide account lands on the school list",
          client.get("/").url == "/schools/")
    leaving = Client()
    leaving.force_login(User.objects.get(pk=aligned.pk))
    check("the header offers a sign-out button that works",
          'action="/accounts/logout/"' in sd_body
          and leaving.post("/accounts/logout/").status_code == 302
          and leaving.get(f"/schools/{school}/").status_code == 302)
    ally_all = data.load_school_ally(school, "Autumn", [], [])
    ally_sev = data.load_school_ally(school, "Autumn", ["Severe"], [])
    every = data.load_school_lenses(school, "Autumn", user, [], [])
    narrowed = data.load_school_lenses(
        school, "Autumn", user, ["risk", "alignment", "reading", "bogus"], ["not-an-item"])
    check("lenses: no lens lists every module, with the matrix columns",
          len(every["rows"]) == len(listed) and bool(every["columns"]) and not every["filtered"],
          f"{len(every['rows'])} modules")
    check("lenses: several lenses narrow, never widen, and say how many flag",
          len(narrowed["rows"]) <= len(every["rows"]) and narrowed["filtered"]
          and "flagged by at least one of 3 lenses" in narrowed["status"] and len(narrowed["notes"]) == 3)
    risk_only = data.load_school_lenses(school, "Autumn", user, ["risk"], [])
    focused = data.load_school_lenses(school, "Autumn", user, ["alignment"], [every["columns"][0]])
    check("lenses: a lens keeps only the columns it speaks to",
          risk_only["columns"] == ["Accessibility"] and risk_only["columns_narrowed"]
          and focused["columns"] == [every["columns"][0]] and not every["columns_narrowed"])
    check("lenses: show all columns restores every one, in the same order",
          data.load_school_lenses(school, "Autumn", user, ["risk"], [], True)["columns"] == every["columns"])
    cols_page = client.get(f"/schools/{school}/?view=alignment&lens=risk").content.decode("utf-8", "replace")
    check("lenses: the page says columns are narrowed and offers the switch",
          "Show all columns" in cols_page and "cols=all" in cols_page)
    check("lenses: every flagged module is one the school has",
          {r["code"] for r in narrowed["rows"]} <= {r["code"] for r in every["rows"]})
    check("lenses: the SGA lens is not offered to an account without view_sga_analytics",
          all(o["key"] != "sga" for o in narrowed["lens_options"])
          and data.load_school_lenses(school, "Autumn", user, ["sga"], [])["filtered"] is False)
    lp = client.get(f"/schools/{school}/?view=alignment&lens=risk&lens=alignment&item=nope&lens=junk")
    check("lenses: the alignment page renders with lenses and odd parameters",
          lp.status_code == 200 and "Per-lens notes" in lp.content.decode("utf-8", "replace"))
    # Each view puts its own content in the panel and nothing else's, and the
    # tab bar holds only tabs. A template splice once put the Trends panel inside
    # the tab bar, so Trends showed the alignment filter and lost a tab.
    panel_marker = {"modules": "Reading list", "alignment": "Filter modules",
                    "comments": "What advisors wrote", "ally": "What to fix",
                    "trends": "figures behind the charts"}
    tab_names = ["Modules", "Template Alignment", "Spot-Check Comments",
                 "Ally Analytics", "Trends"]
    if data.fixes_enabled(school):
        panel_marker["fixes"] = "Template sections a module lead"
        tab_names.append("Reported Fixes")
    problems = []
    for view_name, marker in panel_marker.items():
        html = client.get(f"/schools/{school}/?view={view_name}").content.decode("utf-8", "replace")
        bar = html[html.index('<p class="tabs-links">'):]
        bar = bar[:bar.index("</p>")]
        panel = html[html.index('<section class="panel">'):]
        if any(tag in bar for tag in ("<div", "<table", "<script", "<form")):
            problems.append(f"{view_name}: content inside the tab bar")
        problems += [f"{view_name}: tab {t} missing" for t in tab_names if t not in bar]
        if marker not in panel and not (view_name == "trends" and "Historical" in panel):
            problems.append(f"{view_name}: its own content is missing")
        problems += [f"{view_name}: shows {other}'s content" for other, m in panel_marker.items()
                     if other != view_name and m in panel[:panel.index("</section>")]]
    check("every school view shows its own panel and a clean tab bar", not problems, "; ".join(problems))
    check("ally analytics: modules and issue profile are built",
          bool(ally_all["modules"]) and len(ally_all["modules"]) <= len(listed) + 5,
          f"{len(ally_all['modules'])} modules, {len(ally_all['profile'])} issue types")
    check("ally analytics: a severity filter only narrows",
          len(ally_sev["modules"]) <= len(ally_all["modules"])
          and all(r["severity"] == "Severe" for r in ally_sev["profile"]))
    check("ally analytics: the issue filter narrows the module table",
          not ally_all["issue_options"] or len(data.load_school_ally(
              school, "Autumn", [], ally_all["issue_options"][:1])["modules"])
          <= len(ally_all["modules"]))
    check("ally analytics renders for a DLA, and survives odd filters",
          client.get(f"/schools/{school}/?view=ally&sev=Severe&sev=bogus&issue=nope")
          .status_code == 200
          and "What to fix" in client.get(f"/schools/{school}/?view=ally").content.decode("utf-8", "replace")
          and "Ally Analytics" in client.get(f"/schools/{school}/").content.decode("utf-8", "replace"))
    trend, trend_msg = data.load_school_trend(school, "Autumn")
    check("trends: carried forward, so a partial snapshot never drops courses",
          trend is not None and trend["Courses"].is_monotonic_increasing,
          trend_msg or f"{len(trend)} snapshots")
    tr = client.get(f"/schools/{school}/?view=trends").content.decode("utf-8", "replace")
    check("trends view renders for a DLA, with charts or the reason there are none",
          "Average accessibility score over time" in tr or "snapshot" in tr or "Historical" in tr)
    check("trends is not served to a module lead",
          "Average accessibility score" not in aligned_client.get(
              f"/schools/{school}/?view=trends").content.decode("utf-8", "replace")
          and "Trends" not in aligned_client.get(f"/schools/{school}/").content.decode("utf-8", "replace"))
    check("ally analytics is not offered to a module lead",
          "What to fix" not in aligned_client.get(f"/schools/{school}/?view=ally").content.decode("utf-8", "replace")
          and "Ally Analytics" not in aligned_client.get(f"/schools/{school}/").content.decode("utf-8", "replace"))
    check("other school is refused its dashboard",
          outsider_client.get(f"/schools/{school}/").status_code == 403)
    check("an unknown school is a 404 once access is granted",
          client.get("/schools/ZZZ/").status_code == 404)
    check("the school list shows only permitted schools",
          f"/schools/{school}/" in aligned_client.get("/schools/").content.decode("utf-8", "replace")
          and (other is None or f"/schools/{other}/" not in
               aligned_client.get("/schools/").content.decode("utf-8", "replace")))

    # The headline figures must agree with the Streamlit page's own rules,
    # worked out here from the raw frames rather than through the dashboard.
    df_aut, df_spr = data._frames()
    target = processing.resolve_semester_df(df_aut, df_spr, "Autumn")
    mine = target[processing.school_series(target["New module code"]) == school]
    shown = {label: value for label, value, _ in data.load_school(school, "Autumn", user)["headline"]}
    average = processing.mean_score(mine)
    check("headline figures match processing's own rules",
          shown["Total modules"] == str(len(mine))
          and shown["Modules with no activity"] == str(len(mine) - len(processing.scoreable(mine)))
          and shown["Average Ally score"] == (f"{average:.1%}" if average is not None else "—"),
          f"{school}: {len(mine)} modules")

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
