# deploy/

Operational material for the production deployment. Not rendered in the
application — `views/docs.py` renders only the files it names explicitly, and a
recovery guide inside the app is useless when the app is down.

## Contents

| File | Purpose |
| :--- | :--- |
| [`RESTORE.md`](RESTORE.md) | Recovery runbook. Database restore, full VM rebuild, selective row recovery. |
| `streamlit-config.toml.example` | Template for `.streamlit/config.toml`, which is gitignored and so exists only on the server. |
| [`caddy-django.example`](caddy-django.example) | The one Caddy block that routes the Django platform (`/module-reports`). The real Caddyfile stays off the repository. |

See also [`../.env.example`](../.env.example) in the project root — every
environment variable the container needs, with notes on how to reobtain each one.

## What is deliberately not here

**This repository is public.** The following are part of the deployment but are
not committed, and their absence is intentional rather than an oversight:

- **The Caddyfile.** It routes many unrelated services on the same VM.
  Publishing it would disclose the server's full service topology, and Caddy
  configs commonly carry ACME DNS tokens or basicauth hashes.
- **The SQLite backup script and its systemd units.** They cover five separate
  applications on the VM, so they are not specific to this project.
- **`.env`, `rclone.conf`, and any real credential.**

These live on the VM and are swept into the nightly backup archive alongside the
databases. `RESTORE.md` describes retrieving them.

This gives *recovery* but not *version history*. If you want change tracking for
the infrastructure config, the answer is a private `uos-foss` infrastructure
repository — not adding these files here.

## Backups in one paragraph

A nightly systemd timer runs a script that takes an online `sqlite3 .backup` of
every database under the VM's project directories, verifies each with
`PRAGMA integrity_check`, compresses it, and uploads it via rclone to Google
Drive — **not encrypted** — along with an archive of the configuration files
listed above. Local copies are kept in `/var/backups/sqlite` for 30 days;
remote copies for 30 days, with a monthly tier retained for a year. The database
is the only copy of every audit ever recorded — audits are never written back to
Google Sheets.

## Deploying the Django platform

The `dlr-platform` service in `docker-compose.yml` serves the module report at
its own path, beside the Streamlit app. It reads the same shared database and
never migrates it. First time, on the VM:

1. **`.env`**: add the variables under "Django platform" in `.env.example`,
   chiefly `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`,
   `DJANGO_CSRF_TRUSTED_ORIGINS` and `DJANGO_SCRIPT_NAME`. It refuses to start
   without a secret key.
2. **Google**: add `https://<host>/module-reports/accounts/google/login/callback/`
   to the OAuth client's authorised redirect URIs. Without it Google sign-in
   fails after the account chooser.
3. **Caddy**: add the block from `caddy-django.example` and reload Caddy.
4. **Start it**: `docker compose up -d --build dlr-platform`. The Streamlit
   service is untouched by this.
5. **First account**: sign in with Google once, then align it with a school (or
   give it a role) in the Django admin at `/module-reports/admin/`, or create a
   break-glass local account with
   `docker compose exec dlr-platform python manage.py createsuperuser`.

Django's own database (accounts, role assignments, each person's school
alignment) is `dlr_platform.sqlite3` in `/opt/shared-audit-data`, the directory
the nightly backup already sweeps. Confirm the backup script picks up that
file name the first time; it is not the shared audit database, and losing it
would reset who may see which school.

The image is built from the repo root with `Dockerfile.django`, separately from
the Streamlit image. `.dockerignore` keeps `.env`, local environments and local
databases out of both.
