from django import template
from django.utils.html import escape
from django.utils.safestring import mark_safe

from markdown_it import MarkdownIt

import report_model

register = template.Library()

# CommonMark with raw HTML switched off, so typed tags are shown as text, and
# markdown-it's own link check refuses javascript: URLs. A single newline is a
# line break, which is how advisors type in the Audit Portal's text area.
_markdown = MarkdownIt("commonmark", {"html": False, "breaks": True})


@register.filter
def section_icon(key):
    """The Blackboard Ultra content-type icon for a template section. The SVG
    strings are fixed constants in report_model, never user data."""
    return mark_safe(report_model.CONTENT_TYPE_ICONS.get(
        report_model.SECTION_CONTENT_TYPE.get(key), ""))


@register.simple_tag
def learning_module_icon():
    return mark_safe(report_model.CONTENT_TYPE_ICONS["learning_module"])


@register.filter
def markdown_html(value):
    """
    A comment as full markdown (lists, emphasis, links, headings) rendered to
    HTML, as st.markdown shows it on the Streamlit page. Used for the module
    report's advisor comment and the School Dashboard's Spot-Check Comments, so
    one comment reads the same on both. Input is
    processing.format_comment_markdown()'s output.
    """
    return mark_safe(_markdown.render(value or ""))


@register.filter
def school_name(code):
    """A school's full name from SITS ("School of Education"), or the code
    itself when SITS has not given one."""
    from modules import data
    code = str(code or "")
    return data.school_names().get(code.upper(), code)


STATUS_WORDS = {
    "✅": "done", "❌": "outstanding", "🔧": "reported fixed, awaiting check",
    "🟢": "accessibility good", "🟠": "major accessibility issues",
    "🔴": "severe accessibility issues", "⚪": "nothing to judge yet",
}


@register.filter
def status_cell(symbol):
    """A tick, cross or traffic light with a spoken name, so the matrix does not
    rely on colour or on how a screen reader happens to read an emoji."""
    symbol = str(symbol or "")
    word = STATUS_WORDS.get(symbol)
    if not word:
        return symbol
    return mark_safe(f'<span role="img" aria-label="{word}">{escape(symbol)}</span>')
