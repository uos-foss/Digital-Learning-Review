import streamlit as st
import pandas as pd
import datetime
import logging
import json
from processing import get_module_mapping
from database import (
    get_active_audit_fields,
    get_audit_responses,
    save_audit_response,
    get_comment_bank,
    update_module_lead_sqlite
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
    
    schools_list = ["ALA", "ECN", "EDC", "GPL", "IJC", "MGT", "SPR"]
    
    user_caps = st.session_state.get("capabilities", [])
    only_own_school = any(c.lower() == "view only own school" for c in user_caps)
    
    if only_own_school:
        school_context_badge = f" <span style='font-size: 16px; vertical-align: middle; background-color: rgba(59, 130, 246, 0.1); color: #3b82f6; padding: 4px 10px; border-radius: 12px; margin-left: 12px; border: 1px solid rgba(59, 130, 246, 0.2);'>Context: {st.session_state.saved_school}</span>"
        st.markdown(f"<h1>Module Report{school_context_badge}</h1>", unsafe_allow_html=True)
        combined_options = [opt for opt in combined_options if opt.startswith(st.session_state.saved_school)]
    else:
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

    st.selectbox(
        "Search by Module Code or Name", 
        options=[""] + combined_options, 
        index=current_idx, 
        key="unified_search",
        on_change=on_module_change
    )
    
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
                except:
                    snapshot_date_str = raw_date

        # 2b. Grouped Ally / Accessibility Profile Card
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
        
        # Determine if current user has elevated privileges (DLA or ADMIN)
        username_upper = str(st.session_state.get("username", "")).strip().upper()
        is_dla_or_admin = username_upper in ["DLA", "ADMIN"]
        
        preview_mode = False
        if is_dla_or_admin:
            preview_mode = st.toggle("Preview as Standard User", value=False, key=f"preview_mode_{selected_code}")
            
        if is_dla_or_admin and not preview_mode:
            # Elevated Privilege Mode: Editable Form
            prev_responses = get_audit_responses(selected_code) if selected_code else {}
            comment_bank = get_comment_bank()
            cb_options = [c['id'] for c in comment_bank]
            cb_format_map = {c['id']: f"{c['category']}: {c['comment']}" for c in comment_bank}
            def format_cb(cb_id):
                return cb_format_map.get(cb_id, str(cb_id))
            
            if selected_code in checklist_sums:
                sum_entry = checklist_sums[selected_code]
                audit_status = sum_entry.get('Status', '❌ Not Audited')
                actionable = sum_entry.get('Actionable Items', 0)
            else:
                audit_status = '❌ Not Audited'
                actionable = 0
                
            if leganto_missing:
                actionable += 1
                
            expander_title = f"📝 Edit Module Checklist ({audit_status} | {actionable} Actionable Items)"
                
            with st.expander(expander_title, expanded=True):
                # Check when it was last updated
                last_updated = None
                last_auditor = None
                if prev_responses:
                    ts_vals = [r['timestamp'] for r in prev_responses.values() if r['timestamp']]
                    auditor_vals = [r['auditor'] for r in prev_responses.values() if r['auditor']]
                    if ts_vals:
                        last_updated = max(ts_vals)
                    if auditor_vals:
                        last_auditor = auditor_vals[-1]
                
                if last_updated:
                    st.info(f"Last updated: {last_updated} by {last_auditor}. Showing current answers below.")
                else:
                    st.info("No checklist details submitted yet for this module.")
                
                with st.form("module_checklist_edit_form"):
                    new_mod_lead = st.text_input("Module Lead Name:", value=mod_lead)
                    st.markdown("---")
                    
                    # Automated Leganto Reading List check
                    leganto_label = "Leganto Reading List: OK / Connected" if not leganto_missing else "Leganto Reading List: Missing List"
                    st.checkbox(
                        f"**{leganto_label}**",
                        value=not leganto_missing,
                        disabled=True,
                        help="Automatically determined from system records. To fix this, set up the module's reading list in Leganto.",
                        key=f"rc_chk_{selected_code}_leganto_auto"
                    )
                    st.markdown("---")
                    
                    responses_input = {}
                    if not active_fields:
                        st.warning("No active audit fields are defined. Contact an administrator to add fields.")
                    else:
                        for field in active_fields:
                            fid = field['id']
                            label = field['label']
                            desc = field['description']
                            ftype = field['field_type']
                            
                            prev_val = prev_responses.get(fid, {}).get('value', None)
                            
                            if ftype == 'boolean':
                                def_val = str(prev_val).upper() == 'TRUE' if prev_val is not None else False
                                responses_input[fid] = st.checkbox(label, value=def_val, help=desc, key=f"rc_chk_{selected_code}_{fid}")
                            elif ftype == 'text':
                                prev_tags = []
                                prev_custom = ""
                                if prev_val:
                                    try:
                                        data = json.loads(prev_val)
                                        if isinstance(data, dict) and ("tags" in data or "custom" in data):
                                            prev_tags = data.get("tags", [])
                                            prev_custom = data.get("custom", "")
                                        else:
                                            prev_custom = prev_val
                                    except Exception:
                                        prev_custom = prev_val
                                        
                                st.markdown(f"**{label}**")
                                if desc:
                                    st.caption(desc)
                                    
                                cb_options = [c['id'] for c in comment_bank]
                                mapped_prev_tags = []
                                for pt in prev_tags:
                                    if isinstance(pt, int) and pt in cb_options:
                                        mapped_prev_tags.append(pt)
                                    elif isinstance(pt, str):
                                        matched = False
                                        for c in comment_bank:
                                            if c['comment'] == pt:
                                                mapped_prev_tags.append(c['id'])
                                                matched = True
                                                break
                                        if not matched:
                                            prev_custom = (pt + "\n" + prev_custom) if prev_custom else pt
                                            
                                sel_tags = st.multiselect(
                                    "Select Standard Comments (Tags):",
                                    options=cb_options,
                                    default=mapped_prev_tags,
                                    format_func=format_cb,
                                    key=f"rc_tags_{selected_code}_{fid}"
                                )
                                default_template = "**Observation:** \n\n**Action:** "
                                custom_val = prev_custom if prev_custom.strip() else default_template
                                custom_text = st.text_area(
                                    "Additional Custom Observations:",
                                    value=custom_val,
                                    key=f"rc_custom_{selected_code}_{fid}"
                                )
                                responses_input[fid] = {"type": "text", "tags_key": f"rc_tags_{selected_code}_{fid}", "custom_key": f"rc_custom_{selected_code}_{fid}"}
                                
                    st.markdown("---")
                    prev_audited = str(prev_responses.get('system_audit_complete', {}).get('value', 'False')).upper() == 'TRUE'
                    responses_input['system_audit_complete'] = st.checkbox(
                        "**Mark this module as officially audited**", 
                        value=prev_audited, 
                        help="Tick this box to officially mark the module as audited in the system.",
                        key=f"sys_audit_{selected_code}"
                    )
                    
                    submitted = st.form_submit_button("Save Updates")
                    if submitted:
                        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        try:
                            # Save module lead update if changed
                            if new_mod_lead.strip() != mod_lead:
                                update_module_lead_sqlite(selected_code, new_mod_lead)
                                
                            for fid, input_info in responses_input.items():
                                if isinstance(input_info, dict) and input_info.get("type") == "text":
                                    t_val = st.session_state.get(input_info["tags_key"], [])
                                    c_val = st.session_state.get(input_info["custom_key"], "").strip()
                                    if c_val == "**Observation:** \n\n**Action:**" or c_val == "**Observation:**\n\n**Action:**":
                                        c_val = ""
                                    combined_val = json.dumps({"tags": t_val, "custom": c_val})
                                    save_audit_response(selected_code, fid, combined_val, username_upper, timestamp)
                                else:
                                    save_audit_response(selected_code, fid, str(input_info), username_upper, timestamp)
                                    
                            # Invalidate all st.cache_data to refresh sit list & checklist immediately
                            st.cache_data.clear()
                            
                            logging.info(f"✅ Checklist and metadata updated successfully for module '{selected_code}' by '{username_upper}'.")
                            st.success("Updates saved successfully!")
                            st.rerun()
                        except Exception as e:
                            logging.error(f"❌ Error updating module data for '{selected_code}': {e}")
                            st.error(f"Error saving updates: {e}")
                            
        else:
            # Read-Only Summary Mode for non-elevated users
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
                        
                        if ftype == 'boolean':
                            is_compliant = (str(val).upper() == 'TRUE')
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
                                    custom = data.get("custom", "").strip()
                                    
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
                                    if custom and custom.strip() not in ("", "**Observation:**", "**Observation:** \n\n**Action:**", "**Observation:**\n\n**Action:**"):
                                        pending_items.append({
                                            'type': 'custom',
                                            'comment': custom
                                        })
                            except Exception:
                                if str(val).strip():
                                    pending_items.append({
                                        'type': 'custom',
                                        'comment': str(val)
                                    })
            
            # Display Actions & Recommendations Expander
            expander_title = f"Actions & Recommendations ({len(pending_items)})"
            with st.expander(expander_title, expanded=(len(pending_items) > 0)):
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
                            title = f"❌ {item['label']}"
                            body = f"{item['description']}"
                            st.markdown(f"""
                            <div style="border-left: 4px solid #EF4444; background-color: rgba(239, 68, 68, 0.02); padding: 12px 16px; margin-bottom: 12px; border-radius: 4px; border-top: 1px solid rgba(239, 68, 68, 0.05); border-right: 1px solid rgba(239, 68, 68, 0.05); border-bottom: 1px solid rgba(239, 68, 68, 0.05);">
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
                            title = "📝 Auditor Note"
                            body = f"{item['comment']}"
                            import re
                            body_html = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', body)
                            body_html = body_html.replace('\n', '<br/>')
                            st.markdown(f"""
                            <div style="border-left: 4px solid #6B7280; background-color: rgba(107, 114, 128, 0.02); padding: 12px 16px; margin-bottom: 12px; border-radius: 4px; border-top: 1px solid rgba(107, 114, 128, 0.05); border-right: 1px solid rgba(107, 114, 128, 0.05); border-bottom: 1px solid rgba(107, 114, 128, 0.05);">
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
                            
            st.caption(f"Last updated: {last_updated_str}")
        
        # SITS Assessment Strategy removed as per request
        pass

