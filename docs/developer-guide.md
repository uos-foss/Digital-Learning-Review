Technical documentation for developers working on the portal.

### 🛠️ Architecture Overview

The platform is a **Streamlit** application backed by a **SQLite** database.
Google Sheets is no longer a request-time dependency: it is an upstream source
drained into SQLite by a separate ETL step. Nothing the user does in the app
touches the Sheets API.

```text
  REQUEST PATH (every page load)
  ─────────────────────────────────────────────────────────────
  ┌───────────────────────────────────────────────────────────┐
  │              Streamlit Client App (app.py)                │
  │        st.navigation  →  views/*.py  →  processing.py     │
  └────────┬──────────────────┬───────────────────┬───────────┘
           │ read / write     │ sign-in           │ events
           ▼                  ▼                   ▼
   ┌───────────────┐  ┌────────────────┐  ┌───────────────┐
   │  database.py  │  │    auth.py     │  │    app.log    │
   │  (all SQL)    │  │  + security.py │  │  (persistent) │
   └───────┬───────┘  └───────┬────────┘  └───────────────┘
           │                  │
           ▼                  ▼
   ┌───────────────┐  ┌────────────────┐
   │ audit_cache.db│  │ Browser cookie │
   │ SQLite, WAL,  │  │ (session       │
   │ host volume   │  │  restore)      │
   └───────▲───────┘  └────────────────┘
           │
  ─────────┼───────────────────────────────────────────────────
  ETL PATH │ (manual: Admin Panel button, or python sync_data.py)
           │
   ┌───────┴───────┐      ┌────────────────┐      ┌───────────┐
   │  sync_data.py │─────▶│ data_manager.py│─────▶│  Google   │
   │   (pull ETL)  │      │    (gspread)   │◀─────│  Sheets   │
   └───────────────┘      └────────────────┘      └───────────┘
        push-back is limited to comment bank and audit field
        definitions; audits and feedback never leave SQLite
```

### 📁 Modular File Structure

* **`app.py`** — Entrypoint. Configures the root logger, holds `__version__`,
  defines the cached data loaders, builds the sidebar and page routing, and
  wraps each view in a page function.
* **`auth.py`** — Pluggable authentication. Four providers (`EnvAuthProvider`,
  `SQLiteAuthProvider`, `ActiveDirectoryAuthProvider`, `GoogleOAuthProvider`),
  the OAuth callback handling, and cookie-based session restore and sign-out.
* **`security.py`** — Password hashing primitives: `hash_password`,
  `verify_password`, `needs_rehash`.
* **`database.py`** — Database path resolution, connection handling, schema
  initialisation and migration, and all table-level CRUD. The largest module,
  and the only one that should contain SQL.
* **`data_manager.py`** — Low-level Google Sheets access: the gspread client,
  reads, appends and header initialisation, with retry handling.
* **`processing.py`** — Pandas transformations. Dataframe cleaning, the
  `FACULTY_SCHOOLS` list, semester resolution, compliance gap calculations and
  the school comparison aggregation. No I/O.
* **`sync_data.py`** — The Sheets → SQLite ETL pipeline, the two push-back
  functions, and the Blackboard links CSV importer. Runnable as a script.
* **`background_tasks.py`** — A threaded scheduler that pushed unsynced
  checklists to Sheets. **Currently disabled** — the import in `app.py` is
  commented out, since SQLite became the primary store and there is nothing to
  push. Retained in the tree rather than deleted.
* **`views/`** — One module per page, separating rendering from the business
  logic in `processing.py` and `database.py`.
* **`docs/`** — The markdown rendered by the Resources & Support page.

### ⚙️ Environment Variables

All configuration comes from `.env`, injected into the container by
`docker-compose.yml`. Nothing is read from a credentials file on disk.

| Variable | Purpose |
| :--- | :--- |
| `DB_PATH` | SQLite location inside the container. Defaults to `/app/data/audit_cache.db`. |
| `AM_I_DOCKER` | Set to `true` to force container path resolution. |
| `AUTH_PROVIDER` | Selects the sign-in provider — see below. |
| `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `OAUTH_REDIRECT_URI` | Google sign-in. `REDIRECT_URI` is accepted as a fallback. |
| `GOOGLE_SA_CLIENT_ID` | The service account's own client id — a different credential from the OAuth one. |
| `GOOGLE_TYPE`, `GOOGLE_PROJECT_ID`, `GOOGLE_PRIVATE_KEY_ID`, `GOOGLE_PRIVATE_KEY`, `GOOGLE_CLIENT_EMAIL`, `GOOGLE_AUTH_URI`, `GOOGLE_TOKEN_URI`, `GOOGLE_AUTH_PROVIDER_X509_CERT_URL`, `GOOGLE_CLIENT_X509_CERT_URL`, `GOOGLE_UNIVERSE_DOMAIN` | Service-account fields reassembled into credentials by `get_gspread_client()`. `GOOGLE_PRIVATE_KEY` keeps its `\n` escapes; they are expanded at load. |
| `MAIN_SPREADSHEET_ID`, `ASSESSMENT_SPREADSHEET_ID`, `CHECKLIST_SPREADSHEET_ID`, `USERS_SPREADSHEET_ID`, `AI_RESPONSES_SPREADSHEET_ID`, `DATA_SHEET_ID` | Upstream sheets for the ETL. |
| `USER_ADMIN`, `USER_DLA`, `USER_FACULTY`, `USER_<SCHOOL>` | Seed credentials, used only by `EnvAuthProvider` and initial seeding. |

> [!NOTE]
> **`GOOGLE_CLIENT_ID` is deprecated.** It was previously read as *both* the
> OAuth web client id and the service account's `client_id` — two different
> credentials sharing one variable. Where `.env` defined it twice, the last
> definition won and the service account silently received the OAuth id. This
> was harmless only because `from_service_account_info` signs with the private
> key and `client_email` and never uses `client_id`.
>
> Both call sites now read their own variable and fall back to
> `GOOGLE_CLIENT_ID`, so an old `.env` keeps working. Set
> `GOOGLE_OAUTH_CLIENT_ID` and `GOOGLE_SA_CLIENT_ID` and the legacy name can be
> removed entirely.

### 💾 Database Location

`database.py::get_database_path()` resolves `DB_PATH` in this order:

1. Inside Docker (or with `AM_I_DOCKER=true`), the `DB_PATH` environment
   variable, defaulting to `/app/data/audit_cache.db`.
2. A sibling `../shared-data/` directory, if present — used when several sibling
   apps share one database locally.
3. Otherwise `./data/audit_cache.db` in the project folder.

The database runs in WAL mode with busy timeouts so multiple containers can
share it concurrently. In production it lives on a host volume, **not** in the
image — rebuilding the container does not touch the data.

### 🔐 Authentication

`AUTH_PROVIDER` in `.env` selects the provider:

| Value | Provider |
| :--- | :--- |
| *(unset or unrecognised)* | `SQLiteAuthProvider` — the default |
| `ENV` | `EnvAuthProvider` — credentials from environment variables |
| `AD` / `ACTIVE_DIRECTORY` | `ActiveDirectoryAuthProvider` |
| `GOOGLE` / `GOOGLE_OAUTH` | `GoogleOAuthProvider` |

Passwords are hashed with **scrypt** from the standard library — no third-party
dependency. The stored format carries its own cost parameters so they can be
raised later without a second migration:

```text
scrypt$<n>$<r>$<p>$<base64 salt>$<base64 derived key>
```

Legacy unsalted SHA-256 digests are still verified, and any account still
holding one is re-hashed transparently on its next successful sign-in. That
fallback can be removed from `security.py` once every account has signed in at
least once.

> [!IMPORTANT]
> Accounts using Google sign-in legitimately carry an **empty** `PasswordHash`.
> Those rows are not broken and must not be deleted as cleanup — deleting one
> revokes that person's access. They are not a bypass either: an empty stored
> hash never matches any input.

### 📝 Logging

Configured globally in `app.py` and inherited by every module.

* **Level**: `INFO` — normal operations, sign-ins, syncs, and all warnings and
  errors.
* **File**: `app.log` in the project root, git-ignored and mounted as a volume
  in production so it survives container rebuilds.
* **Format**: `YYYY-MM-DD HH:MM:SS [LEVEL] Message`
* Readable in-app from the Admin Panel's Log Viewer.

### 📦 Releasing a New Version

Versions follow **Semantic Versioning** and are kept in step with git tags.

1. **Update the version**: increment `__version__` in `app.py`.
2. **Write the release note**: add an entry to `docs/changelog.md`. This is
   plain markdown — no Python change and no code review needed for wording.
3. **Commit**: stage the changes and commit (e.g. `Release version 1.14.0`).
4. **Tag**: create a matching tag (e.g. `v1.14.0`).
5. **Push**: push commits and tags together.

### 🐳 Deployment

The portal is containerised with **Docker Compose**. The image is built from
`python:3.11-slim`.

#### Configuration

* **`Dockerfile`** — Installs dependencies from `REQUIREMENTS.txt` in a separate
  layer for caching, then copies the application.
* **`docker-compose.yml`** — Injects `.env`, sets the restart policy, and mounts
  three volumes: `app.log`, the read-only `.streamlit` config directory, and the
  shared database directory `/opt/shared-audit-data` → `/app/data`.
* **Networking** — The container binds to `127.0.0.1:8500` on the host only, and
  serves under the base path `digital-learning-review`, so a native Caddy
  instance can reverse-proxy it alongside other Streamlit apps.

#### First deployment

```bash
# 1. Clone the repository onto the server
git clone <your-repo-url> && cd Digital-Learning-Review

# 2. Create the production .env file
nano .env

# 3. Create the log file so the volume mount binds to a file, not a directory
touch app.log

# 4. Ensure the shared database directory exists on the host
sudo mkdir -p /opt/shared-audit-data

# 5. Build and start in the background
docker compose up -d --build
```

#### Updating a running deployment

```bash
git pull origin main
docker compose up -d --build
```

Only modified layers rebuild. The mounted `app.log` and the database directory
are untouched by a rebuild.

> [!IMPORTANT]
> **Applying `.env` changes**: editing `.env` on the host does not affect a
> running container, which holds the old values in memory. Recreate it:
> ```bash
> docker compose up -d
> ```

#### Monitoring

```bash
# Running containers
docker compose ps

# Follow container output
docker compose logs -f

# Stop
docker compose down
```
