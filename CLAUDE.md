# Digital Learning Review — working notes

Streamlit dashboard for the Faculty of Social Sciences VLE audit. Deployed by
Docker Compose on an Ubuntu VM behind Caddy.

This file records what is **not** obvious from reading the code. Everything else
— structure, past fixes, git history — read from the repo itself.

## Who does what

Audits are carried out by **Digital Learning Advisors on the module lead's
behalf**. Module leads do not fill in their own audits. This is why the Audit
Portal has both `notes_to_lead` ("Notes for Module Lead") and `auditor_notes`
("🔒 Internal Notes", explicitly not visible to leads).

Do not describe the audit as something leads complete. Older code and docs used
"Module Lead Checklist" for what is now the Audit Portal — that name was wrong
about who does the work, so do not reintroduce it.

## Data architecture

**SQLite is the source of truth.** `database.py` owns the schema and every
query. Google Sheets is an *upstream source only*, drained into SQLite by
`sync_data.py` when an admin clicks Trigger Full Sync, or by running that module
as a script.

- Never add a gspread call to a request path. If a page needs data, it comes
  from SQLite. The whole point of the v1.9 migration was removing Sheets from
  page loads, and the API quota ceiling with it.
- Write-back to Sheets is limited to the comment bank and audit field
  definitions. Audits and feedback never leave SQLite.
- `background_tasks.py` is deliberately disabled (the import in `app.py` is
  commented out). It pushed checklists to Sheets and has no job now. Leave it.
- The database lives on a host volume (`/opt/shared-audit-data` → `/app/data`),
  shared with sibling apps. It is not in git and is not in the image.

**The `users` table is authoritative in SQLite.** The Admin Panel writes there
and never back to Sheets, so the Users sheet is always stale. Sync must only
insert genuinely new accounts — `sync_new_users_only()`. Anything that rebuilds
the table (`if_exists='replace'`) silently reverts role and status edits, and
would undo the scrypt password migration. Roles do sync wholesale; those are
genuinely sheet-managed.

## Ally accessibility data

`ally_courses` / `ally_issues` / `ally_content` (course grain — a Blackboard
course shell, not a SITS module) are the source of truth, populated by the
importer in the Admin Panel from Anthology's institutional report export.
`ally_scores` is a legacy projection rebuilt from `ally_courses` for views not
yet migrated; do not write to it directly. Multiple Blackboard shells can share
one module code (different cohorts) — aggregate to module grain on read via
`processing.aggregate_ally_to_modules()`, never at import time.

- **Only `CURRENT_ACADEMIC_YEAR` (`processing.py`) is ingested and shown.** A
  prior import silently stored a mislabeled prior-year snapshot that displayed
  against the current year's module list for months before anyone noticed. Do
  not backfill or surface other years without a deliberate decision to do so.
- **Content maturity has exactly two positive states: `Not yet built` and
  `In progress`.** There is deliberately no `Built`/`Complete` state —
  `classify_content_maturity()` in `processing.py` only measures file counts,
  and module leads build just-in-time throughout the course (often up to the
  final assessment), so a file count can show a course has started but never
  that it is finished. A three-state version with a `Built` tier existed
  earlier and was removed on that reasoning; do not reintroduce it.
- **Ally's own scores are shown unmodified.** An earlier credibility-weighting
  model (shrinking scores toward a prior at low file counts) was removed — it
  distorted the majority of modules at typical file counts, only ever pushed
  scores down, and disagreed with the score module leads see in Blackboard
  itself. Content maturity gates which courses count toward averages/rankings
  instead of a score adjustment.
- `diagnostics/check_ally_export.py <csv> <academic_year>` sanity-checks a new
  export (scope, grain, score invariants, SITS reconciliation) before trusting
  an import — run it against any new Ally export.

## Leganto reading-list data

There are **two separate, disjoint Leganto exports** — don't conflate them:

- `leganto_nolist` — modules confirmed to have **no** reading list at all.
  Surfaced everywhere as the `Leganto Missing` boolean. Imported through the
  generic CSV-to-table hub in the Admin Panel.
- `leganto_lists` — course-grain status/items for modules that **do** have a
  list (Draft vs Published, citation count). Source of truth for the
  `Leganto List Status` / `Leganto List Items` fields. Populated by the
  dedicated importer (`_render_leganto_import()` in `views/admin_panel.py`),
  via `processing.parse_leganto_lists_export()` and
  `database.save_leganto_snapshot()` — same shape as the Ally pipeline below.
  A module absent from *both* exports just gets blank status, not `Missing`.

Same aggregation rule as Ally: a module can have more than one course
occurrence, so roll up to module grain on read via
`processing.aggregate_leganto_to_modules()`, never at import time.

- **The export has no per-row academic year column.** Unlike Ally's `Term
  name`, the year is an explicit operator choice at import time
  (`_render_leganto_import()`'s year selector), not read from the file. The
  importer only warns when the tag looks inconsistent with the course names
  in the file — it never infers or enforces a year on its own.
- **`leganto_lists`'s primary key includes `academic_year`**
  (`course_code, snapshot_date, academic_year`), unlike `ally_courses`. Two
  different years can legitimately produce identical-looking rows for the
  same course on the same snapshot date — e.g. a reference import of a prior
  year's export ahead of the real current-year one — and without
  `academic_year` in the key those rows silently collide and overwrite each
  other. `save_leganto_snapshot()`'s change-detection (skip-if-unchanged)
  is likewise scoped per `academic_year`, not just per `course_code`, for the
  same reason. Preserve this if the table is ever touched again.
- `database.purge_leganto_lists(academic_year)` deletes one year's rows only
  — the way to drop a reference/test import once the real export for that
  year lands, without touching other years.

## Module readiness (template alignment) data

`readiness_courses` / `readiness_sections` hold the faculty **Template
Alignment Report** (called Template Adherence before 2026/27): per Blackboard
course, the visible/hidden/deleted/missing state of each required template
section and when each was last changed. Imported by `_render_readiness_import()`
in `views/admin_panel.py` via `processing.parse_readiness_export()` and
`database.save_readiness_snapshot()` — same pipeline shape as Ally.

- **Only 3 of the 14 sections carry any signal.** Eleven ship *visible* and are
  institutional boilerplate nobody is expected to edit, so `Visible` on those
  means nothing. `WELCOME_MODULE_OUTLINE`, `KEY_STAFF_CONTACTS` and
  `ASSESSMENT_DETAIL` ship *hidden* and must be unhidden by the module lead —
  `LEAD_OWNED_SECTIONS`, derived from the `TEMPLATE_SECTIONS` catalogue. Triage
  on those; the vendor's `COMPLETENESS_SCORE_PERCENT` / `Alignment_STATUS` are
  stored and shown verbatim for continuity with the faculty report but restate
  the visible-section count — 43 of the 45 courses in the first excerpt sat on
  exactly 78.6% / "Needs Review", the untouched post-rollover default.
- **Status and edit evidence are separate questions, and both are needed.**
  Status says whether a student can see the section; evidence says who moved it.
  `classify_section_state()` combines them into the `SECTION_STATES` model, and
  the combinations are not variations on a theme:
  - `drafted_hidden` — worked on and *still hidden*. 34 sections across 25
    modules in the 2026-27 export. The work exists and no student can see it, so
    the remedy is one click. A status-only reading calls this "not started",
    which is both wrong and insulting to whoever did the work.
  - `visible_unattributed` — visible, but the only date is a bulk push or the
    course creation date. Counted as ready, because students really can see it,
    but it is *not* evidence anyone prepared it and auto-complete must never
    key off it. Only 2 sections today — but if a template revision ever ships
    these three visible by default, this becomes the mass default and every
    module reads "3 of 3 ready" with no work done. Two checks in
    `diagnostics/check_readiness_export.py` guard that: the attribution share
    alarm, and the most-hidden-sections drift check.
- **`TEMPLATE_SECTIONS` maps each section to the `audit_fields.id` it answers.**
  That mapping is the point: the data pre-answers the existing checklist rather
  than sitting beside it as a rival score. Keep it in step with `audit_fields`.
- **Sections are discovered from the column names**, not a fixed list — any
  column ending `_STATUS` other than `Alignment_STATUS`, paired with its
  `_LAST_MODIFIED` sibling. The template is versioned and changes between years,
  so a revised template imports without a code change; only the catalogue needs
  a new label. `readiness_sections` is long for the same reason.
- **A last-modified date is not evidence of *lead* activity on its own — and a
  shared batch date is usually not IT either.** Aside from the original
  template rollout, IT does not push bulk content edits. What actually
  produces a date shared across many of a school's courses is most often
  Professional Services (PS) / school admin staff working through a batch of
  modules editing a specific section (commonly Key Staff Contacts) on the
  lead's behalf — genuine content work, just not done by the lead, and which
  section(s) get PS-edited this way varies by school. The export gives only a
  date, no time or editor, so a real IT rollout and a PS team clearing a
  worklist in one afternoon are indistinguishable in the data.
  `detect_bulk_edit_dates()` flags a (school, date) on *either*
  `READINESS_BULK_EDIT_SHARE` of the school **or** `READINESS_BULK_EDIT_MIN_MODULES`
  modules outright, and `classify_edit_evidence()` reduces those to *no
  positive evidence of lead activity* — never evidence the section itself is
  unfinished. Both tests are needed: share alone is scale-dependent, and the
  faculty-wide export proved it — the ALA batch of 23/07 touched 25 modules,
  which is 56% of the 45-module excerpt the rule was first calibrated on but
  only 18% of the real 142-module school. Adding the floor moved 131 lead-section
  observations out of `lead_edit`. Over-flagging is the safe error here, since a
  batch hit only ever withholds *lead* evidence, not readiness. Re-run
  `diagnostics/check_readiness_export.py` on each new export — it prints the
  distribution, what was flagged, and the closest cases that were not.
  **Resolved for Phase 4** (`processing.readiness_prefill_for_module()`): the
  Audit Portal checklist question is "is this section done", not "did the
  lead do it personally", so a `bulk`-evidenced Visible section is suggested
  ticked exactly like a `lead_edit`-evidenced one — see "Audit Portal
  pre-fill" below. This is a different question from *lead-engagement*
  evidence, which `classify_edit_evidence()` still tracks separately and
  unchanged.
- **Both primary keys include `academic_year`** (`leganto_lists`'s reasoning,
  not `ally_courses`'s) so a reference import of a prior year cannot collide
  with the real one on a shared snapshot date.
  `database.purge_readiness(academic_year)` drops one year, parent and child.
- Same aggregation rule as Ally and Leganto: multiple shells per module, so roll
  up on read via `processing.aggregate_readiness_to_modules()`, never at import
  time. Section status combines worst-wins via `READINESS_SECTION_RANK`.
- The readiness tables are **blocked from the generic CSV import hub**, like the
  Ally tables — the export needs melting and date conversion. Export still works.
- `diagnostics/check_readiness_export.py <csv> <academic_year>` sanity-checks a
  new export before trusting an import. It cross-checks the export's own
  `HIDDEN_SECTIONS` / `DELETED_SECTIONS` summary text against its per-section
  columns, re-asserts the 11/3 split, and prints the date distribution behind
  `READINESS_BULK_EDIT_SHARE`. Run it against any new export.

## Unified module findings

`processing.derive_module_findings(active_row, responses, active_fields,
comment_bank)` is the **only** place that decides what a module has
outstanding. Every source — checklist fields, Leganto, Ally, template
readiness — is classified there, tagged `source` and `state`
(`'pending'`/`'completed'`). Two consumers read from it:

- `app.py::load_checklist_data()` sums every pending finding into
  `Actionable Items`, the badge on School Dashboard / Faculty Overview.
- `views/module_report.py::view_module_report()` filters the same list —
  `source in ('checklist', 'leganto')` builds the generic worklist cards;
  `source == 'checklist'` alone drives the health banner's "N checklist items
  outstanding" wording, so it doesn't double-narrate against Ally/Leganto/
  readiness's own dedicated bullets, which read `active_row`/`ally_profile`
  directly and are unaffected by this.

**Why this exists**: before it, the badge and the module report page each
computed "what's outstanding" independently and disagreed. Concretely, the
badge never counted a Leganto list stuck in Draft, never counted template
readiness at all, and undercounted legacy free-text custom observations the
module report page showed as cards — so a module could show 9 outstanding
items on its own page and 0 on the dashboard that's meant to prioritise
across the school. Do not reintroduce a second, hand-written "count what's
pending" anywhere; add a new source to `derive_module_findings()` instead.

**Ally and readiness findings are produced but never rendered generically** —
both already have their own richer display (the accessibility card, the
Blackboard Template block), so `view_module_report()` deliberately excludes
those two sources from the generic pending/completed card list. They still
count toward `Actionable Items`, which is the whole point: the badge now
agrees with what those richer views show.

**A never-audited module's checklist fields do not count toward
`Actionable Items`** until the module has at least one row in
`audit_responses` — `load_checklist_data()` calls
`derive_module_findings(row, {}, active_fields=[], comment_bank)` (empty
`active_fields`) for modules with no audit trail, so only Leganto/Ally/
readiness findings reach the badge for them. This preserves the badge's prior
behaviour deliberately: ~1,560 of ~1,570 modules have never been audited, and
counting all 8 checklist fields as pending for every one of them would swamp
the badge with a constant rather than a differentiated signal. The module
report page still shows all 8 as pending cards for an unaudited module — that
asymmetry (quiet badge, full worklist once you open the module) is
deliberate, not a bug to fix by making them agree.

**`has_audit` needs a real auditor, not just a dict entry.** Because
`checklist_sums` now holds an entry for any module with a data-only pending
finding, `selected_code in checklist_sums` no longer means "a person has
audited this". Data-only entries are stamped `'Auditor': 'System'`; check
`sum_entry.get('Auditor') not in (None, '', 'System')` instead — see
`view_module_report()`.

`parse_custom_observations()` lives in `processing.py`, not `database.py` — it
is pure string/JSON parsing with no I/O. `database.py` imports and re-exports
it so nothing importing it from there breaks.

## Audit Portal pre-fill

`processing.readiness_prefill_for_module(active_row)` turns a module's
template-readiness section states into checklist suggestions for the Audit
Portal: `{audit_field_id: {'suggested': bool, 'evidence_text': str,
'section_key': str}}`, one entry per `TEMPLATE_SECTIONS` section that carries
an `audit_fields.id` (7 of 14 sections; the other 7 have no checklist
counterpart and are never suggested on).

- **The suggestion is a status question, not a "did the lead do it" question.**
  `suggested` is `True` whenever the section's state is in
  `READINESS_READY_STATES` (`visible_edited` or `visible_unattributed`) —
  i.e. whenever it is Visible, regardless of which evidence class produced
  that state. This applies identically to the 3 lead-owned fields
  (`welcome_outline`, `contacts_complete`, `assessment_brief`) and the 4
  institution-owned-but-mapped ones (`sga`, `student_voice`,
  `assessment_overview`, `encore_link`) — a deliberate decision, not an
  oversight: a batch-dated lead-owned section is frequently genuine
  Professional Services work rather than untouched (see "Module readiness"
  above), and institutional sections were never the lead's to edit in the
  first place. `evidence_text` (from `readiness_evidence_words()`) still
  names which case it is, so an advisor is never shown a bare tick with no
  reason — see `views/audit_portal.py`'s checkbox loop.
- **A suggestion never overwrites a saved answer.** `get_audit_responses()`'s
  value always wins when present; the suggestion only supplies the checkbox's
  default when the module has never been answered. Leaving a suggested box
  ticked and pressing Save Draft/Submit records it exactly like a manual tick
  — `audit_responses` still only ever gets a row when a human presses one of
  those buttons, with no schema change and no machine-written rows.
- **A module absent from the readiness data returns an empty dict from
  `readiness_prefill_for_module()`**, which the Audit Portal must read as "no
  suggestion, fall back to the ordinary blank-form default" — never as
  "suggest unticked". Do not conflate the two.
- `readiness_evidence_words()`, `fmt_report_date()` and
  `readiness_created_date()` live in `processing.py` (moved from
  `views/module_report.py`, pure string/date formatting, no I/O) precisely so
  the module report's Blackboard Template block and the Audit Portal's
  suggestion caption read from the same sentence for the same section and can
  never drift apart.
- `resolve_active_row(code, df_aut, df_spr)` in `processing.py` is the one
  place that picks Spring's row over Autumn's when a module runs in both -
  was duplicated identically in `views/audit_portal.py` and
  `views/module_report.py` before being centralised for `views/
  school_dashboard.py`'s spot-check flagging to reuse too.

## Spot-check flagging

Manual auditing does not scale past the handful of modules that get a real
audit each year. Rather than a system trying to decide what needs checking,
a DLA flags modules themselves from the School Dashboard's module list
(🎯 Flag for Spot-Check) - based on their own judgement (experience, spread
across levels, some deliberate randomness), not a stratified sample. An
earlier version of this feature *did* auto-sample and auto-assign; it was
rolled back specifically because that judgement belongs with the DLAs, not
an algorithm, and because most real DLA accounts are faculty-wide rather
than tied to one school (see `get_edit_checklist_users()` in the deleted
`dev/spot-check-sampling` branch, if it's ever worth revisiting why).

`spot_checks` (owned by this portal) tracks flags through to outcome —
`database.py`: `flag_module_for_spot_check()`, `get_spot_checks_for_user()`,
`get_school_spot_checks()`, `get_pending_spot_check()`,
`mark_spot_check_checked()`, `get_spot_check_agreement_summary()`,
`purge_spot_checks()`. The flagging action and the school's history table
live in `views/school_dashboard.py`'s new "🎯 Spot-Checks" view; the
snapshot/diff logic is I/O-free in `processing.py`
(`build_spot_check_snapshot()`, `compute_spot_check_agreement()`).

- **A flag has no separate recording UI.** Flagging a module just adds it to
  the flagger's normal Audit Portal queue (`views/audit_portal.py`'s "Your
  Spot-Checks" panel). Saving a real audit response for it — Save Draft or
  Submit, whichever comes first — is what closes it out:
  `compute_spot_check_agreement()` diffs what was actually ticked against
  `readiness_prefill_for_module()`'s suggestion as it was frozen into
  `data_verdict_snapshot` at the moment of flagging, not against whatever the
  data says by the time the advisor opens it. Only the flagger's own save
  closes their spot-check — a different person saving the same module leaves
  it pending, so the agreement rate stays a measure of the flagger's own
  judgement.
- **There is no `assigned_to` distinct from `flagged_by`.** The person who
  chooses a module is the person who checks it; nothing round-robins or
  auto-assigns.
- **A field the snapshot suggested but that is missing from what was saved**
  (e.g. the audit field has since been deactivated) is excluded from the
  agreement comparison entirely, not counted as disagreement - there is no
  signal to compare.
- `database.purge_spot_checks(academic_year)` drops one year - there is no
  `sample_round` to scope a purge to, unlike the abandoned sampled design.

## Conventions

- **School list**: use `FACULTY_SCHOOLS` from `processing.py`. There were once
  five hardcoded copies. Do not add a sixth.
- **`processing.py` is I/O-free** — pandas transformations only. SQL belongs in
  `database.py`, Sheets access in `data_manager.py`, ETL in `sync_data.py`.
- **Semester selection**: always go through `resolve_semester_df()`. "All year"
  used to mean different things on different pages. Year-long modules appear in
  *both* Autumn and Spring frames; "All year" narrows to just those.
- **Capability checks**: `any(c.lower() == "edit_checklist" for c in user_caps)`
  where `user_caps = st.session_state.get("capabilities", [])`. Capabilities are
  lowercase tokens: `view_all`, `view_school`, `edit_checklist`,
  `access_admin_panel`.
- **Cross-page navigation**: `st.switch_page(st.session_state.pg_module)` — page
  objects are stashed in session state in `app.py`. Do not set a session key and
  call `st.rerun()`; the old `view_selection` router was removed in v1.8 and
  buttons doing that silently did nothing for several releases.
- **`pg_audit` is only registered in the navigation for `edit_checklist`
  holders**, and `st.switch_page` raises on an unregistered page. Any button
  jumping there needs a `can_audit` guard, not just a permission check inside
  the destination.
- **Date formatting**: User-facing dates always display as `DD-MM-YYYY`
  (e.g., "06-08-2026") using `strftime('%d-%m-%Y')`. Internal storage and
  database columns use ISO format (`YYYY-MM-DD HH:MM:SS`) for sortability.
  Timestamps shown to users follow `DD-MM-YYYY HH:MM:SS` when time is included.

## Auth

`AUTH_PROVIDER` selects between Env / SQLite (default) / Active Directory /
Google OAuth. Passwords use scrypt via `security.py`; legacy SHA-256 digests
still verify and are re-hashed transparently on successful login.

Accounts that sign in with Google carry an **empty `PasswordHash`**. Those rows
are correct — deleting one revokes that person's access. An empty hash never
matches any input, so it is not a bypass.

The CookieManager is a Streamlit component and can only write a cookie on a run
where it actually renders. `check_password()` deliberately skips rendering it
once logged in, so any cookie write must happen on a run that falls through that
fast path. A queued write sitting below the early return will never execute —
that bug is why OAuth sessions did not survive a refresh.

## Docs and releases

User-facing documentation is markdown in `docs/`, rendered by `views/docs.py`.
Edit the markdown, not the Python.

- `docs/help.md`, `docs/changelog.md`, `docs/developer-guide.md`
- A release means: bump `__version__` in `app.py`, add an entry to
  `docs/changelog.md`, commit, tag `vX.Y.Z`.
- Paths in `views/docs.py` resolve from `__file__`, not the working directory —
  the container runs from `/app`.

## Verifying changes

There is **no test suite**. To check work:

```bash
python -m streamlit run app.py --server.port=8599 --server.headless=true
```

It boots without credentials and exercises every import and data loader against
the local database, which catches most breakage. Anything past the login screen
needs a real sign-in — ask the user rather than entering credentials.

`app.log` is the best evidence for auth and sync behaviour; it records logins,
cookie restores, syncs and audit submissions. `diagnostics/` holds ad-hoc
inspection scripts, not tests.
