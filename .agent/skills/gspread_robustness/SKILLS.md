---
name: gspread-robustness
description: Enhances Google Sheets interactions via gspread. Use when optimizing database operations in data_manager.py, handling API rate limits, or modifying checkout checklist schemas.
---
# Gspread API & Sheet Database Robustness Playbook

## Core Goals
* Eliminate API throttling (HTTP 429 Errors).
* Enforce defensive schema-validation for inputs writing back to the Google Sheet.

## Instructions
1. **Batching Reads/Writes**: When updating `data_manager.py` for checklists or feedback tracking, evaluate if operations can be grouped using `spreadsheet.values_update()` or cell-list appends rather than sequential single-cell writes.
2. **Defensive Formatting**: Every transaction writing back to the Google Sheet must go through a type-casting and string-sanitization pipeline inside `processing.py` before execution.
3. **Token Management**: Look for long-running processes or continuous queries and ensure there is an exponential backoff wrapper around the `gspread` connector initialization.

## Constraints
* Never hardcode Spreadsheet IDs, worksheet names, or credential objects into the codebase. Use `os.getenv()`.
* Do not modify existing historical checklist column tracking layout without running a schema validation check.