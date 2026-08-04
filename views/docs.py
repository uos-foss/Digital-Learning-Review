"""
Documentation views for the Resources & Support page.

The prose lives in `docs/*.md` rather than in this module, so a changelog entry
or a help correction is a markdown edit rather than a Python change. Paths are
resolved from `__file__`, not the working directory, because the container runs
from /app while local development runs from the project root.
"""

import logging
from pathlib import Path

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = PROJECT_ROOT / "docs"
ASSETS_DIR = PROJECT_ROOT / "assets"


def _render_doc(filename: str):
    """
    Renders a markdown file from docs/.

    Every user can reach this page, so a missing file reports the path it looked
    for and moves on rather than raising - a documentation gap should not take
    the tab down.
    """
    path = DOCS_DIR / filename
    try:
        st.markdown(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        logging.error(f"❌ Documentation file not found: {path}")
        st.error(f"Documentation file not found: `{path}`")
    except OSError as e:
        logging.error(f"❌ Could not read documentation file {path}: {e}")
        st.error(f"Could not read `{path}`: {e}")


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


def view_contribute():
    st.title("🤝 How to Contribute")
    st.write("Learn how to collaborate, update, and extend the Digital Learning Review project.")

    import streamlit.components.v1 as components

    html_path = ASSETS_DIR / "contribute.html"
    if html_path.exists():
        try:
            html_content = html_path.read_text(encoding="utf-8")

            # Render full-width responsive container
            # Height of 650px fits a standard 16:9 slide nicely
            components.html(html_content, height=650, scrolling=True)
        except Exception as e:
            st.error(f"Failed to load the slide deck: {e}")
    else:
        st.warning(f"The HTML slide deck is currently missing. Expected it at `{html_path}`.")
