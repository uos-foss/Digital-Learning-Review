import streamlit as st

def view_help():
    st.title("💡 Help & Support Guide")
    st.write("Welcome to the Digital Learning Review Support Portal. Below you will find answers and guides for using this dashboard.")
    
    st.markdown("""
    ### 📂 Navigation & Core Modules
    
    1. **🏛️ Faculty Overview**: 
       * A high-level birds-eye view of all modules across the faculty. Includes average Ally accessibility scores and total completed self-audits.
    2. **🏫 School Dashboard**: 
       * School-specific analytics (e.g. ALA, ECN, EDC) automatically pre-filtered based on your active school view preference.
    3. **📋 Module Report Card**: 
       * A detail-rich, unified card search that presents full audit metrics for a single module side-by-side (Autumn vs. Spring).
    4. **✅ Module Lead Checklist**: 
       * The interactive self-audit form where module leaders can submit reviews directly back to the persistent Google Sheets ledger.
    
    ### 👤 Multi-Tenancy & School Ownership
    
    * **Saved School View**: Located in the sidebar under **User Session**. When you log in with your school-specific password, the portal optionally defaults to your team's specific school to exclude external clutter while maintaining open, non-siloed data access.
    * **Active School View Selector**: Administrators or faculty-wide users can use the sidebar dropdown to seamlessly toggle between specific schools or choose "All Schools".
    
    ### 🔄 How Data Syncing Works
    
    * Data is fetched in real-time from our central **Google Sheets** database.
    * To conserve API limits, the system caches results for 1 hour. If you submit a checklist update, the cache is instantly cleared for that module, so you can see your update reflected immediately!
    
    ### 📜 Local Logging & Auditing (`app.log`)
    
    To ensure seamless operations, the system maintains a persistent local text log called `app.log` in the root directory. This logs:
    * **Success/Failed Login Audits**: Tracks which schools are actively logging in.
    * **Sync Actions**: Logs when Google Sheets data caches are refreshed.
    * **Checklist Submissions**: Records who updated which module.
    """)
    st.info("✉️ For technical support or database access requests, please contact the **FOSS Digital Learning Team**.")

def view_changelog():
    st.title("📜 Release Changelog")
    st.write("Track the recent updates and system releases for the VLE Review Audit Platform.")
    
    st.markdown("""
    ### 🚀 Version 1.3.0 (Current) - *Local Activity Logging & Layout Tuning*
    * **Centralized File Logging**: Configured a persistent `app.log` file tracking successful logins, logouts, database syncs, and self-audit submissions.
    * **Stateless Page Routing**: Refactored the sidebar radio navigation widget to be stateless, resolving previous state-retention overrides when clicking support links.
    * **Sidebar Aesthetics**: Separated core operational tools from help/changelog resources using dedicated full-width action buttons.
    
    ### 📂 Version 1.2.0 - *Code Modularization*
    * **Refactored Architecture**: Split monolithic script into elegant, clean components under the `views/` directory.
    * **Introduced Documentation Views**: Added fully integrated Help, Changelog, and Developer Guide pages.
    
    ### 🔐 Version 1.1.0 - *Persistent Authentication*
    * **Cookie Persistence**: Integrated `stx.CookieManager` for secure, zero-flash session preservation across browser reloads.
    * **Security Hardening**: Completely removed plain-text credentials from source code, reading strictly from environment variables.
    
    ### 📈 Version 1.0.0 - *Saved Views & Session States*
    * **Active School View**: Created sidebar preferences and smart default selectors to tailor viewports dynamically without siloing.
    * **Unified Search**: Standardized module search fields to eliminate dropdown focus issues.
    * **Checklist Version History**: Added Google Sheets integration for self-audits with a complete historical version trail.
    """)

def view_developer_guide():
    st.title("💻 Developer Guide")
    st.write("Technical documentation and architectural design patterns for developers.")
    
    st.markdown("""
    ### 🛠️ Architecture Overview
    
    The platform is built on **Streamlit** (Frontend logic), backed by **Google Sheets** (gspread database engine), and audited by local file logging.
    
    ```mermaid
    graph TD
        A[Streamlit Client App] -->|Reads / Writes| B(gspread Connector)
        B -->|API Fetch| C[Google Sheets Cloud Database]
        A -->|Cookie Session| D(stx.CookieManager)
        D -->|Persists| E[Local Browser Cookie]
        A -->|Logs Events| F[(app.log file)]
        G[auth.py / views] -->|Globally import logging| F
    ```
    
    ### 📁 Modular File Structure
    
    * **`app.py`**: Entrypoint initializing global layouts, navigating pages, executing cached database operations, and configuring the global root logger.
    * **`auth.py`**: Secure authentication gateway, session restoration engine, and cookie persistence layer.
    * **`data_manager.py`**: Google Sheets low-level API operations, cell appends, and header initializations.
    * **`processing.py`**: Dataframe cleaning, school-wide metric aggregations, and compliance gap calculations.
    * **`views/`**: Contains page-specific modular functions separating business logic from view state rendering.
    
    ### 📝 Central Logger Details
    
    Log configuration is established globally in `app.py` and inherited across all modules:
    * **Level**: `INFO` (captures normal operations, logins, database syncs, and all warnings/errors).
    * **File**: Written locally to `app.log`.
    * **Format**: `YYYY-MM-DD HH:MM:SS [LEVEL] Message`
    
    ### 🧪 Running Locally
    
    1. Clone this repository.
    2. Create a secure `.env` file containing your `MAIN_SPREADSHEET_ID`, `CHECKLIST_SPREADSHEET_ID`, and Google Service Account JSON variables.
    3. Install dependencies: `pip install -r REQUIREMENTS.txt`
    4. Start the server: `streamlit run app.py`
    """)
