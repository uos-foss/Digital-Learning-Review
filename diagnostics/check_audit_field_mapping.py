"""
Checks that audit_fields (edited via the Admin Panel's Audit Field Manager,
and bidirectionally synced with the Google Sheets "Checklist_Fields" tab)
still agrees with processing.TEMPLATE_SECTIONS about which checklist field
maps to which Blackboard Template Alignment section.

Both editing surfaces are free text with no structural link back to
TEMPLATE_SECTIONS, so a wording change on either side can silently retarget
which section a field's answer overrides via readiness_manual_override() -
exactly what happened to 'student_voice', whose own label ("Student Voice >
How Your Feedback Shapes This Module") named a different section than the
one it was actually mapped to in code. The Admin Panel and the Sheets sync
now lock a mapped field's label to its section's canonical name going
forward (see views/admin_panel.py's Audit Field Manager and sync_data.py's
sync_checklist_fields()), but this is the thing to run after touching
TEMPLATE_SECTIONS, restoring an old Sheets version, or any time this class
of bug is suspected again.

    python diagnostics/check_audit_field_mapping.py
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from database import get_db_connection, table_exists  # noqa: E402
from processing import (  # noqa: E402
    TEMPLATE_SECTIONS, SECTION_KEY_BY_AUDIT_FIELD, LEAD_OWNED_SECTIONS,
    INERT_TEXT_FIELD_IDS,
)

FAILURES = []


def check(label, condition, detail=""):
    mark = "PASS" if condition else "FAIL"
    print(f"  [{mark}] {label}" + (f"  ({detail})" if detail else ""))
    if not condition:
        FAILURES.append(label)


def main():
    with get_db_connection() as conn:
        if not table_exists(conn, "audit_fields"):
            print("No audit_fields table - nothing to check.")
            return 1
        rows = conn.execute(
            "SELECT id, label, field_type, is_active FROM audit_fields").fetchall()
    fields = {r[0]: {'label': r[1], 'field_type': r[2], 'is_active': bool(r[3])} for r in rows}

    print(f"{len(fields)} audit_fields rows; "
          f"{len(SECTION_KEY_BY_AUDIT_FIELD)} audit_field_ids mapped in TEMPLATE_SECTIONS\n")

    print("Mapped fields (checklist answer overrides a Template Alignment section)")
    for fid, section_key in sorted(SECTION_KEY_BY_AUDIT_FIELD.items()):
        canonical = TEMPLATE_SECTIONS[section_key][0]
        owner = TEMPLATE_SECTIONS[section_key][1]
        present = fid in fields
        check(f"'{fid}' exists in audit_fields", present)
        if not present:
            continue
        row = fields[fid]
        check(f"'{fid}' label matches its section ('{canonical}')",
              row['label'] == canonical,
              f"stored as {row['label']!r}" if row['label'] != canonical else "")
        check(f"'{fid}' is a boolean/yes-no field",
              row['field_type'] in ('boolean', 'yes/no'),
              f"stored as {row['field_type']!r}")
        if not row['is_active']:
            print(f"    note: '{fid}' is inactive - {section_key}'s manual-override "
                  f"check is currently unreachable from the Audit Portal")
        lead_flag = "lead-owned" if section_key in LEAD_OWNED_SECTIONS else "institution-owned"
        print(f"    {fid:<20} -> {section_key:<28} ({lead_flag})  \"{canonical}\"")
    print()

    print("Free-standing fields (no Template Alignment section - intentionally not locked)")
    mapped_ids = set(SECTION_KEY_BY_AUDIT_FIELD)
    free = {fid: row for fid, row in fields.items() if fid not in mapped_ids}
    for fid, row in sorted(free.items()):
        flag = " - inert, never becomes a finding" if fid in INERT_TEXT_FIELD_IDS else ""
        print(f"    {fid:<20} ({row['field_type']}){flag}")
    print()

    print("INERT_TEXT_FIELD_IDS (never becomes a finding)")
    for fid in INERT_TEXT_FIELD_IDS:
        check(f"'{fid}' exists and is text",
              fid in fields and fields[fid]['field_type'] == 'text')

    print()
    if FAILURES:
        print(f"{len(FAILURES)} CHECK(S) FAILED:")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
