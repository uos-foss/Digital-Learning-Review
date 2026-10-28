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
| Users and roles tables migrated into Django | Not started |

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
- **Platform name and layout** (added 28-10-2026). Django is also to host the
  other Fossdigital Python tools (see "Beyond DLR" below), so "FoSS Module
  Reports" and `/module-reports` are too narrow. Choose a neutral platform name
  (`SITE_NAME`; "FoSS Digital Tools" or similar is the user's preference) and URL layout, with module reports as one app under it, and a
  signed-in home listing the apps an account may use. Also make
  `web/dlr/routers.py` handle more than the one shared database, so each app can
  keep its own file.

Exit: the pattern, the cache decision and the platform name are written into `CLAUDE.md`.

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
- **Which apps an account may use**, not only which schools: Groups must also
  express app access, since GPL criteria and the AI Audit form arrive later
  (see "Beyond DLR"). The audiences differ: GPL is edited by GPL staff and viewed
  by students, and the DEdCPsy editor is for selected EDC staff only, so these are
  separate groups from the DLA roles, not a reuse of them. Check whether GPL's
  allowed-staff list holds people who are not in the DLR `users` table.
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

The biggest phase and the one that lets DLAs leave Streamlit.

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

## Phase 3b: AI Audit as a form app

Added 28-10-2026. The satellite AI-Audit survey rolls into Django as a form app.
**Respondents are not signed in**; the form captures an email address instead, so
this is a public view that must sit outside the login requirement the rest of the
platform has, with CSRF on, rate limiting, and a decision on whether the address
is verified (a typed address proves nothing about who submitted). It writes `assessment_responses` through
`database.py` as the satellite does today (the table is shared, so the schema
stays unmanaged by Django), with the question wording from
`../AI-Audit/questions.py` and the rollups from `processing.py`. Retires the
AI-Audit container. Check first that nothing else relies on its URL.

Exit: a respondent can submit a declaration in Django without signing in and Faculty Overview reads it unchanged.

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

## Beyond DLR: other Fossdigital tools

Added 28-10-2026. Django becomes the platform for the Fossdigital tools that are
staff-facing Python apps with a database. One Django project, one app per tool,
one database file per app, shared `accounts`.

- **GPL assessment criteria** (`gpldash.shef.ac.uk`, an alias of fossdigital): a
  Streamlit app of about 2,600 lines with its own SQLite, Google sign-in, docx
  generation and emailed access requests. GPL staff edit and students view. The
  aim is **variants for any school that wants it**, so design it with a school as
  the unit of configuration (criteria library, branding, who edits) rather than
  GPL hard-wired. Port as a `criteria` app **after Phase 7**, so two Streamlit
  ports never run at once. Serve the gpldash host as an alias to its path. The
  docx generation (`docxtpl`, `python-docx`) and the SMTP access-request flow are
  both kept, so they join the Django image: measure the image and memory, and
  confirm outbound mail is available from the Django container.
- **Students viewing GPL criteria** is the one student-facing piece on the
  platform. Decide whether it needs sign-in or is public, and whether it should
  run as its own compose service so staff-tool deploys cannot take it down.
- **DEdCPsy mapping editor**: for selected EDC staff only, so a dedicated group.
  Still lower priority than GPL. The public mapping page is static and stays as
  it is; only the small editor app is ported.
- **Not in scope, on purpose.** `Fossdigital-Landing` stays an independent Astro
  site, the front door that must stay up. `py-quiz` stays a separate Node
  service: timed student assessments must not share deploys, memory or outages
  with staff tooling. At most it could use Django sign-in for its admin area
  later.
- Deploy as separate compose services from one image if blast radius becomes a
  worry, so a fault in one app does not take down the rest.

## Risks

- **Sibling apps.** AI-Audit is the only sibling inspected. Others may read the
  shared database (SITS leads, `ally_*`). Confirm with their owners before
  Phase 5.
- **Users migration.** Capability edits made live in Streamlit can be lost if
  the roles decision is made carelessly.
- **Cache staleness** across two workers, until Phase 0 settles it.
- **Importer memory** in a container sized for read-heavy pages.
- **Docs.** The rewrite is real work, and out-of-date help is worse than none.
- **Coverage.** Importers, `database.py` writes, auth and the Django views have
  no tests today, only `web/smoke.py`.

## Open decisions

- Is Django authoritative for roles from Phase 2, or only after cutover?
- Does the generic CSV hub survive?
- The final URL path, and the neutral platform name (see Phase 0).
- Whether the GPL port reuses the DLR school alignment for its per-school variants or needs its own model.
- Whether students can view GPL criteria without signing in.
- Whether AI Audit email addresses are verified.
- Does Sheets write-back (comment bank and audit field definitions, through
  `data_manager.py`) survive, or does it end with Streamlit?
- Where the "my schools" preference is stored.
