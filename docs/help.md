Welcome to the Digital Learning Review portal. This page explains what each
part of the dashboard does and where its numbers come from.

### 📂 Pages

The sidebar shows only the pages your account has access to, so you may not see
all of these.

1. **School Dashboard**: one school at a time, with module-level detail.
   Requires the `view_school_dashboard` capability. Accounts holding
   `view_school` are locked to their own school; everyone else can switch
   schools from the selector at the top of the page.
2. **Module report**: a single module in full: metadata, Ally accessibility
   profile, reading-list status, audit responses and SITS assessment strategy,
   organised as Accessibility Report and Module Checks and Readiness tabs,
   with a single Actions panel listing everything still outstanding across
   every source.
3. **Audit Portal**: where Digital Learning Advisors carry out a module's
   audit on the module lead's behalf, recording checklist findings and notes.
   Audits can be saved as a draft and submitted when complete. Requires the
   `edit_checklist` capability.
4. **Resources & Support** (this page): help, the release changelog, and a form
   for reporting bugs or requesting features.
5. **Admin Panel**: user and role management, audit field configuration, data
   import/export, logs and diagnostics. Requires `access_admin_panel`, or the
   reduced `access_admin_limited` scope (Module Manager and a restricted User
   Control tab only, with no Role Capabilities, no delete/password-reset/
   masquerade, no assigning admin roles) available to Digital Learning
   Advisors.

### 🗓️ Semester Selector

The **Select Semester** control at the top of the sidebar (Autumn / Spring /
All year) filters every school and module-level view.

Modules that run across the whole year appear in **both** Autumn and Spring, so
they are never missed by someone working in a single semester. Selecting
**All year** narrows the view to those year-long modules on their own.

### 🏫 School Dashboard

Seven tabs:

* **Modules Overview**: four summary cards (total modules, modules with no
  activity, average Ally score, outstanding actionable items), then every
  module in the school with its lead, level, Ally score, reading-list status,
  build stage and audit status.
* **Template Alignment**: how well modules follow the Blackboard template
  that gives students a consistent, accessible experience, combining the
  Template Alignment Report's data with manual audit answers where recorded,
  plus a per-module item table (checklist, readiness, Leganto and Ally
  findings) beneath the chart.
* **Ally Analytics**: a single view holding the issue-by-severity chart and the
  module table side by side, both driven by the severity and issue filters
  above them. No filters shows every module; narrowing to Severe replaces
  the old dedicated severe-issues list. (Reconciliation against SITS moved
  to the Admin Panel's Module Manager tab, since it's a data-integrity
  check, not an accessibility metric.)
* **Trends**: the school's accessibility score and content volume over the
  stored Ally snapshots.
* **Priority Action List**: modules most in need of attention.
* **Assessment Types**: SITS assessment strategy for this school's modules.
* **Spot-Checks**: every module the school has flagged this year, its status
  and agreement result once checked; see "Data Reliability and Audit
  Rationale" below for what spot-checking is for.
* **Spot-Check Comments**: the Additional Comments an advisor wrote when
  auditing those flagged modules, in full and newest first, with a search box
  and a CSV export. The Spot-Checks view shows the same text one line at a
  time and holds the jump and remove-flag actions; this view is for reading
  it. A flagged module nobody has audited yet has no comment, and is hidden
  unless you tick "Include flagged modules with no comment yet".

> **Ally Analytics, Trends and Priority Action List are temporarily
> admin-only.** While those views are being reworked, only accounts with
> `access_admin_panel` see these three tabs; everyone else sees the other
> three as normal. This is expected to be temporary.

> **Reading the two compliance figures correctly.** The portal reports
> compliance twice, over deliberately different sets of modules:
>
> * **Template Alignment** (this dashboard, and the Faculty Overview tab of
>   the same name) covers **every module in the school**. A module an advisor
>   has audited uses their recorded answer; a module nobody has audited falls
>   back to the Template Alignment Report's own data, so it is not counted as
>   a failure merely for being unaudited.
> * **VLE Compliance** (the School Comparison table on the Faculty Overview)
>   covers **submitted audits only**, because for a school-against-school
>   comparison an unaudited module tells us nothing.
>
> Always read VLE Compliance alongside the **Audited %** column beside it: a
> high figure drawn from a handful of audited modules is not the same claim as
> one drawn from most of the school.

> **Reading Ally scores correctly.** Ally reports three scores, and the portal
> shows all three because they mean different things:
>
> * **Files**: uploaded documents such as PDFs, Word files and PowerPoints. Fixing these
>   means correcting the source document and re-uploading it.
> * **Editor pages**: pages built with the Blackboard content editor. These
>   are usually fixable in place in a couple of minutes.
> * **Overall**: the two combined, weighted by how much content sits behind
>   each.
>
> A module scoring well overall can still hide a completely inaccessible
> document, which is why the module report lists the actual issues rather than
> stopping at the score.
>
> **Build stage matters more than the score early in the year.** A freshly
> rolled-over course contains only its template (about two files and two dozen
> editor pages), and Ally scores that template close to 100%. Every average in
> the portal therefore covers only courses marked *In progress*, and the
> Priority Action List ignores courses that have not started yet. There is no
> "Complete" or "Built" stage, because module leads build just-in-time throughout the
> course, often right up to the final assessment, so no count of files can ever
> say a course is finished, only that it has started. Before term starts, the
> build-out tracker is the useful view; the scores become meaningful as
> material goes up.

### ⚡ Jumping Between Views

Click any row in the module tables on the School Dashboard to reveal buttons
that take you straight to that module's **Module report** or open it in the
**Audit Portal**, without going back through the menus.

### 🔑 Signing In

The portal supports several sign-in methods, selected by the administrator.
Most deployments use either a username and password held in the portal's own
database, or **Sign in with Google**.

If your account signs in with Google, it will show no password in the Admin
Panel. That is expected and correct. Your identity is confirmed by Google, and
the account entry simply records that you are permitted access.

Sessions persist across browser reloads via a cookie, so you should not need to
sign in repeatedly.

### 🔄 Where the Data Comes From

The portal reads from a local **SQLite** database. Pages refresh their data
every few seconds, so anything you save appears almost immediately.

That database is populated from several sources:

| Source | Contents | How it is updated |
| :--- | :--- | :--- |
| **SITS** | Module list, module leads, teaching periods, assessment strategy | Imported in the Admin Panel whenever a fresh export is available |
| **Ally** | Accessibility scores, content counts and per-check issue counts, with history | Institutional report, imported periodically |
| **Leganto** | Which modules have no reading list, and whether a list is Draft or Published | Monthly |
| **Template Alignment Report** | Which required Blackboard template sections are visible, hidden, deleted or missing, and when each changed | Faculty report, imported periodically |
| **Blackboard** | Direct links to each module's VLE site | CSV import in the Admin Panel |
| **Audits** | Advisor findings against each module | Saved in the Audit Portal as advisors work |

Audits are saved straight to the portal's own database, and nothing is written
back to a spreadsheet. External data arrives through the importers in the
Admin Panel's **Data Import/Export** tab rather than a live spreadsheet
connection, which is why the portal no longer runs into spreadsheet API limits.

Module leads corrected by hand in **Module Manager** are kept when a new SITS
export is imported, unless the administrator importing it chooses to take the
SITS name instead.

### 🎯 Data Reliability and Audit Rationale

The portal draws on two different kinds of evidence, and they answer
different questions.

**Automated signals** come from institutional systems: Blackboard Ally
(accessibility), the Template Alignment Report, and Leganto (reading lists).
These are snapshots, refreshed when a new export is imported, not live
feeds, so every figure on the portal carries the date it was captured. They
measure presence and process: whether a section is visible, whether it has
been edited, whether a reading list exists. They do not measure quality. A
visible, edited section is evidence that someone did something to it. It is
not evidence that the content is good, current, or pedagogically sound.

**Human judgement**, recorded through the Audit Portal and spot-checks, is
the other half. A saved audit answer always takes precedence over an
automated signal wherever both exist for the same field, and the portal
labels the two differently throughout ("Automatically detected" versus
"Manually verified") so it is never ambiguous which one you are looking at.

> **Why the audit does not aim to check everything itself.** Manually
> auditing every module in the faculty does not scale to a small team. The
> automated signals exist to direct that limited time toward the modules and
> sections most likely to need it, not to replace the judgement of the
> Digital Learning Advisor carrying out the review. When a finding is raised
> with a module lead, it is a signal from the institution's own systems plus
> the advisor's own review of it, not a personal verdict on the module
> lead's teaching or expertise.

### 🗂️ Module Manager

The Admin Panel's Module Manager tab covers two things: which modules are
active, and who leads them. It's reachable with either `access_admin_panel`
or the reduced `access_admin_limited` scope, so Digital Learning Advisors can
use it without full admin rights.

**Inactive Modules.** Some modules in SITS are not really running: skeleton
shells, modules merged into another, or archived records. Administrators can
mark these as inactive, one at a time or in bulk from a module_code CSV with
a single reason applied to the batch, which removes them from every
dashboard, count and analytic so they do not drag down a school's figures.
They can be restored at any time, and the current inactive list can be
exported to CSV for round-trip editing. The same sub-tab also shows the
Ally/SITS reconciliation: Blackboard courses Ally tracks with no matching
SITS module (usually shell, custom or programme-level sites, so candidates for
marking inactive, but occasionally real provision SITS hasn't caught up on),
and SITS modules with no Blackboard course.

**Module Leads.** An overview of every module lead, grouped by name, so
inconsistent spellings or casing for the same person are visible as separate
rows rather than hidden. Renaming a group updates every module carrying that
exact name in one action. A second, per-module list below covers active and
inactive modules alike for one-off corrections, such as reassigning a single
module to a different lead.

### 👤 User Control

The Admin Panel's User Control tab manages accounts and roles. Full admin
holders see the whole tab, including Role Capabilities; the reduced
`access_admin_limited` scope hides Role Capabilities entirely and excludes
delete, password-reset and masquerade actions, and can't assign an admin
role to anyone.

User Accounts includes a Bulk Import/Export section: importing a CSV of
usernames, roles, schools and plaintext passwords validates every row up
front (permitted roles, real school codes, in-file duplicate usernames)
before writing anything, and hashes passwords on the way in. A matching
Bulk Remove accepts a CSV of usernames (the same file used to import works),
behind a confirmation checkbox; it skips your own account and, for a
limited admin, any admin account. Usernames are matched case-insensitively
throughout, so re-importing an existing account never creates a duplicate
under different casing.

### 📜 Activity Logging

The portal keeps a local log (`app.log`) recording sign-ins, data syncs and
audit submissions. Administrators can read it from the Admin Panel's Log Viewer
without needing server access.
