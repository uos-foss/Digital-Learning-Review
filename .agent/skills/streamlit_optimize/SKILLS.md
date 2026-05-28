---
name: streamlit-optimize
description: Refactors and optimizes Streamlit application files. Use when adjusting view rendering, fixing state mutations, optimizing st.cache_data, or handling session-state bugs.
---
# Streamlit Performance & State Optimization Guide

## Core Goals
* Prevent unnecessary script re-executions.
* Enforce memory-efficient data mutations using pandas and Streamlit session states.

## Instructions
1. **Session State Interception**: When modifying `views/` or `app.py`, ensure any interactive input widgets (like the Select Semester radio button) are bound explicitly to `st.session_state` keys. Use immediate `on_change` callback functions rather than downstream conditional logic to update state keys.
2. **Cache Boundaries**: 
   * Use `st.cache_data` strictly for low-level read operations pulling from `data_manager.py`.
   * Never place un-hashable parameters (like live `gspread` client instances) inside cached function signatures.
3. **Lazy Execution**: When editing the `views/` router, ensure code evaluation is completely isolated inside active conditional branches to preserve the lazy-loading architecture.

## Constraints
* Do not duplicate dataframe memory allocations; mutate in-place or use lightweight filtered views.
* Do not break the cookie persistence layer managed by `stx.CookieManager`.