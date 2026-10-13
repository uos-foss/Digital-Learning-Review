"""
`with get_db_connection() as conn:` is a complete unit of work.

Leaving the block commits (or rolls back on an exception, which propagates)
and then closes the connection. sqlite3's own context manager does not close,
which left every one of these connections open until garbage collection.
Uses a throwaway SQLite file; the real database is never touched.

Run from the repo root:  .venv/Scripts/python -m pytest
"""

import sqlite3

import pytest

import database


@pytest.fixture
def db(tmp_path, monkeypatch):
    path = tmp_path / "conn.db"
    monkeypatch.setattr(database, "DB_PATH", str(path))
    with database.get_db_connection() as conn:
        conn.execute("CREATE TABLE t (x INTEGER)")
    return path


def _count(path):
    conn = sqlite3.connect(path)
    try:
        return conn.execute("SELECT COUNT(*) FROM t").fetchone()[0]
    finally:
        conn.close()


def _is_closed(conn):
    try:
        conn.execute("SELECT 1")
    except sqlite3.ProgrammingError:
        return True
    return False


def test_the_block_commits_and_closes(db):
    with database.get_db_connection() as conn:
        conn.execute("INSERT INTO t VALUES (1)")
    assert _is_closed(conn)
    assert _count(db) == 1


def test_an_exception_rolls_back_closes_and_propagates(db):
    with pytest.raises(ValueError):
        with database.get_db_connection() as conn:
            conn.execute("INSERT INTO t VALUES (1)")
            raise ValueError("boom")
    assert _is_closed(conn)
    assert _count(db) == 0


def test_rows_are_still_addressable_by_column_name(db):
    with database.get_db_connection() as conn:
        conn.execute("INSERT INTO t VALUES (7)")
        row = conn.execute("SELECT x FROM t").fetchone()
    assert row["x"] == 7


def test_a_connection_held_without_with_is_still_closed_explicitly(db):
    conn = database.get_db_connection()
    assert not _is_closed(conn)
    conn.close()
    assert _is_closed(conn)
