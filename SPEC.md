# Project Specification: Digital Learning Review Dashboard

## 1. Project Overview
The Digital Learning Review Dashboard is a Streamlit-based web application that aggregates and visualizes Virtual Learning Environment (VLE) audit data. It serves as a central hub for faculty to track compliance, accessibility scores, and review self-audit checklists across various modules, schools, and semesters. 

**Primary Goals & KPIs:**
- Achieve high Ally accessibility scores across modules.
- Ensure full compliance with the module lead self-audit checklists.

## 2. Architecture & Tech Stack
- **Language:** Python 3.13
- **Framework:** Streamlit
- **Data Manipulation:** Pandas
- **Data Integration:** Google Sheets API (`gspread`, `google-auth`, `tenacity` for rate limit backoff)
- **Deployment & Infrastructure:** Docker & Docker Compose. Currently deployed on an Ubuntu VM, accessible at [https://fossdigital.shef.ac.uk/digital-learning-review/](https://fossdigital.shef.ac.uk/digital-learning-review/). (Note: CI/CD pipelines are not yet established).

## 3. Data Sources & Workflows
The application relies heavily on Google Sheets as its backend database. The environment variables map to the respective Google Sheets:

- **Main Audit Data (`MAIN_SPREADSHEET_ID`):** Contains "All Schools Aut" and "All Schools SPR" tabs. May involve manual edits by auditors.
- **Ally Accessibility Scores (`ALLY_SPREADSHEET_ID`):** Contains module accessibility data. Updated monthly with new tabs added.
- **Leganto Lists (`LEGANTO_NOLIST_ID`):** Tracks modules missing reading lists. Updated monthly with new tabs.
- **Self-Audit Checklist (`CHECKLIST_SPREADSHEET_ID`):** A synchronous sheet where module leads input data. It experiences heavy write operations during specific periods of the academic year.
- **SITS Assessment Data (`ASSESSMENT_SPREADSHEET_ID`):** Contains formal assessment data. Updated annually with new tabs added.

**Caching Strategy:** The app uses Streamlit's `@st.cache_data` with a Time-To-Live (TTL) of 3600 seconds (1 hour) to minimize API calls to Google Sheets while keeping data reasonably fresh.

## 4. User Roles & Access Control
The application uses a custom authentication system (`auth.py`) mapped to user credentials in a secure environment.

- **Capabilities System:** Access to specific views is governed by user capabilities (e.g., "view faculty overview", "complete module checklist").
- **Roles:**
  - `ADMIN`: Full access, including the Admin Panel.
  - `DLA` (Digital Learning Advisor): Advanced access, including Developer Guide and Contribution docs.
  - Standard Users: Access restricted based on assigned capabilities (typically School Dashboard and Module Report Card).
- *Future Note:* Alternative authentication methods are planned for the roadmap.

## 5. Core Views & Navigation
- **🏫 School Dashboard:** The default core view, filtering data by school and active semester.
- **🏛️ Faculty Overview:** High-level aggregated data across the entire faculty.
- **📋 Module Report Card:** Deep dive into a specific module's compliance and scores.
- **✅ Module Checklist:** Interface for viewing/completing self-audits.
- **Utilities:** App Feedback, Help & Support, Release Changelog.
- **Admin/Developer Views:** Admin Panel, Developer Guide, How to Contribute.

## 6. Codebase Structure
- `app.py`: The main entry point, handles routing, session state, caching, and sidebar navigation.
- `auth.py`: Manages login, session persistence, and capability-based access control.
- `data_manager.py`: Handles Google Sheets API authentication, raw data fetching, and implements exponential backoff (`tenacity`) for API rate limit handling.
- `processing.py`: Contains the ETL logic, merging different data sources, calculating metrics like "Ally Shift", and a defensive formatting pipeline for sanitizing outgoing data.
- `views/`: Contains individual Streamlit page modules (e.g., `school_dashboard.py`, `faculty_overview.py`) to keep `app.py` clean.
- `assets/`: Static files and branding.
- `diagnostics/`: Tools for checking data integrity.

## 7. Future Roadmap

The active development roadmap includes the following initiatives. They are structured to provide clear execution context for AI development partners.

### 7.1. UI/UX Refresh and Aesthetic Improvements
- **Context/Rationale:** To maintain visual consistency between streamlit applications.  
- **Technical Scope:** Use the project ../GPL-assessment-criteria-new as the exemplar, migrate legacy radio-button sidebar to Streamlit's native st.navigation and st.page_link API. Strip out OS-dependent emojis and replace them with crisp, native Streamlit Material Icons.
- **Success Criteria:** The application should align visually with the GPL Assessment Criteria Generator project ../GPL-assessment-criteria-new. 

### 7.2. Move to a Hybrid Cache-Database Model
- **Context/Rationale:** Relying entirely on gspread is a major architectural bottleneck, given that a lot of the data in the sheets is fairly static. 
- **Technical Scope:** 
Static/Slow-Moving Data (SITS, Ally, Leganto, Main Audit): Keep these in Google Sheets, but instead of querying them on every user session, use a SQLite as a read-cache. High-Write Data (Self-Audit Checklist): Write directly to the database first for instant, reliable updates, and asynchronously sync back to Google Sheets if a backup is required.

Define the Database Schema: Create a Python script (database.py) to initialize an SQLite database.

Build a Background Data Sync: Fetch data from Google Sheets, clean it using your processing.py logic, and dump it into SQLite.

Update data_manager.py: Point your Streamlit views to read directly from SQLite instead of hitting gspread on runtime.

- **Success Criteria:** [User to define the expected outputs, e.g., new charts on the School Dashboard based on the new data.]

### 7.3. Integration of Additional Audit Data Sources
- **Context/Rationale:** [User to specify what new data is being brought in, e.g., Canvas APIs, internal student systems, survey results.]
- **Technical Scope:** Expected creation of new fetchers in `data_manager.py` and ETL logic in `processing.py`.
- **Success Criteria:** [User to define the expected outputs, e.g., new charts on the School Dashboard based on the new data.]

### 7.4. Implementation of Alternative Authentication Methods
- **Context/Rationale:** [User to explain the shift from the current system, e.g., moving to University SSO/SAML, OAuth with Google/Microsoft.]
- **Technical Scope:** Refactoring or replacing `auth.py`, updating capability mapping, and ensuring secure session state persistence.
- **Success Criteria:** [User to define the exact login flow and security requirements.]

### 7.5. Migration to a Hybrid Cache-Database Layer (SQLite)

- **Context/Rationale:** Heavy write operations from simultaneous Module Leads filling out checklists can trigger Google API rate limits (`quota exceeded`), degrading user experience. Introducing an SQLite layer minimizes Google API requests by serving read queries from local cache and accepting high-volume checklist writes instantly.
    
- **Data Flow Architecture:**
    
    ```
    [ Google Sheets ] ──(sync_data.py)──> [ Local SQLite Cache (Read) ] ──> [ Streamlit App ]
                                                                                  │
    [ Google Backup ] <──(Async Sync)──── [ Local SQLite DB (Write) ] <───────────┘
    ```
    
- **Database Schema Specification:** The SQLite database file should reside at `./data/audit_cache.db` and be persisted across Docker container updates.
    
    #### Table: `main_vle_audit` (Local Cache of Static Audit Sheet)
    
    |Column Name|SQLite Type|Description|
    |---|---|---|
    |`module_code`|TEXT (PK)|Unique module identifier|
    |`module_name`|TEXT|Human-readable name of the module|
    |`semester`|TEXT|Autumn (Aut) / Spring (Spr)|
    |`school`|TEXT|Faculty school/department|
    |`ally_score`|REAL|Overall Ally Score|
    |`sga_visible`|INTEGER|Boolean (0/1) indicating Skills development visibility|
    |`briefs_shared`|INTEGER|Boolean (0/1) indicating Assessment briefs shared|
    
    #### Table: `self_audit_checklist` (High-Write Operational Datastore)
    
    |Column Name|SQLite Type|Description|
    |---|---|---|
    |`id`|TEXT (PK)|Compound unique key (`module_code` + `semester`)|
    |`module_code`|TEXT|Linked module code|
    |`semester`|TEXT|Targeted semester|
    |`structure_complete`|INTEGER|Checkbox state (0 or 1)|
    |`briefs_uploaded`|INTEGER|Checkbox state (0 or 1)|
    |`accessibility_checked`|INTEGER|Checkbox state (0 or 1)|
    |`last_updated`|TEXT|UTC Timestamp of change (ISO format)|
    |`updated_by`|TEXT|Username/Email of modifier|
    
- **Execution Blueprint: `database.py`**
    
    ```
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
    
        # Create high-write dynamic table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS self_audit_checklist (
                id TEXT PRIMARY KEY,
                module_code TEXT,
                semester TEXT,
                structure_complete INTEGER DEFAULT 0,
                briefs_uploaded INTEGER DEFAULT 0,
                accessibility_checked INTEGER DEFAULT 0,
                last_updated TEXT,
                updated_by TEXT
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
        with get_db_connection() as conn:
            df.to_sql(table_name, conn, if_exists='replace', index=False)
    ```
    
- **Execution Blueprint: `sync_data.py`**
    
    ```
    import sys
    import pandas as pd
    from database import cache_dataframe_to_sqlite, init_db
    
    def run_synchronization():
        """ETL pipeline extracting Google Sheets data and writing to SQLite."""
        print("🔄 Pulling raw data from Google Sheets API...")
        try:
            init_db()
            # Fetch and clean from existing pipeline
            # raw_df = fetch_all_google_sheets_data()
            # clean_df = clean_gspread_data(raw_df)
    
            # Simulated output save
            # cache_dataframe_to_sqlite(clean_df, "main_vle_audit")
            print("✅ Sync Process Completed: Local SQLite cache updated.")
        except Exception as e:
            print(f"❌ Synchronisation failed: {str(e)}", file=sys.stderr)
    
    if __name__ == "__main__":
        run_synchronization()
    ```
    
- **Execution Blueprint: Streamlit Data Read/Write Mechanics**
    
    ```
    import pandas as pd
    import streamlit as st
    from datetime import datetime
    from database import get_db_connection
    
    @st.cache_data(ttl=600)
    def load_audit_data_from_cache() -> pd.DataFrame:
        """Reads cached audit data instantly from local SQLite storage."""
        try:
            with get_db_connection() as conn:
                df = pd.read_sql_query("SELECT * FROM main_vle_audit", conn)
            return df
        except Exception as e:
            st.error(f"Error reading cache database: {e}")
            return pd.DataFrame()
    
    def save_checklist_record(module_code: str, semester: str, data: dict, user: str):
        """Saves or updates checklist answers directly to SQLite to protect Google API quotas."""
        record_id = f"{module_code}_{semester}"
        now_str = datetime.utcnow().isoformat()
    
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO self_audit_checklist (
                    id, module_code, semester, structure_complete, briefs_uploaded, accessibility_checked, last_updated, updated_by
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    structure_complete=excluded.structure_complete,
                    briefs_uploaded=excluded.briefs_uploaded,
                    accessibility_checked=excluded.accessibility_checked,
                    last_updated=excluded.last_updated,
                    updated_by=excluded.updated_by
            """, (
                record_id, module_code, semester, 
                data.get('structure_complete', 0),
                data.get('briefs_uploaded', 0),
                data.get('accessibility_checked', 0),
                now_str, user
            ))
            conn.commit()
    ```
    
- **Container Volume Configuration (`docker-compose.yml`):** Ensure database persistence is guaranteed by mapping host directories to the container path:
    
    ```
    version: '3.8'
    
    services:
      streamlit-dashboard:
        build: .
        container_name: vle_dashboard_app
        restart: always
        ports:
          - "8501:8501"
        volumes:
          - ./data:/app/data  # Persists cache database safely on host system
    ```