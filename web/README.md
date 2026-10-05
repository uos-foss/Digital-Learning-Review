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

- **Google sign-in / SSO.** Django's built-in login is used as a placeholder.
  `django-allauth` is the next step, and the doc's sign-in section covers it.
- **School scoping.** Pages check only that a user is signed in. Real scoping
  needs the account-to-school model the doc describes, which the spike does
  not invent.
- **Writes.** Nothing here saves an audit. When it does, it should call
  `database.save_audit_response()` so both front ends behave identically.
- **Deployment.** No Dockerfile, no compose service, no Caddy route.

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

The logic tests need neither Django nor a database:

```bash
cd web && ../.venv-django/Scripts/python -m pytest
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
  dlr/settings.py     Repo root on sys.path; two databases
  dlr/routers.py      auditdata -> shared database; never migrate it
  dlr/hashers.py      Verify existing scrypt hashes, never write them
  auditdata/models.py Unmanaged models over audit_fields, audit_responses
  modules/loaders.py  Builds one module's row (see the warning below)
  modules/views.py    Report page, HTMX fragment, Plotly chart
  tests/              Pure logic tests, no database
  smoke.py            End-to-end check against the real database
```

Two databases: `default` is Django's own small SQLite file, `audit` is the
shared `audit_cache.db` that Streamlit and AI-Audit also read. The router
refuses to migrate the shared schema in either direction, so Django can never
alter a table another app depends on. `manage.py makemigrations --check`
confirms it proposes nothing.

## The finding that matters

**The module-row assembly is trapped inside Streamlit, and
`modules/loaders.py` currently duplicates it.**

`derive_module_findings()` documents the row it needs (`Ally Severe`,
`Template Sections`, `Leganto List Status` and so on), but the code that
*builds* that row lives in `app.py::load_audit_data()`, which is wrapped in
`@st.cache_data` and sits in a module that configures Streamlit pages at
import time. Django cannot call it, so `loaders.py` repeats the mapping for a
single module.

Two copies of that mapping is exactly the drift risk that keeping both front
ends in one repo is meant to prevent. **Before porting any further page,
extract the row assembly out of `app.py` into a Streamlit-free loader at the
repo root that both front ends import, and delete the duplication in
`loaders.py`.** Everything it needs is already free of Streamlit: the
`database.get_*_latest()` queries and the `processing.aggregate_*_to_modules()`
functions. Only the assembly is stuck.

That extraction is worth doing for the Streamlit app regardless, since it
would also make `load_audit_data()` testable for the first time.

## Smaller things noticed

- **`school_of(code)` is missing.** The first-three-letters rule is copied
  about 16 times across the Streamlit app, and `loaders.py` now makes 17. One
  helper in `processing.py` would settle it, and it is a prerequisite for any
  other faculty using this code.
- **Row keys carry spaces** (`Ally Overall`, `Module name`), which Django
  templates cannot resolve by dot notation. `views._display()` maps them to
  template-friendly names in one place, which is where that renaming belongs
  anyway.
- **`audit_responses` has a composite primary key**, which Django does not
  support. The model treats `module_code` as the key for reads, which is fine
  for reading and another reason writes should keep going through
  `database.py`.
- **The SITS table is not modelled.** It has no primary key, and its name
  carries the academic year, which is a contract with AI-Audit. `loaders.py`
  reads it with pandas, exactly as the Streamlit app does.
