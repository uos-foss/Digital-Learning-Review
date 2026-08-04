import streamlit as st
import pandas as pd
import datetime
import logging
import json
from processing import get_module_mapping, FACULTY_SCHOOLS
from database import (
    get_active_audit_fields,
    get_audit_responses,
    get_ai_declarations,
    save_audit_response,
    get_comment_bank,
    update_module_lead_sqlite,
    parse_custom_observations
)

def title_case_name(name: str) -> str:
    if not name:
        return name
    words = name.split()
    title_words = []
    for word in words:
        if '-' in word:
            parts = word.split('-')
            processed_parts = []
            for part in parts:
                p = part.capitalize()
                if p.lower().startswith('mc') and len(p) > 2:
                    p = 'Mc' + p[2:].capitalize()
                elif len(p) > 2 and p[:2].upper() in ["O'", "D'", "L'"]:
                    p = p[:2].upper() + p[2:].capitalize()
                processed_parts.append(p)
            word = '-'.join(processed_parts)
        else:
            word = word.capitalize()
            if word.lower().startswith('mc') and len(word) > 2:
                word = 'Mc' + word[2:].capitalize()
            elif len(word) > 2 and word[:2].upper() in ["O'", "D'", "L'"]:
                word = word[:2].upper() + word[2:].capitalize()
        title_words.append(word)
    return ' '.join(title_words)

def view_module_report(df_aut, df_spr, checklist_sums, df_assess=None, load_checklist_data_cache=None):
    module_mapping = get_module_mapping(df_aut, df_spr)
    combined_options = sorted([f"{code} - {name}" for code, name in module_mapping.items()])
    
    schools_list = list(FACULTY_SCHOOLS)
    
    # Check layout parameter for default layout
    default_mini = False
    if "layout" in st.query_params and st.query_params.get("layout") == "mini":
        default_mini = True
    elif "mini" in st.query_params and st.query_params.get("mini") == "true":
        default_mini = True
        
    if "minified_mode" not in st.session_state:
        st.session_state.minified_mode = default_mini
        
    minified_mode = st.session_state.minified_mode

    if minified_mode:
        st.markdown("""
            <style>
            /* Hide sidebar and collapse control */
            [data-testid="stSidebar"], [data-testid="collapsedControl"] {
                display: none !important;
            }
            /* Hide Streamlit top header bar */
            [data-testid="stHeader"], .stAppHeader {
                display: none !important;
            }
            /* Adjust padding on the main viewport */
            div.block-container {
                padding-top: 1rem !important;
                padding-left: 1rem !important;
                padding-right: 1rem !important;
                padding-bottom: 1rem !important;
            }
            /* Make form containers take full width and less padding */
            div[data-testid="stForm"] {
                padding: 12px !important;
            }
            </style>
        """, unsafe_allow_html=True)

    user_caps = st.session_state.get("capabilities", [])
    only_own_school = any(c.lower() == "view_school" for c in user_caps) and not any(c.lower() == "view_all" for c in user_caps)
    
    if only_own_school:
        if not minified_mode:
            school_context_badge = f" <span style='font-size: 16px; vertical-align: middle; background-color: rgba(59, 130, 246, 0.1); color: #3b82f6; padding: 4px 10px; border-radius: 12px; margin-left: 12px; border: 1px solid rgba(59, 130, 246, 0.2);'>Context: {st.session_state.saved_school}</span>"
            st.markdown(f"<h1>Module Report{school_context_badge}</h1>", unsafe_allow_html=True)
        combined_options = [opt for opt in combined_options if opt.startswith(st.session_state.saved_school)]
    else:
        if not minified_mode:
            st.title("Module Report")
            # Optional multi-tenant school filter to focus without siloing
            if st.session_state.saved_school != "All":
                filter_by_school = st.checkbox(f"Focus on my school ({st.session_state.saved_school})", value=True, key="rc_focus_school")
                if filter_by_school:
                    combined_options = [opt for opt in combined_options if opt.startswith(st.session_state.saved_school)]
                else:
                    selected_school = st.selectbox(
                        "Select School to Focus", 
                        ["All Schools"] + schools_list,
                        index=0,
                        key="rc_school_select",
                        help="Switch to another school's module list."
                    )
                    if selected_school != "All Schools":
                        combined_options = [opt for opt in combined_options if opt.startswith(selected_school)]
            else:
                # Fallback for "All Schools" users (e.g. FACULTY) to filter module list by school
                selected_school = st.selectbox(
                    "Filter by School", 
                    ["All Schools"] + schools_list,
                    index=0,
                    key="rc_school_select_all",
                    help="Filter the module selection list by a specific school."
                )
                if selected_school != "All Schools":
                    combined_options = [opt for opt in combined_options if opt.startswith(selected_school)]
            
    if 'selected_module_code' not in st.session_state:
        st.session_state.selected_module_code = ""

    current_idx = 0
    if st.session_state.selected_module_code:
        for i, opt in enumerate(combined_options):
            if opt.startswith(st.session_state.selected_module_code + " -"):
                current_idx = i + 1
                break

    def on_module_change():
        if st.session_state.unified_search:
            st.session_state.selected_module_code = st.session_state.unified_search.split(" - ")[0]
        else:
            st.session_state.selected_module_code = ""

    col_search, col_mini = st.columns([3, 1])
    with col_search:
        st.selectbox(
            "Search by Module Code or Name", 
            options=[""] + combined_options, 
            index=current_idx, 
            key="unified_search",
            on_change=on_module_change
        )
    with col_mini:
        st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True) # align with selectbox label
        minified_val = st.toggle("Minified View", value=minified_mode, key="minified_mode_toggle", help="Toggle compact single-column layout for side-by-side auditing with Blackboard.")
        if minified_val != minified_mode:
            st.session_state.minified_mode = minified_val
            st.rerun()
    
    selected_code = st.session_state.selected_module_code
    
    if selected_code:
        # Extract Autumn and Spring module audit rows
        aut_m = df_aut[df_aut['New module code'] == selected_code] if not df_aut.empty else pd.DataFrame()
        spr_m = df_spr[df_spr['New module code'] == selected_code] if not df_spr.empty else pd.DataFrame()
        
        # Determine active row for metadata
        active_row = spr_m.iloc[0] if not spr_m.empty else (aut_m.iloc[0] if not aut_m.empty else None)
        
        mod_lead = "Unknown Lead"
        prog_lead = "Unknown Lead"
        ug_pg = "UG"
        url = ""
        
        # Check Leganto status (needed for checklist rendering if we decide to show it)
        leganto_missing = False
        if not aut_m.empty and 'Leganto Missing' in aut_m.columns:
            if aut_m.iloc[0]['Leganto Missing'] is True:
                leganto_missing = True
        if not spr_m.empty and 'Leganto Missing' in spr_m.columns:
            if spr_m.iloc[0]['Leganto Missing'] is True:
                leganto_missing = True

        # 1. Overview Metadata Header Card
        if active_row is not None:
            raw_mod_lead = str(active_row.get('Mod. lead', '')).strip()
            if not raw_mod_lead or raw_mod_lead.lower() == 'nan':
                mod_lead = "<span style='color: #9CA3AF;'>--</span>"
            else:
                mod_lead = title_case_name(raw_mod_lead)
                
            ug_pg = str(active_row.get('UG/ PG/ Other', '')).strip()
            if not ug_pg or ug_pg == 'nan':
                ug_pg = "<span style='color: #9CA3AF;'>--</span>"
                
            url = str(active_row.get('URL', '')).strip()
            if url == 'nan':
                url = ''
                
            sa_status = checklist_sums.get(selected_code, {}).get('Status', "❌ No Submission")
            
            if minified_mode:
                # Render a very compact info bar for side-by-side auditing
                with st.container(border=True):
                    c1, c2 = st.columns(2)
                    with c1:
                        if url:
                            st.markdown(f"🔗 **[Open Blackboard Site 🌐]({url})**")
                        else:
                            st.markdown("⚠️ **VLE Link Missing**")
                    with c2:
                        st.markdown(f"Status: **{sa_status}**")
            else:
                with st.container(border=True):
                    c1, c2, c3, c4 = st.columns(4)
                    with c1:
                        st.markdown(f"**Module Lead:**  \n{mod_lead}", unsafe_allow_html=True)
                    with c2:
                        st.markdown(f"**Level:**  \n{ug_pg}", unsafe_allow_html=True)
                    with c3:
                        if url:
                            st.markdown(f"**VLE Link:**  \n[Open Module Site]({url})", unsafe_allow_html=True)
                        else:
                            st.markdown("**VLE Link:**  \n<span style='color: #9CA3AF;'>--</span>", unsafe_allow_html=True)
                    with c4:
                        st.markdown(f"**Checklist Status:**  \n{sa_status}", unsafe_allow_html=True)
        
        # Extract Ally scores
        ally_score = None
        ally_files = 0
        if active_row is not None:
            ally_score = active_row.get('Ally 25/26 All', None)
            if pd.isna(ally_score):
                ally_score = active_row.get('Ally Weighted', None)
            if pd.isna(ally_score):
                ally_score = active_row.get('Ally Measured', None)
                
            ally_files = active_row.get('Total Files', 0)
            if pd.isna(ally_files) or ally_files == 0:
                ally_files = active_row.get('Ally 25/26 Files', 0)
                
        st.markdown(" ")
        
        # Get latest snapshot date if available in local ally table
        snapshot_date_str = None
        df_ally_local = st.session_state.get("df_ally_local", pd.DataFrame())
        if not df_ally_local.empty and 'module_code' in df_ally_local.columns:
            module_rows = df_ally_local[df_ally_local['module_code'].astype(str).str.strip().str.upper() == selected_code.strip().upper()]
            if not module_rows.empty and 'snapshot_date' in module_rows.columns:
                latest_row = module_rows.sort_values('snapshot_date').iloc[-1]
                raw_date = str(latest_row['snapshot_date'])
                try:
                    parsed_dt = pd.to_datetime(raw_date, errors='coerce')
                    if not pd.isna(parsed_dt):
                        snapshot_date_str = parsed_dt.strftime('%d-%m-%Y')
                    else:
                        snapshot_date_str = raw_date
                except Exception:
                    snapshot_date_str = raw_date

        # 2b. Grouped Ally / Accessibility Profile Card
        if not minified_mode:
            with st.container(border=True):
                st.subheader("Ally Accessibility", help="The accessibility score is credibility-weighted using the Asymptotic Credibility Model (k=0.15, baseline=50%) to ensure reliability even for low file counts.")
                if pd.notna(ally_score):
                    score_val = float(ally_score)
                    files_val = int(ally_files) if pd.notna(ally_files) else 0
                    
                    # A balanced 3-column layout: Score Badge | Progress Bar | Files Scanned Metric
                    col_score, col_progress, col_files = st.columns([1.3, 1.7, 1.0])
                    
                    if files_val == 0:
                        with col_score:
                            st.markdown(f"""
                            <div style="text-align: center; border-radius: 10px; padding: 12px 8px; background-color: #6B728010; border: 1px solid #6B728033; box-shadow: 0 2px 6px #6B728008; margin-top: 5px;">
                                <span style="font-size: 10px; font-weight: 700; color: #6B7280; text-transform: uppercase; letter-spacing: 0.8px; display: block; margin-bottom: 2px;">Ally Score</span>
                                <h2 style="margin: 0; color: #6B7280; font-size: 26px; font-weight: 800; font-family: system-ui, -apple-system, sans-serif; padding: 6px 0;">N/A</h2>
                            </div>
                            """, unsafe_allow_html=True)
                            if snapshot_date_str:
                                st.markdown(f"<div style='text-align: center; margin-top: 5px; font-size: 11px; color: #6B7280;'>Snapshot Date: <b>{snapshot_date_str}</b></div>", unsafe_allow_html=True)
                        with col_progress:
                            st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)
                            st.markdown("**Ally Score Over Time:**")
                            st.caption("No files scanned to evaluate.")
                    else:
                        with col_score:
                            # Color coding logic (matching Blackboard Ally score tiers and descriptions)
                            if score_val >= 1.0:
                                color = "#047857" # Dark Green
                                level = "Perfect"
                                description = "Perfect! No accessibility issues were found by the tool."
                            elif score_val >= 0.67:
                                color = "#10B981" # Light Green
                                level = "High"
                                description = "Almost there. The file is mostly accessible, but minor improvements are still possible."
                            elif score_val >= 0.34:
                                color = "#F59E0B" # Amber/Orange
                                level = "Medium"
                                description = "A little better. The file is somewhat accessible and needs improvement."
                            else:
                                color = "#EF4444" # Red
                                level = "Low"
                                description = "Needs help! The file has severe or multiple accessibility issues."
                            
                            st.markdown(f"""
                            <div style="text-align: center; border-radius: 10px; padding: 12px 8px; background-color: {color}10; border: 1px solid {color}33; box-shadow: 0 2px 6px {color}08; margin-top: 5px;">
                                <span style="font-size: 10px; font-weight: 700; color: {color}; text-transform: uppercase; letter-spacing: 0.8px; display: block; margin-bottom: 2px;">{level} (Weighted)</span>
                                <h2 style="margin: 0; color: {color}; font-size: 34px; font-weight: 800; font-family: system-ui, -apple-system, sans-serif;">{score_val:.1%}</h2>
                            </div>
                            """, unsafe_allow_html=True)
                            
                            if snapshot_date_str:
                                st.markdown(f"<div style='text-align: center; margin-top: 5px; font-size: 11px; color: #6B7280;'>Snapshot Date: <b>{snapshot_date_str}</b></div>", unsafe_allow_html=True)
                            else:
                                st.markdown("<div style='text-align: center; margin-top: 5px; font-size: 11px; color: #6B7280;'>Snapshot Date: <b>Latest Sync</b></div>", unsafe_allow_html=True)
                            
                        with col_progress:
                            st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)
                            st.markdown("**Ally Score Over Time:**")
                            
                            df_ally_local = st.session_state.get("df_ally_local", pd.DataFrame())
                            if not df_ally_local.empty and 'snapshot_date' in df_ally_local.columns:
                                module_history = df_ally_local[df_ally_local['module_code'] == selected_code].copy()
                                if not module_history.empty and len(module_history) > 1:
                                    module_history['snapshot_date'] = pd.to_datetime(module_history['snapshot_date'])
                                    module_history = module_history.sort_values('snapshot_date').set_index('snapshot_date')
                                    st.line_chart(module_history['weighted'], height=100)
                                else:
                                    st.progress(score_val)
                                    st.caption(description)
                            else:
                                st.progress(score_val)
                                st.caption(description)
                        
                    with col_files:
                        st.metric("Files Scanned", f"{files_val}", help="Total number of uploaded learning materials and files processed by Ally.")
                        
                    st.markdown("<div style='height: 15px;'></div>", unsafe_allow_html=True)
                    
                    # Low file count context warning (only for files > 0 but < 5)
                    if 0 < files_val < 5:
                        st.info(f"ℹ️ **Accessibility Compliance Note**: While the Ally score is high, only a low number of files (**{files_val}** files) have been uploaded. A high score on very few files does not automatically indicate comprehensive VLE accessibility.")
                    
                    # Explicit note explaining the weighted score calculation
                    st.caption("ℹ️ Ally Accessibility is calculated using monthly snapshot data, so may be out of date. Refer to your own module's Ally Course Report inside Blackboard. **Weighted Score**: Adjusted via the Asymptotic Credibility Model. Modules with few uploaded files are blended with a neutral 50% baseline score to ensure scores are statistically representative of actual VLE usage.")
                else:
                    st.info("No Ally accessibility score data is available for this module.")
                
            st.markdown("---")
        
        # 3. Integration: Add Dynamic Checklist editing/summary
        active_fields = get_active_audit_fields()
        
        # Determine if current user has edit checklist capabilities
        is_dla_or_admin = any(c.lower() == "edit_checklist" for c in user_caps)
        
        if is_dla_or_admin:
            st.info("ℹ️ **Auditor Mode**: You have permissions to audit this module. To make changes or record observations, please open the dedicated Audit Portal.")
            if st.button("✏️ Open Audit Portal to Edit Checklist", use_container_width=True, key=f"ap_redir_{selected_code}"):
                st.switch_page(st.session_state.pg_audit)
        
        # Read-Only Summary Mode for all users
        pending_items = []
        completed_items = []
        
        # Leganto Reading List status
        if leganto_missing:
            pending_items.append({
                'type': 'boolean',
                'label': 'Leganto Reading List Missing',
                'description': 'This module is currently flagged as missing a reading list in Leganto. Ensure the module\'s reading list is set up and linked in Leganto.'
            })
        else:
            completed_items.append({
                'type': 'boolean',
                'label': 'Leganto Reading List: OK / Connected',
                'description': 'The module has a reading list connected in Leganto.'
            })
            
        has_audit = selected_code in checklist_sums
        last_updated_str = "Never"
        
        if has_audit:
            sum_entry = checklist_sums[selected_code]
            responses = sum_entry.get('Responses', {})
            comment_bank = get_comment_bank()
            last_updated_str = f"{sum_entry.get('Timestamp', 'Never')} by {sum_entry.get('Auditor', 'Unknown')}"
            
            if active_fields:
                compliant_tag_ids = {c['id'] for c in comment_bank if "Compliant" in c.get('category', '') or "No action needed" in c.get('advice', '')}
                cb_lookup = {c['id']: c for c in comment_bank}
                
                for field in active_fields:
                    fid = field['id']
                    label = field['label']
                    action_label = field.get('action_label') or label
                    desc = field['description']
                    ftype = field['field_type']
                    val = responses.get(fid, None)
                    
                    if ftype == 'boolean' or ftype == 'yes/no':
                        if ftype == 'boolean':
                            is_compliant = (str(val).upper() == 'TRUE')
                        else:
                            is_compliant = (str(val).upper() == 'YES')
                            
                        if is_compliant:
                            completed_items.append({
                                'type': 'boolean',
                                'label': label,
                                'description': desc
                            })
                        else:
                            pending_items.append({
                                'type': 'boolean',
                                'label': action_label,
                                'description': desc
                            })
                    elif ftype == 'text' and val:
                        try:
                            data = json.loads(val)
                            if isinstance(data, dict):
                                tags = data.get("tags", [])
                                custom = data.get("custom", "")
                                
                                for tag_id in tags:
                                    tag_info = cb_lookup.get(tag_id)
                                    if tag_info:
                                        is_compliant = tag_id in compliant_tag_ids
                                        if is_compliant:
                                            completed_items.append({
                                                'type': 'tag',
                                                'category': tag_info.get('category', 'General'),
                                                'comment': tag_info.get('comment', ''),
                                                'advice': tag_info.get('advice', ''),
                                                'resource_url': tag_info.get('resource_url', ''),
                                                'resource_text': tag_info.get('resource_text', '')
                                            })
                                        else:
                                            pending_items.append({
                                                'type': 'tag',
                                                'category': tag_info.get('category', 'General'),
                                                'comment': tag_info.get('comment', ''),
                                                'advice': tag_info.get('advice', ''),
                                                'resource_url': tag_info.get('resource_url', ''),
                                                'resource_text': tag_info.get('resource_text', '')
                                            })
                                    else:
                                        pending_items.append({
                                            'type': 'legacy_tag',
                                            'comment': str(tag_id)
                                        })
                                        
                                custom_obs_list = parse_custom_observations(custom)
                                for obs in custom_obs_list:
                                    pending_items.append({
                                        'type': 'custom',
                                        'category': label,
                                        'label': obs.get('observation', ''),
                                        'description': obs.get('action', '')
                                    })
                        except Exception:
                            if str(val).strip():
                                custom_obs_list = parse_custom_observations(val)
                                for obs in custom_obs_list:
                                    pending_items.append({
                                        'type': 'custom',
                                        'category': label,
                                        'label': obs.get('observation', ''),
                                        'description': obs.get('action', '')
                                    })
            
            # Display Actions & Recommendations Expander
            expander_title = f"Actions & Recommendations ({len(pending_items)})"
            parent_pending = st.container() if minified_mode else st.expander(expander_title, expanded=(len(pending_items) > 0))
            with parent_pending:
                if minified_mode:
                    st.markdown(f"#### ⚠️ Actions & Recommendations ({len(pending_items)})")
                if not has_audit:
                    st.markdown("""
                    <div style="border-left: 4px solid #EF4444; background-color: rgba(239, 68, 68, 0.02); padding: 12px 16px; border-radius: 8px; margin-bottom: 12px; border-top: 1px solid rgba(239, 68, 68, 0.05); border-right: 1px solid rgba(239, 68, 68, 0.05); border-bottom: 1px solid rgba(239, 68, 68, 0.05);">
                        <h4 style="margin: 0; color: #EF4444; font-size: 15px; font-weight: 600;">Module Not Yet Audited</h4>
                        <p style="margin: 5px 0 0 0; color: #B91C1C; font-size: 14px;">Please check back later.</p>
                    </div>
                    """, unsafe_allow_html=True)
                
                if has_audit and not pending_items:
                    st.markdown("""
                    <div style="border-left: 4px solid #10B981; background-color: rgba(16, 185, 129, 0.02); padding: 12px 16px; border-radius: 4px; margin-bottom: 12px; border-top: 1px solid rgba(16, 185, 129, 0.05); border-right: 1px solid rgba(16, 185, 129, 0.05); border-bottom: 1px solid rgba(16, 185, 129, 0.05);">
                        <h4 style="margin: 0; color: #047857; font-size: 15px; font-weight: 600;">All Criteria Met</h4>
                        <p style="margin: 5px 0 0 0; color: #065F46; font-size: 14px;">No actionable changes or recommendations are currently pending for this VLE module.</p>
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    for item in pending_items:
                        if item['type'] == 'boolean':
                            title = f"📌 {item['label']}"
                            body = f"{item['description']}"
                            st.markdown(f"""
                            <div style="border-left: 4px solid #F59E0B; background-color: rgba(245, 158, 11, 0.02); padding: 12px 16px; margin-bottom: 12px; border-radius: 4px; border-top: 1px solid rgba(245, 158, 11, 0.05); border-right: 1px solid rgba(245, 158, 11, 0.05); border-bottom: 1px solid rgba(245, 158, 11, 0.05);">
                                <h4 style="margin: 0 0 6px 0; color: #1F2937; font-size: 15px; font-weight: 600;">{title}</h4>
                                <p style="margin: 0; color: #4B5563; font-size: 14px; line-height: 1.5;">{body}</p>
                            </div>
                            """, unsafe_allow_html=True)
                        elif item['type'] == 'tag':
                            title = f"📌 {item['category']}"
                            body = f"<strong>Observation:</strong> {item['comment']}"
                            if item['advice']:
                                body += f"<br/><br/><strong>Action:</strong> {item['advice']}"
                            if item['resource_url']:
                                label_link = item['resource_text'] if item['resource_text'] else "Useful Link / Signpost"
                                body += f"<br/><br/>🔗 <strong>Resource:</strong> <a href='{item['resource_url']}' target='_blank' style='color: #2563EB; text-decoration: underline;'>{label_link}</a>"
                            
                            st.markdown(f"""
                            <div style="border-left: 4px solid #F59E0B; background-color: rgba(245, 158, 11, 0.02); padding: 12px 16px; margin-bottom: 12px; border-radius: 4px; border-top: 1px solid rgba(245, 158, 11, 0.05); border-right: 1px solid rgba(245, 158, 11, 0.05); border-bottom: 1px solid rgba(245, 158, 11, 0.05);">
                                <h4 style="margin: 0 0 6px 0; color: #1F2937; font-size: 15px; font-weight: 600;">{title}</h4>
                                <div style="margin: 0; color: #4B5563; font-size: 14px; line-height: 1.5;">{body}</div>
                            </div>
                            """, unsafe_allow_html=True)
                        elif item['type'] == 'legacy_tag':
                            title = "📌 Legacy Observation"
                            body = f"<strong>Observation:</strong> {item['comment']}"
                            st.markdown(f"""
                            <div style="border-left: 4px solid #F59E0B; background-color: rgba(245, 158, 11, 0.02); padding: 12px 16px; margin-bottom: 12px; border-radius: 4px; border-top: 1px solid rgba(245, 158, 11, 0.05); border-right: 1px solid rgba(245, 158, 11, 0.05); border-bottom: 1px solid rgba(245, 158, 11, 0.05);">
                                <h4 style="margin: 0 0 6px 0; color: #1F2937; font-size: 15px; font-weight: 600;">{title}</h4>
                                <div style="margin: 0; color: #4B5563; font-size: 14px; line-height: 1.5;">{body}</div>
                            </div>
                            """, unsafe_allow_html=True)
                        elif item['type'] == 'custom':
                            title_text = item.get('label', '').strip()
                            if not title_text:
                                title_text = item.get('category', 'Custom Observation')
                            title = f"📌 {title_text}"
                            body = item.get('description', '')
                            
                            import re
                            body_html = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', body)
                            body_html = body_html.replace('\n', '<br/>')
                            st.markdown(f"""
                            <div style="border-left: 4px solid #F59E0B; background-color: rgba(245, 158, 11, 0.02); padding: 12px 16px; margin-bottom: 12px; border-radius: 4px; border-top: 1px solid rgba(245, 158, 11, 0.05); border-right: 1px solid rgba(245, 158, 11, 0.05); border-bottom: 1px solid rgba(245, 158, 11, 0.05);">
                                <h4 style="margin: 0 0 6px 0; color: #1F2937; font-size: 15px; font-weight: 600;">{title}</h4>
                                <p style="margin: 0; color: #4B5563; font-size: 14px; line-height: 1.5;">{body_html}</p>
                            </div>
                            """, unsafe_allow_html=True)
            
            # Display Completed Check Criteria Expander
            with st.expander("View Completed Check Criteria", expanded=False):
                if not completed_items:
                    st.caption("No completed checklist criteria recorded yet.")
                else:
                    for item in completed_items:
                        if item['type'] == 'boolean':
                            st.markdown(f"""
                            <div style="border-left: 4px solid #10B981; background-color: rgba(16, 185, 129, 0.01); padding: 8px 12px; margin-bottom: 8px; border-radius: 4px; border-top: 1px solid rgba(16, 185, 129, 0.02); border-right: 1px solid rgba(16, 185, 129, 0.02); border-bottom: 1px solid rgba(16, 185, 129, 0.02);">
                                <span style="color: #047857; font-weight: 600; font-size: 14px;">✅ {item['label']}</span>
                            </div>
                            """, unsafe_allow_html=True)
                        elif item['type'] == 'tag':
                            st.markdown(f"""
                            <div style="border-left: 4px solid #10B981; background-color: rgba(16, 185, 129, 0.01); padding: 8px 12px; margin-bottom: 8px; border-radius: 4px; border-top: 1px solid rgba(16, 185, 129, 0.02); border-right: 1px solid rgba(16, 185, 129, 0.02); border-bottom: 1px solid rgba(16, 185, 129, 0.02);">
                                <span style="color: #047857; font-weight: 600; font-size: 14px;">✅ {item['category']} Compliant: {item['comment']}</span>
                            </div>
                            """, unsafe_allow_html=True)
                            
            # Render confidential internal notes if user is an auditor
            if is_dla_or_admin and has_audit:
                auditor_notes = str(responses.get('auditor_notes', '')).strip()
                if auditor_notes and auditor_notes.lower() != 'none':
                    st.info(f"🔒 **Auditor Notes (Internal/Auditors Only):**\n\n{auditor_notes}")
                    
            st.caption(f"Last updated: {last_updated_str}")

        # --- AI in the Curriculum ---------------------------------------
        # Declared by the module lead in the satellite AI-Audit app, not by an
        # auditor here. One row per assessment.
        st.divider()
        st.subheader("🤖 AI in the Curriculum")

        ai_rows = get_ai_declarations()
        if not ai_rows.empty:
            ai_rows = ai_rows[ai_rows['module_code'] == str(module_code).strip().upper()]

        if ai_rows.empty:
            st.caption(
                "No declaration submitted for this module yet. Module leads complete "
                "these themselves in the AI in the Curriculum Audit."
            )
        else:
            gen_ai = "Yes" if (
                ai_rows['gen_ai_activity'].astype(str).str.strip().str.lower() == "yes"
            ).any() else "No"
            latest = ai_rows['timestamp'].max()

            st.caption(
                f"Declared by the module lead · {len(ai_rows)} assessment(s) · "
                f"Gen AI engaged learning activity: **{gen_ai}** · last updated {latest}"
            )

            for _, row in ai_rows.iterrows():
                with st.container(border=True):
                    st.markdown(
                        f"**{row.get('assessment_title', 'Assessment')}** "
                        f"({row.get('assessment_type', 'Unknown type')})"
                    )
                    st.write(f"**How usable is generative AI for this assessment?** {row.get('ai_usability', '—')}")
                    st.write(f"**Intended use of generative AI:** {row.get('ai_intended_use', '—')}")

