Welcome to the Digital Learning Review portal. This page explains what each
part of the dashboard does and where its numbers come from.

### 📂 Pages

The sidebar shows only the pages your account has access to, so you may not see
all of these.

1. **Faculty Overview** — All schools side by side. Requires the `view_all`
   capability.
2. **School Dashboard** — One school at a time, with module-level detail.
   Accounts holding `view_school` are locked to their own school; everyone else
   can switch schools from the selector at the top of the page.
3. **Module report** — A single module in full: metadata, Ally accessibility
   profile, reading-list status, audit responses and SITS assessment strategy.
4. **Audit Portal** — Where Digital Learning Advisors carry out a module's
   audit on the module lead's behalf, recording findings, notes for the lead,
   and internal notes that leads do not see. Audits can be saved as a draft and
   submitted when complete. Requires the `edit_checklist` capability.
5. **Resources & Support** — This page: help, the release changelog, and a form
   for reporting bugs or requesting features.
6. **Admin Panel** — User and role management, audit field configuration, data
   import/export, logs and diagnostics. Requires `access_admin_panel`.

### 🗓️ Semester Selector

The **Select Semester** control at the top of the sidebar (Autumn / Spring /
All year) filters every school and module-level view.

Modules that run across the whole year appear in **both** Autumn and Spring, so
they are never missed by someone working in a single semester. Selecting
**All year** narrows the view to those year-long modules on their own.

### 🏛️ Faculty Overview

Five tabs:

* **School Comparison** — One row per school: module count, audit coverage,
  average Ally score, VLE compliance and an overall status badge. Faculty-wide
  totals sit beneath the table. Click any row to open that school's dashboard.
* **Ally Analytics** — The faculty's accessibility profile, in six tabs: the
  issue league table, build-out tracker, files against editor pages, severity
  load by school, score distribution and a data-coverage check.
* **Compliance Gap** — Which audit checks are most often failed.
* **Priority Action List** — Modules most in need of attention.
* **Assessment Types** — SITS assessment strategy overall, or compared across
  schools as absolute counts or normalised percentages, with a cross-tab pivot
  under the expandable table.

> **Reading VLE Compliance correctly.** Compliance is calculated across
> **submitted audits only** — an unaudited module tells us nothing about
> whether it complies. Always read the figure alongside the Audited column: a
> school showing 95% compliance on 3 of 60 modules audited is not in better
> shape than one showing 70% on 55 of 60. The status badge reflects both Ally
> and compliance, and shows "— No Data" where neither is available.

### 🏫 School Dashboard

Six tabs. Note that these are **not** the same set as the Faculty Overview —
this page has All Modules and Trends, and does not have School Comparison.

* **All Modules** — Every module in the school with its lead, Ally score, build
  stage and audit status.
* **Ally Analytics** — Six tabs: what to fix, build progress, files against
  editor pages, severe issues, a per-module table, and reconciliation against
  SITS.
* **Trends** — The school's accessibility score and content volume over the
  stored Ally snapshots.
* **Compliance Gap**, **Priority Action List**, **Assessment Types** — As on
  the Faculty Overview, scoped to this school.

> **Reading Ally scores correctly.** Ally reports three scores, and the portal
> shows all three because they mean different things:
>
> * **Files** — uploaded documents: PDFs, Word files, PowerPoints. Fixing these
>   means correcting the source document and re-uploading it.
> * **Editor pages** — pages built with the Blackboard content editor. These
>   are usually fixable in place in a couple of minutes.
> * **Overall** — the two combined, weighted by how much content sits behind
>   each.
>
> A module scoring well overall can still hide a completely inaccessible
> document, which is why the module report lists the actual issues rather than
> stopping at the score.
>
> **Build stage matters more than the score early in the year.** A freshly
> rolled-over course contains only its template — about two files and two dozen
> editor pages — and Ally scores that template close to 100%. Every average in
> the portal therefore covers only courses marked *In progress*, and the
> Priority Action List ignores courses that have not started yet. There is no
> "Complete" or "Built" stage — module leads build just-in-time throughout the
> course, often right up to the final assessment, so no count of files can ever
> say a course is finished, only that it has started. Before term starts, the
> build-out tracker is the useful view; the scores become meaningful as
> material goes up.

### ⚡ Jumping Between Views

Click any row in the module tables on the School Dashboard to reveal buttons
that take you straight to that module's **Module report** or open it in the
**Audit Portal**, without going back through the menus. The same applies to
rows in the Faculty Overview's School Comparison table, which open the relevant
school dashboard.

Opening a school this way is a one-off: it does not change your saved school
preference.

### 🔑 Signing In

The portal supports several sign-in methods, selected by the administrator.
Most deployments use either a username and password held in the portal's own
database, or **Sign in with Google**.

If your account signs in with Google, it will show no password in the Admin
Panel. That is expected and correct — your identity is confirmed by Google, and
the account entry simply records that you are permitted access.

Sessions persist across browser reloads via a cookie, so you should not need to
sign in repeatedly.

### 🔄 Where the Data Comes From

The portal reads from a local **SQLite** database. Pages refresh their data
every few seconds, so anything you save appears almost immediately.

That database is populated from several sources:

| Source | Contents | How it is updated |
| :--- | :--- | :--- |
| **SITS** | Module list, teaching periods, assessment strategy | Imported annually |
| **Ally** | Accessibility scores, content counts and per-check issue counts, with history | Institutional report, imported periodically |
| **Leganto** | Which modules have no reading list, and whether a list is Draft or Published | Monthly |
| **Template Alignment Report** | Which required Blackboard template sections are visible, hidden, deleted or missing, and when each changed | Faculty report, imported periodically |
| **Blackboard** | Direct links to each module's VLE site | CSV import in the Admin Panel |
| **Audits** | Advisor findings against each module | Saved in the Audit Portal as advisors work |

Audits are saved straight to the portal's own database — nothing is written
back to a spreadsheet. Google Sheets is now used only as an **upstream source**:
an administrator refreshes from it on demand using **Trigger Full Sync** in the
Admin Panel. This is why the portal no longer runs into spreadsheet API limits.

### 🚫 Inactive Modules

Some modules in SITS are not really running — skeleton shells, modules merged
into another, or archived records. Administrators can mark these as inactive in
the Admin Panel, which removes them from every dashboard, count and analytic so
they do not drag down a school's figures. They can be restored at any time.

### 📜 Activity Logging

The portal keeps a local log (`app.log`) recording sign-ins, data syncs and
audit submissions. Administrators can read it from the Admin Panel's Log Viewer
without needing server access.
