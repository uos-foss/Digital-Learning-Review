# Roadmap: moving the app to Django only

The aim, stated 16-10-2026, is to move everything into Django and retire
Streamlit. Streamlit stays the DLA tool until Phase 3 is done, and stays running
until Phase 7. This file orders the work. It has no dates: add them when
capacity is known. `README.md` in this folder says what the first spike proved;
`CLAUDE.md` at the repo root holds the rules each phase must keep.

Order is driven by one idea: unblock the fix-claim rollout first, then work
towards retirement in the order that keeps DLAs productive.

## Where things stand

| Area | State |
|---|---|
| Module report, module finder, fix-claim form | In Django |
| School Dashboard read views (modules, alignment and lenses, comments, fixes, Ally, trends) | In Django |
| Google sign-in, roles as Groups, school alignment on `Profile` | In Django |
| Audit Portal, spot-check flag, un-flag, remove and check | Streamlit only |
| Faculty Overview (nine views), School Dashboard SGA and AI tabs | Streamlit only |
| Admin Panel (nine sections) and all importers | Streamlit only |
| PDF and CSV exports, docs and FAQ pages, feedback form | Streamlit only |
| Users and roles tables migrated into Django | First slice done (import and first sign-in) |
| Audit answers, claims and lead overrides carry an academic year | Not started: blocks the first rollover, and must land before Phase 3 |

What already makes this tractable: `processing.py`, `database.py`, `loaders.py`,
`report_model.py`, `security.py` and `sync_data.py` contain no Streamlit. All of
it is in `app.py`, `auth.py`, the dead `background_tasks.py` and `views/`
(about 7,800 lines). A phase is therefore a port of views and forms onto shared
rules, not a rewrite of the rules.

## Phase 0: decisions and foundations

Small, cross-cutting, and done first because every later phase leans on it.

- **The write pattern.** A Django write is a view that checks login, capability
  and school scope (before the object is looked up), then calls one
  `database.py` function. No SQL in views. CSRF on every POST. `web/smoke.py`
  stubs the save so it never writes to the shared database. The fix-claim form
  is the template.
- **Cache invalidation across workers.** Django caches module sources for 300
  seconds per gunicorn worker, and there are two workers, so a write handled by
  one is not seen by the other until the TTL passes. Streamlit clears its cache
  on every write. Choose a mechanism (a data-version value in the database that
  each request compares, or dropping the cache on write) before more writes
  arrive.
- **School focus.** Streamlit keeps `context_school` and `context_focus_own` in
  session state. In Django the school is in the URL and the "my schools" toggle
  is a stored preference.
- **Test coverage.** Add tests for the `database.py` writes that Django will
  start calling, and for permissions on the new views, before porting them.
- **A freeze.** No new features in Streamlit from here, only bug fixes.
- **Year-aware audit state.** Ally, Leganto, readiness, SGA and spot-checks
  already carry an academic year. `audit_responses`, `audit_response_history`,
  `fix_claims` and `module_lead_overrides` do not, so at rollover last year's
  ticks would read as this year's audit: modules "audited" and "complete"
  before anyone has looked. Add `academic_year` to them (an additive migration,
  existing rows backfilled `2026-27`, the year in each key) and filter every
  reader on `CURRENT_ACADEMIC_YEAR`, proving it a no-op for 2026-27 by
  fingerprinting `load_audit_frames()` and `derive_module_findings()` for every
  module before and after. It is the same work whichever front end runs it, and
  it must land before the Django Audit Portal is written, so Phase 3 is built
  year-aware and not retrofitted. See "Running a new academic year" below.

Exit: the pattern and the cache decision are written into `CLAUDE.md`, and the
audit tables are year-aware.

## Phase 1: unblock the fix-claim rollout

Blocks rolling `fix_claims` out beyond GPL. The design is settled in
`CLAUDE.md` ("Planned, not built: claims on unaudited modules").

- Any pending template-mapped section is claimable on an unaudited module
  (lead-owned and institution-owned, plus Learning Materials).
- An explicit "checked" action by a DLA per claim (confirm or reject), stored as
  a new column on `fix_claims`, replaces the timestamp test. An unrelated audit
  save then stops ending claims.
- An unaudited-module claim does not lapse by itself. It ends when the export
  shows the section ready or a DLA checks it.
- Each claim shows its age and whether an export since then still disagrees.
- DLA worklists: "reported fixed, awaiting check", "data now says ready, DLA
  said no", and the reverse ("DLA said yes, data now says not ready").
- A claim still never changes a verdict or a count.

Both front ends read the rule from `report_model.claimable_fixes()` and
`processing.py`. Exit: rolling out to a second school is safe.

## Phase 2: identity and access

- **Migrate users and roles.** A management command reads the SQLite `users` and
  `roles` tables: `Status` becomes `is_active`, `School` becomes
  `Profile.all_schools` or `Profile.schools`, `Role` becomes a Group. Per-user
  capability overrides and any custom role need a decision, because `seed_roles`
  today uses a hard-coded map and does not read the live `roles` table.
- **Decide who is authoritative for roles.** Either Django reads the live
  `roles` table until Streamlit goes, or Django becomes authoritative now and
  edits made in Streamlit's Role Capabilities tab stop mattering.
- **Match modules to people at scale.** The lead ownership question: names in
  SITS to accounts, with a human confirming the uncertain matches. This unlocks
  "own modules first" ordering for module leads and any later ownership gating.
- **Entra ID** alongside, when IT allows. Drop the Active Directory and Env
  providers, which do nothing or nothing real.
- Keep the break-glass local superuser.

First slice built (16-10-2026): `import_streamlit_users` pre-creates accounts
from the Streamlit tables using the live roles table, first sign-in connects to
them, and a first-time sign-in with no access sees a "Waiting for access" page.
Still to do in this phase: per-user capability overrides, retiring Streamlit's
user admin so the import stops being re-run, lead-to-module matching, and Entra.

Exit: every current user can sign in to Django with the right role and schools.

## Phase 3: the DLA tool

The biggest phase and the one that lets DLAs leave Streamlit. Depends on the
year-aware audit tables from Phase 0.

- **Audit form.** Booleans pre-filled by `readiness_prefill_for_module()`, text
  fields, Save Draft and Submit through `save_audit_responses` (one transaction,
  change history logged), status Not Started to Draft to Submitted with Update
  Audit afterwards.
- **Spot-check closing.** A pending flag closes on either save
  (`mark_spot_check_checked`, agreement from `compute_spot_check_agreement`). A
  Submit for an unflagged module records a checked row
  (`record_unflagged_spot_check`). Any DLA working the school can close a flag.
- **Queue** of pending flags for the schools in scope.
- **School Dashboard write side.** Flag, un-flag (pending only), remove (checked
  rows admin only), the re-flag guard for checked modules, and the jumps between
  dashboard, report and portal.
- Cache invalidation after every save (Phase 0).

Exit: a DLA can run a full audit and spot-check cycle in Django, and the
Streamlit Audit Portal is read-only or redirects.

## Phase 4: Faculty Overview and the rest of the School Dashboard

All read-only, reading shared rules.

- Faculty Overview's nine views: All Modules, School Comparison, Template
  Alignment, Ally Analytics, Trends, Priority Action List, Spot-Checks,
  Spot-Check Comments, AI in the Curriculum (with its Module Status section).
- The School Dashboard's Graduate Attributes view and the Awaiting and Declared
  AI tabs.
- CSV exports for both.
- Port any rule still written inline in a Streamlit view into `processing.py`
  first, proving it a no-op as was done for the lenses.

Exit: no read-side view is left only in Streamlit.

## Phase 5: the Admin Panel and importers

Ordered by risk, lowest first.

1. Module Manager (inactive modules, module leads and overrides).
2. Audit Field Manager. Its raw deletes move into `database.py`.
3. User Control and the Reported Fixes rollout setting (or the Django admin).
4. Feedback Explorer, System Dashboard, Log Viewer, Database Explorer, and
   System Maintenance (the schema check, legacy table drops and log truncate;
   its cache-purge button disappears with the Phase 0 cache decision).
5. Importers, one by one: Template Alignment (readiness), Leganto, Ally (with
   the Blackboard links import), SGA.
6. **SITS last, and carefully.** The AI-Audit app reads
   `sits_assessment_2026_27`: every column stays TEXT, it is always a full
   replace in one transaction with `executemany`, and module lead overrides are
   applied into the table. The lead-change diff is import-decision logic and
   needs care.
7. Decide whether the generic CSV hub survives. Its raw DDL and DML move into
   `database.py` if it does.

The `parse_*`, `save_*`, `replace_*` and `purge_*` functions are reusable as they
are. The work is the UI: uploads, previews, diff tables and confirm steps become
forms and views. Importers hold large DataFrames, so measure memory against the
container limit.

Exit: every import and admin task runs from Django.

## Phase 6: exports, documents and feedback

- PDF export of the module report (`report_pdf.py`).
- The feedback form.
- The docs and FAQ pages from `docs/`, with the role-based FAQ visibility and
  the FAQ heading parser, rendered by a Markdown library.
- A rewrite of `docs/` for the Django interface. It describes Streamlit today.
- `docs/year-rollover.md`, the annual runbook above, rehearsed once before it is trusted.

## Phase 7: cutover and retirement

- A parallel run, then Caddy: redirect `/digital-learning-review` to the Django
  site and decide the final path (it is `/module-reports` today). Update the
  Google OAuth redirect URIs.
- Delete `app.py`, `auth.py`, `views/`, `background_tasks.py`, `Dockerfile`, the
  `vle-portal` compose service, `.streamlit` and the Streamlit example config.
- Fold what Django imports from the repo root into `web/requirements.txt` and
  remove `REQUIREMENTS.txt`.
- Remove the Streamlit mentions left in comments and docs, and archive one-off
  scripts such as the spot-check backfill.
- Re-measure memory, since the 1 GB limit was a Streamlit concern.
- Update `CLAUDE.md`, `README.md` and `docs/developer-guide.md`.

Exit: nothing in the repo imports Streamlit.

## Running a new academic year

Nobody has done a rollover yet: the app has been a single-year tool for
2026-27. The year is a constant (`processing.CURRENT_ACADEMIC_YEAR`), the SITS
table's name carries it (`sits_assessment_2026_27`, about 25 references plus a
contract with the AI-Audit app), and the audit state has no year at all. The
next cycle starts around August to September 2027, so nothing here is urgent
before about June 2027, but the data work is the same whichever front end
carries it and Phase 3 should not be built without it.

**Before the first rollover**, in this order:

1. The year-aware audit tables (Phase 0, above).
2. A fix claim belongs to one year, so the "checked" column from Phase 1 is
   built with the year in its key and a new year starts with no claims.
3. One source for the year: the SITS table name, the SITS `Year` filter
   (`26/27` to `2026-27`) and the importer label are all derived from
   `CURRENT_ACADEMIC_YEAR` instead of being written out in about 25 places.
4. Agree the SITS table name with AI-Audit's owner. A stable name (a view or a
   fixed table, with last year archived by rename) is a one-off change for
   AI-Audit. A new name each year is an annual coordination cost.
5. Year-scope `module_lead_overrides`, so last year's hand-set leads appear in
   the SITS importer's lead-change table as candidates to carry over, not as
   silent overrides on the new rows.
6. Only if DLAs ask: a read-only `?year=` on the Django module report and
   school dashboard, so last year's audit stays viewable. Ally, Leganto and the
   other sources keep showing the current year only unless that is decided.
7. A rollover check (a dry-run script in `diagnostics/` style) that prints the
   pre-flight state and confirms every year-aware table is empty for the new
   year. The year constant itself changes by a reviewed commit, never by a script.
8. Tests for the year-to-label and table-name functions, and for the audit
   readers ignoring rows from another year.

**The annual runbook** is written as `docs/year-rollover.md`, in an order that
does not depend on which front end is live:

1. Freeze and snapshot (June to July): a final import of each source, a copy of
   the shared database and of Django's accounts database tagged
   `pre-rollover-YYYY` (the rollback for everything below), records of
   spot-check outcomes and reported fixes, and every pending spot-check and
   unchecked claim closed.
2. Cut the year: one reviewed commit and deploy in a quiet week. The app opens
   on the new year with every year-aware table empty, which is the first smoke
   test.
3. Load the new year's data in dependency order: SITS first (reviewing the
   lead-change table with care), then Ally, readiness (the first export is the
   untouched-template baseline, so re-read the drift alarms), Leganto and SGA.
   Review `audit_fields` and `TEMPLATE_SECTIONS` against the new template.
4. Accounts: re-run `import_streamlit_users` until Streamlit's user admin goes,
   revoke leavers by hand (the import never removes access), and decide whether
   `feature_schools` carries over.
5. Open the audit year: a fresh DLA queue, spot-check flagging by DLA judgement,
   and the module-report link announced to leads.
6. Mid-year cadence: Ally and readiness re-imports on schedule, SITS when
   registrations change, SGA and Leganto when exports arrive.
7. Close-out in July: the year-end extract, then step 1 for the next year.

| Step | Today | After Phase 3 | After Phase 5 | After Phase 7 |
|---|---|---|---|---|
| Backup and snapshot | host shell | same | same | same |
| Cut the year | code commit | same | same | same |
| Imports | Streamlit Admin Panel | Streamlit | Django | Django |
| Users | `import_streamlit_users` | same, or Django admin | Django admin, Entra | Django admin |
| Audit and spot-checks | Streamlit | Django | Django | Django |

Do a dress rehearsal once, in spring 2027, not first in August: copy the live
database, set `CURRENT_ACADEMIC_YEAR` to `2027-28` locally, run the whole
runbook on the copy with a year-relabelled SITS export, and confirm that the
empty state is clean, that no 2026-27 answers appear in 2027-28 views, that
AI-Audit still reads SITS, and that restoring the pre-rollover copy works.
Record the timings in `docs/year-rollover.md`.

## Risks

- **Sibling apps.** AI-Audit is the only sibling inspected. Others may read the
  shared database (SITS leads, `ally_*`). Confirm with their owners before
  Phase 5.
- **Users migration.** Capability edits made live in Streamlit can be lost if
  the roles decision is made carelessly.
- **Cache staleness** across two workers, until Phase 0 settles it.
- **Importer memory** in a container sized for read-heavy pages.
- **Docs.** The rewrite is real work, and out-of-date help is worse than none.
- **Stale answers across the year boundary.** Until the audit tables carry a
  year, the first rollover would present 2026-27 ticks as 2027-28 audits.
- **The SITS table name** is a contract with AI-Audit. Changing it unannounced
  breaks that app.
- **Coverage.** Importers, `database.py` writes, auth and the Django views have
  no tests today, only `web/smoke.py`.

## Open decisions

- Is Django authoritative for roles from Phase 2, or only after cutover?
- Does the generic CSV hub survive?
- The final URL path.
- Does Sheets write-back (comment bank and audit field definitions, through
  `data_manager.py`) survive, or does it end with Streamlit?
- Where the "my schools" preference is stored.
- The SITS table name: a stable name with an annual archive (recommended), or a
  new name each year. Needs a word with AI-Audit's owner.
- Should last year's audit answers stay readable after rollover (a year picker),
  or is an export and archive enough?
- Fix claims and `feature_schools`: start each year empty and re-roll out, or
  carry the school rollout forward?
- Is there a fixed date each year when the VLE template rolls over? It sets the
  timing of steps 2 and 3 and when the first readiness export means anything.
