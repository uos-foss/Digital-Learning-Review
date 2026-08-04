# Digital Learning Review Dashboard

A Streamlit web application for the Faculty of Social Sciences VLE audit. It
aggregates module data from SITS, Ally, Leganto and Blackboard, and gives
Digital Learning Advisors a place to record audit findings and report on
accessibility and VLE compliance across the faculty's seven schools.

Deployed at
[fossdigital.shef.ac.uk/digital-learning-review](https://fossdigital.shef.ac.uk/digital-learning-review/).

**What it is measured against:**
- Ally accessibility scores across modules.
- Compliance with the VLE audit checklist.

## 🛠️ Tech Stack

- **Language:** Python 3.11
- **Framework:** Streamlit
- **Database:** SQLite (WAL mode, on a shared host volume)
- **Data:** Pandas, Google Sheets API (`gspread`, `google-auth`, `tenacity`)
- **Deployment:** Docker & Docker Compose on an Ubuntu VM behind Caddy

## 📊 How Data Flows

**SQLite is the source of truth.** Every page reads from it. Google Sheets is
an upstream source only, drained into SQLite by `sync_data.py` when an
administrator triggers a full sync — it is not touched during a page load.

| Source | Contents | Updated |
| :--- | :--- | :--- |
| SITS | Module list, teaching periods, assessment strategy | Annually |
| Ally | Accessibility scores and file counts, with history | Monthly |
| Leganto | Modules missing a reading list | Monthly |
| Blackboard | Module VLE links | CSV import in the Admin Panel |
| Audits | Advisor findings per module | Saved in the app |

Audits and feedback are written to SQLite and never pushed back to a
spreadsheet. Write-back is limited to the comment bank and audit field
definitions.

## 🚀 Features

- **Faculty Overview** — School Comparison, Ally analytics, compliance gap,
  priority actions and SITS assessment types across all seven schools.
- **School Dashboard** — The same analysis scoped to one school, plus a module
  roster and accessibility trends over time.
- **Module report** — A single module in full: metadata, Ally profile,
  reading-list status, audit responses and assessment strategy.
- **Audit Portal** — Where advisors record findings, notes for the module lead,
  and internal notes. Audits save as a draft and submit when complete.
- **Admin Panel** — Users and roles, audit field configuration, data
  import/export, inactive modules, logs and a database explorer.

## 🔐 Access Control

Sign-in supports a username and password held in SQLite (default) or **Sign in
with Google**, selected by `AUTH_PROVIDER`. Passwords are hashed with scrypt.

Access is driven by capabilities attached to a role:

| Role | Capabilities |
| :--- | :--- |
| `admin` | `view_all`, `edit_checklist`, `access_admin_panel` |
| `DLA` | `view_all`, `edit_checklist` |
| `SA` | `view_school`, `edit_checklist` |
| `FOSS` | `view_all` |
| `SL` | `view_all` |
| `ML` | `view_school` |

## ▶️ Running It

Configuration comes from a `.env` file — see `docs/developer-guide.md` for the
variables involved.

```bash
# Local
pip install -r REQUIREMENTS.txt
streamlit run app.py

# Production
docker compose up -d --build
```

The database is created on first run. In production it lives on the host at
`/opt/shared-audit-data`, mounted into the container, so it survives rebuilds.

## 📚 Documentation

- **[CLAUDE.md](CLAUDE.md)** — conventions and constraints for anyone (or
  anything) changing the code.
- **[docs/developer-guide.md](docs/developer-guide.md)** — architecture,
  database location, auth providers, deployment. Also rendered in-app under
  Resources & Support.
- **[deploy/RESTORE.md](deploy/RESTORE.md)** — recovery runbook: database
  restore, full VM rebuild, and what the backups do and don't cover.
- **[docs/changelog.md](docs/changelog.md)** — release history.
- **[docs/help.md](docs/help.md)** — the in-app user guide.
- **[SPEC.md](SPEC.md)** — the original project brief. Historical; kept for
  provenance and no longer accurate.

## 🗺️ Roadmap

- UI/UX refresh and aesthetic improvements.
- Integration of additional audit data sources.
- Drop the frozen `main_vle_audit_*` baseline tables once the live audit set
  covers enough modules to replace the 25/26 reference fields they still
  supply (Prog. lead, module URLs, and the Ally/Leganto fallbacks). The
  upstream spreadsheet behind them was retired in v1.15.0.
