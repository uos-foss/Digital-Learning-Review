"""
The spike's pages. Three things are being proved here:

1. A module report page built by calling processing.derive_module_findings()
   unchanged, with no Streamlit anywhere in the request path.
2. The URL identifies what is on screen (/modules/EDC004/), so links are
   shareable and the back button works. No session state holds the selection.
3. A Plotly chart and an HTMX panel both render inside a Django template.

Scoping is a placeholder: `view_module` below checks only that the user is
signed in. Real school scoping needs the account-to-school model described in
the platform doc, which the spike deliberately does not invent.
"""

import json

from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import render

import processing

from auditdata.models import AuditField
from modules import data


@login_required
def module_index(request):
    """A landing page listing the checklist questions, as a smoke test that
    the shared database is readable through the router and the models."""
    fields = AuditField.objects.using("audit").filter(is_active=1)
    return render(request, "modules/index.html", {"fields": fields})


@login_required
def module_report(request, code):
    row, findings = data.load_findings(code)
    if row is None:
        raise Http404(f"{code} is not in SITS for the current academic year.")

    actions = [f for f in findings if f.get("state") == "pending"]
    done = [f for f in findings if f.get("state") == "completed"]

    return render(request, "modules/report.html", {
        "code": code,
        "module": _display(row),
        "actions": actions,
        "done": done,
        "by_source": _count_by_source(findings),
    })


@login_required
def module_accessibility(request, code):
    """
    An HTMX fragment, loaded when the Accessibility tab is clicked rather than
    on every page load. Proves partial rendering works; the Ally detail itself
    is left for the real port.
    """
    row = data.load_module_row(code)
    if row is None:
        raise Http404(code)

    return render(request, "modules/_accessibility.html", {
        "code": code,
        "module": _display(row),
        "chart": _score_chart(row),
    })


def _display(row):
    """
    A view model with template-friendly names. The row's own keys ('Ally
    Overall', 'Module name') carry spaces, which Django templates cannot
    resolve by dot notation, and the pandas-era naming does not belong in a
    template anyway. One place to rename, rather than a filter at every use.
    """
    overall = row.get("Ally Overall")
    return {
        "code": row.get("New module code", ""),
        "name": row.get("Module name", ""),
        "lead": row.get("Module Lead", ""),
        # The module record carries no 'School' column; every reader derives
        # it from the code through this one helper.
        "school": processing.school_of(row.get("New module code", "")),
        "ally_overall_pct": round(float(overall) * 100, 1) if overall is not None else None,
        "ally_enabled": row.get("Ally Enabled", True),
        "ally_severe": row.get("Ally Severe", 0),
        "ally_major": row.get("Ally Major", 0),
        "leganto_missing": row.get("Leganto Missing", False),
        "leganto_status": row.get("Leganto List Status", ""),
        "leganto_items": row.get("Leganto List Items", 0),
        "section_count": len(row.get("Template Sections") or {}),
        "sga_attributes": row.get("SGA Attributes"),
    }


def _count_by_source(findings):
    counts = {}
    for finding in findings:
        source = finding.get("source", "unknown")
        state = finding.get("state", "unknown")
        entry = counts.setdefault(source, {"pending": 0, "completed": 0})
        if state in entry:
            entry[state] += 1
    return counts


def _score_chart(row):
    """
    One Plotly figure, serialised for plotly.js in the template. Rendering to
    JSON rather than a full HTML snippet keeps one copy of the library on the
    page however many charts it ends up showing.
    """
    import plotly.graph_objects as go

    score = row.get("Ally Overall")
    if score is None:
        return None

    figure = go.Figure(go.Indicator(
        mode="gauge+number",
        value=round(float(score) * 100, 1),
        number={"suffix": "%"},
        title={"text": "Ally overall score"},
        gauge={"axis": {"range": [0, 100]}},
    ))
    figure.update_layout(height=260, margin={"t": 40, "b": 10, "l": 10, "r": 10})
    return json.dumps(figure.to_plotly_json(), default=str)
