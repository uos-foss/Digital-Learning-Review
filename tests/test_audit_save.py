"""
Saving an audit is one transaction.

database.save_audit_responses() writes every answer and the audit_status in a
single connection, so a failure part-way leaves the audit exactly as it was.
Uses a throwaway SQLite file; the real database is never touched.

Run from the repo root:  .venv/Scripts/python -m pytest
"""

import sqlite3

import pytest

import database


@pytest.fixture
def db(tmp_path, monkeypatch):
    path = tmp_path / "audit.db"
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE audit_responses (
            module_code TEXT, field_id TEXT, value TEXT,
            auditor_username TEXT, timestamp TEXT,
            PRIMARY KEY (module_code, field_id));
        CREATE TABLE audit_response_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT, module_code TEXT, field_id TEXT,
            old_value TEXT, new_value TEXT, changed_by TEXT, changed_at TEXT);
    """)
    conn.commit()
    conn.close()
    monkeypatch.setattr(database, "DB_PATH", str(path))
    return path


def _rows(path, table):
    conn = sqlite3.connect(path)
    try:
        return conn.execute(f"SELECT * FROM {table} ORDER BY 1, 2").fetchall()
    finally:
        conn.close()


def test_every_answer_and_the_status_are_saved_together(db):
    database.save_audit_responses(
        "tst001", {"sga": "True", "comments": "ok", "audit_status": "submitted"},
        "DLA1", "2026-10-13 10:00:00")
    saved = {r[1]: r[2] for r in _rows(db, "audit_responses")}
    assert saved == {"sga": "True", "comments": "ok", "audit_status": "submitted"}
    assert {r[0] for r in _rows(db, "audit_responses")} == {"TST001"}
    assert len(_rows(db, "audit_response_history")) == 3


def test_a_failure_part_way_leaves_the_audit_untouched(db):
    database.save_audit_responses(
        "TST001", {"sga": "False", "audit_status": "draft"}, "DLA1", "2026-10-13 09:00:00")
    before = (_rows(db, "audit_responses"), _rows(db, "audit_response_history"))

    # A value sqlite can't bind fails the second field, after the first wrote.
    with pytest.raises(Exception):
        database.save_audit_responses(
            "TST001", {"sga": "True", "comments": object(), "audit_status": "submitted"},
            "DLA1", "2026-10-13 10:00:00")

    assert (_rows(db, "audit_responses"), _rows(db, "audit_response_history")) == before


def test_an_unchanged_value_adds_no_history_row(db):
    database.save_audit_responses("TST001", {"sga": "True"}, "DLA1", "2026-10-13 09:00:00")
    database.save_audit_responses("TST001", {"sga": "True"}, "DLA1", "2026-10-13 10:00:00")
    assert len(_rows(db, "audit_response_history")) == 1


def test_the_single_field_wrapper_still_works(db):
    database.save_audit_response("tst001", "sga", "True", "DLA1", "2026-10-13 09:00:00")
    assert _rows(db, "audit_responses")[0][:3] == ("TST001", "sga", "True")
