"""
The module report, and the pages around it.

A port of the Streamlit module report (`views/module_report.py`), read-only.
Everything the Streamlit report shows, in plain tables: header, a collapsed
Report Summary, the advisor comment, headline tables and Actions, then two tabs
(?tab=template, ?tab=accessibility). Icons, gauges and dropdowns are small and
muted on purpose; the Streamlit page is the loud version.
What the report says is decided in `report_model.build_report()` and the rules
under it in `processing.py`; a view here fetches that and renders it, and no
rule is worked out in a view or a template. The URL identifies the page
(/modules/EDC004/), so a module has an address a lead can be
sent. The one write is the "Fixed something?" form (`report_fix`), which saves
a lead's claim through `database.save_fix_claim()`. Not here: the PDF export,
which stays in Streamlit for now.

School scoping is real: `accounts.models.may_view_module()` decides, from the
signed-in account's `view_all` permission or its school alignment. A module
outside that is a 403, not a crash and not a silently empty page.
"""

import processing

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from accounts.models import (has_any_access, has_basic_school_view, may_view_module,
                             may_view_school, schools_of)
from auditdata.models import AuditField
import report_model
from modules import charts, data


@login_required
def module_index(request):
    """
    The module finder: search by code, name or lead across the schools this
    account may see. An exact code goes straight to that module's report. The
    check that the shared database is readable (the checklist questions) is
    kept for staff, at the foot of the page.
    """
    q = request.GET.get("q", "").strip()[:100]
    allowed = schools_of(request.user)
    school = request.GET.get("school", "").strip().upper()
    finder = data.find_modules(q, school, allowed)

    hits = finder["results"]
    if len(hits) == 1 and q.upper() == hits[0]["code"]:
        return redirect("modules:report", code=hits[0]["code"])

    context = {"finder": finder}
    if request.user.is_staff:
        context["platform_check"] = True
        context["fields"] = AuditField.objects.using("audit").filter(is_active=1)
    return render(request, "modules/index.html", context)


def _require_access(request, code):
    """
    403 unless this account may see this module's school.

    Ordered deliberately: the access check runs before the module is looked
    up, so a 404 never tells someone outside a school which codes exist
    inside it.
    """
    if not may_view_module(request.user, code):
        raise PermissionDenied(
            f"{request.user.username} is not aligned with "
            f"{processing.school_of(code) or 'that school'}.")


TABS = ("template", "accessibility")


@login_required
def module_report(request, code):
    _require_access(request, code)
    report = data.load_report(code, request.user)
    if report is None:
        raise Http404(f"{code} is not in SITS for the current academic year.")
    tab = request.GET.get("tab", "template")
    if tab not in TABS:
        tab = "template"
    context = {"code": report["code"], "report": report, "text": report_model,
               "tab": tab}
    if tab == "accessibility":
        context["gauges"] = charts.gauges_for(report["ally"])
    return render(request, "modules/report.html", context)


@login_required
@require_POST
def report_fix(request, code):
    """
    A module lead reports template sections as fixed. Access is checked before
    the module is looked up, like the report, and the claimable set is worked
    out again here, so only what the page could have offered is saved. A claim
    only adds wording and moves the item to "Reported fixed": it never changes
    a verdict or a count.
    """
    _require_access(request, code)
    report = data.load_report(code, request.user)
    if report is None:
        raise Http404(f"{code} is not in SITS for the current academic year.")
    if not report["claimable"]:
        raise PermissionDenied("Reporting fixes is not available for this module.")
    chosen = request.POST.getlist("field")
    if not chosen:
        messages.warning(request, "Tick at least one section.")
    else:
        saved = data.save_fix_claims(report, request.user, chosen,
                                     request.POST.get("note", "").strip()[:500])
        if saved:
            messages.success(request, f"Reported {saved} section{'s' if saved != 1 else ''} as fixed.")
        else:
            messages.warning(request, "Nothing was saved: those sections can no longer be reported.")
    return redirect("modules:report", code=report["code"])


SCHOOL_VIEWS = ("modules", "alignment", "comments", "fixes", "ally", "trends", "ai")


@login_required
def home(request):
    """
    Where signing in lands. An account with exactly one school goes straight to
    it, which is every module lead and any DLA aligned with a single school;
    anyone with several (or the whole faculty) chooses from the list.
    """
    if not has_any_access(request.user):
        return render(request, "accounts/no_access.html")
    schools = schools_of(request.user)
    if len(schools) == 1:
        return redirect("schools:dashboard", school=schools[0])
    return redirect("schools:index")


@login_required
def school_index(request):
    """The schools this account may open."""
    schools = schools_of(request.user)
    return render(request, "modules/schools.html", {"schools": schools})


@login_required
def school_dashboard(request, school):
    """
    One school's dashboard: headline figures, then its modules or the Template
    Alignment matrix. Read-only; flagging spot-checks stays in Streamlit.
    Access is checked before the code is validated, so a 404 never reveals
    which schools exist to someone outside them.
    """
    school = str(school).strip().upper()
    if not may_view_school(request.user, school):
        raise PermissionDenied(
            f"{request.user.username} is not aligned with {school}.")
    if school not in processing.FACULTY_SCHOOLS:
        raise Http404(f"{school} is not a school in this faculty.")

    semester = request.GET.get("semester", "Autumn")
    if semester not in report_model.SEMESTERS:
        semester = "Autumn"
    # A module lead gets the basic page: the modules list, whatever view is
    # asked for. Reading is not restricted (they read every report in scope);
    # this only keeps the DLA's matrix, comments and fix queue out of their way.
    basic = has_basic_school_view(request.user)
    view = request.GET.get("view", "modules")
    if view not in SCHOOL_VIEWS or basic:
        view = "modules"
    # Ally Analytics is for everyone who gets more than the basic page. The
    # Streamlit page keeps it admin-only, for no reason on record.
    ally_on = not basic
    fixes_on = data.fixes_enabled(school) and not basic
    if view == "fixes" and not fixes_on:
        view = "modules"

    context = {
        "school": school, "semester": semester, "view": view,
        "semesters": report_model.SEMESTERS, "fixes_on": fixes_on, "basic": basic, "ally_on": ally_on,
        "show_options": (("all", "All"), ("awaiting", "Awaiting check"),
                         ("checked", "Checked")),
        "dashboard": data.load_school(school, semester, request.user),
        "text": report_model,
    }
    if view == "comments":
        comments = data.load_school_comments(school)
        status = request.GET.get("status", "all").lower()
        if status not in ("all", "checked", "pending"):
            status = "all"
        search = request.GET.get("q", "")[:200]
        include_empty = request.GET.get("empty") == "1"
        context.update(
            comments=comments, status=status, search=search,
            include_empty=include_empty,
            cards=report_model.filter_comment_cards(
                comments["cards"], status=status, search=search,
                include_empty=include_empty))
    elif view == "alignment":
        all_columns = request.GET.get("cols") == "all"
        context["lenses"] = data.load_school_lenses(
            school, semester, request.user,
            request.GET.getlist("lens"), request.GET.getlist("item"), all_columns)
        toggled = request.GET.copy()
        if all_columns:
            toggled.pop("cols", None)
        else:
            toggled["cols"] = "all"
        context["columns_toggle_url"] = "?" + toggled.urlencode()
    elif view == "trends":
        trend, message = data.load_school_trend(school, semester)
        context["trend_message"] = message
        if trend is not None:
            context["trend_figures"] = charts.trend_figures(trend)
            context["trend_rows"] = [
                {"date": d.strftime("%d-%m-%Y"), "score": f"{r['Overall score'] * 100:.1f}%",
                 "files": int(r["Files uploaded"]), "courses": int(r["Courses"])}
                for d, r in trend.iloc[::-1].iterrows()]
            context["trend_caption"] = processing.ALLY_TREND_CAPTION
    elif view == "ally":
        context["ally"] = data.load_school_ally(
            school, semester, request.GET.getlist("sev"), request.GET.getlist("issue"))
    elif view == "ai":
        context["ai"] = data.load_school_ai(school, semester)
    elif view == "fixes":
        fixes = data.load_school_fixes(school)
        show = request.GET.get("show", "all")
        if show not in ("all", "awaiting", "checked"):
            show = "all"
        rows = [r for r in fixes["rows"]
                if show == "all" or (show == "checked") == r["checked"]]
        context.update(fixes=fixes, show=show, fix_rows=rows)
    return render(request, "modules/school.html", context)
