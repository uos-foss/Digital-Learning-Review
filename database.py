import sqlite3
import os
import pandas as pd
import platform

def get_database_path():
    """
    Dynamically determines the path to the shared SQLite database.
    1. If running inside Docker (production VM), uses standard '/app/data/audit_cache.db'.
    2. If running locally, looks for a sibling 'shared-data' directory 
       or defaults to a local './data/audit_cache.db' directory.
    """
    production_path = os.getenv("DB_PATH", "/app/data/audit_cache.db")
    if (os.name == "posix" and os.path.exists("/app/data")) or os.environ.get("AM_I_DOCKER") == "true":
        return production_path

    # Check for ../shared-data/ sibling folder relative to this file
    sibling_shared_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "shared-data"))
    if os.path.exists(sibling_shared_dir):
        return os.path.join(sibling_shared_dir, "audit_cache.db")

    # Default fallback to localized project folder
    local_fallback_dir = os.path.join(os.path.dirname(__file__), "data")
    return os.path.join(local_fallback_dir, "audit_cache.db")

DB_PATH = get_database_path()

def init_db():
    """Initializes schema and tables if they do not exist."""
    db_dir = os.path.dirname(DB_PATH)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
        
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
            comments TEXT,
            is_synced INTEGER DEFAULT 0
        )
    """)
    
    # Graceful migration for existing DB
    try:
        cursor.execute("ALTER TABLE self_audit_checklist ADD COLUMN is_synced INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass # Column already exists
        
    # Create AI Audit write queue table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ai_audit_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            module_code TEXT,
            module_title TEXT,
            school TEXT,
            user_id TEXT,
            gen_ai_activity TEXT,
            assessment_title TEXT,
            assessment_type TEXT,
            ai_usability TEXT,
            ai_intended_use TEXT,
            status TEXT,
            is_synced INTEGER DEFAULT 0
        )
    """)
        
    conn.commit()
    conn.close()

def get_db_connection():
    """
    Establishes an SQLite connection to the shared database.
    """
    # 1. Ensure the enclosing folder structure exists locally or in-container
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    
    conn = sqlite3.connect(DB_PATH)

    # 🌟 THE FIX: Allow accessing columns by names (string keys) instead of tuple numbers
    conn.row_factory = sqlite3.Row
    
    # Enable WAL mode for asynchronous concurrency
    conn.execute("PRAGMA journal_mode=WAL;")
    # Set a busy timeout (5000ms) to handle multi-client queues gracefully
    conn.execute("PRAGMA busy_timeout=5000;")
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
                id, timestamp, module_code, module_name, welcome_message, contacts_complete, outline_visible, assessment_overview, comments, is_synced
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
            ON CONFLICT(id) DO UPDATE SET
                timestamp=excluded.timestamp,
                module_name=excluded.module_name,
                welcome_message=excluded.welcome_message,
                contacts_complete=excluded.contacts_complete,
                outline_visible=excluded.outline_visible,
                assessment_overview=excluded.assessment_overview,
                comments=excluded.comments,
                is_synced=0
        """, (
            record_id, timestamp, module_code, module_name, welcome_msg, contacts, outline, assessment, comments
        ))
        conn.commit()

def get_unsynced_checklists():
    """Returns a list of checklist records that haven't been synced to Google Sheets yet."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM self_audit_checklist WHERE is_synced = 0")
        return [dict(row) for row in cursor.fetchall()]

def mark_checklists_synced(record_ids: list):
    """Marks a list of checklist IDs as synced."""
    if not record_ids:
        return
    with get_db_connection() as conn:
        cursor = conn.cursor()
        placeholders = ','.join('?' * len(record_ids))
        cursor.execute(f"UPDATE self_audit_checklist SET is_synced = 1 WHERE id IN ({placeholders})", record_ids)
        conn.commit()

def save_ai_response(payload: dict):
    """Saves a new AI Audit response to the local queue."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO ai_audit_queue (
                timestamp, module_code, module_title, school, user_id,
                gen_ai_activity, assessment_title, assessment_type,
                ai_usability, ai_intended_use, status, is_synced
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
        """, (
            payload.get("Timestamp", ""),
            payload.get("Module Code", ""),
            payload.get("Module Title", ""),
            payload.get("School", ""),
            payload.get("User ID", ""),
            payload.get("Gen AI Learning Activity", ""),
            payload.get("Assessment Title", ""),
            payload.get("Assessment Type", ""),
            payload.get("AI Usability", ""),
            payload.get("AI Intended Use", ""),
            payload.get("Status", "")
        ))
        conn.commit()

def get_unsynced_ai_responses():
    """Returns a list of AI Audit records that haven't been synced to Google Sheets yet."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM ai_audit_queue WHERE is_synced = 0")
        return [dict(row) for row in cursor.fetchall()]

def mark_ai_responses_synced(record_ids: list):
    """Marks a list of AI Audit queue IDs as synced."""
    if not record_ids:
        return
    with get_db_connection() as conn:
        cursor = conn.cursor()
        placeholders = ','.join('?' * len(record_ids))
        cursor.execute(f"UPDATE ai_audit_queue SET is_synced = 1 WHERE id IN ({placeholders})", record_ids)
        conn.commit()
