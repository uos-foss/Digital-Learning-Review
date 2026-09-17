# Code review findings — September 2026

A sweep of the codebase for redundancies and improvements, run 16-09-2026
against `370c50f`. Recorded here so the unfixed items are not lost.

Findings are grouped by whether they are defects or duplication. Each says
what is wrong, where, and — where it matters — why the obvious fix is not
the right one. Mark an item `[RESOLVED]` rather than deleting it, following
`module_dashboard_review.md`'s convention, so the reasoning survives.

## Resolved (commit 370c50f)

- `[RESOLVED]` **Unreachable accessibility caption.** The `st.caption()`
  explaining what "Severe" means sat after `build_accessibility_risk_list()`'s
  `return` in `views/ally_widgets.py`, so it had never rendered on either
  School Dashboard or Faculty Overview. Its text moved into the `note`
  string, which both call sites already render above the table. Widening the
  4-tuple return was the alternative, but that shape is shared with the other
  priority lenses.
- `[RESOLVED]` **`Ally Score` sorted lexicographically.** The `Score` column
  in the same function was pre-formatted to a string and given a bare
  `TextColumn`, so `st.dataframe` put `9.1%` above `94.9%`. Now numeric with
  `NumberColumn(format="%.1f%%")`. This is the same bug, and the same fix,
  already applied to School Dashboard's own Ally Score column in Aug 2026 —
  the shared widget was missed at the time.
- `[RESOLVED]` **Stray `return result, totals`** after
  `derive_module_findings()`'s real return in `processing.py` — a copy-paste
  remnant from `get_school_comparison()`; neither name exists in that scope.
- `[RESOLVED]` **UTF-8 BOM on `views/audit_portal.py`.** Python's importer
  tolerated it, but it broke `ast.parse`-based tooling; this was the one
  project file static analysis could not read.
- `[RESOLVED]` **Unused imports** — `os`/`datetime` (`app.py`), `platform`
  (`database.py`), `pandas` (`views/audit_portal.py`), `datetime`
  (`views/module_report.py`).

## Outstanding — defects

### 1. Masquerade is advertised as view-only but does not gate most writes

**Highest priority of what remains.** `masquerade.py`'s own docstring says
"View-only - callers must gate writes with `is_masquerading()`", and the
sidebar banner tells the user "changes are disabled". Only
`views/audit_portal.py` and `views/feedback.py` actually check.

- `views/admin_panel.py` — **37** write/purge/delete call sites, **zero**
  guards.
- `views/school_dashboard.py` — `flag_module_for_spot_check()` (~line 377)
  and `delete_spot_check()` (~line 1062) unguarded.

Because `start_masquerade()` adopts the *target's* capabilities, an admin
shadowing another admin gets a fully writable Admin Panel while the banner
claims otherwise. Needs a deliberate decision: either gate the write paths,
or narrow the banner's claim to match what is actually enforced.

### 2. Unescaped database content interpolated into HTML

`views/module_report.py` (~lines 1234–1247) puts `mod_lead`, `ug_pg` and
`url` straight into an `unsafe_allow_html` block, with `url` also landing
inside an `href='...'`. `_render_ally_issue_card()` and
`_render_section_card()` do the same with their row values.

Lower severity than free text — these come from SITS/Blackboard imports
rather than a DLA's keyboard — but an apostrophe in a module lead's name
already breaks the `href` quoting today. `_render_actions_panel()` already
`html.escape()`s its custom-observation text and documents why; the same
discipline has not reached the metadata bar or the card renderers.

### 3. `get_db_connection()` connections are never closed

85 `with get_db_connection() as conn:` blocks across the codebase; only
`init_db()` calls `conn.close()`. `sqlite3.Connection.__enter__/__exit__`
commits or rolls back — it does **not** close (verified on this repo's
Python 3.14).

CPython's refcounting closes them promptly in practice, which is why this
has not bitten, but it holds WAL read locks longer than necessary and the
timing is undefined. A `@contextmanager` wrapper with
`try/finally: conn.close()` fixes all 85 sites with no call-site changes.

### 4. Audit saves are one connection and one transaction per field

`views/audit_portal.py` (~lines 371–375) loops over every field calling
`save_audit_response()`, each of which opens a connection, runs a SELECT, an
INSERT and a COMMIT. An 8-field audit save is 9 connections and 9
transactions — and it is not atomic, so a failure part-way leaves the audit
partly written with no `audit_status`. A batch variant taking
`{field_id: value}` would make it one transaction.

## Outstanding — redundancies

### 5. Triplicated school-context block

**Highest-value consolidation.** The `only_own_school` / focus-checkbox /
school-selectbox / `context_school` write-back logic is near-identical in
`views/school_dashboard.py` (~60–135), `views/audit_portal.py` (~36–110) and
`views/module_report.py` (~1000–1070) — roughly 70 lines each, differing
only in widget key prefix (`sd_`/`ap_`/`rc_`), page title, and whether it
filters a module list or picks a school.

CLAUDE.md's "School context locking" section documents a subtle, hard-won
reason this must use plain session keys rather than a shared widget `key=`.
That invariant is currently protected by three copies staying in sync by
hand. One `resolve_school_context(page_prefix, title, ...)` helper would
make it enforceable in a single place.

### 6. Two title-case implementations for academic names

`views/module_report.py`'s `title_case_name()` handles McDonald / O'Brien /
hyphenated names; `views/school_dashboard.py`'s `to_title_case()` is a bare
`.title()`. `views/admin_panel.py` already imports the good one from
`module_report`, so the codebase has effectively picked a canonical version
— School Dashboard is the lone holdout, and renders the same lead names
differently across three of its tables.

Both belong in `processing.py` (pure string work, no I/O), with the
School Dashboard copy deleted.

### 7. `_ally_issue_profile` / `_ally_issue_categories` are the same function

`views/module_report.py` (~355 and ~366) differ only in which `summarise_*`
they call. One function taking the summariser — or a shared
`_module_issue_rows(code)` both build on — collapses them.

### 8. Import scaffolding duplicated three times

`views/admin_panel.py` repeats the same filename date-extraction
(`re.search(r'(\d{1,2})-(\d{1,2})-(\d{2,4})', …)` + `pd.to_datetime(dayfirst=True)`)
at ~204, ~396 and ~568.

More broadly, `_render_ally_import()`, `_render_leganto_import()` and
`_render_readiness_import()` (~550 lines combined) share one skeleton:
upload → year select → snapshot date → parse → metrics → confirm → write →
`cache_data.clear()`. The parse and write steps are genuinely different per
source; the scaffolding around them is not.

## Verified sound

Checked and found correct — recorded so they are not re-investigated:

- Every invariant CLAUDE.md documents holds: `ALLY_CHECK_CATEGORY` covers all
  38 `ALLY_CHECKS` (`LibraryReference` excluded deliberately —
  `prepare_ally_issues()` filters it first), `TEMPLATE_SECTION_TREE` covers
  all 14 sections exactly, and `LEAD_OWNED_SECTIONS` (4) /
  `INSTITUTION_MAPPED_FIELD_IDS` (3) / mapped fields (7) reconcile.
- Exception handling: no bare `except:` anywhere, and the single
  `except Exception: pass` (`processing.py` ~478) is correct and commented —
  it is the legacy-format fallthrough in `parse_custom_observations()`.
- `save_audit_response()`'s history logging correctly writes a row only when
  the value actually changed.
