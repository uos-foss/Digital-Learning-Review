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
        
    # Owned by the satellite AI-Audit app, which shares this database. Kept here
    # only so a cold start from either app produces the same schema - this app
    # never writes it. The column list must stay identical to that app's
    # database.py, or whichever runs first wins and the other breaks.
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
            action_label TEXT,
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

    # The Anthology Ally institutional export, at its native grain. One row per
    # Blackboard course per snapshot - a module can carry more than one course
    # shell (separate cohorts), so aggregation to module_code happens on read.
    #
    # academic_year is a column rather than baked into the table name the way
    # sits_assessment_2026_27 is, so a new year needs no migration.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ally_courses (
            course_id TEXT,
            snapshot_date TEXT,
            academic_year TEXT,
            module_code TEXT,
            course_code TEXT,
            course_name TEXT,
            course_url TEXT,
            department_name TEXT,
            students INTEGER,
            ally_enabled INTEGER,
            last_checked_on TEXT,
            deleted_on TEXT,
            total_files INTEGER,
            total_wysiwyg INTEGER,
            overall_score REAL,
            files_score REAL,
            wysiwyg_score REAL,
            PRIMARY KEY (course_id, snapshot_date)
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_ally_courses_mod
        ON ally_courses (module_code, academic_year, snapshot_date)
    """)

    # The issue census, long rather than wide: Ally ships 39 check columns today
    # and adds more over time, and a long table absorbs a new check without a
    # migration. Only non-zero counts are stored.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ally_issues (
            course_id TEXT,
            snapshot_date TEXT,
            check_name TEXT,
            severity INTEGER,
            items INTEGER,
            PRIMARY KEY (course_id, snapshot_date, check_name)
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_ally_issues_snap
        ON ally_issues (snapshot_date, check_name)
    """)

    # The content-type census, same shape and for the same reason.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ally_content (
            course_id TEXT,
            snapshot_date TEXT,
            content_type TEXT,
            items INTEGER,
            PRIMARY KEY (course_id, snapshot_date, content_type)
        )
    """)

    # Create leganto_nolist table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS leganto_nolist (
            module_code TEXT PRIMARY KEY
        )
    """)

    # Leganto reading-list status/items for courses that DO have a list
    # (draft vs published, and citation counts). Snapshot-per-import, same
    # shape as ally_courses, so a later real-year import doesn't destroy a
    # reference/test set and a specific academic_year can be purged on its
    # own once real data replaces it.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS leganto_lists (
            course_code TEXT,
            snapshot_date TEXT,
            academic_year TEXT,
            module_code TEXT,
            course_name TEXT,
            school TEXT,
            course_term TEXT,
            list_info TEXT,
            draft_lists INTEGER,
            published_lists INTEGER,
            draft_items INTEGER,
            published_items INTEGER,
            status TEXT,
            PRIMARY KEY (course_code, snapshot_date, academic_year)
        )
    """)

    # The faculty Template Alignment Report, at its native grain: one row per
    # Blackboard course per snapshot. As with Ally, a module can carry more than
    # one course shell, so aggregation to module_code happens on read.
    #
    # academic_year is in the primary key, matching leganto_lists rather than
    # ally_courses. Same reason: a reference import of a prior year's export
    # alongside the current one would otherwise collide on a shared snapshot
    # date and silently overwrite.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS readiness_courses (
            course_number TEXT,
            snapshot_date TEXT,
            academic_year TEXT,
            module_code TEXT,
            course_name TEXT,
            course_created_date TEXT,
            term_name TEXT,
            student_count INTEGER,
            school_name TEXT,
            expected_sections INTEGER,
            visible_sections INTEGER,
            hidden_sections INTEGER,
            deleted_sections INTEGER,
            missing_sections INTEGER,
            completeness_score REAL,
            alignment_status TEXT,
            template_version TEXT,
            PRIMARY KEY (course_number, snapshot_date, academic_year)
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_readiness_mod
        ON readiness_courses (module_code, academic_year, snapshot_date)
    """)

    # Per-section status, long rather than wide. The template is versioned
    # (TEMPLATE_VERSION_INDICATOR) and its section list changes between years -
    # 14 sections in 2026/27 - so a wide table would need a migration each time
    # the template gains or loses one. Long absorbs it.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS readiness_sections (
            course_number TEXT,
            snapshot_date TEXT,
            academic_year TEXT,
            section_key TEXT,
            status TEXT,
            last_modified TEXT,
            PRIMARY KEY (course_number, snapshot_date, academic_year, section_key)
        )
    """)

    # Create blackboard_links table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS blackboard_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            module_code TEXT UNIQUE NOT NULL,
            blackboard_link TEXT NOT NULL,
            academic_year TEXT NOT NULL,
            import_date TEXT,
            last_updated TEXT
        )
    """)

    # Create inactive_modules table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS inactive_modules (
            module_code TEXT PRIMARY KEY,
            reason TEXT,
            marked_date TEXT,
            marked_by TEXT
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
            ("welcome_message", "Welcome message present?", "Welcome Message Missing", "Check if welcome message is present on VLE.", "boolean", 1, 1),
            ("contacts_complete", "Key staff contacts complete?", "Staff Contact Details Incomplete", "Verify key contacts are populated.", "boolean", 1, 2),
            ("outline_visible", "Module outline visible?", "Module Outline Missing", "Ensure module outline is visible to students.", "boolean", 1, 3),
            ("assessment_overview", "Assessment overview consistent with SITS?", "Assessment Overview Mismatch", "Cross-reference assessment overview with SITS.", "boolean", 1, 4),
            ("comments", "Additional Observations", "Additional Observations", "Provide any extra comments or observations.", "text", 1, 5)
        ]
        cursor.executemany("""
            INSERT INTO audit_fields (id, label, action_label, description, field_type, is_active, display_order)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, default_fields)
        
    # Migrate audit_fields to include action_label if missing
    cursor.execute("PRAGMA table_info(audit_fields)")
    columns = [row[1] for row in cursor.fetchall()]
    if 'action_label' not in columns:
        cursor.execute("ALTER TABLE audit_fields ADD COLUMN action_label TEXT")
        logging.info("Migrated audit_fields table: added action_label column.")
        
    # Populate/Update defaults for standard fields to be rephrased action items
    cursor.execute("UPDATE audit_fields SET action_label = 'Welcome Message Missing' WHERE id = 'welcome_message' AND (action_label IS NULL OR action_label = '')")
    cursor.execute("UPDATE audit_fields SET action_label = 'Staff Contact Details Incomplete' WHERE id = 'contacts_complete' AND (action_label IS NULL OR action_label = '')")
    cursor.execute("UPDATE audit_fields SET action_label = 'Module Outline Missing' WHERE id = 'outline_visible' AND (action_label IS NULL OR action_label = '')")
    cursor.execute("UPDATE audit_fields SET action_label = 'Assessment Overview Mismatch' WHERE id = 'assessment_overview' AND (action_label IS NULL OR action_label = '')")
    cursor.execute("UPDATE audit_fields SET action_label = 'Additional Observations' WHERE id = 'comments' AND (action_label IS NULL OR action_label = '')")
        
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

# The ai_audit_queue write helpers that used to live here are gone. That queue
# belongs to the satellite AI-Audit app: it inserts the rows, pushes them to its
# own sheet and then deletes them. Writing it from here would have double-posted
# every submission, because that app removes the rows this app only flagged as
# synced. Read the table if you need it; do not write it.

# --- New Dynamic Fields and Response helper functions ---

def get_audit_fields():
    """Returns all active and inactive audit fields ordered by display_order."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, label, action_label, description, field_type, is_active, display_order FROM audit_fields ORDER BY display_order")
        return [dict(row) for row in cursor.fetchall()]

def get_active_audit_fields():
    """Returns only active audit fields ordered by display_order."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, label, action_label, description, field_type, is_active, display_order FROM audit_fields WHERE is_active = 1 ORDER BY display_order")
        return [dict(row) for row in cursor.fetchall()]

def save_audit_field(field_id: str, label: str, action_label: str, description: str, field_type: str, is_active: int, display_order: int):
    """Saves or updates an audit field definition."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO audit_fields (id, label, action_label, description, field_type, is_active, display_order)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                label=excluded.label,
                action_label=excluded.action_label,
                description=excluded.description,
                field_type=excluded.field_type,
                is_active=excluded.is_active,
                display_order=excluded.display_order
        """, (field_id.strip().lower(), label, action_label, description, field_type, is_active, display_order))
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

def table_exists(conn, table_name):
    """True if the named table is present. Defined here rather than in app.py
    so that database.py can use it without importing the entry point."""
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
    return cursor.fetchone() is not None

def get_all_audit_responses():
    """Returns all audit responses as a DataFrame."""
    with get_db_connection() as conn:
        return pd.read_sql_query("SELECT * FROM audit_responses", conn)

def get_ai_declarations():
    """
    Every AI in the Curriculum declaration, as a DataFrame, one row per
    assessment.

    Owned by the satellite AI-Audit app - see the shared database contract in
    docs/developer-guide.md. Read only: this portal must never write these
    tables. ai_audit_queue is that app's durable record; ai_audit_responses is
    its cache of the responses spreadsheet and holds the same declarations
    again, so the two are unioned and de-duplicated with the queue winning.

    Returns an empty frame if the satellite has never run against this
    database, which is the normal state of a fresh local checkout.
    """
    columns = ['module_code', 'module_title', 'school', 'user_id', 'timestamp',
               'gen_ai_activity', 'assessment_title', 'assessment_type',
               'ai_usability', 'ai_intended_use', 'status']
    frames = []

    with get_db_connection() as conn:
        if table_exists(conn, 'ai_audit_queue'):
            frames.append(pd.read_sql_query(
                """
                SELECT module_code, module_title, school, user_id, timestamp,
                       gen_ai_activity, assessment_title, assessment_type,
                       ai_usability, ai_intended_use, status
                FROM ai_audit_queue
                """, conn))

        if table_exists(conn, 'ai_audit_responses'):
            # That table is written by df.to_sql from the spreadsheet, so its
            # columns are the sheet's display headers rather than these names.
            df_resp = pd.read_sql_query("SELECT * FROM ai_audit_responses", conn)
            if not df_resp.empty:
                renames = {
                    'Module Code': 'module_code', 'Module Title': 'module_title',
                    'School': 'school', 'User ID': 'user_id', 'Timestamp': 'timestamp',
                    'Gen AI Learning Activity': 'gen_ai_activity',
                    'Assessment Title': 'assessment_title',
                    'Assessment Type': 'assessment_type',
                    'AI Usability': 'ai_usability',
                    'AI Intended Use': 'ai_intended_use', 'Status': 'status',
                }
                df_resp = df_resp.rename(columns=renames)
                for col in columns:
                    if col not in df_resp.columns:
                        df_resp[col] = ""
                frames.append(df_resp[columns])

    if not frames:
        return pd.DataFrame(columns=columns)

    df = pd.concat(frames, ignore_index=True)
    if df.empty:
        return pd.DataFrame(columns=columns)

    df['module_code'] = df['module_code'].astype(str).str.strip().str.upper()

    key = pd.DataFrame({
        c: df[c].astype(str).str.strip().str.upper()
        for c in ['timestamp', 'module_code', 'assessment_title', 'user_id']
    })
    return df[~key.duplicated(keep='first')].reset_index(drop=True)

# --- Ally institutional report -------------------------------------------
#
# These read the export at its native Blackboard-course grain and leave the
# rollup to module level to processing.aggregate_ally_to_modules(), so the
# weighting rules stay in one testable, I/O-free place.

def get_ally_academic_years():
    """Academic years present in ally_courses, newest first."""
    with get_db_connection() as conn:
        if not table_exists(conn, 'ally_courses'):
            return []
        rows = conn.execute(
            "SELECT DISTINCT academic_year FROM ally_courses "
            "WHERE academic_year IS NOT NULL AND academic_year != '' "
            "ORDER BY academic_year DESC"
        ).fetchall()
    return [r[0] for r in rows]

def get_ally_courses_latest(academic_year=None):
    """One row per Blackboard course, at that course's latest snapshot.

    Snapshots are stored only when a course actually changes, so different
    courses sit at different snapshot_dates and a single MAX over the whole
    table would drop everything that has not moved recently.
    """
    with get_db_connection() as conn:
        if not table_exists(conn, 'ally_courses'):
            return pd.DataFrame()
        if academic_year:
            sql = """
                SELECT c.* FROM ally_courses c
                JOIN (
                    SELECT course_id, MAX(snapshot_date) AS ms
                    FROM ally_courses WHERE academic_year = ? GROUP BY course_id
                ) m ON c.course_id = m.course_id AND c.snapshot_date = m.ms
                WHERE c.academic_year = ?
            """
            return pd.read_sql_query(sql, conn, params=(academic_year, academic_year))
        sql = """
            SELECT c.* FROM ally_courses c
            JOIN (
                SELECT course_id, MAX(snapshot_date) AS ms
                FROM ally_courses GROUP BY course_id
            ) m ON c.course_id = m.course_id AND c.snapshot_date = m.ms
        """
        return pd.read_sql_query(sql, conn)

def _latest_child(table, value_col, academic_year=None):
    """Rows from ally_issues / ally_content for each course's latest snapshot,
    carrying module_code and academic_year across from ally_courses."""
    with get_db_connection() as conn:
        if not table_exists(conn, table) or not table_exists(conn, 'ally_courses'):
            return pd.DataFrame()
        year_filter = "WHERE c.academic_year = ?" if academic_year else ""
        sql = f"""
            SELECT c.module_code, c.academic_year, c.course_id, c.snapshot_date,
                   t.{value_col}, t.items{', t.severity' if table == 'ally_issues' else ''}
            FROM ally_courses c
            JOIN (
                SELECT course_id, MAX(snapshot_date) AS ms
                FROM ally_courses {"WHERE academic_year = ?" if academic_year else ""}
                GROUP BY course_id
            ) m ON c.course_id = m.course_id AND c.snapshot_date = m.ms
            JOIN {table} t
              ON t.course_id = c.course_id AND t.snapshot_date = c.snapshot_date
            {year_filter}
        """
        params = (academic_year, academic_year) if academic_year else ()
        return pd.read_sql_query(sql, conn, params=params)

def get_ally_issues_latest(academic_year=None):
    """Long issue rows for each course's latest snapshot, keyed to module_code."""
    return _latest_child('ally_issues', 'check_name', academic_year)

def get_ally_content_latest(academic_year=None):
    """Long content-type rows for each course's latest snapshot."""
    return _latest_child('ally_content', 'content_type', academic_year)

def get_ally_history(module_code=None, academic_year=None):
    """Every stored snapshot at course grain, for trend charts."""
    clauses, params = [], []
    if module_code:
        clauses.append("module_code = ?")
        params.append(str(module_code).strip().upper())
    if academic_year:
        clauses.append("academic_year = ?")
        params.append(academic_year)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    with get_db_connection() as conn:
        if not table_exists(conn, 'ally_courses'):
            return pd.DataFrame()
        return pd.read_sql_query(
            f"SELECT * FROM ally_courses {where} ORDER BY snapshot_date", conn,
            params=tuple(params))

# The fields that decide whether a course has actually moved since its last
# stored snapshot. Ally re-reports unchanged courses in every weekly export,
# so without this the series fills with ~900 identical rows a week.
_ALLY_CHANGE_COLS = ['last_checked_on', 'total_files', 'total_wysiwyg',
                     'overall_score', 'files_score', 'wysiwyg_score',
                     'students', 'ally_enabled', 'deleted_on']

def save_ally_snapshot(df_courses, df_issues, df_content, force_all=False):
    """Writes one Ally export into ally_courses / ally_issues / ally_content.

    Courses whose measurements are identical to their most recent stored
    snapshot are skipped unless force_all, so the snapshot series holds genuine
    observations only. Returns a dict of counts for the import report.
    """
    if df_courses is None or df_courses.empty:
        return {'courses_written': 0, 'courses_unchanged': 0, 'issues': 0, 'content': 0}

    df_courses = df_courses.copy()

    with get_db_connection() as conn:
        prev = pd.read_sql_query("""
            SELECT c.* FROM ally_courses c
            JOIN (SELECT course_id, MAX(snapshot_date) AS ms
                  FROM ally_courses GROUP BY course_id) m
              ON c.course_id = m.course_id AND c.snapshot_date = m.ms
        """, conn) if table_exists(conn, 'ally_courses') else pd.DataFrame()

    unchanged = 0
    if not force_all and not prev.empty:
        merged = df_courses.merge(
            prev[['course_id'] + _ALLY_CHANGE_COLS],
            on='course_id', how='left', suffixes=('', '_prev'))
        same = pd.Series(True, index=merged.index)
        for col in _ALLY_CHANGE_COLS:
            a = merged[col].astype(str).fillna('')
            b = merged[f'{col}_prev'].astype(str).fillna('')
            same &= (a == b)
        same &= merged['last_checked_on_prev'].notna()
        unchanged = int(same.sum())
        df_courses = df_courses[~same.values].copy()

    if df_courses.empty:
        return {'courses_written': 0, 'courses_unchanged': unchanged, 'issues': 0, 'content': 0}

    keep = set(zip(df_courses['course_id'], df_courses['snapshot_date']))

    def _filter_child(df):
        if df is None or df.empty:
            return pd.DataFrame()
        mask = [k in keep for k in zip(df['course_id'], df['snapshot_date'])]
        return df[mask].copy()

    issues = _filter_child(df_issues)
    content = _filter_child(df_content)

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.executemany("""
            INSERT INTO ally_courses (
                course_id, snapshot_date, academic_year, module_code, course_code,
                course_name, course_url, department_name, students, ally_enabled,
                last_checked_on, deleted_on, total_files, total_wysiwyg,
                overall_score, files_score, wysiwyg_score)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(course_id, snapshot_date) DO UPDATE SET
                academic_year=excluded.academic_year, module_code=excluded.module_code,
                course_code=excluded.course_code, course_name=excluded.course_name,
                course_url=excluded.course_url, department_name=excluded.department_name,
                students=excluded.students, ally_enabled=excluded.ally_enabled,
                last_checked_on=excluded.last_checked_on, deleted_on=excluded.deleted_on,
                total_files=excluded.total_files, total_wysiwyg=excluded.total_wysiwyg,
                overall_score=excluded.overall_score, files_score=excluded.files_score,
                wysiwyg_score=excluded.wysiwyg_score
        """, df_courses[[
            'course_id', 'snapshot_date', 'academic_year', 'module_code', 'course_code',
            'course_name', 'course_url', 'department_name', 'students', 'ally_enabled',
            'last_checked_on', 'deleted_on', 'total_files', 'total_wysiwyg',
            'overall_score', 'files_score', 'wysiwyg_score']].itertuples(index=False, name=None))

        if not issues.empty:
            cursor.executemany("""
                INSERT INTO ally_issues (course_id, snapshot_date, check_name, severity, items)
                VALUES (?,?,?,?,?)
                ON CONFLICT(course_id, snapshot_date, check_name) DO UPDATE SET
                    severity=excluded.severity, items=excluded.items
            """, issues[['course_id', 'snapshot_date', 'check_name', 'severity', 'items']]
                .itertuples(index=False, name=None))

        if not content.empty:
            cursor.executemany("""
                INSERT INTO ally_content (course_id, snapshot_date, content_type, items)
                VALUES (?,?,?,?)
                ON CONFLICT(course_id, snapshot_date, content_type) DO UPDATE SET
                    items=excluded.items
            """, content[['course_id', 'snapshot_date', 'content_type', 'items']]
                .itertuples(index=False, name=None))
        conn.commit()

    logging.info("Ally snapshot written: %d courses (%d unchanged), %d issue rows, %d content rows",
                 len(df_courses), unchanged, len(issues), len(content))
    return {'courses_written': len(df_courses), 'courses_unchanged': unchanged,
            'issues': len(issues), 'content': len(content)}

def refresh_ally_scores_projection(academic_year=None):
    """Rewrites the legacy ally_scores table from ally_courses.

    ally_scores is kept only so views that have not yet moved onto the new
    tables keep working. measured/weighted no longer mean what they did before
    the institutional export landed - they are Ally's own files and overall
    scores. Retire this once every view reads ally_courses.
    """
    df = get_ally_courses_latest(academic_year)
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM ally_scores")
        if df.empty:
            conn.commit()
            return 0
        agg = (df.groupby(['module_code', 'snapshot_date'], as_index=False)
                 .agg(measured=('files_score', 'mean'),
                      weighted=('overall_score', 'mean'),
                      files=('total_files', 'sum')))
        cursor.executemany(
            "INSERT OR REPLACE INTO ally_scores (module_code, snapshot_date, measured, weighted, files)"
            " VALUES (?,?,?,?,?)",
            agg[['module_code', 'snapshot_date', 'measured', 'weighted', 'files']]
               .itertuples(index=False, name=None))
        conn.commit()
    return len(agg)

def purge_legacy_ally_scores():
    """Empties ally_scores of everything not derived from ally_courses.

    Deliberately not wired into init_db(): that runs on import, and a row
    deleter that fires whenever anything touches the shared database is a trap.
    The Admin Panel calls this behind an explicit confirmation.
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        before = cursor.execute("SELECT COUNT(*) FROM ally_scores").fetchone()[0]
        cursor.execute("DELETE FROM ally_scores")
        conn.commit()
    logging.info("Purged %d legacy ally_scores rows.", before)
    return before

# --- Leganto reading lists -------------------------------------------------

_LEGANTO_CHANGE_COLS = ['status', 'draft_lists', 'published_lists', 'draft_items', 'published_items']

def get_leganto_academic_years():
    """Academic years present in leganto_lists, newest first."""
    with get_db_connection() as conn:
        if not table_exists(conn, 'leganto_lists'):
            return []
        rows = conn.execute(
            "SELECT DISTINCT academic_year FROM leganto_lists "
            "WHERE academic_year IS NOT NULL AND academic_year != '' "
            "ORDER BY academic_year DESC"
        ).fetchall()
    return [r[0] for r in rows]

def get_leganto_lists_latest(academic_year=None):
    """One row per Leganto course, at that course's latest snapshot.

    Snapshots are stored only when a course actually changes (see
    save_leganto_snapshot), so different courses sit at different
    snapshot_dates and a single MAX over the whole table would drop
    everything that has not moved recently.
    """
    with get_db_connection() as conn:
        if not table_exists(conn, 'leganto_lists'):
            return pd.DataFrame()
        if academic_year:
            sql = """
                SELECT c.* FROM leganto_lists c
                JOIN (
                    SELECT course_code, MAX(snapshot_date) AS ms
                    FROM leganto_lists WHERE academic_year = ? GROUP BY course_code
                ) m ON c.course_code = m.course_code AND c.snapshot_date = m.ms
                WHERE c.academic_year = ?
            """
            return pd.read_sql_query(sql, conn, params=(academic_year, academic_year))
        sql = """
            SELECT c.* FROM leganto_lists c
            JOIN (
                SELECT course_code, MAX(snapshot_date) AS ms
                FROM leganto_lists GROUP BY course_code
            ) m ON c.course_code = m.course_code AND c.snapshot_date = m.ms
        """
        return pd.read_sql_query(sql, conn)

def save_leganto_snapshot(df_lists, force_all=False):
    """Writes one Leganto reading-list export into leganto_lists.

    Courses whose status/counts are identical to their most recent stored
    snapshot for the *same academic_year* are skipped unless force_all, so
    the snapshot series holds genuine observations only - same discipline as
    save_ally_snapshot. Scoped to academic_year (unlike save_ally_snapshot,
    which never needed to be): two different years can legitimately carry
    identical-looking rows - e.g. a reference import of last year's export
    followed by this year's real one - and that must never be mistaken for
    "nothing changed" and silently skipped.
    """
    if df_lists is None or df_lists.empty:
        return {'written': 0, 'unchanged': 0}

    df_lists = df_lists.copy()

    with get_db_connection() as conn:
        prev = pd.read_sql_query("""
            SELECT c.* FROM leganto_lists c
            JOIN (SELECT course_code, academic_year, MAX(snapshot_date) AS ms
                  FROM leganto_lists GROUP BY course_code, academic_year) m
              ON c.course_code = m.course_code AND c.academic_year = m.academic_year
             AND c.snapshot_date = m.ms
        """, conn) if table_exists(conn, 'leganto_lists') else pd.DataFrame()

    unchanged = 0
    if not force_all and not prev.empty:
        merged = df_lists.merge(
            prev[['course_code', 'academic_year'] + _LEGANTO_CHANGE_COLS],
            on=['course_code', 'academic_year'], how='left', suffixes=('', '_prev'))
        same = pd.Series(True, index=merged.index)
        for col in _LEGANTO_CHANGE_COLS:
            a = merged[col].astype(str).fillna('')
            b = merged[f'{col}_prev'].astype(str).fillna('')
            same &= (a == b)
        same &= merged['status_prev'].notna()
        unchanged = int(same.sum())
        df_lists = df_lists[~same.values].copy()

    if df_lists.empty:
        return {'written': 0, 'unchanged': unchanged}

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.executemany("""
            INSERT INTO leganto_lists (
                course_code, snapshot_date, academic_year, module_code, course_name,
                school, course_term, list_info, draft_lists, published_lists,
                draft_items, published_items, status)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(course_code, snapshot_date, academic_year) DO UPDATE SET
                module_code=excluded.module_code,
                course_name=excluded.course_name, school=excluded.school,
                course_term=excluded.course_term, list_info=excluded.list_info,
                draft_lists=excluded.draft_lists, published_lists=excluded.published_lists,
                draft_items=excluded.draft_items, published_items=excluded.published_items,
                status=excluded.status
        """, df_lists[[
            'course_code', 'snapshot_date', 'academic_year', 'module_code', 'course_name',
            'school', 'course_term', 'list_info', 'draft_lists', 'published_lists',
            'draft_items', 'published_items', 'status']].itertuples(index=False, name=None))
        conn.commit()

    logging.info("Leganto list snapshot written: %d courses (%d unchanged).",
                 len(df_lists), unchanged)
    return {'written': len(df_lists), 'unchanged': unchanged}

def purge_leganto_lists(academic_year):
    """Deletes every leganto_lists row for one academic_year.

    Scoped to a single year rather than the whole table, so a reference/test
    import (e.g. last year's export, imported early to build against) can be
    dropped cleanly once the real current-year export replaces it.
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        if not table_exists(conn, 'leganto_lists'):
            return 0
        before = cursor.execute(
            "SELECT COUNT(*) FROM leganto_lists WHERE academic_year = ?", (academic_year,)
        ).fetchone()[0]
        cursor.execute("DELETE FROM leganto_lists WHERE academic_year = ?", (academic_year,))
        conn.commit()
    logging.info("Purged %d leganto_lists rows for %s.", before, academic_year)
    return before

# --- Module readiness (template alignment) ---------------------------------
#
# These read the faculty Template Alignment Report at its native Blackboard-
# course grain and leave the rollup to module level to
# processing.aggregate_readiness_to_modules(), so the worst-wins rules and the
# bulk-edit-date judgement stay in one testable, I/O-free place.

_READINESS_CHANGE_COLS = ['visible_sections', 'hidden_sections', 'deleted_sections',
                          'missing_sections', 'completeness_score', 'alignment_status']

def get_readiness_academic_years():
    """Academic years present in readiness_courses, newest first."""
    with get_db_connection() as conn:
        if not table_exists(conn, 'readiness_courses'):
            return []
        rows = conn.execute(
            "SELECT DISTINCT academic_year FROM readiness_courses "
            "WHERE academic_year IS NOT NULL AND academic_year != '' "
            "ORDER BY academic_year DESC"
        ).fetchall()
    return [r[0] for r in rows]

def get_readiness_courses_latest(academic_year=None):
    """One row per Blackboard course, at that course's latest snapshot.

    Snapshots are stored only when a course actually changes (see
    save_readiness_snapshot), so different courses sit at different
    snapshot_dates and a single MAX over the whole table would drop everything
    that has not moved recently.
    """
    with get_db_connection() as conn:
        if not table_exists(conn, 'readiness_courses'):
            return pd.DataFrame()
        if academic_year:
            sql = """
                SELECT c.* FROM readiness_courses c
                JOIN (
                    SELECT course_number, MAX(snapshot_date) AS ms
                    FROM readiness_courses WHERE academic_year = ? GROUP BY course_number
                ) m ON c.course_number = m.course_number AND c.snapshot_date = m.ms
                WHERE c.academic_year = ?
            """
            return pd.read_sql_query(sql, conn, params=(academic_year, academic_year))
        sql = """
            SELECT c.* FROM readiness_courses c
            JOIN (
                SELECT course_number, MAX(snapshot_date) AS ms
                FROM readiness_courses GROUP BY course_number
            ) m ON c.course_number = m.course_number AND c.snapshot_date = m.ms
        """
        return pd.read_sql_query(sql, conn)

def get_readiness_sections_latest(academic_year=None):
    """Long per-section rows for each course's latest snapshot, carrying
    module_code across from readiness_courses."""
    with get_db_connection() as conn:
        if (not table_exists(conn, 'readiness_sections')
                or not table_exists(conn, 'readiness_courses')):
            return pd.DataFrame()
        year_filter = "WHERE c.academic_year = ?" if academic_year else ""
        sql = f"""
            SELECT c.module_code, c.academic_year, c.course_number, c.snapshot_date,
                   c.school_name, c.course_created_date, c.student_count,
                   t.section_key, t.status, t.last_modified
            FROM readiness_courses c
            JOIN (
                SELECT course_number, MAX(snapshot_date) AS ms
                FROM readiness_courses {"WHERE academic_year = ?" if academic_year else ""}
                GROUP BY course_number
            ) m ON c.course_number = m.course_number AND c.snapshot_date = m.ms
            JOIN readiness_sections t
              ON t.course_number = c.course_number
             AND t.snapshot_date = c.snapshot_date
             AND t.academic_year = c.academic_year
            {year_filter}
        """
        params = (academic_year, academic_year) if academic_year else ()
        return pd.read_sql_query(sql, conn, params=params)

def get_readiness_history(module_code=None, academic_year=None):
    """Every stored snapshot at course grain, for trend charts."""
    clauses, params = [], []
    if module_code:
        clauses.append("module_code = ?")
        params.append(str(module_code).strip().upper())
    if academic_year:
        clauses.append("academic_year = ?")
        params.append(academic_year)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    with get_db_connection() as conn:
        if not table_exists(conn, 'readiness_courses'):
            return pd.DataFrame()
        return pd.read_sql_query(
            f"SELECT * FROM readiness_courses {where} ORDER BY snapshot_date", conn,
            params=tuple(params))

def save_readiness_snapshot(df_courses, df_sections, force_all=False):
    """Writes one Template Alignment Report into readiness_courses /
    readiness_sections.

    Courses whose section counts and score are identical to their most recent
    stored snapshot for the *same academic_year* are skipped unless force_all,
    so the series holds genuine observations only. Scoped to academic_year for
    the same reason as save_leganto_snapshot: a reference import of a prior
    year's export must never be mistaken for "nothing changed".

    Returns a dict of counts for the import report.
    """
    empty = {'courses_written': 0, 'courses_unchanged': 0, 'sections': 0}
    if df_courses is None or df_courses.empty:
        return empty

    df_courses = df_courses.copy()

    with get_db_connection() as conn:
        prev = pd.read_sql_query("""
            SELECT c.* FROM readiness_courses c
            JOIN (SELECT course_number, academic_year, MAX(snapshot_date) AS ms
                  FROM readiness_courses GROUP BY course_number, academic_year) m
              ON c.course_number = m.course_number AND c.academic_year = m.academic_year
             AND c.snapshot_date = m.ms
        """, conn) if table_exists(conn, 'readiness_courses') else pd.DataFrame()

    unchanged = 0
    if not force_all and not prev.empty:
        merged = df_courses.merge(
            prev[['course_number', 'academic_year'] + _READINESS_CHANGE_COLS],
            on=['course_number', 'academic_year'], how='left', suffixes=('', '_prev'))
        same = pd.Series(True, index=merged.index)
        for col in _READINESS_CHANGE_COLS:
            a = merged[col].astype(str).fillna('')
            b = merged[f'{col}_prev'].astype(str).fillna('')
            same &= (a == b)
        same &= merged['alignment_status_prev'].notna()
        unchanged = int(same.sum())
        df_courses = df_courses[~same.values].copy()

    if df_courses.empty:
        return {'courses_written': 0, 'courses_unchanged': unchanged, 'sections': 0}

    # Only sections belonging to a course we are actually writing, so the child
    # table never carries rows whose parent snapshot was skipped.
    keep = set(zip(df_courses['course_number'], df_courses['snapshot_date'],
                   df_courses['academic_year']))
    if df_sections is None or df_sections.empty:
        sections = pd.DataFrame()
    else:
        mask = [k in keep for k in zip(df_sections['course_number'],
                                       df_sections['snapshot_date'],
                                       df_sections['academic_year'])]
        sections = df_sections[mask].copy()

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.executemany("""
            INSERT INTO readiness_courses (
                course_number, snapshot_date, academic_year, module_code, course_name,
                course_created_date, term_name, student_count, school_name,
                expected_sections, visible_sections, hidden_sections, deleted_sections,
                missing_sections, completeness_score, alignment_status, template_version)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(course_number, snapshot_date, academic_year) DO UPDATE SET
                module_code=excluded.module_code, course_name=excluded.course_name,
                course_created_date=excluded.course_created_date,
                term_name=excluded.term_name, student_count=excluded.student_count,
                school_name=excluded.school_name,
                expected_sections=excluded.expected_sections,
                visible_sections=excluded.visible_sections,
                hidden_sections=excluded.hidden_sections,
                deleted_sections=excluded.deleted_sections,
                missing_sections=excluded.missing_sections,
                completeness_score=excluded.completeness_score,
                alignment_status=excluded.alignment_status,
                template_version=excluded.template_version
        """, df_courses[[
            'course_number', 'snapshot_date', 'academic_year', 'module_code', 'course_name',
            'course_created_date', 'term_name', 'student_count', 'school_name',
            'expected_sections', 'visible_sections', 'hidden_sections', 'deleted_sections',
            'missing_sections', 'completeness_score', 'alignment_status',
            'template_version']].itertuples(index=False, name=None))

        if not sections.empty:
            cursor.executemany("""
                INSERT INTO readiness_sections (
                    course_number, snapshot_date, academic_year, section_key,
                    status, last_modified)
                VALUES (?,?,?,?,?,?)
                ON CONFLICT(course_number, snapshot_date, academic_year, section_key)
                DO UPDATE SET status=excluded.status, last_modified=excluded.last_modified
            """, sections[['course_number', 'snapshot_date', 'academic_year',
                           'section_key', 'status', 'last_modified']]
                .itertuples(index=False, name=None))
        conn.commit()

    logging.info("Readiness snapshot written: %d courses (%d unchanged), %d section rows.",
                 len(df_courses), unchanged, len(sections))
    return {'courses_written': len(df_courses), 'courses_unchanged': unchanged,
            'sections': len(sections)}

def purge_readiness(academic_year):
    """Deletes every readiness row for one academic_year, parent and child.

    Scoped to a single year rather than the whole table, for the same reason as
    purge_leganto_lists: a reference/test import can be dropped cleanly once the
    real current-year export replaces it.
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        if not table_exists(conn, 'readiness_courses'):
            return 0
        before = cursor.execute(
            "SELECT COUNT(*) FROM readiness_courses WHERE academic_year = ?",
            (academic_year,)).fetchone()[0]
        cursor.execute("DELETE FROM readiness_courses WHERE academic_year = ?",
                       (academic_year,))
        if table_exists(conn, 'readiness_sections'):
            cursor.execute("DELETE FROM readiness_sections WHERE academic_year = ?",
                           (academic_year,))
        conn.commit()
    logging.info("Purged %d readiness_courses rows (and their sections) for %s.",
                 before, academic_year)
    return before

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

def parse_custom_observations(custom):
    """
    Parses additional custom observations field which can be:
    1. A JSON list of dicts: [{"observation": "...", "action": "..."}]
    2. A legacy template string: "**Observation:** ... \n\n**Action:** ..."
    3. A legacy plain text string.
    Returns a list of dicts: [{"observation": "...", "action": "..."}]
    """
    import json
    import re
    
    if not custom:
        return []
    
    # If already a list of dicts
    if isinstance(custom, list):
        parsed = []
        for item in custom:
            if isinstance(item, dict):
                obs = str(item.get("observation", "")).strip()
                act = str(item.get("action", "")).strip()
                if obs or act:
                    parsed.append({"observation": obs, "action": act})
        return parsed
        
    if isinstance(custom, str):
        custom_str = custom.strip()
        
        # Check if it's JSON encoded
        if (custom_str.startswith("[") and custom_str.endswith("]")) or (custom_str.startswith("{") and custom_str.endswith("}")):
            try:
                data = json.loads(custom_str)
                if isinstance(data, list):
                    return parse_custom_observations(data)
                if isinstance(data, dict):
                    if "observation" in data or "action" in data:
                        obs = str(data.get("observation", "")).strip()
                        act = str(data.get("action", "")).strip()
                        if obs or act:
                            return [{"observation": obs, "action": act}]
            except Exception:
                pass
                
        # If it's empty or matches standard placeholders
        if not custom_str or custom_str in ("**Observation:**", "**Observation:** \n\n**Action:**", "**Observation:**\n\n**Action:**"):
            return []
            
        # Try to parse string in format "**Observation:** ... **Action:** ..."
        obs_match = re.search(r'\*\*Observation:\*\*\s*(.*?)(?=\*\*Action:\*\*|$)', custom_str, re.DOTALL | re.IGNORECASE)
        action_match = re.search(r'\*\*Action:\*\*\s*(.*)', custom_str, re.DOTALL | re.IGNORECASE)
        
        obs = obs_match.group(1).strip() if obs_match else ""
        act = action_match.group(1).strip() if action_match else ""
        
        if not obs and not act:
            return [{"observation": custom_str, "action": ""}]
        return [{"observation": obs, "action": act}]
        
    return []

def save_feedback_sqlite(timestamp, username, school, category, rating, comments):
    """Saves a feedback submission in the SQLite database."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO feedback (Timestamp, User, School, Category, Rating, Comments)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (timestamp, username, school, category, rating, comments))
        conn.commit()

def get_inactive_modules():
    """Returns list of module codes marked as inactive."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT module_code, reason, marked_date, marked_by FROM inactive_modules ORDER BY marked_date DESC")
        return [dict(row) for row in cursor.fetchall()]

def mark_module_inactive(module_code: str, reason: str, marked_by: str):
    """Mark a module as inactive."""
    import datetime
    with get_db_connection() as conn:
        cursor = conn.cursor()
        now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute("""
            INSERT OR REPLACE INTO inactive_modules (module_code, reason, marked_date, marked_by)
            VALUES (?, ?, ?, ?)
        """, (module_code.strip().upper(), reason, now, marked_by))
        conn.commit()

def mark_module_active(module_code: str):
    """Unmark a module as inactive (restore to active)."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM inactive_modules WHERE module_code = ?", (module_code.strip().upper(),))
        conn.commit()

def is_module_inactive(module_code: str) -> bool:
    """Check if a module is marked as inactive."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM inactive_modules WHERE module_code = ?", (module_code.strip().upper(),))
        return cursor.fetchone() is not None


# Automatically initialize/migrate database when imported
init_db()

