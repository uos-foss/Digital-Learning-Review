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
    
    ### ⚡ Interactive Launch Control & Deep-Linking
    
    The dashboard now features a **dynamic telemetry router** available on both the Faculty and School roster tables:
    * **Interactive Selection**: Click **ANY row** in a data table (Priority, Drill-Down, or School list) to instantly activate Launch Control.
    * **Jump Commands**: Instantly manifest high-speed teleportation buttons to view the specific **📊 Module Report Card** or the **✅ Lead Checklist** without manual menu diving.
    
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
    ### 🚀 Version 1.5.0 (Current) - *Feedback Integration & Multi-School UX*
    * **Integrated User Feedback Form**: Added a dedicated, sidebar-accessible feedback form page (`views/feedback.py`) that writes submissions directly to a Google Sheets ledger.
    * **Multi-School Focus Toggles**: Restructured the School Dashboard, Module Report Card, and Lead Checklist viewports. Users with school-specific accounts can now temporarily uncheck focus to search modules or view dashboards for other schools.
    * **Enhanced Admin & DLA Access**: Upgraded login session handling so ADMIN and DLA accounts default to "All Schools" viewing while retaining toggle controls to inspect individual schools.
    * **Visual Audit Placeholders**: Fixed the Module Report Card to show a clear "❌ Incomplete" self-audit card indicating missing checklists for un-audited modules rather than displaying empty slots.
    * **Collaboration Resources**: Integrated an updated slide deck presentation in the "How to Contribute" view utilizing `assets/contribute.html` for better developer onboarding.

    ### 📂 Version 1.4.0 - *Lazy-Loaded Controllers & Interactive Routing*
    * **Segmented Control Router**: Replaced inert HTML tabs with native stateful segmented widgets, completely securing viewport focus and unlocking 100% reliable view-state retention across actions.
    * **Instant Deep-Linking**: Upgraded primary analytics tables into interactive row-selectors. Clicking any row now materializes a direct action launch center to teleport instantly to Report Cards or Checklist views.
    * **Lazy Loading Engine**: Optimized view execution logic so only active viewport logic operates, boosting computational efficiency by preventing invisible charts from loading on background screens.
    * **Performance Threshold Lenses**: Completely refactored the Priority Action suite, injecting dynamic analytics lenses for compliance gap summaries and checklist rosters in a single, unified, non-shifting viewport.

    ### 📂 Version 1.3.0 - *Local Activity Logging & Layout Tuning*
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
    
    ```text
    ┌────────────────────────────────────────────────────────┐
    │              Streamlit Client App (app.py)             │
    └───────┬────────────────────┬────────────────────┬──────┘
            │                    │                    │
            ▼ (Reads/Writes)     ▼ (Cookie Session)   ▼ (Logs Events)
     ┌─────────────┐      ┌─────────────┐      ┌─────────────┐
     │   gspread   │      │ stx.Cookie  │      │  Persistent │
     │  Connector  │      │   Manager   │      │   app.log   │
     └──────┬──────┘      └──────┬──────┘      └─────────────┘
            │                    │
            ▼ (API Fetch)        ▼ (Persists)
     ┌─────────────┐      ┌─────────────┐
     │Google Sheets│      │Browser Local│
     │  Cloud DB   │      │   Cookie    │
     └─────────────┘      └─────────────┘
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
    * **File**: Written locally to `app.log` (ignored by `.gitignore` in shared version control).
    * **Format**: `YYYY-MM-DD HH:MM:SS [LEVEL] Message`
    
    ### 📦 Version Control & Tagging (GitHub Desktop)
    
    We align application versions in code with Git history using **Semantic Versioning (SemVer)**:
    1. **Update Code Version**: Increment the `__version__` string inside `app.py` and update the release notes in `views/docs.py`.
    2. **Commit Changes**: Stage your changed files in **GitHub Desktop**, write a summary (e.g., `Release version 1.3.0`), and commit to the main branch.
    3. **Create Tag**: In GitHub Desktop, go to **Repository** -> **Create Tag...** (or press `Ctrl+Shift+T`), type your version (e.g., `v1.3.0`), and hit **Create Tag**.
    4. **Push origin**: Click **Push origin**. GitHub Desktop will automatically publish both your commits and version tags to GitHub in one go!
    
    ### 🐳 Server Deployment with Docker
    
    The portal is fully containerized and configured for quick deployment using **Docker** and **Docker Compose**.
    
    #### 1. Configuration Files & Port Mapping
    * **`Dockerfile`**: Builds a lightweight, secure production-grade Python image, caching dependencies during layers.
    * **`docker-compose.yml`**: Manages environment injection (`.env`), container restart protocols, and maps local logging volumes.
    * **Multi-Container Port Mapping**: To run alongside other Streamlit apps on the server without clashing, the compose file maps **host port `8500`** to container port `8501` (`"8500:8501"`). The app is fully accessible at **`http://127.0.0.1:8500`** on the server!
    
    #### 2. Deploying on Your Server
    To spin up the portal in the background on your production server:
    
    ```bash
    # 1. Clone the repository onto your server
    git clone <your-repo-url> && cd Digital-Learning-Review
    
    # 2. Set up your production .env file
    nano .env
    
    # 3. Create an empty log file to mount securely
    touch app.log
    
    # 4. Build and start the container in detached (background) mode
    docker compose up -d --build
    ```
    
    #### 3. Updating to a New Release & Environment Variables
    When you release a new version (like `v1.3.1`) and want to deploy it onto your active production server:
    
    ```bash
    # 1. Pull down the latest code changes from GitHub
    git pull origin main
    
    # 2. Rebuild the image and recreate the containers with zero downtime
    docker compose up -d --build
    ```
    *(Docker Compose is extremely smart—it will rebuild only modified code layers and recreate your container seamlessly in a split second, keeping your volume-mounted `app.log` file completely intact!)*
    
    > [!IMPORTANT]
    > **Applying `.env` Updates**: If you modify any variables (such as school passwords or spreadsheet IDs) directly inside your host `.env` file, **Docker will continue to use the old cached variables inside active container memory**. To apply your fresh `.env` modifications, you must recreate the container by running:
    > ```bash
    > docker compose up -d
    > ```
    
    #### 4. Monitoring & Commands
    
    ```bash
    # View running containers
    docker compose ps
    
    # Stream real-time container outputs (or inspect local app.log)
    docker compose logs -f
    
    # Stop the application
    docker compose down
    ```
    """)

def view_contribute():
    st.title("🤝 How to Contribute")
    st.write("Learn how to collaborate, update, and extend the Digital Learning Review project.")
    
    import streamlit.components.v1 as components
    import os
    
    html_path = os.path.join("assets", "contribute.html")
    if os.path.exists(html_path):
        try:
            with open(html_path, "r", encoding="utf-8") as f:
                html_content = f.read()
            
            # Render full-width responsive container
            # Height of 650px fits a standard 16:9 slide nicely
            components.html(html_content, height=650, scrolling=True)
        except Exception as e:
            st.error(f"Failed to load the slide deck: {e}")
    else:
        st.warning("The HTML slide deck is currently missing. Please ensure `assets/contribute.html` exists in your repository.")

