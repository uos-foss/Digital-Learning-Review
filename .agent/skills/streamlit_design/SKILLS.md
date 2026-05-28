---
name: streamlit-design
description: Enforces user interface design systems, layouts, and front-end styling constraints across Streamlit view components. Use when modifying page layouts, sidebars, charts, or injecting custom HTML/CSS wrappers.
---
# Streamlit Interface Design & Layout Playbook

## Core Goals
* Maintain a seamless, responsive, and unified UI/UX layout across all dashboards and viewports.
* Eliminate disruptive component-shifting, broken containers, and layout regressions during state re-runs.
* Enforce clear typography hierarchical boundaries and clean visual asset placement.

## Technical Alignment & Constraints
* **Streamlit Engine:** Python 3.13 / Streamlit container system.
* **State Syncing:** Every layout choice must coordinate natively with `st.session_state` keys to keep interaction views non-shifting.
* **No Inline Markdown Chaos:** Do not inject raw, un-sanitized HTML strings for layout structural components; rely heavily on Streamlit's structural layout primitives.

---

## Layout Rules & Implementation Directives

### 1. Structural Containment & Page Hierarchy
* **Sidebar Controls:** Keep the global control plane isolated inside the sidebar layout. Use full-width action buttons or dedicated structural toggles to separate core data operations from help, documentation, or changelog views.
* **Segmented Navigation:** Replace inert HTML tabs or unstable layout selectors with stateful segmented widgets (`st.segmented_control` or custom callback-bound radios). 
  * *Rule:* Every interactive view controller must bind explicitly to an `on_change` state callback function to guarantee immediate view-state retention across continuous re-runs.
* **Lazy Columns:** When utilizing multi-column grids (`st.columns()`), ensure code evaluation logic inside sub-columns operates only if relevant data exists. Prevent un-audited or missing data slots from defaulting to awkward blank rows; instead, materialize explicit visual audit placeholder cards (e.g., "❌ Incomplete Self-Audit").

### 2. Metrics & Data Visualizations (Charts)
* **Alignment Across Views:** Ensure that structural layout sections (such as analytics tabs) inside the `School Dashboard` replicate the exact same structural hierarchy and naming conventions as the `Faculty Overview` for user UX continuity.
* **Chart Clarity:** Chart components (e.g., sorted horizontal/vertical bar charts, data distribution donut charts) must maintain a fixed, predictable axis profile. Always declare the explicit category dimension (e.g., Module Code) cleanly along chart boundaries.
* **Interactive Linking:** High-level tables or matrix overviews should be formatted as interactive row-selectors where possible. Selecting a visual row layout entity must trigger a non-shifting direct action launch pad or route instantly to deep-linked details.

### 3. Native Styling vs. Custom CSS Overrides
* **CSS Safety:** Only use `st.markdown(..., unsafe_allow_html=True)` when embedding isolated visual presentation resources (like standalone slide decks or static asset templates).
* **Responsive Control Containers:** Never attempt to adjust component margins, view widths, or structural padded grid columns using manual HTML `<div style="...">` tags inside Markdown elements. Rely exclusively on:
  * `st.container()` for logical, clean card groupings.
  * `st.expander()` for collapsible secondary action tools.
  * `st.popover()` for configuration details or supplementary user feedback interfaces.

## Verification Checklist
Before finishing any layout or style modification task:
1. Run the Streamlit layout locally and click through every segmented router state to ensure viewports do not shift or break alignment.
2. Verify that changing a sidebar parameter (like a focus school toggle or semester choice) does not cause double-press re-runs or drop active view context memory.
3. Confirm that all dashboard components render beautifully on both desktop widescreen views and narrower browser footprints without overflowing tables or breaking layout grids.