# Digital Learning Review - working notes

Streamlit dashboard for the Faculty of Social Sciences VLE audit. Deployed by
Docker Compose on an Ubuntu VM behind Caddy.

This file records what is **not** obvious from reading the code. Everything else -
structure, past fixes, git history - read from the repo itself.

## Who does what

Audits are carried out by **Digital Learning Advisors on the module lead's
behalf**. Module leads do not fill in their own audits.

The Audit Portal used to have two free-text fields for this, `notes_to_lead`
("Notes for Module Lead") and `auditor_notes` ("🔒 Internal Notes", explicitly
not visible to leads). Both were dropped 19-08-2026 - `notes_to_lead` had no
reader anywhere in the app (dead data from the moment it was typed), and
`auditor_notes`'s only reader (`views/module_report.py`'s internal-notes panel)
was removed alongside it. Old rows for both keys are left in `audit_responses`
untouched, just no longer written or displayed. `active_fields`-driven `'text'`
type checklist fields are the current mechanism for free-text notes on an
audit, but they are not a drop-in replacement - see `INERT_TEXT_FIELD_IDS`
in "Unified module findings" below for the actionable/inert split that
replaces the old lead-visible/internal-only split.

Do not describe the audit as something leads complete. Older code and docs used
"Module Lead Checklist" for what is now the Audit Portal - that name was wrong
about who does the work, so do not reintroduce it.

## Data architecture

**SQLite is the source of truth.** `database.py` owns the schema and every
query. Google Sheets is an *upstream source only*, drained into SQLite by
running `sync_data.py` as a script. The Admin Panel's Trigger Full Sync button
was removed 17-09-2026 - Sheets sync is no longer part of normal operation, and
SITS in particular no longer comes from Sheets at all (see "SITS data" below).

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
insert genuinely new accounts - `sync_new_users_only()`. Anything that rebuilds
the table (`if_exists='replace'`) silently reverts role and status edits, and
would undo the scrypt password migration. Roles do sync wholesale; those are
genuinely sheet-managed.

## SITS data

`sits_assessment_2026_27` (one row per assessment component) is the module
list, module leads and periods every view is built from. It is loaded only by
the dedicated importer, `_render_sits_import()` in `views/admin_panel.py`, via
`processing.parse_sits_export()` / `diff_sits_modules()` and
`database.replace_sits_assessment()`. Added 17-09-2026, when Sheets sync was
retired and the lead data had gone stale since ~May 2026.

- **The satellite AI-Audit app reads this table directly** (same shared
  database) - its name and column names (`processing.SITS_COLUMNS`) are a
  contract with that app. Every column is stored as TEXT: read the CSV with
  `dtype=str, keep_default_na=False`. The generic CSV hub used type inference
  and turned MAB sequence `001` into `1`; SITS is blocked there now.
- **Always a full replace, in one transaction.** SITS has no key, so the
  generic hub's Merge mode appended a duplicate of every row. Rows are
  inserted with `executemany`, not `DataFrame.to_sql` (which commits on its
  own and would break the transaction).
- **Only `CURRENT_ACADEMIC_YEAR` is accepted**, and rows whose code prefix is
  not in `FACULTY_SCHOOLS` are dropped (FCS cross-faculty provision, and the
  SCS/POL codes that appeared in the 2026-27 export) - every view derives a
  school from the first three letters of the code, so those would belong to
  no school. A deliberate user decision; revisit alongside any prefix-to-school
  mapping work rather than quietly admitting them.
- **Hand-set module leads live in `module_lead_overrides`** and are applied
  *into* the SITS table after each import, so readers (including AI-Audit)
  never need a join. `update_module_lead_sqlite()` / `bulk_rename_module_lead()`
  (Module Manager) record an override; `revert_module_lead()` restores
  `sits_lead`. The importer's lead-change table decides the full override set
  per import: a ticked "Keep current" row keeps/creates the override (this is
  also how edits made before overrides existed get captured - rows start
  ticked when already overridden or when `lead_looks_hand_set()` sees
  lowercase (SITS writes names in capitals) or the SITS name with words
  removed (a dropped middle name typed in capitals, e.g. PAUL BRINDLEY for
  PAUL GAVIN BRINDLEY - SITS spacing is too inconsistent to detect this any
  other way); the first live import on
  17-09-2026 had 98 such pre-override hand edits, made days *after* the
  export's own data, which the user wanted kept), an unticked one
  clears it, and an override whose lead now matches SITS (ignoring case and
  whitespace) is cleared automatically. Overrides for modules absent from the
  file are left alone.
- **`sits_imports` logs every import** - the SITS table itself has no date, so
  this is the only answer to "when was SITS last imported", and feeds
  `get_last_import_dates()['sits']` in the sidebar.

## Ally accessibility data

`ally_courses` / `ally_issues` / `ally_content` (course grain - a Blackboard
course shell, not a SITS module) are the source of truth, populated by the
importer in the Admin Panel from Anthology's institutional report export.
`ally_scores` is a legacy projection rebuilt from `ally_courses` for views not
yet migrated; do not write to it directly. Multiple Blackboard shells can share
one module code (different cohorts) - aggregate to module grain on read via
`processing.aggregate_ally_to_modules()`, never at import time.

- **Only `CURRENT_ACADEMIC_YEAR` (`processing.py`) is ingested and shown.** A
  prior import silently stored a mislabeled prior-year snapshot that displayed
  against the current year's module list for months before anyone noticed. Do
  not backfill or surface other years without a deliberate decision to do so.
- **Content maturity has exactly two positive states: `Not yet built` and
  `In progress`.** There is deliberately no `Built`/`Complete` state -
  `classify_content_maturity()` in `processing.py` measures file counts (and,
  since 14-09-2026, score deficit - see below), and module leads build
  just-in-time throughout the course (often up to the final assessment), so
  neither signal can show a course has finished, only that it has started. A
  three-state version with a `Built` tier existed earlier and was removed on
  that reasoning; do not reintroduce it.
- **A template-sized file count no longer forces `Not yet built` on its own.**
  `classify_content_maturity()` also takes the module's `overall_score`/
  `files_score`/`wysiwyg_score`: an untouched rolled-over template scores
  100% on all three (nothing for Ally to flag), so any of them coming back
  below 1.0 is direct evidence someone edited the existing template files in
  place rather than adding new ones - file count alone can't see that. Added
  after EDC004 surfaced the gap: 93.7% overall with 4 real accessibility
  issues, but only a handful of files, so file count alone read it as
  `Not yet built` ("Not started" in the UI) and it silently dropped out of
  every average, ranking and leaderboard that gates on content maturity
  (`aggregate_faculty_stats()`, `ally_widgets.scoreable()`/`mean_score()`,
  the Faculty Overview/School Dashboard breakdowns) - the opposite of what
  the gate exists to do. `views/module_report.py`'s issue list was already
  unaffected by this (it only shows the "nothing to report yet" template
  caption when there are zero issues, real issues render regardless of
  maturity state); this fix is entirely on the aggregate/ranking side.
- **Ally's own scores are shown unmodified.** An earlier credibility-weighting
  model (shrinking scores toward a prior at low file counts) was removed - it
  distorted the majority of modules at typical file counts, only ever pushed
  scores down, and disagreed with the score module leads see in Blackboard
  itself. Content maturity gates which courses count toward averages/rankings
  instead of a score adjustment.
- `diagnostics/check_ally_export.py <csv> <academic_year>` sanity-checks a new
  export (scope, grain, score invariants, SITS reconciliation) before trusting
  an import - run it against any new Ally export.
- **The module report's Accessibility Issues panel shows category summaries
  by default, not the 38 individual `ALLY_CHECKS`.** Added 14-09-2026: the
  per-check list (one bordered card per check, e.g. "PDF is not tagged for
  reading order") is written the way a DLA audits, not the way a module lead
  experiences their own course, and a module with many distinct issue types
  could show 15-20 of them flat with no way to tell what mattered most. It
  also duplicated, badly, something Blackboard already does well: a lead's
  own Ally Course Report links every issue straight to its file, previews
  the problem, and often fixes it in place - a summary page can't compete
  with that and shouldn't try. `processing.summarise_ally_issue_categories()`
  rolls the per-check data up to the 7 groups in `ALLY_CATEGORIES`
  (`ALLY_CHECK_CATEGORY` maps each check to one) - what kind of thing is
  wrong (images, headings/structure, contrast, tables, titles/language,
  links/lists/media, or a file that doesn't open at all) and, once per
  category, *why* it matters to a screen-reader or keyboard user - no
  per-file detail, no fix instructions. `views/module_report.py`'s
  `_render_ally_how_to()` then points the lead at their own Ally Course
  Report for the specifics, deliberately without asserting an exact
  Blackboard menu path (varies by version/site, and a wrong click-by-click
  instruction would actively mislead someone following it) - only the Ally
  indicator icon and the course-level Accessibility Report, both stable
  regardless of version. The full per-check list (`summarise_ally_issues()`,
  unchanged) is still there for a DLA who wants it, just folded into a
  "Full technical detail" expander rather than leading the page. Every
  `ALLY_CHECKS` key must appear exactly once in `ALLY_CHECK_CATEGORY` - a
  new check added to one needs adding to the other, or it silently drops out
  of the category view (`prepare_ally_issues()` on the category path filters
  to `category.notna()`).

## Leganto reading-list data

There are **two separate, disjoint Leganto exports** - don't conflate them:

- `leganto_nolist` - modules confirmed to have **no** reading list at all.
  Surfaced everywhere as the `Leganto Missing` boolean. Imported through the
  generic CSV-to-table hub in the Admin Panel.
- `leganto_lists` - course-grain status/items for modules that **do** have a
  list (Draft vs Published, citation count). Source of truth for the
  `Leganto List Status` / `Leganto List Items` fields. Populated by the
  dedicated importer (`_render_leganto_import()` in `views/admin_panel.py`),
  via `processing.parse_leganto_lists_export()` and
  `database.save_leganto_snapshot()` - same shape as the Ally pipeline below.
  A module absent from *both* exports just gets blank status, not `Missing`.

Same aggregation rule as Ally: a module can have more than one course
occurrence, so roll up to module grain on read via
`processing.aggregate_leganto_to_modules()`, never at import time.

- **The export has no per-row academic year column.** Unlike Ally's `Term
  name`, the year is an explicit operator choice at import time
  (`_render_leganto_import()`'s year selector), not read from the file. The
  importer only warns when the tag looks inconsistent with the course names
  in the file - it never infers or enforces a year on its own.
- **`leganto_lists`'s primary key includes `academic_year`**
  (`course_code, snapshot_date, academic_year`), unlike `ally_courses`. Two
  different years can legitimately produce identical-looking rows for the
  same course on the same snapshot date - e.g. a reference import of a prior
  year's export ahead of the real current-year one - and without
  `academic_year` in the key those rows silently collide and overwrite each
  other. `save_leganto_snapshot()`'s change-detection (skip-if-unchanged)
  is likewise scoped per `academic_year`, not just per `course_code`, for the
  same reason. Preserve this if the table is ever touched again.
- `database.purge_leganto_lists(academic_year)` deletes one year's rows only -
  the way to drop a reference/test import once the real export for that
  year lands, without touching other years.

## Module readiness (template alignment) data

`readiness_courses` / `readiness_sections` hold the faculty **Template
Alignment Report** (called Template Adherence before 2026/27): per Blackboard
course, the visible/hidden/deleted/missing state of each required template
section and when each was last changed. Imported by `_render_readiness_import()`
in `views/admin_panel.py` via `processing.parse_readiness_export()` and
`database.save_readiness_snapshot()` - same pipeline shape as Ally.

- **Only 4 of the 14 sections carry any signal - `LEAD_OWNED_SECTIONS`,
  derived from the `TEMPLATE_SECTIONS` catalogue.** The other ten ship
  *visible* and are institutional boilerplate nobody is expected to edit, so
  `Visible` on those means nothing. `WELCOME_MODULE_OUTLINE`,
  `KEY_STAFF_CONTACTS` and `ASSESSMENT_DETAIL` ship *hidden* and must be
  unhidden by the module lead - `SECTIONS_SHIP_HIDDEN`, a fixed empirical
  fact about the template rollout, separate from `LEAD_OWNED_SECTIONS`
  itself. `HOW_YOUR_FEEDBACK_SHAPES` (see the "Unified module findings"
  entry below) is the fourth lead-owned section and the one exception: it
  ships *visible* like the institutional ten, but still needs someone to
  actually author its content, so `readiness_section_is_ready()` still
  requires edit evidence for it even though it never needs unhiding. Triage
  on `LEAD_OWNED_SECTIONS`; the vendor's `COMPLETENESS_SCORE_PERCENT` /
  `Alignment_STATUS` are stored and shown verbatim for continuity with the
  faculty report but restate the visible-section count - 43 of the 45
  courses in the first excerpt sat on exactly 78.6% / "Needs Review", the
  untouched post-rollover default.
- **Status and edit evidence are separate questions, and both are needed.**
  Status says whether a student can see the section; evidence says whether
  *anyone* edited it. `classify_section_state()` combines them into the
  `SECTION_STATES` model - `edited = evidence in ('lead_edit', 'bulk')`,
  applied the same way to both Visible and Hidden:
  - `drafted_hidden` - edited, and *still hidden*. 359 sections across 202
    modules in the 2026-27 export. The work exists and no student can see it, so
    the remedy is one click. A status-only reading calls this "not started",
    which is both wrong and insulting to whoever did the work.
  - `visible_unedited` - visible, but nothing on record shows it was ever
    edited (evidence is `never_modified` or `unknown`). **Not** counted as
    ready for a lead-owned section, even though students can technically see
    it - the section may still hold template placeholder text (or, for
    `HOW_YOUR_FEEDBACK_SHAPES`, an unwritten document). For the three
    sections in `SECTIONS_SHIP_HIDDEN`, this state was 0 sections in the
    2026-27 export - but if a template revision ever ships those three
    visible by default, this becomes the mass default and every module reads
    "ready" on them with no work done. Two checks in
    `diagnostics/check_readiness_export.py`, scoped to `SECTIONS_SHIP_HIDDEN`
    specifically (not the wider `LEAD_OWNED_SECTIONS`), guard that: the
    visible-and-unedited share alarm, and the most-hidden-sections drift
    check. `HOW_YOUR_FEEDBACK_SHAPES` is deliberately excluded from both - it
    ships visible by design (see above), so reading `visible_unedited` there
    on an untouched module is normal, not drift.
  Changed 08-09-2026, twice in one day. The question used to be "does the
  data attribute this to the lead" (`visible_edited` vs one combined
  `visible_unattributed` covering both bulk and never-edited alike). DLAs
  found that misleading: a section with zero edit evidence read identically -
  same green badge, same pre-ticked checklist box - to one a lead had
  genuinely finished. The fix that followed first re-split `bulk` out on its
  own with a footer naming Professional Services as the likely editor, which
  DLAs also rejected - a bulk date (many courses changed the same day) can't
  actually distinguish PS running a worklist from several leads independently
  hitting the same faculty deadline, so naming a specific, possibly wrong,
  culprit was worse than not naming one, and it was needlessly long besides.
  The question that stuck is simpler than either attempt: **edited at all, or
  not** - `lead_edit` and `bulk` are now treated identically everywhere a
  human reads them (badge, tooltip, ready/not-ready), full stop.
  `classify_edit_evidence()` still tracks the lead_edit/bulk split
  internally, for `detect_bulk_edit_dates()` and diagnostics - it's just not
  read by `classify_section_state()` or narrated in the UI any more.
  Fixing this also caught a real bug: because only `lead_edit` used to count
  as "edited" for Hidden sections, a bulk-edited-but-still-hidden section
  read `not_started` ("no sign of being edited") while its own footer said
  "Last changed \<date>..." - a literal contradiction on one card. That's
  exactly why `drafted_hidden`'s count jumped from 34/25 to 359/202 sections/
  modules: every bulk-hidden section was being told "not started" when it had
  genuinely been worked on, just not made visible.
- **`TEMPLATE_SECTIONS` maps each section to the `audit_fields.id` it answers.**
  For a mapped field this is no longer a suggestion sitting beside a separate
  checklist score: since 14-09-2026 (see "Unified module findings" below) the
  mapped section *is* that field's only outstanding-item finding - the
  checklist question itself no longer generates one of its own. Keep the
  mapping in step with `audit_fields`.
- **Sections are discovered from the column names**, not a fixed list - any
  column ending `_STATUS` other than `Alignment_STATUS`, paired with its
  `_LAST_MODIFIED` sibling. The template is versioned and changes between years,
  so a revised template imports without a code change; only the catalogue needs
  a new label. `readiness_sections` is long for the same reason.
- **A last-modified date is not evidence of *lead* activity on its own - and a
  shared batch date is usually not IT either.** Aside from the original
  template rollout, IT does not push bulk content edits. What actually
  produces a date shared across many of a school's courses is most often
  Professional Services (PS) / school admin staff working through a batch of
  modules editing a specific section (commonly Key Staff Contacts) on the
  lead's behalf - genuine content work, just not done by the lead, and which
  section(s) get PS-edited this way varies by school. The export gives only a
  date, no time or editor, so a real IT rollout and a PS team clearing a
  worklist in one afternoon are indistinguishable in the data.
  `detect_bulk_edit_dates()` flags a (school, date) on *either*
  `READINESS_BULK_EDIT_SHARE` of the school **or** `READINESS_BULK_EDIT_MIN_MODULES`
  modules outright, and `classify_edit_evidence()` reduces those to *no
  positive evidence of lead activity* - never evidence the section itself is
  unfinished. Both tests are needed: share alone is scale-dependent, and the
  faculty-wide export proved it - the ALA batch of 23/07 touched 25 modules,
  which is 56% of the 45-module excerpt the rule was first calibrated on but
  only 18% of the real 142-module school. Adding the floor moved 131 lead-section
  observations out of `lead_edit`. Over-flagging is the safe error here, since a
  batch hit only ever withholds *lead* evidence, not readiness. Re-run
  `diagnostics/check_readiness_export.py` on each new export - it prints the
  distribution, what was flagged, and the closest cases that were not.
  **Resolved for Phase 4** (`processing.readiness_prefill_for_module()`): the
  Audit Portal checklist question is "is this section done", not "did the
  lead do it personally", so a `bulk`-evidenced Visible section is suggested
  ticked exactly like a `lead_edit`-evidenced one - see "Audit Portal
  pre-fill" below. This is a different question from *lead-engagement*
  evidence, which `classify_edit_evidence()` still tracks separately and
  unchanged. It is also a different question from *edited at all* - a
  Visible section with no date evidence whatsoever (`visible_unedited`) is
  not suggested ticked; see the `visible_unedited` bullet above.
- **Both primary keys include `academic_year`** (`leganto_lists`'s reasoning,
  not `ally_courses`'s) so a reference import of a prior year cannot collide
  with the real one on a shared snapshot date.
  `database.purge_readiness(academic_year)` drops one year, parent and child.
- Same aggregation rule as Ally and Leganto: multiple shells per module, so roll
  up on read via `processing.aggregate_readiness_to_modules()`, never at import
  time. Section status combines worst-wins via `READINESS_SECTION_RANK`.
- The readiness tables are **blocked from the generic CSV import hub**, like the
  Ally tables - the export needs melting and date conversion. Export still works.
- `diagnostics/check_readiness_export.py <csv> <academic_year>` sanity-checks a
  new export before trusting an import. It cross-checks the export's own
  `HIDDEN_SECTIONS` / `DELETED_SECTIONS` summary text against its per-section
  columns, re-asserts the 11/3 split, and prints the date distribution behind
  `READINESS_BULK_EDIT_SHARE`. Run it against any new export.

## Unified module findings

`processing.derive_module_findings(active_row, responses, active_fields)` is
the **only** place that decides what a module has outstanding. Every source -
checklist fields, Leganto, Ally, template readiness - is classified there,
tagged `source` and `state` (`'pending'`/`'completed'`). Two consumers read
from it:

- `app.py::load_checklist_data()` sums every pending finding into
  `Actionable Items`, the badge on School Dashboard / Faculty Overview.
- `views/module_report.py::view_module_report()` filters the same list -
  `source in ('checklist', 'leganto')` builds the generic worklist cards;
  a widened checklist-count (`source == 'checklist'`, plus a `'readiness'`
  finding for one of `INSTITUTION_MAPPED_FIELD_IDS` - see below) drives the
  health banner's "N checklist items outstanding" wording, so it doesn't
  double-narrate against Ally/Leganto/lead-owned-readiness's own dedicated
  bullets, which read `active_row`/`ally_profile` directly and are
  unaffected by this.

**Why this exists**: before it, the badge and the module report page each
computed "what's outstanding" independently and disagreed. Concretely, the
badge never counted a Leganto list stuck in Draft, never counted template
readiness at all, and undercounted legacy free-text custom observations the
module report page showed as cards - so a module could show 9 outstanding
items on its own page and 0 on the dashboard that's meant to prioritise
across the school. Do not reintroduce a second, hand-written "count what's
pending" anywhere; add a new source to `derive_module_findings()` instead.

**A checklist boolean field that maps to a Template Alignment section
(`field_id` in `SECTION_KEY_BY_AUDIT_FIELD`) produces no `'checklist'`
finding of its own - only a `'readiness'` one.** Before 14-09-2026, both
loops ran for a mapped field: a `'checklist'` finding built purely from
`responses.get(fid)` (pending until literally ticked, with no data-
awareness), and - for the 3 lead-owned fields only - a separate
`'readiness'` finding using `readiness_manual_override()`. Because both read
the same underlying answer, an unanswered-and-not-yet-ready or a manually
recorded-incomplete mapped field produced *two* pending findings for one
real gap, inflating `Actionable Items` by exactly that duplicate; an
unanswered-but-data-ready field produced one of each state instead, showing
the module report's To Do list and Blackboard Template card visibly
disagreeing about the same section on screen (the bug that prompted this
fix). The 4 institution-owned mapped fields (`sga`, `student_voice`,
`assessment_overview`, `encore_link`) had it worse: with no readiness
counterpart outside `deleted`/`missing` states, their checklist finding was
the *only* signal, and it never reflected the readiness data at all for
`Visible`/`Hidden` states - same contradiction, no duplicate-count symptom
to notice it by. The readiness loop is now generalised to run for *any*
section with a non-`None` `audit_field_id`, not just lead-owned ones -
`readiness_manual_override()` first, `readiness_section_is_ready()`
otherwise (see "Module readiness" above) - and is the single source of
truth for that field's pending/completed state *and* its wording:
label/description come from `SECTION_STATES`'s badge/action text, the same
words `_render_section_card()` already shows, not the checklist field's own
`label`/`action_label`. `learning_materials`, the one boolean checklist
field with no `TEMPLATE_SECTIONS` counterpart, is unaffected and keeps its
ordinary `'checklist'` finding. Because the merged finding's `source` is
`'readiness'`, it drops out of `view_module_report()`'s generic
`pending_items` worklist (`source in ('checklist', 'leganto')`) entirely -
a mapped field's status now lives solely in the Blackboard Template card.
`INSTITUTION_MAPPED_FIELD_IDS` (`processing.py`) widens the health banner's
checklist bullet to still count a `'readiness'` pending finding for one of
those institution-owned fields, so a DLA manually marking one incomplete
still surfaces there exactly as it did when that was a `'checklist'`
finding - the lead-owned fields already have their own "Lead Sections
Outstanding" bullet, unaffected by any of this. (Counts as of 14-09-2026:
4 institution-owned mapped fields, 3 lead-owned - see the 15-09-2026 note
below for why that split is no longer current.)

**`view_module_report()`'s Module Checks and Readiness tab is two columns,
not one stacked page: Blackboard Template cards on the left (~3/4 width),
a single consolidated "Actions" panel on the right (~1/4 width).** Settled
14-09-2026 after two narrower fixes on the same module (EDC003) both proved
insufficient. The generic worklist used to render checklist/Leganto findings
as individually bordered cards in the same column as the Blackboard Template
block, stacked below it; once mapped-field findings moved to `'readiness'`
(see above), a module whose only gaps were mapped fields showed a plain
"✅ Nothing outstanding right now" success tick directly under red "Manually
verified incomplete" cards - the exact contradiction this whole redesign
exists to prevent, just with the colours swapped. Naming the outstanding
sections in an `st.warning()` instead of a bare count fixed the colour
mismatch but not the layout: a DLA still had to scroll back up and hunt
through a tree of up to 14 sections to find them, and checklist/Leganto
items still rendered in a visually different style (bordered cards) from
template-mapped ones (a warning banner) for what is, to a module lead,
the exact same kind of question - "what do I need to do". The fix: `actions`
(`view_module_report()`) became every `state == 'pending'` finding across
*all* sources except `'ally'` (which had its own tab) - checklist, Leganto
and `'readiness'` findings together, unfiltered by source for the first time
- rendered by `_render_actions_panel()` as one bullet list inside a single
amber panel, same style regardless of which source produced the item. The
`'ally'` exception didn't survive the next day - see the entry below on why
Ally findings render here too as of 15-09-2026. The richly-detailed
Blackboard Template cards are still not duplicated in this panel; everything
else that used to have its own card style now has exactly one.

**A `'readiness'` finding's `label`/`description` must say the same thing as
the Blackboard Template card's own badge/action text whenever a manual
override applies, not the raw data state.** Missed in the original merge
(14-09-2026), caught the same day: `derive_module_findings()`'s readiness
loop computed `badge`/`action` from `SECTION_STATES` unconditionally, then
only used `readiness_manual_override()` to decide `state` (pending/
completed) - so a manually-recorded-incomplete section showed "Manually
verified incomplete" on its Blackboard Template card (`_render_section_card()`,
`views/module_report.py`, which has its own equivalent override block) but
"Visible, unedited - may still hold placeholder text" in the Actions panel -
two different explanations for one fact, sitting side by side in the two-
column layout above. Fixed by having the readiness loop overwrite `badge`/
`action` with the identical "Manually verified complete/incomplete" /
"A Digital Learning Advisor has recorded this as complete/not yet complete
in the audit." wording `_render_section_card()` uses, whenever `manual is
not None`. The two call sites duplicate this text rather than sharing a
helper - if this drifts again, factor it into one function both read from.

**`HOW_YOUR_FEEDBACK_SHAPES` (the `student_voice` mapped field) moved from
institution-owned to lead-owned on 15-09-2026.** It had been grouped with
`sga`/`assessment_overview`/`encore_link` as content nobody but the
institution touches, but unlike those three it's a document someone
genuinely has to go in and author - how *this module's* student feedback
shaped it - not fixed boilerplate. `TEMPLATE_SECTIONS['HOW_YOUR_FEEDBACK_SHAPES']`'s
owner is now `'lead'`. This changes, all via the existing owner-driven logic
(no new special-casing needed):
- `readiness_section_is_ready()` now requires edit evidence for it, not just
  Visible - `visible_unedited` no longer counts as ready for this field.
- `views/module_report.py::_render_section_card()` no longer collapses its
  Blackboard Template card to the generic institution copy - it shows the
  full `SECTION_STATES` badge, action text and last-edited date, the same as
  the other lead-owned sections.
- `readiness_prefill_for_module()`'s Audit Portal suggestion for
  `student_voice` now also requires edited evidence, not Visible alone.
- `INSTITUTION_MAPPED_FIELD_IDS` no longer includes it - a manually-recorded
  verdict on it now surfaces via the "Lead Sections Outstanding" banner
  bullet instead of the checklist-items-outstanding one.
- `LEAD_OWNED_SECTIONS` (4 sections) and `SECTIONS_SHIP_HIDDEN` (3 sections -
  `WELCOME_MODULE_OUTLINE`, `KEY_STAFF_CONTACTS`, `ASSESSMENT_DETAIL`) are
  no longer the same set. `LEAD_OWNED_SECTIONS` is about who is responsible
  for the content; `SECTIONS_SHIP_HIDDEN` is the fixed, separate fact about
  which of those the template ships hidden by default and therefore need an
  unhide action on top of the edit. `HOW_YOUR_FEEDBACK_SHAPES` ships
  *visible*, like the institution sections, so it is the one lead-owned
  section that never needs unhiding - only writing.
  `diagnostics/check_readiness_export.py`'s hidden-by-default drift check
  and its visible-and-unedited share alarm are both scoped to
  `SECTIONS_SHIP_HIDDEN` specifically, not `LEAD_OWNED_SECTIONS`, so they
  don't false-alarm on `HOW_YOUR_FEEDBACK_SHAPES` reading
  `visible_unedited` on every untouched module - that's its normal resting
  state, not template drift. If `TEMPLATE_SECTIONS` is ever restructured
  again, keep these two constants intentionally distinct rather than
  re-merging them.

**A recorded `reading_list` answer overrides Leganto as well as the
template data.** Added 23-09-2026 when `reading_list` was linked to
`MODULE_READING_LIST`. The tick means "the reading list is published (or
not needed) and the section is visible to students". Leganto is exported
rarely and often lags Blackboard, so once a DLA has answered,
`derive_module_findings()` emits no `'leganto'` finding for that module at
all: the `'readiness'` finding carries the verdict, and emitting both would
either contradict it (ticked) or count one gap twice (unticked).
`view_module_report()` likewise drops the health banner's Leganto bullet
when there is an answer. Without an answer, the two data checks stay
separate: the readiness finding reads section visibility only, and the
Leganto finding reads Leganto only. The Audit Portal suggestion
(`readiness_prefill_for_module()`) and the Template Alignment tab
(`calculate_dynamic_compliance_gap()`) gate on both, via
`leganto_blocks_reading_list()`: Missing, Draft or Mixed blocks the tick. A
blank status (module in neither Leganto export) does not block, matching the
Leganto finding's own "OK / Connected" reading. "Not needed" has no Leganto
signal; it is the DLA's call, recorded by ticking. Leganto columns shown
elsewhere (dashboards, the Leganto importer) still report the raw data.

**`INERT_TEXT_FIELD_IDS` opts specific `'text'`-type audit fields out of
finding generation entirely** - their value is saved and shown in the Audit
Portal like any other field, but never becomes a checklist finding, so it
never shows as an Outstanding card and never counts toward `Actionable
Items`. Added 19-08-2026 when `notes_to_lead`/`auditor_notes` were dropped in
favour of ordinary `'text'` audit fields (see "Who does what" above): by
default a `'text'` field is actionable (counted, like every other checklist
field), which is right for a field meant to flag something that should stay
open until resolved, but wrong for `comments` ("Additional Comments"), a
catch-all note box that would otherwise turn any unrelated remark into a
permanent open action item. `comments` carries years of legacy tag/custom-
observation JSON from before the Audit Portal dropped the tag-picker UI for
`'text'` fields (5 modules' worth as of 19-08-2026) - that data still
round-trips through `parse_custom_observations()` if this field is ever made
actionable again, it's just not read into findings while inert. Decide new
`'text'` fields' membership deliberately; don't default new ones into this
set without reason.

**`NOTE_OVERRIDE_FIELDS` (a `'text'` field vetoing a `boolean` field's
tick) was added 19-08-2026 and removed 11-09-2026, unused.** It was built
for `learning_materials`/`lm_note` - an auditor ticking `learning_materials`
but still writing a problem into `lm_note` would keep the module `'pending'`
regardless of the checkbox - but the `lm_note` field it depended on was
never actually created in `audit_fields`, so the mechanism had no way to
ever receive data. Decided not worth building out (the two-tick-meanings
problem it was solving for `learning_materials` isn't being addressed this
way). If a similar veto is wanted for some field in future, the pattern is
straightforward to reintroduce - see git history around this date.

**Ally and readiness findings both render generically now, alongside their
own richer displays.** Originally (this paragraph, pre-14-09-2026)
`view_module_report()` excluded both sources from the generic
pending/completed card list, on the reasoning that each already had its own
richer display (the accessibility card, the Blackboard Template block) and
didn't need a second, plainer rendering. Readiness was pulled back in on
14-09-2026 for the two-column Actions panel (see the "Module Checks and
Readiness tab" entry above) - a manually-recorded-incomplete mapped field
needed to show as an action, not just on its Blackboard Template card.
`source != 'ally'` was left in the Actions filter at the time, on the same
"has its own tab" reasoning.

That carve-out turned out to be the exact badge-vs-page disagreement this
whole findings system exists to prevent, just for Ally instead of readiness:
`Actionable Items` on School Dashboard already counted a severe Ally issue
or a disabled Ally scan as pending (`derive_module_findings()`'s `'ally'`
block always produced them), but the module report's own Actions panel never
showed them - a DLA could see the badge but nothing telling them what it
was counting. Fixed 15-09-2026: `source != 'ally'` dropped from the
`actions` filter in `view_module_report()`, so Ally findings render in the
Actions panel exactly like every other source, still alongside (not
instead of) the Accessibility tab's own richer display.

Caught the same day, before this had been used on a real module for long:
the severe-issue finding only ever fired on `Ally Severe > 0`, but the
health banner above it (`_render_health_banner()`) has always shown a
"N major accessibility issue types" bullet too, from the same `ally_profile`
data, independent of `derive_module_findings()`. A module with major-only
issues and zero severe ones (real example: 7 major issue types, 40 items)
showed that banner line but produced no `'ally'` finding at all - the exact
same badge-vs-page disagreement, one severity tier further down, on day one
of the fix meant to remove it. The trigger is now `Ally Severe > 0 or
Ally Major > 0`, matching the banner's own two severity bullets exactly
(minor issues alone still aren't a finding, same as the banner). `Ally
Major` was added to `app.py`'s `module_row()` alongside `Ally Severe` for
this. The finding's wording also now quotes the module's actual Ally score
(`row.get('Ally Overall')`, threaded through `module_row()` the same way)
and points at both this page's own Accessibility Report tab and the
module's own Ally Course Report in Blackboard, the same pairing
`_render_ally_how_to()` already used.

The label was briefly severity-specific ("Severe accessibility issue found
by Ally" / "Major accessibility issue found by Ally") and was flattened to
one generic "Accessibility issues found by Ally" the same day, before this
had reached real users - a severity word in the title sitting next to a
high overall score (most major-only modules still score in the 90s, e.g.
94.9%) read as overstating the problem. The description still explains
what to do regardless of which tier triggered it.

**A never-audited module's checklist fields do not count toward
`Actionable Items`** until the module has at least one row in
`audit_responses` - `load_checklist_data()` calls
`derive_module_findings(row, {}, active_fields=[], comment_bank)` (empty
`active_fields`) for modules with no audit trail, so only Leganto/Ally/
readiness findings reach the badge for them. This preserves the badge's prior
behaviour deliberately: ~1,560 of ~1,570 modules have never been audited, and
counting all 8 checklist fields as pending for every one of them would swamp
the badge with a constant rather than a differentiated signal. The module
report page still shows all 8 as pending cards for an unaudited module - that
asymmetry (quiet badge, full worklist once you open the module) is
deliberate, not a bug to fix by making them agree.

**`has_audit` needs a real auditor, not just a dict entry.** Because
`checklist_sums` now holds an entry for any module with a data-only pending
finding, `selected_code in checklist_sums` no longer means "a person has
audited this". Data-only entries are stamped `'Auditor': 'System'`; check
`sum_entry.get('Auditor') not in (None, '', 'System')` instead - see
`view_module_report()`.

`parse_custom_observations()` lives in `processing.py`, not `database.py` - it
is pure string/JSON parsing with no I/O. `database.py` imports and re-exports
it so nothing importing it from there breaks.

## Audit Portal pre-fill

`processing.readiness_prefill_for_module(active_row)` turns a module's
template-readiness section states into checklist suggestions for the Audit
Portal: `{audit_field_id: {'suggested': bool, 'evidence_text': str,
'section_key': str}}`, one entry per `TEMPLATE_SECTIONS` section that carries
an `audit_fields.id` (8 of 14 sections since `reading_list` was linked to
`MODULE_READING_LIST` on 23-09-2026; the other 6 have no checklist
counterpart and are never suggested on).

- **The suggestion comes from `processing.readiness_section_is_ready(section_key,
  state)`, not a bare `state in READINESS_READY_STATES` check** - the two
  differ by section ownership, and the difference matters. For the
  lead-owned fields (`welcome_outline`, `contacts_complete`,
  `assessment_brief`, and - since 15-09-2026 - `student_voice`),
  `suggested` requires Visible **and** edited (`state == 'visible_edited'`) -
  a Visible section with no edit evidence at all (`visible_unedited`) is
  not suggested. For the institution-owned-but-mapped fields (`sga`,
  `assessment_overview`, `reading_list`, `encore_link`), Visible is enough on its own,
  `visible_unedited` included - those sections were never the lead's to
  edit, so sitting untouched since course creation is their normal, correct
  state. `evidence_text` (from `readiness_evidence_words()`) still gives the
  date either way, so an advisor is never shown a bare tick with no reason -
  see `views/audit_portal.py`'s checkbox loop.
  Changed 08/09-09-2026, then 15-09-2026. First, `suggested` was a bare
  visibility question (any Visible state); DLAs flagged that as misleading,
  since a template-default section nobody had touched looked identical to
  genuinely finished work - same green badge, same pre-ticked box (see the
  `visible_unedited` bullet under "Module readiness" above). The fix that
  followed made `suggested` require edited-too, applied uniformly to all 7
  mapped fields - which silently broke the (then) 4 institutional ones:
  since nobody is expected to edit them, most modules' sections there are
  genuinely `visible_unedited` (490–628 of 904 modules per field in the
  2026-27 export), and the uniform rule would have suggested nearly all of
  them unticked. Caught before it shipped. `readiness_section_is_ready()`
  is the fix - same edited requirement for lead-owned fields, Visible-alone
  for institutional ones - and both `readiness_prefill_for_module()` and
  `calculate_dynamic_compliance_gap()` now call it instead of testing
  `READINESS_READY_STATES` directly, so they can't diverge on this again.
  `student_voice` moved from the institutional group to the lead-owned one
  on 15-09-2026 - see the dated note under "Unified module findings" above -
  so it now requires the same edited evidence `welcome_outline`/
  `contacts_complete`/`assessment_brief` always have.
- **A suggestion never overwrites a saved answer.** `get_audit_responses()`'s
  value always wins when present; the suggestion only supplies the checkbox's
  default when the module has never been answered. Leaving a suggested box
  ticked and pressing Save Draft/Submit records it exactly like a manual tick -
  `audit_responses` still only ever gets a row when a human presses one of
  those buttons, with no schema change and no machine-written rows.
- **A module absent from the readiness data returns an empty dict from
  `readiness_prefill_for_module()`**, which the Audit Portal must read as "no
  suggestion, fall back to the ordinary blank-form default" - never as
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
- **`processing.calculate_dynamic_compliance_gap()`** (the "Template
  Alignment" tab on both Faculty Overview and School Dashboard - renamed
  from "Compliance Gap"/"Checklist Completion" on 07-09-2026 to name what
  it's actually measuring: how well modules follow the template that gives
  students a consistent, accessible experience, not a punitive checklist)
  is the second consumer of `readiness_section_is_ready()`'s same
  ready/not-ready read, at school-wide scale rather than one module at a
  time. Manual auditing only ever covers a handful of modules a year - the
  data is meant to do the bulk of the compliance checking automatically,
  with manual spot-checks as a sample-and-anomaly check on top, not the
  primary source (see "Spot-check flagging" below). Before 07-09-2026 this
  metric counted only literal `audit_responses` rows, so an unaudited
  module was always counted as a gap for all 8 boolean fields even when the
  Template Alignment Report already showed most of its sections Visible -
  understating whole-school compliance by orders of magnitude for the 7
  fields `TEMPLATE_SECTIONS` maps (all but `learning_materials`, which has
  no template counterpart and stays manual-only). It now uses
  `readiness_manual_override()` per module/field - the same "a real answer
  always wins over the data" rule `derive_module_findings()` already
  applies - so this metric can never disagree with what an advisor has
  actually verified.

## Spot-check flagging

Manual auditing does not scale past the handful of modules that get a real
audit each year. Rather than a system trying to decide what needs checking,
a DLA flags modules themselves from the School Dashboard's module list -
select one or more rows and use 🎯 Flag for Spot-Check - based on their own
judgement (experience, spread across levels, some deliberate randomness),
not a stratified sample. An earlier version of this feature *did*
auto-sample and auto-assign; it was rolled back specifically because that
judgement belongs with the DLAs, not an algorithm (see
`get_edit_checklist_users()` in the deleted `dev/spot-check-sampling`
branch, if it's ever worth revisiting why). Note that branch's premise -
that `users.School='All'` meant most DLAs had no real school alignment -
was itself wrong: in reality DLAs are aligned with one or more specific
schools but are provisioned faculty-wide *access* for practical reasons: see
the corrected project memory on this. The schema has no field for a DLA's
actual school alignment(s) today.

`spot_checks` (owned by this portal) tracks flags through to outcome -
`database.py`: `flag_module_for_spot_check()`, `get_spot_checks_for_schools()`,
`get_school_spot_checks()`, `get_pending_spot_check()`,
`mark_spot_check_checked()`, `get_spot_check_agreement_summary()`,
`purge_spot_checks()`. Agreement is still computed and stored on every
checked row, but since 22-09-2026 it is not shown anywhere in the UI (the
Spot-Checks table's Agreement column and the "Agreement to date" caption were
removed): it means little to schools or module leads.
`get_spot_check_agreement_summary()` is kept but currently has no caller.
The flagging action and the school's history table
live in `views/school_dashboard.py`'s new "🎯 Spot-Checks" view; the
snapshot/diff logic is I/O-free in `processing.py`
(`build_spot_check_snapshot()`, `compute_spot_check_agreement()`).

- **A flag belongs to the school it was raised in, not to the DLA who raised
  it.** Changed 19-08-2026: any DLA currently working that school - their
  own, or one they've deliberately switched context into to cover a
  colleague, see "School context locking" below - sees it in their Audit
  Portal queue and can close it out, not only the original flagger. A flag
  has no separate recording UI; opening one from the queue and saving a real
  audit response for it - Save Draft or Submit, whichever comes first - is
  what closes it out. `compute_spot_check_agreement()` diffs what was
  actually ticked against `readiness_prefill_for_module()`'s suggestion as it
  was frozen into `data_verdict_snapshot` at the moment of flagging, not
  against whatever the data says by the time it's opened - that part is
  unchanged. `checked_by` (added alongside this change) records who actually
  closed it, separately from `flagged_by`, since the two are now routinely
  different people. This reverses the pre-19-08-2026 design, where only the
  flagger's own save could close their spot-check specifically so the
  agreement rate measured the flagger's own judgement; that guarantee is
  gone - the rate now reflects whoever ends up completing the module, which
  was the deliberate trade-off for making cover-for-a-colleague workable. The
  underlying human-judgement principle this feature was built on (see
  [[feedback_prefer-human-judgment-over-automation]]) is unaffected: a person
  still chooses which modules get spot-checked, nothing auto-samples.
- **Submitting an audit for a module nobody flagged records it as a checked
  spot-check** (`database.record_unflagged_spot_check()`, added 22-09-2026).
  Before this, an unprompted audit left the School Dashboard's Spot-Check
  column blank, so the module read as never audited. The auditor is both
  `flagged_by` and `checked_by`, the snapshot is built at submit time (the
  same data the form just suggested), and agreement is computed the same
  way. Submit only, not Save Draft, and only when the module has no
  `spot_checks` row at all this year, checked in the INSERT itself, so
  "Update Audit" never adds duplicates. A pending flag still closes through
  `mark_spot_check_checked()` as before, on either button. These rows count
  toward the agreement rate like any other checked row.
  `scripts/backfill_unflagged_spot_checks.py` (dry run unless `--apply`) adds
  the same rows for audits submitted before this existed. Those get 0/0
  agreement ("n/a") rather than a measured one: what the DLA was shown at the
  time is gone, and comparing against today's data would count later edits by
  a lead as the DLA disagreeing.
- **There is still no `assigned_to` distinct from `flagged_by`.** Any DLA
  working the school can pick up a flag from the shared queue; nothing
  round-robins or auto-assigns a specific person to a specific flag.
- **A field the snapshot suggested but that is missing from what was saved**
  (e.g. the audit field has since been deactivated) is excluded from the
  agreement comparison entirely, not counted as disagreement - there is no
  signal to compare.
- `database.purge_spot_checks(academic_year)` drops one year - there is no
  `sample_round` to scope a purge to, unlike the abandoned sampled design.
- **The free-text comment on a spot-checked module is read through
  `database.get_spot_check_comments()`**, which joins `spot_checks` to each
  module's *current* `audit_responses` row for the `comments` field. Both
  School Dashboard views that show it read that one query - the "🎯
  Spot-Checks" table's comment column and the "💬 Spot-Check Comments" view
  beside it - so the two can't show different text for the same module, and
  neither reads the whole of `audit_responses` to find it. The comment is
  whatever the audit says now, not a snapshot taken when the flag was closed;
  `audit_response_history` is the trail if an earlier wording is needed.
  `views/school_dashboard.py`'s `comment_field_label()` takes the heading from
  `audit_fields` rather than hardcoding "Additional Comments", and
  `format_comment_markdown()` turns a stored value into display markdown:
  single newlines become line breaks, and the legacy observation/action JSON
  a handful of modules still carry (see `INERT_TEXT_FIELD_IDS` under "Unified
  module findings") is unpacked into labelled lines instead of being shown
  raw. A module re-flagged later in the same year has one row per flag; the
  comments view collapses those to one card per module, keeping the most
  recent flag, since there is only ever one comment to read.
- **`database.delete_spot_check(id)`** removes one row outright - reachable
  from the "🎯 Spot-Checks" view's Remove Flag action, behind a confirm
  checkbox since deleting a `checked` row also deletes its agreement result.
  Deliberately a hard delete rather than a separate "reset to pending"
  mutation: resetting a checked module for a clean re-run is delete, then
  re-flag from "📋 All Modules" - one function covers both removing a
  mis-flagged module and resetting a checked one.

## Conventions

- **Caching**: `load_audit_data()`, `load_checklist_data()` and
  `load_assessment_data()` in `app.py` are `@st.cache_data(ttl=300)`. The ttl
  is a safety net for an external change (e.g. a sibling app writing to the
  shared database), not the primary invalidation mechanism - every real write
  path (Admin Panel imports/edits/purges, Audit Portal saves, spot-check
  flagging) already calls `st.cache_data.clear()` the moment it writes, so
  raising the ttl costs nothing in freshness. It was `ttl=10` until 12 August
  2026, which meant almost every click more than a few seconds apart paid the
  full reload cost (several queries plus Ally/Leganto/readiness aggregation)
  for no benefit. A write path that doesn't affect these loaders' output (like
  flagging a module - `spot_checks` isn't read by any of the three) should not
  call `st.cache_data.clear()` just out of habit; a plain `st.rerun()` is
  enough to refresh what actually depends on session/query-time state.

- **Never write `st.session_state` from inside an `@st.cache_data`-decorated
  function.** `st.cache_data`'s cache is shared across every session (unlike
  `st.session_state`, which is per-session); on a cache HIT the function body
  doesn't run at all, so any `st.session_state[...] = ...` inside it only
  ever executes for whichever session happened to trigger the one real
  (cache-miss) call. Every other session's script runs `load_audit_data()`,
  gets the cached return value instantly, and never reaches that line - its
  own `st.session_state` simply never receives the key, for as long as the
  cache stays warm (up to the 300s ttl above, longer if another session's
  call keeps refreshing it). Found 15-09-2026: `load_audit_data()` used to
  stash `df_ally_courses`/`df_ally_issues`/`df_ally_content`/
  `df_readiness_sections` into `st.session_state` this way. Symptom: a
  module's Accessibility Report tab would show real gauge scores (e.g.
  94.9% overall, 62.5% files) but "✅ No accessibility issues reported"
  underneath, intermittently, "fixing itself" on some refreshes and not
  others - exactly what you'd expect from whether *this* session happened to
  be the one whose rerun landed on a cache miss. Fixed by returning the four
  frames from `load_audit_data()` instead (now a 6-tuple with `df_aut`,
  `df_spr`) and moving the `st.session_state[...]` assignments to the call
  site in `app.py` (just below `with st.spinner(...)`), which is *not*
  cached and therefore runs for every session on every rerun regardless of
  whether the `load_audit_data()` call itself was a hit or a miss. If a
  future loader needs to stash something in session_state, assign it at the
  call site, never inside the cached function.

- **Interactive column sort on `st.dataframe` tables is unreliable when the
  table also has `on_select="rerun"`** (e.g. the "All Modules" table in
  `views/school_dashboard.py`) - this is an upstream Streamlit limitation, not
  an app bug. Streamlit does not track click-to-sort state across a script
  rerun ([streamlit/streamlit#10701](https://github.com/streamlit/streamlit/issues/10701),
  open/unfixed as of Streamlit 1.61.1), so a rerun triggered by interacting
  with the table (row selection, or another widget on the page) can silently
  drop the sort back to the underlying row order while the header arrow still
  shows the stale sort direction. Confirmed 19 Aug 2026 on the School
  Dashboard's Module Code column: descending sort was a clean, complete
  reverse-alphabetical order, but ascending showed a scrambled order with no
  relationship to alphabetical order at all - i.e. the sort silently reverted
  to natural row order. Don't chase this as a data/dtype bug in this repo's
  code first - check whether the reported "wrong" direction is actually just
  unsorted before assuming e.g. a formatting issue (see the actual `Ally
  Score` text-vs-numeric sort bug this was first confused with, fixed 19 Aug
  2026 in `views/school_dashboard.py` - that one *was* a real app bug: a
  percentage was pre-formatted into a string and given a bare column_config
  label instead of `st.column_config.NumberColumn`, so the grid sorted it
  lexicographically). No app-side fix for the rerun/sort issue exists yet;
  it needs an upstream Streamlit fix.
- **School list**: use `FACULTY_SCHOOLS` from `processing.py`. There were once
  five hardcoded copies. Do not add a sixth.
- **`processing.py` is I/O-free** - pandas transformations only. SQL belongs in
  `database.py`, Sheets access in `data_manager.py`, ETL in `sync_data.py`.
- **Semester selection**: always go through `resolve_semester_df()`. "All year"
  used to mean different things on different pages. Year-long modules appear in
  *both* Autumn and Spring frames; "All year" narrows to just those.
- **Capability checks**: `any(c.lower() == "edit_checklist" for c in user_caps)`
  where `user_caps = st.session_state.get("capabilities", [])`. Capabilities are
  lowercase tokens: `view_all`, `view_school`, `view_school_dashboard`,
  `edit_checklist`, `access_admin_panel`, `access_admin_limited`.
- **`view_school` is scoping, not page access - it never gates a page.** It
  only drives `only_own_school` (own-school vs faculty-wide filtering) inside
  School Dashboard, Audit Portal and Module Report; every role that can reach
  those pages at all holds it. Gating a page's *visibility* on a role needs a
  dedicated capability instead - `view_school_dashboard` (added 16-09-2026)
  is `pg_school`'s gate in `app.py`, deliberately separate from `view_school`
  so ML can keep the scoping capability (needed to lock Module Report, the
  only school-scoped page ML can still reach, to their own school) while
  being excluded from the School Dashboard nav entry, the sidebar link, and
  the drill-down button on Faculty Overview (`views/faculty_overview.py`) -
  the same `st.switch_page`-raises-on-an-unregistered-page hazard
  `pg_audit`/`edit_checklist` already guards against, applied here too.
  Every other seeded role (`admin`, `DLA`, `FOSS`, `SA`, `SL`) was given
  `view_school_dashboard` alongside its existing capabilities in `auth.py`'s
  `EnvAuthProvider` and `data_manager.py`'s Sheets/SQLite seed defaults; a
  live deployment's SQLite `roles` table needs an admin to tick the new
  capability per existing role in the Admin Panel's Role Capabilities tab
  (`views/admin_panel.py`'s `available_caps`) - seeding doesn't touch rows
  that already exist.
- **ML never holds `edit_checklist`.** Every hardcoded capability mapping
  (`auth.py`'s `EnvAuthProvider` and the `ActiveDirectoryAuthProvider`
  placeholder, `data_manager.py`'s Sheets/SQLite seed defaults) used to give
  ML `edit_checklist` alongside `view_school` - wrong per "Who does what"
  above: DLAs audit on the module lead's behalf, module leads do not fill in
  their own audits. Caught 16-09-2026 while fixing the `view_school_dashboard`
  rollout above: an admin correcting the live `roles` table by hand kept
  re-adding `edit_checklist` to ML because that's what the (buggy) seed
  defaults had always shipped. Fixed in code to `["view_school"]` only. This
  also means ML was never actually meant to reach the Audit Portal at all -
  `can_audit`/`is_dla_or_admin` in `app.py` and the `edit_checklist` check in
  `views/audit_portal.py` already gate that page correctly on `edit_checklist`
  regardless of `view_school`; ML's `view_school` capability is now doing
  exactly one job, scoping Module Report to their own school.
- **Cross-page navigation**: `st.switch_page(st.session_state.pg_module)` - page
  objects are stashed in session state in `app.py`. Do not set a session key and
  call `st.rerun()`; the old `view_selection` router was removed in v1.8 and
  buttons doing that silently did nothing for several releases.
- **`pg_audit` is only registered in the navigation for `edit_checklist`
  holders**, and `st.switch_page` raises on an unregistered page. Any button
  jumping there needs a `can_audit` guard, not just a permission check inside
  the destination.
- **School context locking**: `views/school_dashboard.py`,
  `views/audit_portal.py` and `views/module_report.py` all read/write two
  **plain** session-state values - `context_school` (a school code, or the
  literal `"All Schools"`) and `context_focus_own` (bool) - that are never
  passed as any widget's own `key=`. Each page's checkbox/selectbox seeds its
  `value=`/`index=` from these on every render and writes the result back
  immediately after, e.g.:
  ```python
  filter_by_school = st.checkbox(label,
      value=st.session_state.get("context_focus_own", True),
      key="sd_context_focus_own_widget", ...)
  st.session_state.context_focus_own = filter_by_school
  ```
  This applies to **both** branches that offer an override: the "Focus on my
  school(s)" checkbox branch (accounts with specific own school(s)) and the
  `["All Schools"]` fallback selectbox branch (faculty-wide accounts -
  `sd_school_select_all` / `ap_school_select_all` / `rc_school_select_all` -
  which is what most real DLA accounts actually hit day to day, since they're
  provisioned `saved_school="All"` even when genuinely aligned with specific
  schools; see the project memory on this). Both branches write the same
  `context_school` key, so a school picked via either one is honoured by
  every page regardless of which branch that page's own account type uses.
  Added/corrected 19-08-2026.

  **Why plain values, not a shared widget `key=`:** an earlier version of
  this (same day) gave the checkbox/selectbox on all three pages the
  identical `key=`, reasoning that Streamlit keys a widget's value by that
  string across the whole session. That's true only for the page that most
  recently rendered it - confirmed with a throwaway two-page
  `st.navigation()`/`st.Page(function)` sandbox app: a widget's *own*
  session-state entry is cleared the moment its page's function stops
  executing for one run, even when a *different* page's function creates a
  widget with the exact same `key=` moments later. A plain
  `st.session_state[...] = value` write (never bound to any widget) is not
  subject to that cleanup and survives navigation through any number of
  other pages, including ones that never reference the key at all (also
  confirmed in the sandbox, including through a page list built with
  `position="hidden"` and manual `st.page_link()`s, matching this app's
  actual sidebar exactly) - hence the two-tier design above. If this is ever
  touched again: do not reach for a shared `key=` as the fix, it looks
  correct and silently isn't once real page-to-page navigation is involved.

  Every quick-action launcher on School Dashboard that jumps to the Report
  Card or Audit Portal (the "All Modules" table, the Priority Action List,
  and the Spot-Checks tab) sets `context_focus_own`/`context_school`
  directly to the school currently being viewed before `st.switch_page`, so
  the destination page shows that exact school even before the DLA touches
  its own controls. Default behaviour (own school(s), checkbox ticked) is
  unchanged. `only_own_school` (`view_school` without `view_all`) accounts
  have no override at all and are unaffected by any of this.
- **Date formatting**: User-facing dates always display as `DD-MM-YYYY`
  (e.g., "06-08-2026") using `strftime('%d-%m-%Y')`. Internal storage and
  database columns use ISO format (`YYYY-MM-DD HH:MM:SS`) for sortability.
  Timestamps shown to users follow `DD-MM-YYYY HH:MM:SS` when time is included.

## Auth

`AUTH_PROVIDER` selects between Env / SQLite (default) / Active Directory /
Google OAuth. Passwords use scrypt via `security.py`; legacy SHA-256 digests
still verify and are re-hashed transparently on successful login.

Accounts that sign in with Google carry an **empty `PasswordHash`**. Those rows
are correct - deleting one revokes that person's access. An empty hash never
matches any input, so it is not a bypass.

The CookieManager is a Streamlit component and can only write a cookie on a run
where it actually renders. `check_password()` deliberately skips rendering it
once logged in, so any cookie write must happen on a run that falls through that
fast path. A queued write sitting below the early return will never execute -
that bug is why OAuth sessions did not survive a refresh.

The session cookie holds a **signed token, never a bare username** (see
`make_session_token()` / `verify_session_token()` in `auth.py`). Until 22-09-2026
it held the plain username, and since CookieManager writes from JavaScript
(no HttpOnly) anyone could set it to an admin's name in devtools and skip the
password. Every cookie write goes through `_write_session_cookie()`; do not add
a `cookie_manager.set()` with a raw username again. `SESSION_COOKIE_SECRET`
unset means no cookie is written or restored, by design.

## Docs and releases

User-facing documentation is markdown in `docs/`, rendered by `views/docs.py`.
Edit the markdown, not the Python.

- `docs/help.md`, `docs/changelog.md`, `docs/developer-guide.md`
- A release means: bump `__version__` in `app.py`, add an entry to
  `docs/changelog.md`, commit, tag `vX.Y.Z`.
- Paths in `views/docs.py` resolve from `__file__`, not the working directory -
  the container runs from `/app`.

## Verifying changes

There is **no test suite**. To check work:

```bash
python -m streamlit run app.py --server.port=8599 --server.headless=true
```

It boots without credentials and exercises every import and data loader against
the local database, which catches most breakage. Anything past the login screen
needs a real sign-in - ask the user rather than entering credentials.

`app.log` is the best evidence for auth and sync behaviour; it records logins,
cookie restores, syncs and audit submissions. `diagnostics/` holds ad-hoc
inspection scripts, not tests.

## Known outstanding issues

`CODE_REVIEW_FINDINGS.md` records what a September 2026 sweep for
redundancies and improvements turned up, including the items not yet fixed -
most notably that **masquerade mode does not actually gate writes** in the
Admin Panel or the School Dashboard's spot-check actions, despite
`masquerade.py`'s docstring and the sidebar banner both saying it is
view-only. Read it before starting work in those areas, and mark an item
`[RESOLVED]` there rather than deleting it when you fix one.
