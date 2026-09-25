"""
PDF export of a single module report.

Takes the already-decided content of the on-screen report (findings,
section card wording, Ally scores) as plain data and lays it out as an A4
PDF. It classifies nothing itself: views/module_report.py builds the payload
from the same helpers that render the page, so the PDF and the page can never
say different things about the same module. No Streamlit;
build_module_report_pdf() returns bytes for a download button.

Built with Typst, from the template in assets/module_report.typ, as a
tagged PDF/UA-1 document. That is why this is not fpdf2 (the first version
was): fpdf2 cannot tag headings, paragraphs or lists, or mark page footers
as decoration, so a screen reader got one flat run of text with the footer
read out mid-page. Typst tags from the document's own structure, so the
template decides what a screen reader meets, in this order:

- H1 module title, H2 per report section, H3/H4... for cards. Every card
  title is a real heading, so a screen reader can jump card to card, and a
  card's status badge sits inside its heading, so it is heard with the
  title ("Assessment Detail, NOT STARTED") rather than lost after the body.
  Heading levels follow the template tree's depth and never skip a level,
  which PDF/UA forbids.
- The module details and the Ally scores are tables with header rows, so
  each value is read with its label.
- Fills, edge bars and the page footer are marked as decoration.

Checked with PAC (PDF Accessibility Checker) - rerun it after changing the
template. Data goes to Typst as JSON through sys.inputs, never pasted into
the markup, so module text containing #, $, * or [ can't be read as Typst
code. Fonts are the bundled Noto Sans only (assets/fonts, SIL OFL), with
system fonts ignored, so the PDF comes out the same on Windows and in the
Docker image.

Every coloured piece of text goes through _readable(), so it meets WCAG's
4.5:1 contrast against whatever it sits on - the page's palette (amber
#F59E0B, green #10B981) is for fills and rules, and read as low as 1.9:1
when used as text on its own tint.
"""
import json
import re
import unicodedata
from pathlib import Path

import typst

_ASSETS = Path(__file__).resolve().parent / "assets"
_TEMPLATE = _ASSETS / "module_report.typ"
_FONTS = _ASSETS / "fonts"

INK = (31, 41, 55)
BODY = (55, 65, 81)
MUTED = (107, 114, 128)
ACCENT = (37, 99, 235)
AMBER = "#F59E0B"
COMMENT_RULE = "#93C5FD"


def _clean(text):
    """
    Plain text for the PDF: HTML tags and markdown emphasis/links dropped,
    keeping the words, and emoji removed (Noto Sans has none, and they are
    decoration on the page, never the only carrier of meaning).
    """
    text = re.sub(r"<br\s*/?>", "\n", str(text or ""))
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = text.replace("**", "").replace("__", "")
    # The page's wording points at a tab; the PDF has a section instead.
    text = text.replace("Accessibility Report tab", "Accessibility Report section")
    text = "".join(ch for ch in text
                   if unicodedata.category(ch) not in ("So", "Cs", "Co")
                   and ch not in "\ufe0f\u200d")
    return re.sub(r"[ \t]+", " ", text).strip()


def _rgb(hex_colour):
    h = str(hex_colour or "#6B7280").lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _hex(rgb):
    return "#{:02X}{:02X}{:02X}".format(*rgb)


def _tint(rgb, amount=0.9):
    """Mix a colour with white - the PDF equivalent of the page's 5-10% fills."""
    return tuple(int(c + (255 - c) * amount) for c in rgb)


def _luminance(rgb):
    def channel(c):
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (channel(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(a, b):
    la, lb = _luminance(a), _luminance(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def _readable(fg, bg=(255, 255, 255), target=4.5):
    """fg, darkened just enough to reach WCAG AA contrast against bg."""
    while _contrast(fg, bg) < target:
        fg = tuple(int(c * 0.92) for c in fg)
    return fg


def _card(title=None, level=3, colour="#6B7280", badge=None, lines=(), depth=0, fill=True):
    """
    One card for the template: a coloured left rule, an optional tinted
    fill, an optional heading (with its badge) and lines of text below it.
    `lines` is a sequence of (text, size_pt, rgb). Colours are resolved here
    so every text colour is checked against the fill it actually sits on.
    """
    rgb = _rgb(colour)
    bg = _tint(rgb, 0.94) if fill else (255, 255, 255)
    badge_bg = _tint(rgb, 0.82)
    return {
        'title': _clean(title) or None,
        'level': level,
        'depth': depth,
        'fill': _hex(bg) if fill else None,
        'rule': _hex(rgb),
        'badge': _clean(badge).upper() or None,
        'badge_bg': _hex(badge_bg),
        'badge_ink': _hex(_readable(rgb, badge_bg)),
        'lines': [{'text': _clean(t), 'size': size, 'ink': _hex(_readable(ink, bg))}
                  for t, size, ink in lines if _clean(t)],
    }


def _point(text):
    """A summary point's leading '**Label:**' (if any) split off to set in bold."""
    match = re.match(r"\*\*(.+?)\*\*\s*(.*)", str(text), re.S)
    bold, rest = (match.group(1), match.group(2)) if match else ("", str(text))
    return {'bold': _clean(bold), 'text': _clean(rest)}


def _paragraphs(markdown):
    """Comment markdown as paragraphs of lines: blank lines split paragraphs,
    single newlines are line breaks, as format_comment_markdown() intends."""
    paras = []
    for block in re.split(r"\n\s*\n", str(markdown or "")):
        lines = [_clean(line) for line in block.split("\n")]
        lines = [line for line in lines if line]
        if lines:
            paras.append(lines)
    return paras


def _template_cards(rows):
    """TEMPLATE_SECTION_TREE rows as cards. A row at depth d is a level 3 + d
    heading: children are always one level below their parent, so levels
    never skip."""
    out = []
    for row in rows:
        depth = int(row.get("depth", 0))
        if row["kind"] == "heading":
            out.append({'group': _clean(row["label"]), 'level': 3 + depth, 'depth': depth,
                        'note': _clean(row.get("note")),
                        'note_ink': _hex(MUTED)})
            continue
        lines = []
        if row.get("show_detail"):
            lines = [(row.get("action"), 8.5, BODY), (row.get("footer"), 8, MUTED)]
        out.append(_card(row["label"], level=3 + depth, colour=row.get("colour"),
                         badge=row.get("badge"), lines=lines, depth=depth))
    return out


def _ally(ally):
    if ally is None:
        return None
    if ally.get("message"):
        return {'message': _clean(ally["message"])}

    scores = []
    for label, pct, sub, colour in ally.get("scores") or []:
        rgb = _rgb(colour)
        bg = _tint(rgb, 0.9)
        scores.append({'label': _clean(label).upper(),
                       # Words, not "--": a screen reader reads that as "dash dash".
                       'value': "No score" if pct is None else f"{pct:.1f}%",
                       'sub': _clean(sub), 'bg': _hex(bg),
                       'ink': _hex(_readable(rgb, bg)), 'sub_ink': _hex(_readable(MUTED, bg))})

    categories = ally.get("categories") or []
    summary, cards = "", []
    if categories:
        total = sum(int(c.get("items", 0)) for c in categories)
        summary = (f"Summary of accessibility issues ({total} item{'' if total == 1 else 's'} "
                   f"across {len(categories)} area{'' if len(categories) == 1 else 's'})")
        for c in categories:
            items, checks = int(c.get("items", 0)), int(c.get("checks", 0))
            count = (f"{items} item{'' if items == 1 else 's'} across {checks} "
                     f"issue type{'' if checks == 1 else 's'}")
            cards.append(_card(c.get("title"), level=4, colour=c.get("colour"),
                               lines=[(count, 8, MUTED), (c.get("why"), 9, (75, 85, 99))]))
    return {
        'intro': _clean(f"Based on the institutional Ally data snapshot from "
                        f"{ally.get('snapshot_date') or 'an unknown date'}. This is a summary, not a "
                        "replacement for the Ally Accessibility Report in Blackboard "
                        "(Books & Course Tools > Ally Accessibility Report), which is live "
                        "and shows which files are affected."),
        'maturity': (_card(None, colour="#6B7280", lines=[(ally["maturity"], 9, INK)])
                     if ally.get("maturity") else None),
        'scores': scores,
        'disabled': (_card("Ally is switched off for this course", level=3, colour=AMBER,
                           lines=[("Students get no alternative formats and the module "
                                   "lead sees no feedback.", 9, MUTED)])
                     if ally.get("disabled") else None),
        'summary': summary,
        'categories': cards,
        'empty': ("This course still holds only its rolled-over template, so there's "
                  "nothing to report yet." if ally.get("is_template")
                  else "No accessibility issues reported."),
    }


def build_module_report_pdf(data):
    """
    data keys (all optional except code/name):
      code, name, lead, level, site_url, audit_status, generated
      summary_intro, points (markdown strings), refreshed
      comment (markdown), comment_heading
      actions: [{'label', 'description'}]
      template: [{'kind': 'heading'|'section', 'depth', 'label', 'badge',
                  'colour', 'action', 'footer', 'show_detail'}]
      ally: None, or {'message'} when there is no Ally record, or
            {'snapshot_date', 'maturity', 'scores': [(label, pct|None, sub, colour)],
             'disabled', 'categories': [{'title', 'items', 'checks', 'why', 'colour'}],
             'is_template'}
    """
    code, name = _clean(data.get("code")), _clean(data.get("name"))
    generated = _clean(data.get("generated"))
    comment = _paragraphs(data.get("comment"))
    view = {
        'title': f"Module Report - {code} {name}",
        'author': "Faculty of Social Sciences Digital Learning",
        'eyebrow': "FACULTY OF SOCIAL SCIENCES - MODULE REPORT",
        'heading': f"{code} - {name}",
        'footer': f"Module Report - {code} - generated {generated}",
        'meta': [{'label': label, 'value': _clean(value) or "Not recorded"} for label, value in (
            ("Module Lead", data.get("lead")), ("Level", data.get("level")),
            ("Audit Status", data.get("audit_status")), ("Report generated", generated))],
        'site_url': str(data.get("site_url") or "") or None,
        'muted': _hex(MUTED),
        'accent': _hex(ACCENT),
        'intro': _clean(data.get("summary_intro")),
        'points': [_point(p) for p in data.get("points") or []],
        'refreshed': _clean(data.get("refreshed")),
        'comment': ({'heading': _clean(data.get("comment_heading"))
                                or "Comments from your Digital Learning Advisor",
                     'card': _card(None, colour=COMMENT_RULE, fill=False),
                     'paragraphs': comment} if comment else None),
        'actions': [_card(item.get("label"), level=3, colour=AMBER,
                          lines=[(item.get("description"), 9, MUTED)])
                    for item in data.get("actions") or []],
        'template': _template_cards(data.get("template") or []),
        'ally': _ally(data.get("ally")),
    }
    return typst.compile(
        str(_TEMPLATE),
        root=str(_ASSETS),
        font_paths=[str(_FONTS)],
        ignore_system_fonts=True,
        sys_inputs={'data': json.dumps(view)},
        pdf_standards=["ua-1"],
    )
