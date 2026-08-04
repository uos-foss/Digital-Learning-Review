# deploy/

Operational material for the production deployment. Not rendered in the
application — `views/docs.py` renders only the files it names explicitly, and a
recovery guide inside the app is useless when the app is down.

## Contents

| File | Purpose |
| :--- | :--- |
| [`RESTORE.md`](RESTORE.md) | Recovery runbook. Database restore, full VM rebuild, selective row recovery. |
| `streamlit-config.toml.example` | Template for `.streamlit/config.toml`, which is gitignored and so exists only on the server. |

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

These live on the VM and are protected by being swept into the nightly encrypted
backup archive alongside the databases. `RESTORE.md` describes retrieving them.

This gives *recovery* but not *version history*. If you want change tracking for
the infrastructure config, the answer is a private `uos-foss` infrastructure
repository — not adding these files here.

## Backups in one paragraph

A nightly systemd timer runs a script that takes an online `sqlite3 .backup` of
every database under the VM's project directories, verifies each with
`PRAGMA integrity_check`, compresses it, and uploads it through an encrypted
rclone remote to Google Drive, along with an archive of the configuration files
listed above. Local copies are kept in `/var/backups/sqlite` for 30 days;
remote copies for 30 days, with a monthly tier retained for a year. The database
is the only copy of every audit ever recorded — audits are never written back to
Google Sheets.
