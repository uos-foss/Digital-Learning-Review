# Digital Learning Review Dashboard

## 📌 Project Overview
The Digital Learning Review Dashboard is a Streamlit-based web application that aggregates and visualizes Virtual Learning Environment (VLE) audit data. It serves as a central hub for faculty to track compliance, accessibility scores, and review audit checklists across various modules, schools, and semesters.

**Key KPIs Monitored:**
- High Ally accessibility scores across modules.
- Full compliance with module lead audit checklists.

## 🛠️ Tech Stack & Architecture
- **Language:** Python 3.13
- **Framework:** Streamlit
- **Data:** SQLite, Pandas, Google Sheets API (`gspread`, `google-auth`)
- **Deployment:** Docker & Docker Compose (Ubuntu VM at [https://fossdigital.shef.ac.uk/digital-learning-review/](https://fossdigital.shef.ac.uk/digital-learning-review/))

## 📊 Data Sources
The dashboard relies on multiple Google Sheets for data:
- **Main Audit Data**: Manually updated by auditors.
- **Ally Accessibility Scores**: Updated monthly.
- **Leganto Lists**: Missing reading lists, updated monthly.
- **Audit Checklist**: Synchronous input from module leads and support staff.
- **SITS Assessment Data**: Updated annually.

## 🚀 Core Features
- **School Dashboard & Faculty Overview:** Filtered views for high-level and granular data.
- **Module Report Card:** Deep dive into specific module compliance.
- **Module Checklist:** Interactive auditing tool.
- **Capability-Based Access:** Content visibility is tailored to specific roles (`ADMIN`, `DLA`, and capabilities).

## 🗺️ Roadmap
- UI/UX Refresh and aesthetic improvements.
- Integration of additional audit data sources.
- Implementation of alternative authentication methods.

For a comprehensive architectural overview, please refer to the [SPEC.md](SPEC.md) file.
