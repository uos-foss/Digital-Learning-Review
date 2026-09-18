"""
Documentation views for the Resources & Support page.

The prose lives in `docs/*.md` rather than in this module, so a changelog entry
or a help correction is a markdown edit rather than a Python change. Paths are
resolved from `__file__`, not the working directory, because the container runs
from /app while local development runs from the project root.
"""

import logging
import re
from pathlib import Path

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = PROJECT_ROOT / "docs"

# A markdown heading at the two levels the FAQ files use: '##' groups related
# questions, '###' is a question itself. Deliberately not a full markdown
# parser - the FAQ files contain no fenced code blocks, so there is nothing a
# line-level match can mistake a heading for. If one ever gains a code block
# with a '###' line inside it, this needs to learn about fences.
_FAQ_HEADING = re.compile(r"^(#{2,3})\s+(.*\S)\s*$")


def _read_doc(filename: str):
    """
    Returns a docs/ markdown file's text, or None having already reported why.

    Every user can reach these pages, so a missing file reports the path it
    looked for and moves on rather than raising - a documentation gap should
    not take the tab down.
    """
    path = DOCS_DIR / filename
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        logging.error(f"❌ Documentation file not found: {path}")
        st.error(f"Documentation file not found: `{path}`")
    except OSError as e:
        logging.error(f"❌ Could not read documentation file {path}: {e}")
        st.error(f"Could not read `{path}`: {e}")
    return None


def _render_doc(filename: str):
    """Renders a markdown file from docs/ as one continuous page."""
    text = _read_doc(filename)
    if text is not None:
        st.markdown(text)


def _render_faq_doc(filename: str):
    """
    Renders an FAQ markdown file as collapsed expanders, one per question.

    The source stays ordinary markdown - '### question' with its answer
    beneath, optionally grouped under '## section' - so editing the FAQ is
    still a markdown edit, and the file would still read correctly if it were
    ever rendered flat by _render_doc(). The splitting happens here rather
    than in the files because an FAQ is scanned rather than read: a reader
    wants the list of questions first and one answer second.

    Anything before the first heading renders as a plain intro above the
    expanders.
    """
    text = _read_doc(filename)
    if text is None:
        return

    intro = []
    question = None
    body = []

    def flush_intro():
        # Held back until the first heading so it renders above the expanders
        # rather than after them. Emptied on the first call, so every later
        # call is a no-op.
        nonlocal intro
        if intro:
            blurb = "\n".join(intro).strip()
            if blurb:
                st.markdown(blurb)
            intro = []

    def flush_question():
        nonlocal question, body
        if question is not None:
            with st.expander(question, expanded=False):
                st.markdown("\n".join(body).strip())
        question, body = None, []

    for line in text.splitlines():
        match = _FAQ_HEADING.match(line)
        if match and match.group(1) == "###":
            flush_intro()
            flush_question()
            question = match.group(2)
        elif match and match.group(1) == "##":
            flush_intro()
            flush_question()
            st.subheader(match.group(2))
        elif question is not None:
            body.append(line)
        else:
            intro.append(line)

    flush_intro()
    flush_question()


def view_about():
    st.title("👋 Welcome to the Digital Learning Review Portal")
    _render_doc("about.md")


def view_help():
    st.title("💡 Help & Support Guide")
    _render_doc("help.md")
    st.info("✉️ For technical support or database access requests, please contact the **FOSS Digital Learning Team**.")


def view_changelog():
    st.title("📜 Release Changelog")
    _render_doc("changelog.md")


def view_developer_guide():
    st.title("💻 Developer Guide")
    _render_doc("developer-guide.md")


def view_faq():
    """
    Frequently asked questions, split by audience.

    Every section is visible to every account rather than filtered by
    capability: a module lead reading how the audit checklist works is the
    point, not a leak - a finding raised with them is easier to act on when
    they can see where it came from - and an advisor needs to know what a lead
    sees in order to answer their questions about it.
    """
    st.title("❓ Frequently Asked Questions")
    tabs = st.tabs([
        "🌐 Everyone",
        "🔍 For Digital Learning Advisors",
        "🧑‍🏫 For Module Leads",
        "🏫 For School Leadership",
    ])
    for tab, filename in zip(tabs, ("faq-everyone.md", "faq-dla.md",
                                    "faq-ml.md", "faq-sl.md")):
        with tab:
            _render_faq_doc(filename)
