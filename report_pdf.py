"""
PDF export of a single module report.

Takes the already-decided content of the on-screen report (findings,
section card wording, Ally scores) as plain data and lays it out as an A4
PDF with fpdf2. It classifies nothing itself: views/module_report.py builds
the payload from the same helpers that render the page, so the PDF and the
page can never say different things about the same module. No I/O, no
Streamlit - build_module_report_pdf() returns bytes for a download button.

fpdf2's built-in Helvetica only covers Latin-1, so every string goes through
_t(), which maps the typographic punctuation the app uses to plain
equivalents and drops anything else (mainly emoji) rather than failing.

Accessibility: every coloured piece of text goes through _readable(), so it
meets WCAG's 4.5:1 contrast against whatever it sits on - the page's
palette (amber #F59E0B, green #10B981) is for fills and rules, and read as
low as 1.9:1 when used as text on its own tint. The document declares its
language, shows its title rather than the filename, and has a bookmark per
section. What fpdf2 can't do is tag the content (headings, paragraphs,
lists) or mark the page footer as decoration, so this is not a tagged
PDF/UA document: the web page remains the accessible version.
"""
import re
import unicodedata

from fpdf import FPDF, ViewerPreferences

INK = (31, 41, 55)
MUTED = (107, 114, 128)
RULE = (229, 231, 235)
ACCENT = (37, 99, 235)
AMBER = "#F59E0B"

_PUNCT = {
    "—": "-", "–": "-", "‘": "'", "’": "'", "“": '"',
    "”": '"', "…": "...", "•": "-", " ": " ", "→": "->",
}


def _t(text):
    """Latin-1-safe text for the core font."""
    if text is None:
        return ""
    text = str(text)
    for src, dst in _PUNCT.items():
        text = text.replace(src, dst)
    text = unicodedata.normalize("NFKC", text)
    return text.encode("latin-1", "ignore").decode("latin-1").strip()


def _plain(text):
    """Drop HTML tags and markdown emphasis/links, keeping the words."""
    text = re.sub(r"<br\s*/?>", "\n", str(text or ""))
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = text.replace("**", "").replace("__", "")
    # The page's wording points at a tab; the PDF has a section instead.
    text = text.replace("Accessibility Report tab", "Accessibility Report section")
    return _t(text)


def _rgb(hex_colour):
    h = str(hex_colour or "#6B7280").lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


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


class _ReportPDF(FPDF):
    def __init__(self, footer_text):
        super().__init__(format="A4")
        self.footer_text = footer_text
        self.set_margins(16, 16, 16)
        self.set_auto_page_break(True, margin=18)

    def footer(self):
        self.set_y(-12)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(*MUTED)
        self.cell(0, 5, _t(self.footer_text), align="L")
        self.set_x(self.l_margin)
        self.cell(0, 5, f"Page {self.page_no()} of {{nb}}", align="R")

    def multi_cell(self, *args, align="L", **kwargs):
        # fpdf2 justifies by default, which spreads short lines out.
        return super().multi_cell(*args, align=align, **kwargs)

    @property
    def content_w(self):
        return self.w - self.l_margin - self.r_margin

    def heading(self, text):
        # Keep a heading with at least a few lines of what follows it.
        if self.get_y() > self.h - 45:
            self.add_page()
        self.ln(4)
        # A bookmark per section, so the document can be navigated.
        self.start_section(_t(text))
        self.set_font("Helvetica", "B", 13)
        self.set_text_color(*INK)
        self.cell(0, 7, _t(text), new_x="LMARGIN", new_y="NEXT")
        y = self.get_y()
        self.set_draw_color(*RULE)
        self.set_line_width(0.3)
        self.line(self.l_margin, y, self.w - self.r_margin, y)
        self.ln(3)

    def para(self, text, size=10, colour=INK, style="", h=5):
        self.set_font("Helvetica", style, size)
        self.set_text_color(*colour)
        self.multi_cell(0, h, _t(text), new_x="LMARGIN", new_y="NEXT")

    def bullet(self, text, indent=4):
        """A bullet whose leading '**Label:**' (if any) is set in bold."""
        match = re.match(r"\*\*(.+?)\*\*\s*(.*)", str(text), re.S)
        bold, rest = (match.group(1), match.group(2)) if match else ("", str(text))
        left = self.l_margin
        self.set_x(left + indent)
        self.set_font("Helvetica", "", 10)
        self.set_text_color(*INK)
        self.cell(4, 5, "-")
        self.set_left_margin(left + indent + 4)
        if bold:
            self.set_font("Helvetica", "B", 10)
            self.write(5, _t(bold) + " ")
            self.set_font("Helvetica", "", 10)
        self.write(5, _plain(rest))
        self.ln(6)
        self.set_left_margin(left)
        self.set_x(left)

    def card(self, title, badge=None, colour="#6B7280", lines=(), indent=0, fill=True):
        """
        A block with a coloured left rule, like the page's section cards.
        `lines` is a sequence of (text, size, rgb) drawn below the title.
        """
        rgb = _rgb(colour)
        x = self.l_margin + indent
        w = self.content_w - indent
        card_bg = _tint(rgb, 0.94) if fill else (255, 255, 255)
        badge_w = 0
        if badge:
            self.set_font("Helvetica", "B", 8)
            badge_w = self.get_string_width(_t(badge).upper()) + 4

        title_w = w - 8 - badge_w - 2
        lines = [(t, size, c) for t, size, c in lines if t]

        # Measure first so the fill can be drawn beneath the text - fpdf2
        # has no z-order, and drawing text twice would duplicate it for
        # copy/paste and screen readers.
        height = 2
        if title:
            self.set_font("Helvetica", "B", 10)
            height += self.multi_cell(title_w, 5, _t(title), dry_run=True, output="HEIGHT")
        for text, size, _ in lines:
            self.set_font("Helvetica", "", size)
            height += self.multi_cell(w - 8, size * 0.45, _t(text), dry_run=True,
                                      output="HEIGHT") + 0.5
        height += 1.5

        if self.get_y() + height > self.page_break_trigger:
            self.add_page()
        top = self.get_y()
        if fill:
            self.set_fill_color(*card_bg)
            self.rect(x, top, w, height, style="F")
        self.set_fill_color(*rgb)
        self.rect(x, top, 1.2, height, style="F")

        # The badge is drawn before the text, although it sits top right, so
        # that text extraction and screen readers meet the status first
        # ("NOT STARTED, Assessment Detail, ...") rather than after the
        # description and date.
        if badge:
            badge_bg = _tint(rgb, 0.82)
            self.set_font("Helvetica", "B", 8)
            self.set_fill_color(*badge_bg)
            self.set_text_color(*_readable(rgb, badge_bg))
            self.set_xy(x + w - badge_w - 3, top + 2.1)
            self.cell(badge_w, 4.8, _t(badge).upper(), align="C", fill=True)

        y = top + 2
        if title:
            self.set_xy(x + 4, y)
            self.set_font("Helvetica", "B", 10)
            self.set_text_color(*INK)
            self.multi_cell(title_w, 5, _t(title), new_x="LMARGIN", new_y="NEXT")
            y = self.get_y()
        for text, size, text_rgb in lines:
            self.set_xy(x + 4, y)
            self.set_font("Helvetica", "", size)
            self.set_text_color(*_readable(text_rgb, card_bg))
            self.multi_cell(w - 8, size * 0.45, _t(text), new_x="LMARGIN", new_y="NEXT")
            y = self.get_y() + 0.5

        self.set_xy(self.l_margin, top + height + 1.5)


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
    code, name = data.get("code", ""), data.get("name", "")
    pdf = _ReportPDF(f"Module Report - {code} - generated {data.get('generated', '')}")
    pdf.set_title(_t(f"Module Report - {code} {name}"))
    pdf.set_author("Faculty of Social Sciences Digital Learning")
    pdf.set_lang("en-GB")
    # Viewers show the title above rather than "Module Report - EDC313.pdf".
    pdf.viewer_preferences = ViewerPreferences(display_doc_title=True)
    pdf.add_page()

    # Title block.
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*MUTED)
    pdf.cell(0, 5, "FACULTY OF SOCIAL SCIENCES - MODULE REPORT", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "B", 18)
    pdf.set_text_color(*INK)
    pdf.multi_cell(0, 8, _t(f"{code} - {name}"), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    meta = [("Module Lead", data.get("lead") or "--"),
            ("Level", data.get("level") or "--"),
            ("Audit Status", data.get("audit_status") or "--"),
            ("Report generated", data.get("generated") or "--")]
    # Audit Status can carry a full timestamp, so it gets the widest column.
    widths = [w * pdf.content_w for w in (0.28, 0.16, 0.34, 0.22)]
    top = pdf.get_y()
    pdf.set_fill_color(249, 250, 251)
    pdf.rect(pdf.l_margin, top, pdf.content_w, 14, style="F")
    x = pdf.l_margin + 3
    for (label, value), col_w in zip(meta, widths):
        pdf.set_xy(x, top + 2)
        pdf.set_font("Helvetica", "", 7.5)
        pdf.set_text_color(*MUTED)
        pdf.cell(col_w - 4, 4, label.upper())
        # Shrink rather than overflow into the next column.
        size = 9
        pdf.set_font("Helvetica", "B", size)
        while size > 6 and pdf.get_string_width(_t(value)) > col_w - 4:
            size -= 0.5
            pdf.set_font("Helvetica", "B", size)
        pdf.set_xy(x, top + 6.5)
        pdf.set_text_color(*INK)
        pdf.cell(col_w - 4, 5, _t(value))
        x += col_w
    pdf.set_xy(pdf.l_margin, top + 16)
    if data.get("site_url"):
        pdf.set_font("Helvetica", "U", 9)
        pdf.set_text_color(*ACCENT)
        pdf.cell(0, 5, "Open the module site in Blackboard", link=data["site_url"],
                 new_x="LMARGIN", new_y="NEXT")

    # Summary.
    pdf.heading("Report Summary")
    if data.get("summary_intro"):
        pdf.para(data["summary_intro"])
        pdf.ln(2)
    points = data.get("points") or []
    if points:
        pdf.para("Still to do", style="B")
        pdf.ln(1)
        for point in points:
            pdf.bullet(point)
    else:
        pdf.para("Nothing outstanding right now.")
    if data.get("refreshed"):
        pdf.ln(1)
        pdf.para(data["refreshed"], size=8, colour=MUTED, h=4)

    if data.get("comment"):
        pdf.heading(data.get("comment_heading") or "Comments from your Digital Learning Advisor")
        pdf.card("", colour="#93C5FD", fill=False,
                 lines=[(_plain(data["comment"]), 10, INK)])

    # Actions.
    actions = data.get("actions") or []
    pdf.heading(f"Actions ({len(actions)})")
    if actions:
        for item in actions:
            pdf.card(_plain(item.get("label")), colour=AMBER,
                     lines=[(_plain(item.get("description")), 9, MUTED)])
    else:
        pdf.para("Nothing outstanding right now.")

    # Blackboard template.
    template = data.get("template") or []
    if template:
        pdf.heading("Blackboard Template")
        pdf.para("The structure of your Blackboard course and its measured or observed "
                 "state - for example whether items are visible to students or have "
                 "been edited.", size=9, colour=MUTED, h=4.5)
        pdf.ln(2)
        for row in template:
            indent = row.get("depth", 0) * 7
            if row["kind"] == "heading":
                pdf.set_x(pdf.l_margin + indent)
                pdf.set_font("Helvetica", "B", 10)
                pdf.set_text_color(*INK)
                pdf.cell(0, 7, _t(row["label"]), new_x="LMARGIN", new_y="NEXT")
                if row.get("note"):
                    pdf.set_x(pdf.l_margin + indent)
                    pdf.para(row["note"], size=8, colour=MUTED, h=4)
                continue
            lines = []
            if row.get("show_detail"):
                lines = [(_plain(row.get("action")), 8.5, (55, 65, 81)),
                         (_plain(row.get("footer")), 8, MUTED)]
            pdf.card(row["label"], badge=row.get("badge"), colour=row.get("colour"),
                     lines=lines, indent=indent)

    # Accessibility.
    ally = data.get("ally")
    if ally is not None:
        pdf.heading("Accessibility Report")
        if ally.get("message"):
            pdf.para(ally["message"])
        else:
            pdf.para(f"Based on the institutional Ally data snapshot from "
                     f"{ally.get('snapshot_date') or '--'}. This is a summary, not a "
                     "replacement for the Ally Accessibility Report in Blackboard "
                     "(Books & Course Tools > Ally Accessibility Report), which is live "
                     "and shows which files are affected.", size=9, colour=MUTED, h=4.5)
            pdf.ln(3)
            if ally.get("maturity"):
                pdf.card(ally["maturity"], colour="#6B7280", lines=[])

            scores = ally.get("scores") or []
            if scores:
                box_w = (pdf.content_w - 6) / len(scores)
                top = pdf.get_y()
                for i, (label, pct, sub, colour) in enumerate(scores):
                    rgb = _rgb(colour)
                    box_bg = _tint(rgb, 0.9)
                    x = pdf.l_margin + i * (box_w + 3)
                    pdf.set_fill_color(*box_bg)
                    pdf.rect(x, top, box_w, 22, style="F")
                    pdf.set_xy(x, top + 2)
                    pdf.set_font("Helvetica", "B", 8)
                    pdf.set_text_color(*_readable(rgb, box_bg))
                    pdf.cell(box_w, 4, _t(label).upper(), align="C")
                    pdf.set_xy(x, top + 6.5)
                    pdf.set_font("Helvetica", "B", 17)
                    pdf.cell(box_w, 8, "--" if pct is None else f"{pct:.1f}%", align="C")
                    pdf.set_xy(x, top + 15.5)
                    pdf.set_font("Helvetica", "", 8)
                    pdf.set_text_color(*_readable(MUTED, box_bg))
                    pdf.cell(box_w, 4, _t(sub), align="C")
                pdf.set_xy(pdf.l_margin, top + 26)

            if ally.get("disabled"):
                pdf.card("Ally is switched off for this course", colour=AMBER,
                         lines=[("Students get no alternative formats and the module lead "
                                 "sees no feedback.", 9, MUTED)])

            categories = ally.get("categories") or []
            if categories:
                total = sum(int(c.get("items", 0)) for c in categories)
                pdf.ln(1)
                pdf.para(f"Summary of accessibility issues ({total} items across "
                         f"{len(categories)} area{'' if len(categories) == 1 else 's'})",
                         style="B")
                pdf.ln(2)
                for c in categories:
                    items, checks = int(c.get("items", 0)), int(c.get("checks", 0))
                    count = (f"{items} item{'' if items == 1 else 's'} across {checks} "
                             f"issue type{'' if checks == 1 else 's'}")
                    pdf.card(c.get("title"), colour=c.get("colour"),
                             lines=[(count, 8, MUTED), (_plain(c.get("why")), 9, (75, 85, 99))])
            elif ally.get("is_template"):
                pdf.para("This course still holds only its rolled-over template, so "
                         "there's nothing to report yet.", colour=MUTED)
            else:
                pdf.para("No accessibility issues reported.")

    return bytes(pdf.output())
