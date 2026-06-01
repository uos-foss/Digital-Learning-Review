# Project Specification: Digital Learning Review Dashboard

## 1. Project Overview
The Digital Learning Review Dashboard is a Streamlit-based web application that aggregates and visualizes Virtual Learning Environment (VLE) audit data. It is being built to replace a lengthy manual spreadsheet called the VLE Audit, where manual checks were done to all faculty VLE modules and findings recorded in the audit spreadsheet. The new dashboard aims to replace this by pulling much of the data from other sources. The manual audit data remains in there temporarily so there is data to look at and work with, but it will be removed at some point.

It serves as a central hub for faculty to track compliance, accessibility scores, and review self-audit checklists across various modules, schools, and semesters. 

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

# 7. Future Features & Architectural Roadmap (Antigravity Target Execution)

This section outlines the immediate and long-term architectural refactors required for the system. It serves as an actionable specification for Google Antigravity 2.0 autonomous orchestrators and sub-agents to generate plans, code commits, and test suites.

## 7.1. Phase 1: Migration to a Centralized, Hybrid Cache-Database Layer (SQLite)

### Context & Rationale
Heavy write operations from simultaneous Module Leads filling out checklists can trigger Google Sheets API rate limits (`quota exceeded` / HTTP 429), degrading user experience and forcing heavy reliance on `tenacity` retry backoffs. Introducing a centralized SQLite layer minimizes live external API requests by serving read queries directly from a local disk cache and accepting transactional checklist writes instantly. 

Because the sister applications ("AI in the Curriculum Audit" and "Student Feedback Analysis") are deployed in separate repositories and separate Docker containers on the same host, the database will be shared across container boundaries using a host bind mount.

### Architectural Blueprint
- **Database Location:** A dedicated host directory `/opt/shared-audit-data` mounted into the container at `/app/data/audit_cache.db`.
- **Concurrency Mode:** The database must explicitly run in Write-Ahead Logging (WAL) mode to handle concurrent multi-container reads and writes without file-system locking.
- **Role Isolation:** The DLR dashboard acts as the primary "schema owner" and "data sync engine". Sibling applications mount the volume to ingest tables as read-only pools.

### Sub-Agent Task Allocations & Code Modifications

#### Task 1: Initialize Database Engine (`database.py`)
Create or refactor `database.py` to establish connection parameters optimizing for high concurrency across isolated containers.
- **Implementation Rules:** Ensure `PRAGMA journal_mode=WAL;` and `PRAGMA busy_timeout=5000;` are executed on every connection payload to prevent `database is locked` errors during parallel container actions.

```python
import sqlite3
import os

def get_db_connection():
    """
    Establishes a thread-safe connection to the shared SQLite database file
    optimized for multi-container concurrency via WAL mode.
    """
    db_path = os.getenv("DB_PATH", "/app/data/audit_cache.db")
    # Ensure directory exists
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    
    conn = sqlite3.connect(db_path)
    # Enable WAL mode for asynchronous read/write concurrency
    conn.execute("PRAGMA journal_mode=WAL;")
    # Prevent immediate failures on simultaneous writes by waiting up to 5000ms
    conn.execute("PRAGMA busy_timeout=5000;")
    return conn