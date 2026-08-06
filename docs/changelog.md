Recent updates and releases for the Digital Learning Review portal.

### 🚀 Version 1.16.0 (Current) — *Ally Institutional Report*
*5 August 2026*

* **Ally now tells you what is wrong, not just how bad it is.** The full
  Anthology institutional report carries a per-check breakdown — untagged PDFs,
  scanned documents, missing image descriptions, low contrast, and 35 more —
  counted in the number of content items affected. Module reports list a
  module's own issues worst-first, each with plain-English advice and a note on
  whether it is fixable in the Blackboard editor or needs the source document
  re-authored. School and Faculty views roll the same data into an issue league
  table, so one intervention can be aimed at hundreds of items.
* **Files and editor pages are scored separately.** Ally rates uploaded
  documents and pages built in Blackboard independently, and they behave very
  differently — the two are now shown side by side with the volume of content
  behind each. A single blended number hid the distinction, and with it the
  answer to whether a school needs document-authoring support or Blackboard
  training.
* **Scores are qualified by whether a course has moved past its template.** A
  course fresh from rollover holds only its template and Ally scores that
  template close to 100%. Every average now covers only courses with content
  beyond the template, and the Priority Action List ignores the rest. There is
  deliberately no "Built" or "Complete" state to report — module leads build
  just-in-time throughout the course, often up to the final assessment, so a
  file count can only ever show a course has started, never that it is
  finished. A build-out tracker shows that progress instead. **Expect the
  accessibility figures to look sparser than before**: the numbers previously
  on screen were the 2025-26 academic year, and 2026-27 courses are still
  largely templates.
* **The credibility-weighted score has been withdrawn.** It blended thin
  courses toward 50%, which on a rolled-over year moved the faculty average by
  30 points and disagreed with the score module leads see in their own course.
  The portal now shows Ally's own figures unchanged.
* **Severe accessibility issues raise an action.** An unreadable scanned
  document, a corrupt file, a document locked against screen readers, or Ally
  being switched off for a course now counts as an actionable item, in the same
  way a missing Leganto list already did. No audit field is auto-answered — an
  audit response still means something a Digital Learning Advisor recorded.
* **The importer says what it dropped.** The Ally export covers every
  Blackboard course the institution has ever had, so the Admin Panel now asks
  which academic year to import and reports how many rows were discarded, how
  many courses matched SITS, and which codes exist on only one side. Repeat
  imports only store courses whose measurements have actually moved, so a
  weekly import does not fill the history with identical rows. Blackboard
  module links are refreshed from the same file.
* **Fixed**: the Module Report crashed with a `NameError` when a module had an
  AI in the Curriculum declaration, a fault introduced in v1.15.0.

### 🚀 Version 1.15.0 — *Legacy VLE Audit Spreadsheet Retired*
*4 August 2026*

* **The 25/26 audit spreadsheet is no longer an upstream source.** A full sync
  no longer reaches out to it, removing one spreadsheet from the ETL. The 25/26
  baseline it produced stays exactly as it is inside the portal's own database,
  frozen at its final state, and still supplies programme leads, module links
  and accessibility figures for modules the current audit round has not yet
  covered.
* **Critical Compliance Gaps now reflects live audits.** Both the Faculty
  Overview and School Dashboard lens read submitted audits rather than the
  25/26 answers, so the list tracks the current round. Modules that have not
  been audited yet are no longer counted as failing every item — they appear in
  the Missing Audits lens instead, and the compliance figure now states how many
  audited modules it covers.
* **Clearer warning on deleting the legacy tables.** The Admin Panel's cleanup
  action now spells out that it cannot be undone, since no sync will rebuild
  those tables.
* **AI audit responses are no longer synced twice.** The AI in the Curriculum
  form is a separate app that shares this portal's database and already keeps
  its own responses up to date. This portal was fetching the same records a
  second time, which duplicated work and could overwrite that app's data with a
  different copy of the sheet. A full sync now leaves those records alone.
* **AI in the Curriculum declarations now appear in the portal.** Module leads
  complete these themselves in a separate app, and until now the results went
  nowhere. There is a new view on the Faculty Overview and School Dashboard
  showing how many modules have declared and which are still outstanding, and
  the Module Report lists each assessment's declared AI usability and intended
  use. Coverage counts a module once, however many assessments it has.
  Declarations against modules that no longer exist in SITS are shown as a
  warning rather than dropped, so they can be reconciled.

### 🚀 Version 1.14.0 — *School Comparison, Blackboard Links & Security Hardening*
*31 July – 3 August 2026*

* **Faculty School Comparison**: New default tab on the Faculty Overview showing
  all seven schools side by side — modules, audit coverage, average Ally score,
  VLE compliance and a status badge — with faculty totals beneath and row-click
  drill-down into a school's dashboard. Compliance is measured across submitted
  audits only, and audit coverage is shown alongside so a high score on a small
  sample is visible as such.
* **Blackboard Links**: Module VLE links are now held in their own table and
  imported from CSV in the Admin Panel, replacing reliance on links carried in
  the legacy audit data.
* **Inactive Modules**: Administrators can mark modules as inactive (skeleton,
  merged, archived, or not running) to exclude them from all dashboards and
  analytics, with a reason and an audit trail of who marked them. Restorable at
  any time.
* **Password Hashing Migrated to scrypt**: Passwords were stored as unsalted
  SHA-256. They are now hashed with scrypt — salted, memory-hard and
  work-factored. Existing accounts upgrade automatically the next time they sign
  in successfully; no resets were required and nobody was locked out.
* **Sync No Longer Overwrites User Accounts**: A full sync previously rebuilt the
  users table from the spreadsheet, silently reverting any role or status change
  made in the Admin Panel. User sync now adds genuinely new accounts only.
* **Security Fix**: Audit field IDs were being interpolated directly into a SQL
  query in the compliance-gap calculation, and the Admin Panel's CSV import path
  bypassed the validation the table editor applied. The query is now
  parameterised and the CSV path validates field IDs.
* **Semester Consistency Fix**: Selecting "All year" returned Autumn data on the
  Faculty Overview but Spring data on the School Dashboard. Both now resolve the
  selection through shared logic and return genuinely year-long modules.
* **Wider Period Code Support**: Modules using teaching period codes beyond
  `S1`/`S2` are now mapped to the correct semester rather than all falling
  through to a default.
* **Separated Google Credentials**: The OAuth sign-in client and the service
  account used for spreadsheet access were sharing a single `GOOGLE_CLIENT_ID`
  setting, so one silently overwrote the other. They now have their own
  settings, with the old name still honoured so existing deployments keep
  working.
* **Google Sign-In Now Survives a Refresh**: Sessions started with Google were
  not being saved to a browser cookie, so refreshing the page or duplicating the
  tab returned users to the sign-in screen. Username and password sign-ins were
  unaffected. Both now persist for 8 hours.
* **Fixed Dead Navigation Buttons**: Five row drill-down buttons on the Faculty
  Overview and School Dashboard set a session key left over from the pre-v1.8.0
  router and reloaded the same page instead of navigating. They now open the
  target page directly. The jump to the Audit Portal is also hidden from accounts
  without the `edit_checklist` capability, which previously would have errored.
* **Audit Terminology**: Buttons labelled "Lead Checklist" now read "Open Audit
  Portal", since audits are carried out by Digital Learning Advisors rather than
  by module leads.
* **Retired the Background Sync Daemon**: With SQLite as the primary database and
  no write-back to Sheets, the background push daemon introduced in v1.10.0 is no
  longer needed and has been switched off.

### 📂 Version 1.13.0 — *Audit Portal*
*30 July 2026*

* **Dedicated Audit Portal**: The audit checklist moved out of the Module report
  and onto its own page, available to accounts with the `edit_checklist`
  capability — in practice the Digital Learning Advisors who carry out audits.
* **Module Report Simplified**: The report card's inline editable checklist was
  replaced with a read-only summary and a button that opens the module in the
  Audit Portal, so there is now one place where audits are edited.
* **Streamlined Audit Form**: Simplified the portal's layout and form handling,
  with draft and submitted states saved per module.

### 📂 Version 1.12.0 — *Google Sign-In & Role-Based Access*
*29 July 2026*

* **Sign in with Google**: Added Google OAuth as a sign-in option alongside the
  existing username and password. Accounts signing in this way hold no password;
  their entry in the user table records permission to access the portal.
* **Role and Capability Refactor**: Reworked roles into short codes (`admin`,
  `DLA`, `FOSS`, `ML`, `SA`, `SL`) with lowercase capability tokens
  (`view_all`, `view_school`, `edit_checklist`, `access_admin_panel`) driving
  what each account can see and do.
* **Session Fixes**: Reworked cookie writes so a sign-in no longer competes with
  Streamlit's rerun cycle.
* **Trigger Full Sync**: Added a button to the Admin Panel to refresh from
  Google Sheets on demand.
* **Yes/No Audit Fields**: Added a `yes/no` field type to the audit
  configuration, and support for parsing multiple observation and action pairs
  from a single response.

### 📂 Version 1.11.0 — *Leganto Integration & Audit Field Enhancements*
*27–28 July 2026*

* **Leganto Reading List Status**: Modules with no reading list are now flagged
  across the dashboards and the module report.
* **Action Labels**: Audit fields can carry an action label, feeding a redesigned
  "Actions & Recommendations" section on the module report.
* **Ally Credibility Weighting**: Ally scores drawn from very few files are now
  flagged, so a high score on a near-empty module is not read as good practice.
* **Comment Bank Resources**: Comment bank entries can carry a resource link and
  description, synchronised in both directions with Google Sheets.
* **Compact Module Report**: Added a condensed layout for the module report.

### 📂 Version 1.10.0 — *Background Sync & SQLite Concurrency*

* **SQLite WAL Mode**: Moved the local database to Write-Ahead Logging with busy
  timeouts, allowing concurrent access from multiple dashboard instances.
* **Batched Background Sync**: Replaced per-request Google Sheets writes with a
  background daemon pushing offline checklist edits to the cloud. *(Retired in
  v1.14.0 — see above.)*
* **Database Mount Readiness**: Configured the container to use a mounted host
  volume for the database.

### 📂 Version 1.9.0 — *SQLite Hybrid Cache & Operations Toolkit*

* **SQLite Database**: Migrated read operations and checklist submissions to a
  local SQLite database, substantially improving responsiveness and removing the
  Google Sheets API quota ceiling.
* **Background Synchronisation**: Added a backend ETL pipeline keeping the local
  database in step with Google Sheets without blocking the interface.
* **Database Explorer**: Added a SQLite viewer to the Admin Panel for
  diagnostics.
* **Retry Handling**: Added automatic retry with exponential backoff for
  spreadsheet writes.

### 📂 Version 1.8.0 — *Navigation Refresh*

* **Native Streamlit Navigation**: Moved from radio-based routing to
  `st.navigation()` and `st.page_link`.
* **Sidebar Groupings**: Reorganised the sidebar into Main and Admin/Developer
  sections.
* **Material Icons**: Replaced OS-dependent emoji in navigation with Streamlit's
  Material Icons.
* **Semester Selector**: Moved the semester control to the top of the sidebar and
  added an "All year" option.

### 📂 Version 1.7.0 — *Pluggable Auth & Admin Panel*

* **Pluggable Authentication**: Introduced a provider-based authentication system
  reading users and roles from configurable sources.
* **Admin Panel**: Added an interface for managing users, roles and application
  settings from within the dashboard.

### 📂 Version 1.6.0 — *SITS Assessment Insights*

* **SITS Assessment Integration**: Added the assessment type distribution to the
  Faculty Overview and assessment metrics to the School Dashboard.
* **Compare Schools**: Added a stacked bar chart comparing assessment components
  across schools, in absolute counts or normalised percentages, with a cross-tab
  pivot table.
* **Aligned School Dashboard Tabs**: Restructured the School Dashboard to use the
  same tab pattern as the Faculty Overview.
* **Semester Toggle Fix**: Fixed the double-click bug on the semester selector by
  binding it to session state with an `on_change` callback.

### 📂 Version 1.5.0 — *Feedback & Multi-School Access*

* **Feedback Form**: Added a feedback and suggestions form to the portal.
  *(Submissions were originally written to Google Sheets; they are now stored in
  the portal's own database.)*
* **Multi-School Focus Toggles**: School-specific accounts can temporarily
  uncheck focus to view dashboards and search modules outside their own school.
* **Admin and DLA Access**: Admin and DLA accounts now default to viewing all
  schools while retaining controls to inspect an individual school.
* **Audit Placeholders**: The module report now shows a clear "Incomplete" card
  for un-audited modules rather than empty slots.
* **Contribution Guide**: Added the collaboration slide deck to the "How to
  Contribute" view.

### 📂 Version 1.4.0 — *Lazy Loading & Row Drill-Down*

* **Segmented Control Navigation**: Replaced static tabs with stateful segmented
  controls that retain the selected view across interactions.
* **Row Drill-Down**: Analytics tables became row-selectable; selecting a row
  offers direct links to that module's report card or checklist.
* **Lazy Loading**: Only the active view is computed, so charts on inactive tabs
  no longer load.
* **Compliance Lenses**: Reworked the Priority Action view to present compliance
  gap summaries and checklist rosters in a single layout.

### 📂 Version 1.3.0 — *Activity Logging & Layout*

* **File Logging**: Added a persistent `app.log` recording sign-ins, sign-outs,
  data syncs and audit submissions.
* **Stateless Page Routing**: Reworked sidebar navigation so visiting help pages
  no longer overrides the retained view state.
* **Sidebar Layout**: Separated operational tools from help and changelog links.

### 📂 Version 1.2.0 — *Code Modularisation*

* **Refactored Architecture**: Split the monolithic script into components under
  `views/`.
* **Documentation Views**: Added the Help, Changelog and Developer Guide pages.

### 🔐 Version 1.1.0 — *Persistent Authentication*

* **Cookie Persistence**: Added cookie-based session preservation across browser
  reloads.
* **Credential Handling**: Removed plain-text credentials from source, reading
  them from environment variables instead.

### 📈 Version 1.0.0 — *Saved Views & Session State*

* **Active School View**: Added sidebar preferences and default selectors to
  tailor views per user without restricting access to other schools.
* **Unified Search**: Standardised module search fields.
* **Checklist History**: Added a historical version trail for audit submissions.
