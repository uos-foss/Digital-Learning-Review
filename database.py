import sqlite3
import os
import pandas as pd
import platform
import logging

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
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Create high-write dynamic table for checklists
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS audit_checklist (
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
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='self_audit_checklist'")
        if cursor.fetchone():
            cursor.execute("INSERT OR REPLACE INTO audit_checklist SELECT * FROM self_audit_checklist")
            cursor.execute("DROP TABLE self_audit_checklist")
            logging.info("Migrated legacy self_audit_checklist to audit_checklist successfully.")
    except Exception as e:
        logging.error(f"Migration error from self_audit_checklist to audit_checklist: {e}")
        
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

    # Create audit_fields table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS audit_fields (
            id TEXT PRIMARY KEY,
            label TEXT,
            description TEXT,
            field_type TEXT,
            is_active INTEGER DEFAULT 1,
            display_order INTEGER DEFAULT 0
        )
    """)

    # Create audit_responses table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS audit_responses (
            module_code TEXT,
            field_id TEXT,
            value TEXT,
            auditor_username TEXT,
            timestamp TEXT,
            PRIMARY KEY (module_code, field_id)
        )
    """)

    # Create ally_scores table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ally_scores (
            module_code TEXT,
            snapshot_date TEXT,
            measured REAL,
            weighted REAL,
            files INTEGER,
            PRIMARY KEY (module_code, snapshot_date)
        )
    """)

    # Check and migrate ally_scores table if it exists but lacks snapshot_date
    cursor.execute("PRAGMA table_info(ally_scores)")
    ally_columns = [row[1] for row in cursor.fetchall()]
    
    if ally_columns and 'snapshot_date' not in ally_columns:
        cursor.execute("ALTER TABLE ally_scores RENAME TO ally_scores_old")
        cursor.execute("""
            CREATE TABLE ally_scores (
                module_code TEXT,
                snapshot_date TEXT,
                measured REAL,
                weighted REAL,
                files INTEGER,
                PRIMARY KEY (module_code, snapshot_date)
            )
        """)
        cursor.execute("""
            INSERT INTO ally_scores (module_code, snapshot_date, measured, weighted, files)
            SELECT module_code, '2024-09-01', measured, weighted, files
            FROM ally_scores_old
        """)
        cursor.execute("DROP TABLE ally_scores_old")

    # Create leganto_nolist table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS leganto_nolist (
            module_code TEXT PRIMARY KEY
        )
    """)

    # Check and migrate comment_bank table
    cursor.execute("PRAGMA table_info(comment_bank)")
    columns = [row[1] for row in cursor.fetchall()]
    
    if columns and 'category' not in columns:
        # Migrate old comment_bank to new schema
        cursor.execute("ALTER TABLE comment_bank RENAME TO comment_bank_old")
        cursor.execute("""
            CREATE TABLE comment_bank (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT,
                comment TEXT,
                advice TEXT,
                resource_url TEXT,
                resource_text TEXT
            )
        """)
        cursor.execute("""
            INSERT INTO comment_bank (comment)
            SELECT tag FROM comment_bank_old
        """)
        cursor.execute("DROP TABLE comment_bank_old")
    elif not columns:
        # Create comment_bank table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS comment_bank (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT,
                comment TEXT,
                advice TEXT,
                resource_url TEXT,
                resource_text TEXT
            )
        """)

    # Recreate comment_bank table with primary key and autoincrement if it lacks them
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='comment_bank'")
    if cursor.fetchone():
        cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='comment_bank'")
        sql = cursor.fetchone()[0]
        if "PRIMARY KEY" not in sql or "AUTOINCREMENT" not in sql:
            cursor.execute("SELECT * FROM comment_bank")
            old_rows = [dict(r) for r in cursor.fetchall()]
            cursor.execute("DROP TABLE comment_bank")
            cursor.execute("""
                CREATE TABLE comment_bank (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category TEXT,
                    comment TEXT,
                    advice TEXT,
                    resource_url TEXT,
                    resource_text TEXT
                )
            """)
            for row in old_rows:
                url_val = row.get("resource_url") or row.get("resources") or ""
                text_val = row.get("resource_text") or ""
                cursor.execute("""
                    INSERT OR IGNORE INTO comment_bank (id, category, comment, advice, resource_url, resource_text)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (row.get("id"), row.get("category"), row.get("comment"), row.get("advice"), url_val, text_val))

    # Ensure comment_bank has resource_url and resource_text columns if missing
    cursor.execute("PRAGMA table_info(comment_bank)")
    columns = [row[1] for row in cursor.fetchall()]
    if columns:
        if 'resource_url' not in columns:
            if 'resources' in columns:
                cursor.execute("ALTER TABLE comment_bank RENAME COLUMN resources TO resource_url")
                logging.info("Renamed 'resources' column to 'resource_url' in comment_bank table.")
            else:
                cursor.execute("ALTER TABLE comment_bank ADD COLUMN resource_url TEXT")
                logging.info("Added 'resource_url' column to comment_bank table.")
        
        # Re-fetch columns after possible rename
        cursor.execute("PRAGMA table_info(comment_bank)")
        columns = [row[1] for row in cursor.fetchall()]
        
        if 'resource_text' not in columns:
            cursor.execute("ALTER TABLE comment_bank ADD COLUMN resource_text TEXT")
            logging.info("Added 'resource_text' column to comment_bank table.")




    # Create feedback table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS feedback (
            Timestamp TEXT,
            User TEXT,
            School TEXT,
            Category TEXT,
            Rating INTEGER,
            Comments TEXT
        )
    """)

    # Seed default comment bank if empty
    cursor.execute("SELECT COUNT(*) FROM comment_bank")
    if cursor.fetchone()[0] == 0:
        default_tags = [
            ("Accessibility", "Ally report indicates PowerPoint files scoring low due to images with missing descriptions", "Check through the Ally report in course tools to identify files to be fixed. Add image descriptions to images and re-upload the PowerPoint file.", "", ""),
            ("Accessibility", "Ally report: accessibility issues found (descriptions/contrast/headings)", "Review Ally report and fix issues such as image descriptions, contrast, and headings.", "", ""),
            ("Accessibility", "Ally report: untagged or scanned PDFs require OCR", "Run OCR on PDFs to ensure text is readable by screen readers.", "", ""),
            ("VLE Structure", "Upload files directly to VLE (linked Google Drive files bypass Ally checker)", "Upload files directly to VLE instead of linking from Google Drive.", "", ""),
            ("VLE Structure", "VLE structure: partial learning material structure in place", "Complete the missing structure for learning materials.", "", ""),
            ("VLE Structure", "VLE structure: staff contact details or office hours missing", "Add staff contact details and office hours to the VLE.", "", ""),
            ("VLE Structure", "VLE structure: template has not been populated by module lead", "Ensure the module lead populates the required VLE template.", "", ""),
            ("Assessment", "Assessment overview: not completed or inconsistent with SITS", "Update the assessment overview to match SITS exactly.", "", ""),
            ("General", "Module not running: no students or content found", "Confirm if module is running. If not, no further action required.", "", ""),
            ("Compliance", "Compliant: excellent accessibility and structure", "No action needed. Great job!", "", "")
        ]
        cursor.executemany("INSERT INTO comment_bank (category, comment, advice, resource_url, resource_text) VALUES (?, ?, ?, ?, ?)", default_tags)

    # Seed default fields if empty
    cursor.execute("SELECT COUNT(*) FROM audit_fields")
    if cursor.fetchone()[0] == 0:
        default_fields = [
            ("welcome_message", "Welcome message present?", "Check if welcome message is present on VLE.", "boolean", 1, 1),
            ("contacts_complete", "Key staff contacts complete?", "Verify key contacts are populated.", "boolean", 1, 2),
            ("outline_visible", "Module outline visible?", "Ensure module outline is visible to students.", "boolean", 1, 3),
            ("assessment_overview", "Assessment overview consistent with SITS?", "Cross-reference assessment overview with SITS.", "boolean", 1, 4),
            ("comments", "Additional Observations", "Provide any extra comments or observations.", "text", 1, 5)
        ]
        cursor.executemany("""
            INSERT INTO audit_fields (id, label, description, field_type, is_active, display_order)
            VALUES (?, ?, ?, ?, ?, ?)
        """, default_fields)
        
    # Recreate users table with primary key if it lacks one
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
    if cursor.fetchone():
        cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='users'")
        sql = cursor.fetchone()[0]
        if "PRIMARY KEY" not in sql:
            # Load old data
            cursor.execute("SELECT * FROM users")
            old_rows = [dict(r) for r in cursor.fetchall()]
            cursor.execute("DROP TABLE users")
            cursor.execute("""
                CREATE TABLE users (
                    Username TEXT PRIMARY KEY,
                    PasswordHash TEXT,
                    Role TEXT,
                    School TEXT,
                    Capabilities TEXT,
                    Status TEXT
                )
            """)
            for row in old_rows:
                cursor.execute("""
                    INSERT OR IGNORE INTO users (Username, PasswordHash, Role, School, Capabilities, Status)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (row.get("Username"), row.get("PasswordHash"), row.get("Role"), row.get("School"), row.get("Capabilities"), row.get("Status")))
    else:
        cursor.execute("""
            CREATE TABLE users (
                Username TEXT PRIMARY KEY,
                PasswordHash TEXT,
                Role TEXT,
                School TEXT,
                Capabilities TEXT,
                Status TEXT
            )
        """)

    # Recreate roles table with primary key if it lacks one
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='roles'")
    if cursor.fetchone():
        cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='roles'")
        sql = cursor.fetchone()[0]
        if "PRIMARY KEY" not in sql:
            # Load old data
            cursor.execute("SELECT * FROM roles")
            old_rows = [dict(r) for r in cursor.fetchall()]
            cursor.execute("DROP TABLE roles")
            cursor.execute("""
                CREATE TABLE roles (
                    Role TEXT PRIMARY KEY,
                    Capabilities TEXT
                )
            """)
            for row in old_rows:
                cursor.execute("""
                    INSERT OR IGNORE INTO roles (Role, Capabilities)
                    VALUES (?, ?)
                """, (row.get("Role"), row.get("Capabilities")))
    else:
        cursor.execute("""
            CREATE TABLE roles (
                Role TEXT PRIMARY KEY,
                Capabilities TEXT
            )
        """)

    conn.commit()
    conn.close()

def get_db_connection():
    """
    Establishes an SQLite connection to the shared database.
    """
    # Ensure the enclosing folder structure exists locally or in-container
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    
    conn = sqlite3.connect(DB_PATH)
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
    """Saves or updates legacy checklist answers directly to SQLite."""
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
            INSERT INTO audit_checklist (
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
        cursor.execute("SELECT * FROM audit_checklist WHERE is_synced = 0")
        return [dict(row) for row in cursor.fetchall()]

def mark_checklists_synced(record_ids: list):
    """Marks a list of checklist IDs as synced."""
    if not record_ids:
        return
    with get_db_connection() as conn:
        cursor = conn.cursor()
        placeholders = ','.join('?' * len(record_ids))
        cursor.execute(f"UPDATE audit_checklist SET is_synced = 1 WHERE id IN ({placeholders})", record_ids)
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

# --- New Dynamic Fields and Response helper functions ---

def get_audit_fields():
    """Returns all active and inactive audit fields ordered by display_order."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, label, description, field_type, is_active, display_order FROM audit_fields ORDER BY display_order")
        return [dict(row) for row in cursor.fetchall()]

def get_active_audit_fields():
    """Returns only active audit fields ordered by display_order."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, label, description, field_type, is_active, display_order FROM audit_fields WHERE is_active = 1 ORDER BY display_order")
        return [dict(row) for row in cursor.fetchall()]

def save_audit_field(field_id: str, label: str, description: str, field_type: str, is_active: int, display_order: int):
    """Saves or updates an audit field definition."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO audit_fields (id, label, description, field_type, is_active, display_order)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                label=excluded.label,
                description=excluded.description,
                field_type=excluded.field_type,
                is_active=excluded.is_active,
                display_order=excluded.display_order
        """, (field_id.strip().lower(), label, description, field_type, is_active, display_order))
        conn.commit()

def delete_audit_field(field_id: str):
    """Deletes an audit field definition and its associated responses."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM audit_fields WHERE id = ?", (field_id,))
        cursor.execute("DELETE FROM audit_responses WHERE field_id = ?", (field_id,))
        conn.commit()

def get_audit_responses(module_code: str):
    """Returns a dict of responses for a given module code."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT field_id, value, auditor_username, timestamp FROM audit_responses WHERE module_code = ?", (module_code.strip().upper(),))
        rows = cursor.fetchall()
        return {row['field_id']: {
            'value': row['value'],
            'auditor': row['auditor_username'],
            'timestamp': row['timestamp']
        } for row in rows}

def get_all_audit_responses():
    """Returns all audit responses as a DataFrame."""
    with get_db_connection() as conn:
        return pd.read_sql_query("SELECT * FROM audit_responses", conn)

def save_audit_response(module_code: str, field_id: str, value: str, auditor_username: str, timestamp: str):
    """Saves or updates a single audit response."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO audit_responses (module_code, field_id, value, auditor_username, timestamp)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(module_code, field_id) DO UPDATE SET
                value=excluded.value,
                auditor_username=excluded.auditor_username,
                timestamp=excluded.timestamp
        """, (module_code.strip().upper(), field_id, value, auditor_username, timestamp))
        conn.commit()

def save_user_sqlite(username: str, password_hash: str, role: str, school: str, capabilities: str, status: str):
    """Saves or updates a user record in the SQLite database."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO users (Username, PasswordHash, Role, School, Capabilities, Status)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(Username) DO UPDATE SET
                PasswordHash=CASE WHEN excluded.PasswordHash != '' THEN excluded.PasswordHash ELSE users.PasswordHash END,
                Role=excluded.Role,
                School=excluded.School,
                Capabilities=excluded.Capabilities,
                Status=excluded.Status
        """, (username.strip().upper(), password_hash, role, school, capabilities, status))
        conn.commit()

def update_user_field_sqlite(username: str, field_name: str, value: str):
    """Updates a single field for a user in the SQLite database."""
    valid_fields = ["PasswordHash", "Role", "School", "Capabilities", "Status"]
    if field_name not in valid_fields:
        raise ValueError(f"Invalid user field name: {field_name}")
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(f"UPDATE users SET {field_name} = ? WHERE Username = ?", (value, username.strip().upper()))
        conn.commit()

def delete_user_sqlite(username: str):
    """Deletes a user from the SQLite database."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM users WHERE Username = ?", (username.strip().upper(),))
        conn.commit()

def save_role_sqlite(role_name: str, capabilities: str):
    """Saves or updates a role definition in the SQLite database."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO roles (Role, Capabilities)
            VALUES (?, ?)
            ON CONFLICT(Role) DO UPDATE SET
                Capabilities=excluded.Capabilities
        """, (role_name.strip(), capabilities))
        conn.commit()

def update_role_field_sqlite(role_name: str, field_name: str, value: str):
    """Updates a single field for a role in the SQLite database."""
    valid_fields = ["Capabilities"]
    if field_name not in valid_fields:
        raise ValueError(f"Invalid role field name: {field_name}")
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(f"UPDATE roles SET {field_name} = ? WHERE Role = ?", (value, role_name.strip()))
        conn.commit()

def delete_role_sqlite(role_name: str):
    """Deletes a role from the SQLite database."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM roles WHERE Role = ?", (role_name.strip(),))
        conn.commit()

def get_comment_bank():
    """Fetches all predefined quick comments from the database as dictionaries."""
    with get_db_connection() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT id, category, comment, advice, resource_url, resource_text FROM comment_bank ORDER BY category, comment")
        return [dict(row) for row in cursor.fetchall()]

def update_module_lead_sqlite(module_code: str, new_lead: str):
    """Updates the module lead name in SITS and main vle audit tables if they exist."""
    module_code = module_code.strip().upper()
    new_lead = new_lead.strip()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Check and update sits_assessment_2026_27
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='sits_assessment_2026_27'")
        if cursor.fetchone():
            cursor.execute("UPDATE sits_assessment_2026_27 SET [Academic contact] = ? WHERE [CIS unit code] = ?", (new_lead, module_code))
            
        # Check and update main_vle_audit_aut
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='main_vle_audit_aut'")
        if cursor.fetchone():
            cursor.execute("UPDATE main_vle_audit_aut SET [Mod. lead] = ? WHERE [New module code] = ?", (new_lead, module_code))
            
        # Check and update main_vle_audit_spr
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='main_vle_audit_spr'")
        if cursor.fetchone():
            cursor.execute("UPDATE main_vle_audit_spr SET [Mod. lead] = ? WHERE [New module code] = ?", (new_lead, module_code))
            
        conn.commit()

def save_feedback_sqlite(timestamp, username, school, category, rating, comments):
    """Saves a feedback submission in the SQLite database."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO feedback (Timestamp, User, School, Category, Rating, Comments)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (timestamp, username, school, category, rating, comments))
        conn.commit()

# Automatically initialize/migrate database when imported
init_db()

