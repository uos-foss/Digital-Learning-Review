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

### 7.2. Integration of Additional Audit Data Sources
- **Context/Rationale:** [User to specify what new data is being brought in, e.g., Canvas APIs, internal student systems, survey results.]
- **Technical Scope:** Expected creation of new fetchers in `data_manager.py` and ETL logic in `processing.py`.
- **Success Criteria:** [User to define the expected outputs, e.g., new charts on the School Dashboard based on the new data.]

### 7.3. Implementation of Alternative Authentication Methods
- **Context/Rationale:** [User to explain the shift from the current system, e.g., moving to University SSO/SAML, OAuth with Google/Microsoft.]
- **Technical Scope:** Refactoring or replacing `auth.py`, updating capability mapping, and ensuring secure session state persistence.
- **Success Criteria:** [User to define the exact login flow and security requirements.]
