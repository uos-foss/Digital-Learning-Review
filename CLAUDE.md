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
