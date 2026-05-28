import sqlite3
import os
import pandas as pd

DB_DIR = "data"
DB_PATH = os.path.join(DB_DIR, "audit_cache.db")

def init_db():
    """Initializes schema and tables if they do not exist."""
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Create high-write dynamic table for checklists
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS self_audit_checklist (
            id TEXT PRIMARY KEY,
            timestamp TEXT,
            module_code TEXT,
            module_name TEXT,
            welcome_message TEXT,
            contacts_complete TEXT,
            outline_visible TEXT,
            assessment_overview TEXT,
            comments TEXT
        )
    """)
    conn.commit()
    conn.close()

def get_db_connection():
    """Returns a connection to the SQLite database with dictionary rows."""
    init_db()
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    conn.row_factory = sqlite3.Row
    return conn

def cache_dataframe_to_sqlite(df: pd.DataFrame, table_name: str):
    """Writes static audit DataFrames directly to database (overwrites existing tables)."""
    if df is not None and not df.empty:
        with get_db_connection() as conn:
            df.to_sql(table_name, conn, if_exists='replace', index=False)

def save_checklist_record(record_id: str, data_row: list):
    """Saves or updates checklist answers directly to SQLite."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Extract fields from data_row (matches Google Sheets layout)
        timestamp = str(data_row[0])
        module_code = str(data_row[1])
        module_name = str(data_row[2]) if len(data_row) > 2 else ""
        welcome_msg = str(data_row[3]) if len(data_row) > 3 else ""
        contacts = str(data_row[4]) if len(data_row) > 4 else ""
        outline = str(data_row[5]) if len(data_row) > 5 else ""
        assessment = str(data_row[6]) if len(data_row) > 6 else ""
        comments = str(data_row[7]) if len(data_row) > 7 else ""
        
        cursor.execute("""
            INSERT INTO self_audit_checklist (
                id, timestamp, module_code, module_name, welcome_message, contacts_complete, outline_visible, assessment_overview, comments
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                timestamp=excluded.timestamp,
                module_name=excluded.module_name,
                welcome_message=excluded.welcome_message,
                contacts_complete=excluded.contacts_complete,
                outline_visible=excluded.outline_visible,
                assessment_overview=excluded.assessment_overview,
                comments=excluded.comments
        """, (
            record_id, timestamp, module_code, module_name, welcome_msg, contacts, outline, assessment, comments
        ))
        conn.commit()
