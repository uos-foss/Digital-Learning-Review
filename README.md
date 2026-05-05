# Project Summary: Digital Learning Review Dashboard

## 📌 Project Overview

A Streamlit-based web application that aggregates VLE Review audit data from a Google Spreadsheet containing worksheets from multiple schools across semesters, as well as reports generated centrally e.g. Ally Reports and Blackboard Illuminate reports. The dashboard allows users to filter by school and semester to view the data in a clear and concise way.

The dashboard will also incorporate input from module leads in the form of checklists that write into a

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

- [ ] **Module View:** Create a dedicated search/view where a user can input a single Module Code to see its full audit history across both semesters in a "Report Card" format.
    
- [ ] **Compliance Visualizations:** Develop "Gap Analysis" charts (e.g., Heatmaps or Pie Charts) specifically highlighting missing elements where the Blackboard template has not been adhered to.
    
- [ ] **Performance Thresholds:** Add a "Priority List" showing modules with Ally scores below 70% or missing Assessment Briefs.
    
- [ ] **Data Validation Alerts:** Highlight rows where "Module name" or "URL" is missing to help auditors clean the source sheets.
    
- [ ] **Cross-Semester Progress:** Add a metric showing the "Delta" (improvement or decline) in Ally scores from Autumn to Spring.
    
- [ ] **Export Feature:** Add a button to download the currently filtered view as a CSV for external faculty reports.