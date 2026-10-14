from django import template
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
