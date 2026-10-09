#!/usr/bin/env python
"""Django's command-line utility for the platform spike."""
import os
import sys


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "dlr.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Django is not installed in the active environment. See web/README.md - "
            "the spike uses its own virtualenv, separate from the Streamlit app's."
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
