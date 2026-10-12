# Django platform spike

A two or three day spike, not a half-built app. It exists to answer one
question: **can a different front end reuse this project's logic and data
unchanged?** The answer, verified on the live local database, is yes.

Nothing here is deployed, nothing here is wired into Caddy, and the Streamlit
app is untouched. If the platform idea is dropped, deleting `web/`, the two
`.gitignore` additions and `.venv-django/` removes every trace.

Background and the wider case: the **Digital Learning Review: Platform
Options** doc.

## What it proves

| Check | Result |
|---|---|
| `processing.derive_module_findings()` runs unchanged, no Streamlit in the request path | 10 findings for ALA102, 7 pending |
| The shared audit database is readable through a router and unmanaged models | 10 active audit fields through the ORM |
| The readiness, Ally, Leganto and SGA aggregations reuse `processing.py` as is | 14 template sections on the row |
| A module report page renders, with the Actions panel | HTTP 200 |
| An HTMX fragment loads a tab on demand, with a Plotly chart | HTTP 200, chart rendered |
| The URL identifies the page; no session state holds the selection | `/modules/ALA102/` |
| An unknown module is a 404, not a crash | HTTP 404 |
| Anonymous access redirects to sign in | HTTP 302 |
| The existing scrypt password hashes can be verified by Django | `dlr/hashers.py`, verify-only bridge |

## What it does not do

Deliberately out of scope, so the spike stayed small:

- **Institutional SSO.** Google sign-in works (see below); Entra ID is the
  eventual target and an enquiry is with IT.
- **Writes.** Nothing here saves an audit. When it does, it should call
  `database.save_audit_response()` so both front ends behave identically.
- **Deployment.** No Dockerfile, no compose service, no Caddy route.
- **The module report's "Fixed something?" form and PDF export.** The report
  itself is ported, read-only; the form writes and the PDF builds a file, so both
  stay in Streamlit for now.

## Running it

The spike has its own environment, because neither app should install the
other's dependencies. From the repo root:

```bash
python -m venv .venv-django
```

```bash
.venv-django/Scripts/python -m pip install -r web/requirements.txt
```

```bash
cd web && ../.venv-django/Scripts/python manage.py migrate
```

That creates `web/dlr_platform.sqlite3`, which holds Django's own tables only.
Then the smoke check, which reads the real shared database and renders real
pages:

```bash
cd web && ../.venv-django/Scripts/python smoke.py
```

The shared-rule tests live at the repo root now, not here, because they test
`processing.py` rather than anything in `web/`. They need neither Django nor a
database, so either environment runs them:

```bash
.venv/Scripts/python -m pytest
```

## Sign-in and scoping

Google, through `django-allauth`, restricted to verified `sheffield.ac.uk`
addresses by a server-side check in `accounts/adapters.py`. Capabilities are
Django permissions on `accounts.Profile` and roles are Groups:

```bash
cd web && ../.venv-django/Scripts/python manage.py seed_roles
```

Credentials come from the repo root's `.env`, the same file the Streamlit app
reads (`GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`). To sign in with
Google locally, that Google project needs this as an authorised redirect URI:

```
http://localhost:8600/accounts/google/login/callback/
```

Without a client id and secret the page says so and offers the password form
instead, rather than showing a button that fails on click.

School scoping is real: an account is either `all_schools` (DLAs, admins, via
the `view_all` permission) or aligned with specific schools on its profile. A
module outside that returns 403. Set an alignment in the Django admin, or:

```bash
cd web && ../.venv-django/Scripts/python manage.py shell -c "from django.contrib.auth.models import User; from accounts.models import profile_for; p = profile_for(User.objects.get(username='you')); p.set_schools(['EDC','ALA']); p.save()"
```

To click around, create yourself a local account and start the dev server:

```bash
cd web && ../.venv-django/Scripts/python manage.py createsuperuser
```

```bash
cd web && ../.venv-django/Scripts/python manage.py runserver 8600
```

Then open `http://127.0.0.1:8600/modules/ALA102/`. On Linux the paths are
`.venv-django/bin/python`.

## How it is put together

```
web/
  dlr/settings.py     Repo root on sys.path; .env; two databases
  accounts/rules.py   Domain, affiliation and scoping rules, no Django in them
  accounts/adapters.py  Who allauth may let in; signup closed
  accounts/models.py  Profile: affiliation, school alignment, capabilities
  dlr/routers.py      auditdata -> shared database; never migrate it
  dlr/hashers.py      Verify existing scrypt hashes, never write them
  auditdata/models.py Unmanaged models over audit_fields, audit_responses
  modules/data.py     Fetches for a module; sources cached 5 min, audit read fresh
  modules/views.py    One plain module report page: facts, findings, Actions
  ../report_model.py  What the report says, shared with the Streamlit page and PDF
  smoke.py            End-to-end check against the real database
```

Two databases: `default` is Django's own small SQLite file, `audit` is the
shared `audit_cache.db` that Streamlit and AI-Audit also read. The router
refuses to migrate the shared schema in either direction, so Django can never
alter a table another app depends on. `manage.py makemigrations --check`
confirms it proposes nothing.

## The finding that mattered, now fixed

The spike's first version had to **duplicate the module-row mapping**, because
the assembly lived inside `app.py::load_audit_data()`, wrapped in
`@st.cache_data` in a module that configures Streamlit pages at import time.
Nothing outside a running Streamlit script could build a module row.

That assembly now lives in **`loaders.py` at the repo root**, with no
Streamlit in it. `app.py::load_audit_data()` is a thin cached wrapper around
`loaders.load_audit_frames()`, and `modules/data.py` here calls
`loaders.load_module_record(code)`. One mapping, two front ends.

The extraction was verified rather than assumed: all seven returned frames and
the derived findings for all 766 modules were fingerprinted before and after,
and every hash matched. `diagnostics/check_module_loader.py` re-checks it
against the live database, which was impossible before.

**Still duplicated:** `load_checklist_data()` builds its own leaner row in
`module_row()`, re-querying and re-aggregating for the Actionable Items badge.
It agrees with `loaders.py` today, but it should move onto
`loaders.load_module_sources()` when there is appetite to re-verify the badge
counts.

## Smaller things noticed

- **`school_of(code)` is missing.** The first-three-letters rule is copied
  about 16 times across the Streamlit app. One helper in `processing.py` would
  settle it, and it is a prerequisite for any other faculty using this code.
- **Row keys carry spaces** (`Ally Overall`, `Module name`), which Django
  templates cannot resolve by dot notation. `views._display()` maps them to
  template-friendly names in one place, which is where that renaming belongs
  anyway.
- **`audit_responses` has a composite primary key**, which Django does not
  support. The model treats `module_code` as the key for reads, which is fine
  for reading and another reason writes should keep going through
  `database.py`.
- **The SITS table is not modelled.** It has no primary key, and its name
  carries the academic year, which is a contract with AI-Audit. The repo-root
  `loaders.py` reads it with pandas, which both front ends now share.
- **A pre-existing pandas FutureWarning** about concatenating all-NA columns
  fires on the legacy audit tables. It moved with the code and is unchanged;
  fixing it would alter column dtypes, so it wants its own change and its own
  verification.
