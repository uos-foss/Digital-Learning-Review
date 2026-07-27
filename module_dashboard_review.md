# Streamlit Dashboard Design Review & UI/UX Recommendations

**Target Application:** Blackboard Module Readiness Portal (Streamlit)

**Date:** July 2026

## 1. Executive Summary

Overall, the **FoSS Digital Learning Review Portal** presents a clean, functional, and modern baseline design. The layout makes good use of cards, clear color contrast, and structured expanders. Following recent updates, the audit checklist section has been streamlined into an **Actions & Recommendations** workflow. Remaining refinements focus on visual hierarchy, edge-case data logic, typography consistency, and spatial density.

## 2. Key Areas for Improvement

### 2.1. Data Logic & Section Restructuring

- **Conflicting Metric States:**
    
    - **Issue:** The _VLE Accessibility Profile (Ally)_ displays a score of **80.5%** alongside a progress bar, but directly adjacent to it, _Files Scanned_ shows `0`. Below it, a warning banner explicitly notes: _"This module has 0 files uploaded. While the score displays as 100% or N/A..."_.
        
    - **Recommendation:** Hide or disable the numeric score and progress bar when `0` files exist. Instead, display a clear fallback state such as `N/A - No files scanned` to prevent user confusion regarding calculated scores on empty datasets.
        
- **Actionable Items Count & Audit Checklist Restructuring:** `[RESOLVED]`
    
    - **Previous Issue:** The main expander header stated **"Actionable Items: 3"**, but displaying green ticks alongside red crosses made the count feel unintuitive.
        
    - **Implemented Solution:** Restructured the audit section into **"Actions & Recommendations"**. Passing criteria (green checkmarks) are hidden from the primary view to eliminate visual clutter, and incomplete items are rendered directly as descriptive action items alongside comments.
        

### 2.2. Visual Hierarchy & Formatting

- **Emoji Usage & Standardization:**
    
    - **Issue:** The interface uses multiple disparate emoji styles across titles, headers, labels, and status badges (📋, 🎓, 📚, 🔗, 📌, 📝). This can make the dashboard feel slightly unpolished or busy.
        
    - **Recommendation:** Standardize on standard vector/SVG icons (such as Lucide or FontAwesome via Streamlit components) for navigation and section headings. Reserve emojis strictly for functional status indicators (e.g., standard green ticks ✅ and red crosses ❌).
        
- **Checklist Formatting:**
    
    - **Issue:** Plain text key-value pairs formatted with colon spacing (e.g., `Welcome message present? : ✅`) feel unformatted and unevenly aligned.
        
    - **Recommendation:** Replace raw key-value strings with structured alert banners, card components, or a clean table view.
        

### 2.3. Layout & Spatial Density

- **Top Navigation & Banner Real Estate:**
    
    - **Issue:** The blue banner `Locked to school context: EDC` takes up prominent top-level vertical space directly beneath the main title.
        
    - **Recommendation:** If school context is fixed or purely informative, move it into a smaller header badge (e.g., next to the title as a pill tag `Module Report • Context: EDC`) or place it in the sidebar under the organization details to save primary screen height.
        
- **Metadata Alignment:**
    
    - **Issue:** In the module metadata section (`Module Lead`, `Programme Lead`, `Level`, `VLE Link`), missing data is rendered as _`Not Specified`_ in italics, while other values use regular font weights.
        
    - **Recommendation:** Use uniform placeholder styling across all metadata fields (e.g., greyed out `--` or `Unassigned`) to preserve visual alignment.
        
- **Nested Container Density:**
    
    - **Issue:** Deeply nested shaded callout blocks (like the blue _Accessibility_ observation inside the _Module Audit Status_ expander) can cause visual clutter on smaller screens.
        
    - **Recommendation:** Format recommendations with lightweight subheadings and left border accents rather than heavy full-width nested callout boxes.
        

## 3. Prioritized Action Plan

|   |   |   |   |
|---|---|---|---|
|**Priority**|**Feature / Area**|**Recommended Action**|**Status**|
|**High**|Audit Restructuring|Convert audit block into **"Actions & Recommendations"**. Hide passing ticks and list actionable tasks alongside comments.|**Resolved**|
|**High**|Data Logic|Suppress percentage scores and progress bar when `Files Scanned == 0`. Display `N/A`.|Pending|
|**Medium**|Layout Efficiency|Move `Locked to school context` callout into a badge beside the title or into the sidebar.|Pending|
|**Medium**|Typography|Format action items using structured alert boxes or card views instead of plain text with colons.|Pending|
|**Low**|Iconography|Standardize icons across section headers and remove redundant emojis.|Pending|

## 4. Updated Structural Refinement Concept

```
+-------------------------------------------------------------------------------+
| Module Report  [Badge: EDC Context]                                           |
| Search: [ EDC001 - Foundations of Biology (Human)                       v ] |
+-------------------------------------------------------------------------------+
| Module Lead: Lizzy Shaw | Prog Lead: -- | Level: Foundation | VLE: [Link]      |
+-------------------------------------------------------------------------------+
|  Leganto Reading List       |  Checklist Status                               |
|  [ OK / Connected ]         |  [ Audited ]                                    |
+-------------------------------------------------------------------------------+
|  VLE Accessibility Profile (Ally)                                            |
|  [ N/A - No Files Scanned ] | Ally Score Over Time: [--] | Files Scanned: 0 |
|  (!) Low Content Warning: No files uploaded to evaluate.                      |
+-------------------------------------------------------------------------------+
| > Actions & Recommendations (3 Pending)                                       |
|                                                                               |
|   1. ❌ Assessment Brief Missing                                              |
|      The assessment brief is missing. Please upload or link the brief.        |
|                                                                               |
|   2. ❌ Assessment Overview Mismatch                                         |
|      Assessment overview is inconsistent with SITS. Please review module info. |
|                                                                               |
|   3. 📌 Accessibility Observation                                            |
|      Some uploaded slides are missing image descriptions.                      |
|      Action: Add alternative text (alt text) to images.                       |
|                                                                               |
|   [ > View Completed Check Criteria (Click to expand) ]                      |
+-------------------------------------------------------------------------------+
```