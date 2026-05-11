# Project Summary: Digital Learning Review Dashboard

## 📌 Project Overview

A Streamlit-based web application that aggregates VLE Review audit data from a Google Spreadsheet containing worksheets from multiple schools across semesters, as well as reports generated centrally e.g. Ally Reports and Blackboard Illuminate reports, AI in the curriculum Audit Tell US; basically, any module related data. The dashboard allows users to filter by school and semester to view the data in a clear and concise way.

The dashboard can also incorporate input from module leads or anyone in the faculty in the form of checklists that write into a Google Sheet and this can be visulised in the dashboard in the form of metrics and charts.

There are other datas across the University that could also feed into the dashboard. 

## 🛠️ Tech Stack

- **Language:** Python 3.13
    
- **Libraries:** `streamlit`, `pandas`, `gspread`, `google-auth`.
    
- **Data Source:** Google Sheets.
    


## 📊 Suggested Features

- **Navigation:** Sidebar toggle between "Faculty Overview" and "School Dashboard."
    
- **Advanced Filtering:** Multi-select filters for School and Semester (Aut/Spr) that sync across charts.
    
- **Visuals:** Sorted bar charts showing Ally Scores by Module Code (X-axis).
    
---

## 🚀 Roadmap & To-Do List

- [x] **Module View:** Create a dedicated search/view where a user can input a single Module Code to see its full audit history across both semesters in a "Report Card" format.
    
- [x] **Compliance Visualizations:** Develop "Gap Analysis" charts (e.g., Heatmaps or Pie Charts) specifically highlighting missing elements where the Blackboard template has not been adhered to.
    
- [x] **Performance Thresholds:** Add a "Priority List" showing modules with Ally scores below 70% or missing Assessment Briefs.
    
- [ ] **Data Validation Alerts:** Highlight rows where "Module name" or "URL" is missing to help auditors clean the source sheets.
    
- [x] **Cross-Semester Progress:** Add a metric showing the "Delta" (improvement or decline) in Ally scores from Autumn to Spring.
    
- [x] **Export Feature:** Add a button to download the currently filtered view as a CSV for external faculty reports.
