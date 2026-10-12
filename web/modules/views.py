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
sent. Not here: the "Fixed something?" form and the PDF export, both of which
write or build files and stay in Streamlit for now.

School scoping is real: `accounts.models.may_view_module()` decides, from the
signed-in account's `view_all` permission or its school alignment. A module
outside that is a 403, not a crash and not a silently empty page.
"""

import processing

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import render

from accounts.models import may_view_module, may_view_school
from auditdata.models import AuditField
import report_model
from modules import charts, data


@login_required
def module_index(request):
    """A landing page listing the checklist questions, as a smoke test that
    the shared database is readable through the router and the models."""
    fields = AuditField.objects.using("audit").filter(is_active=1)
    return render(request, "modules/index.html", {"fields": fields})


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


SCHOOL_VIEWS = ("modules", "alignment")


@login_required
def school_index(request):
    """The schools this account may open."""
    schools = [s for s in processing.FACULTY_SCHOOLS if may_view_school(request.user, s)]
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
    view = request.GET.get("view", "modules")
    if view not in SCHOOL_VIEWS:
        view = "modules"

    return render(request, "modules/school.html", {
        "school": school, "semester": semester, "view": view,
        "semesters": report_model.SEMESTERS,
        "dashboard": data.load_school(school, semester, request.user),
        "text": report_model,
    })
