"""
One-off backfill: records every audit submitted before unflagged audits began
to count as spot-checks (22-09-2026) as a checked spot-check, so the School
Dashboard stops showing those modules as never audited.

Picks every module whose audit_status is 'submitted', first submitted on or after
the start of the academic year, with no spot_checks row for that year. Writes
through database.record_unflagged_spot_check(), which re-checks for an
existing row in the insert itself, so a second run adds nothing.

- Dates and auditor: the module's first submission in audit_response_history
  when there is one, otherwise the audit_status row's own timestamp and
  auditor (the history table only started recording in September 2026).
- Agreement is recorded as 0/0 (shown as "n/a"), not measured. The data the
  DLA was actually shown at the time is gone, and comparing against today's
  data would count every later edit by a lead as the DLA disagreeing.

Dry run by default. Prints what it would add and what the year cutoff left
out; pass --apply to write.

    python scripts/backfill_unflagged_spot_checks.py
    python scripts/backfill_unflagged_spot_checks.py --apply
    python scripts/backfill_unflagged_spot_checks.py --since 2026-09-01 --apply
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from database import DB_PATH, get_db_connection, record_unflagged_spot_check  # noqa: E402
from processing import CURRENT_ACADEMIC_YEAR  # noqa: E402


def default_since(academic_year):
    """1 August of the year an academic year starts in: '2026-27' -> '2026-08-01'."""
    return f"{academic_year[:4]}-08-01"


def find_candidates(conn, academic_year):
    """Submitted audits with no spot_checks row this year, oldest first, with
    the first recorded submission where the history has one."""
    return conn.execute("""
        SELECT r.module_code,
               COALESCE(h.changed_at, r.timestamp) AS submitted_on,
               COALESCE(h.changed_by, r.auditor_username) AS auditor
        FROM audit_responses r
        LEFT JOIN (
            SELECT module_code, changed_at, changed_by,
                   ROW_NUMBER() OVER (PARTITION BY module_code ORDER BY changed_at) AS n
            FROM audit_response_history
            WHERE field_id = 'audit_status' AND LOWER(new_value) = 'submitted'
        ) h ON h.module_code = r.module_code AND h.n = 1
        WHERE r.field_id = 'audit_status' AND LOWER(r.value) = 'submitted'
          AND NOT EXISTS (
              SELECT 1 FROM spot_checks s
              WHERE s.module_code = UPPER(TRIM(r.module_code))
                AND s.academic_year = ?)
        ORDER BY submitted_on
    """, (academic_year,)).fetchall()


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--year", default=CURRENT_ACADEMIC_YEAR,
                        help=f"Academic year to record against (default {CURRENT_ACADEMIC_YEAR}).")
    parser.add_argument("--since",
                        help="Only audits first submitted on or after this date, YYYY-MM-DD "
                             "(default 1 August of the year's start).")
    parser.add_argument("--apply", action="store_true",
                        help="Write the rows. Without this, only prints what would be added.")
    args = parser.parse_args()
    since = args.since or default_since(args.year)

    print(f"Database: {DB_PATH}")
    print(f"Academic year {args.year}, audits submitted on or after {since}.\n")

    with get_db_connection() as conn:
        rows = find_candidates(conn, args.year)
    included = [r for r in rows if str(r[1]) >= since]
    excluded = [r for r in rows if str(r[1]) < since]

    if excluded:
        print(f"Left out, before {since} ({len(excluded)}):")
        for code, submitted_on, auditor in excluded:
            print(f"  {code:<10} {submitted_on}  {auditor}")
        print()

    if not included:
        print("Nothing to backfill.")
        return

    print(f"{'Adding' if args.apply else 'Would add'} ({len(included)}):")
    added = 0
    for code, submitted_on, auditor in included:
        print(f"  {code:<10} {submitted_on}  {auditor}")
        if args.apply:
            added += record_unflagged_spot_check(
                code, args.year, str(auditor or '').strip().upper(), str(submitted_on),
                json.dumps({'backfilled': True}), 0, 0,
                notes=f"Backfilled by {os.path.basename(__file__)}: audit submitted "
                      f"without a flag on {submitted_on}, before these were recorded "
                      f"automatically.")

    if args.apply:
        print(f"\nAdded {added} row(s).")
    else:
        print("\nDry run, nothing written. Re-run with --apply to add these.")


if __name__ == "__main__":
    main()
