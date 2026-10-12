import re

from django import template
from django.utils.html import escape
from django.utils.safestring import mark_safe

import report_model

register = template.Library()


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
def comment_html(value):
    """
    An advisor's comment (processing.format_comment_markdown()'s output) as
    HTML. That output uses exactly two pieces of markdown, **bold** and
    trailing-space line breaks, so this handles those and nothing else. The
    text is escaped first and the tags added after, so typed HTML stays text.
    """
    text = escape(value or "")
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    paragraphs = [p for p in re.split(r"\n\s*\n", text) if p.strip()]
    return mark_safe("".join(
        "<p>" + p.strip().replace("\n", "<br>") + "</p>" for p in paragraphs))
