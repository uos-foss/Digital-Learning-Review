# Recovery runbook

How to restore the Digital Learning Review portal. Written to be followed by
someone who has not worked on this system before.

If you are reading this during an incident, start at **Before you start**, then
jump to the scenario that matches.

> **Note on remote names.** Examples below use `gdrive:`. The backup database is
> **not encrypted** — it is a plain `.gz` file, readable by anyone with access to
> the Drive location. If a `gdrive-crypt:` remote is ever added, the paths below
> are otherwise identical.

---

## Before you start

You cannot complete a restore without all of these. Confirm you have them before
touching anything.

| You need | Where it is | If you don't have it |
| :--- | :--- | :--- |
| SSH + sudo on the VM | University IT | Nothing else is possible |
| Access to the backup Drive location | `Server_Backups/sqlite` | See *If the backups are unreachable* |
| The `.env` contents | Password manager, or the config archive in the backup | Rebuild from `.env.example`; expect an afternoon |
| GitHub access to `uos-foss/Digital-Learning-Review` | Public repo — clone needs no auth | — |

The database is the only copy of every audit ever recorded. Audits have never
been written back to Google Sheets since the v1.9 migration. Treat the backup as
irreplaceable and **never restore over a live database without a copy of the
current one first**.

---

## Scenario A — Restore the database only

Use when the VM is healthy but the data is wrong: corruption, a bad sync, or
damage you want to roll back.

### 1. Identify the backup you want

```bash
sudo rclone lsl gdrive:Server_Backups/sqlite/shared-audit-data/ | sort -k4
```

Filenames carry the timestamp of the run: `opt_shared-audit-data_audit_cache_YYYYMMDD_HHMMSS.db.gz`.

Pick the newest one from *before* the damage — not simply the newest.

### 2. Stop every container sharing the database

This is the step people get wrong. **One other application, AI-Audit, mounts the
same volume.** Restoring while it holds an open connection will corrupt the file
you just restored.

```bash
docker ps --format '{{.Names}}\t{{.Mounts}}' | grep shared-audit-data
```

Stop each project found, from its own directory:

```bash
sudo docker compose -f /opt/Digital-Learning-Review/docker-compose.yml down
```

Repeat for `/opt/AI-Audit`. Then confirm nothing is left:

```bash
docker ps --format '{{.Names}}\t{{.Mounts}}' | grep shared-audit-data
```

That must return nothing before you continue.

### 3. Preserve the current database

Even a corrupt database may contain recent audits absent from the backup.

```bash
sudo cp -a /opt/shared-audit-data/audit_cache.db /opt/shared-audit-data/audit_cache.db.pre-restore-$(date +%Y%m%d_%H%M%S)
```

### 4. Fetch and unpack

```bash
sudo rclone copy gdrive:Server_Backups/sqlite/shared-audit-data/opt_shared-audit-data_audit_cache_YYYYMMDD_HHMMSS.db.gz /tmp/restore/
```

```bash
sudo gunzip /tmp/restore/opt_shared-audit-data_audit_cache_YYYYMMDD_HHMMSS.db.gz
```

### 5. Check it before trusting it

```bash
sudo sqlite3 /tmp/restore/opt_shared-audit-data_audit_cache_YYYYMMDD_HHMMSS.db "PRAGMA integrity_check;"
```

Anything other than `ok` — stop and choose an earlier backup.

Sanity-check the contents too, so you know what you are about to install:

```bash
sudo sqlite3 /tmp/restore/opt_shared-audit-data_audit_cache_YYYYMMDD_HHMMSS.db "SELECT 'audit_responses', COUNT(*) FROM audit_responses UNION ALL SELECT 'users', COUNT(*) FROM users UNION ALL SELECT 'ally_scores', COUNT(*) FROM ally_scores;"
```

### 6. Remove the old write-ahead log

The database runs in WAL mode. A restored file is self-contained, but stale
`-wal` and `-shm` files from the previous database will be applied on top of it
and corrupt the result.

```bash
sudo rm -f /opt/shared-audit-data/audit_cache.db-wal /opt/shared-audit-data/audit_cache.db-shm
```

### 7. Move it into place

```bash
sudo mv /tmp/restore/opt_shared-audit-data_audit_cache_YYYYMMDD_HHMMSS.db /opt/shared-audit-data/audit_cache.db
```

### 8. Restart

```bash
sudo docker compose -f /opt/Digital-Learning-Review/docker-compose.yml up -d
```

Then bring AI-Audit back up the same way.

Go to **Verification**.

---

## Scenario B — Rebuild onto a fresh VM

Use after total loss of the server.

### 1. Base system

Install Docker Engine, the Compose plugin, `sqlite3`, `rclone`, and Caddy. Caddy
is installed **natively, not as a container** — it will not return with the
application.

### 2. Restore the configuration archive

The backup contains a config archive alongside the databases, holding every
`.env`, the Caddyfile, `rclone.conf` and each app's `config.toml`.

Chicken-and-egg: you need rclone working to fetch the archive containing
`rclone.conf`. Configure a temporary remote by hand (`rclone config`) against the
backup Drive account, retrieve the archive, then install the real config from it.

### 3. Clone and configure

```bash
sudo git clone https://github.com/uos-foss/Digital-Learning-Review.git /opt/Digital-Learning-Review
```

Place `.env` in the project root from the archive, or rebuild it from
`.env.example` if the archive is unavailable.

Place `.streamlit/config.toml` from the archive, or copy
`deploy/streamlit-config.toml.example`.

### 4. Create the mount points

```bash
sudo mkdir -p /opt/shared-audit-data
```

Create the log file **as a file**. If it does not exist, Docker creates a
*directory* at that path to satisfy the bind mount in `docker-compose.yml`, and
logging fails in a way that is not obvious:

```bash
sudo touch /opt/Digital-Learning-Review/app.log
```

### 5. Restore the database

Follow **Scenario A steps 1, 4, 5, 7** — there are no containers to stop and
nothing to preserve on a fresh machine.

### 6. Start

```bash
sudo docker compose -f /opt/Digital-Learning-Review/docker-compose.yml up -d --build
```

### 7. Restore the reverse proxy

Install the Caddyfile from the config archive and reload Caddy. This app requires
a reverse proxy to `127.0.0.1:8500` serving under the base path
`digital-learning-review`; the container deliberately binds to loopback only and
is unreachable without it.

The same Caddyfile routes the other services on this VM. Restore it whole rather
than reconstructing this app's stanza in isolation.

### 8. DNS and certificates

Confirm `fossdigital.shef.ac.uk` resolves to the new host. Caddy will obtain
certificates automatically on first request once DNS is correct.

Go to **Verification**.

---

## Scenario C — Recover specific rows

Use when most of the database is fine but something specific was deleted — a
module's audits, a user account.

Restore the backup to a **scratch path**, never over the live database:

```bash
sudo sqlite3 /tmp/restore/scratch.db ".dump audit_responses" > /tmp/restore/audit_responses.sql
```

Inspect, edit down to the rows you need, then apply them to the live database
with the containers stopped as in Scenario A step 2.

For a single table you can also attach both databases and copy across:

```bash
sudo sqlite3 /opt/shared-audit-data/audit_cache.db "ATTACH '/tmp/restore/scratch.db' AS bak; INSERT OR IGNORE INTO audit_responses SELECT * FROM bak.audit_responses WHERE module_code='XXX1234';"
```

---

## Verification

Run all of these after any restore.

**1. Integrity**

```bash
sudo sqlite3 /opt/shared-audit-data/audit_cache.db "PRAGMA integrity_check;"
```

**2. The data is actually there**

```bash
sudo sqlite3 /opt/shared-audit-data/audit_cache.db "SELECT 'audit_responses', COUNT(*) FROM audit_responses UNION ALL SELECT 'users', COUNT(*) FROM users UNION ALL SELECT 'roles', COUNT(*) FROM roles;"
```

A `users` count of zero means the restore failed or you restored an empty
database — do not proceed to a sync to "fix" it (see Traps).

**3. The application boots**

```bash
docker logs --tail 50 vle_review_portal
```

**4. A real person can sign in.** Load the site and complete a sign-in. This is
the only check that exercises authentication end to end; nothing above does.

**5. Confirm audits are readable** — open a module you know has a completed audit
and check the responses render.

---

## Traps

Things that have caught people out, or would.

**A Sheets sync will not restore the `users` table.** SQLite is authoritative for
users; the Admin Panel never writes back, so the Users sheet is permanently
stale. `sync_new_users_only()` inserts only genuinely new accounts by design.
Running a full sync after a failed restore will *not* recover roles, statuses or
passwords, and anything that rebuilds the table wholesale would undo the scrypt
password migration.

**Audits exist nowhere but SQLite.** `background_tasks.py`, which once pushed
checklists to Sheets, has been disabled since v1.9. The Sheets copy is frozen at
that date and is not a backup.

**Accounts with an empty `PasswordHash` are not broken.** Google sign-in users
legitimately have no password hash. Deleting those rows as "cleanup" revokes
their access. An empty hash never matches any input, so it is not a bypass.

**Restoring over a live WAL database corrupts it.** Always stop every container
on the shared volume first — AI-Audit as well, not just this one.

**`app.log` must exist as a file before `docker compose up`.** Otherwise Docker
creates a directory at that path.

**The container binds to `127.0.0.1` only.** If the site is unreachable after a
successful restore, the problem is Caddy, not the app. Check
`docker logs vle_review_portal` shows Streamlit listening, then check Caddy.

---

## What is *not* in the backups

Be aware of the limits of what a restore can give you.

- **`app.log`** — the login, sync and audit-submission history. Not backed up;
  lost with the VM.
- **Blackboard links** are imported from a CSV by hand in the Admin Panel. They
  are in the database and so are restored, but if the database is lost entirely
  the original CSV is needed to reimport.
- **Anything after the last successful backup run.** Backups are nightly, so up
  to 24 hours of audit work can be lost. Check the timestamp of the backup you
  restored and tell the advisors what window they need to redo.

---

## If the backups are unreachable

If the Drive location cannot be reached — account disabled, credentials lost —
check for local copies first, which survive independently of the remote:

```bash
sudo ls -la /var/backups/sqlite/
```

Local backups are kept 30 days and live on the VM's own disk, so they exist only
if the VM itself survived.

---

## Keep this current

This runbook is only as good as its last test. Restore Scenario A against a
scratch copy at least once a year, and after any change to the deployment. Update
this file when the procedure changes — a runbook that no longer matches reality
is worse than none, because it is followed under pressure.
