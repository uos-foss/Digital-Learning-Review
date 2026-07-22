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

def view_module_report(df_aut, df_spr, checklist_sums, df_assess=None, load_checklist_data_cache=None):
    st.title("📋 Module Report")
    
    module_mapping = get_module_mapping(df_aut, df_spr)
    combined_options = sorted([f"{code} - {name}" for code, name in module_mapping.items()])
    
    schools_list = ["ALA", "ECN", "EDC", "GPL", "IJC", "MGT", "SPR"]
    
    user_caps = st.session_state.get("capabilities", [])
    only_own_school = any(c.lower() == "view only own school" for c in user_caps)
    
    if only_own_school:
        st.info(f"Locked to school context: **{st.session_state.saved_school}**")
        combined_options = [opt for opt in combined_options if opt.startswith(st.session_state.saved_school)]
    else:
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
        
        # 1. Overview Metadata Header Card
        if active_row is not None:
            mod_lead = str(active_row.get('Mod. lead', '')).strip()
            if not mod_lead or mod_lead == 'nan':
                mod_lead = "*Not Specified*"
                
            prog_lead = str(active_row.get('Prog. lead', '')).strip()
            if not prog_lead or prog_lead == 'nan':
                prog_lead = "*Not Specified*"
                
            ug_pg = str(active_row.get('UG/ PG/ Other', '')).strip()
            if not ug_pg or ug_pg == 'nan':
                ug_pg = "*Not Specified*"
                
            url = str(active_row.get('URL', '')).strip()
            if url == 'nan':
                url = ''
            
            with st.container(border=True):
                c1, c2, c3, c4 = st.columns(4)
                with c1:
                    st.markdown(f"**👤 Module Lead:**  \n{mod_lead}")
                with c2:
                    st.markdown(f"**🎓 Programme Lead:**  \n{prog_lead}")
                with c3:
                    st.markdown(f"**📚 Level:**  \n{ug_pg}")
                with c4:
                    if url:
                        st.markdown(f"**🔗 VLE Link:**  \n[Open Module Site 🌐]({url})")
                    else:
                        st.markdown("**🔗 VLE Link:**  \n*No URL configured*")
        
        # Check Leganto status
        leganto_missing = False
        if not aut_m.empty and 'Leganto Missing' in aut_m.columns:
            if aut_m.iloc[0]['Leganto Missing'] is True:
                leganto_missing = True
        if not spr_m.empty and 'Leganto Missing' in spr_m.columns:
            if spr_m.iloc[0]['Leganto Missing'] is True:
                leganto_missing = True
                
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

        # 2. Row of KPI metrics
        st.markdown(" ")
        col_m1, col_m2 = st.columns(2)
        with col_m1:
            leg_status = "❌ Missing List" if leganto_missing else "✅ OK / Connected"
            st.metric("Leganto Reading List", leg_status)
            
        with col_m2:
            sa_status = checklist_sums.get(selected_code, {}).get('Status', "❌ No Submission")
            st.metric("Checklist Status", sa_status)
            
        if leganto_missing:
            st.error("⚠️ **Action Required**: This module is currently flagged as **missing a reading list** in Leganto.")
            
        st.markdown(" ")
        
        # 2b. Grouped Ally / Accessibility Profile Card
        with st.container(border=True):
            st.markdown("<h3 style='margin-bottom: 15px;'>VLE Accessibility Profile (Ally)</h3>", unsafe_allow_html=True)
            if pd.notna(ally_score):
                score_val = float(ally_score)
                files_val = int(ally_files) if pd.notna(ally_files) else 0
                
                # A balanced 3-column layout: Score Badge | Progress Bar | Files Scanned Metric
                col_score, col_progress, col_files = st.columns([1.3, 1.7, 1.0])
                
                with col_score:
                    # Color coding logic
                    if score_val >= 0.90:
                        color = "#10B981" # Green
                        level = "Excellent Accessibility"
                    elif score_val >= 0.70:
                        color = "#F59E0B" # Amber/Orange
                        level = "Good Accessibility"
                    elif score_val >= 0.50:
                        color = "#EF4444" # Red
                        level = "Needs Improvement"
                    else:
                        color = "#DC2626" # Deep Red
                        level = "Critical Action Required"
                    
                    st.markdown(f"""
                    <div style="text-align: center; border-radius: 10px; padding: 12px 8px; background-color: {color}10; border: 1px solid {color}33; box-shadow: 0 2px 6px {color}08; margin-top: 5px;">
                        <span style="font-size: 10px; font-weight: 700; color: {color}; text-transform: uppercase; letter-spacing: 0.8px; display: block; margin-bottom: 2px;">{level}</span>
                        <h2 style="margin: 0; color: {color}; font-size: 34px; font-weight: 800; font-family: system-ui, -apple-system, sans-serif;">{score_val:.1%}</h2>
                    </div>
                    """, unsafe_allow_html=True)
                    
                with col_progress:
                    st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)
                    st.markdown("**Ally Score Progress:**")
                    st.progress(score_val)
                    
                with col_files:
                    st.metric("Files Scanned", f"{files_val}", help="Total number of uploaded learning materials and files processed by Ally.")
                    
                st.markdown("<div style='height: 15px;'></div>", unsafe_allow_html=True)
                
                # High score / low file count context warning
                if files_val == 0:
                    st.warning("⚠️ **Low Content Warning**: This module has **0 files** uploaded. While the score displays as 100% or N/A, no files have been scanned to verify accessibility.")
                elif files_val < 5:
                    st.info(f"ℹ️ **Accessibility Compliance Note**: While the Ally score is high, only a low number of files (**{files_val}** files) have been uploaded. A high score on very few files does not automatically indicate comprehensive VLE accessibility.")
            else:
                st.info("No Ally accessibility score data is available for this module.")
            
        st.markdown("---")
        
        # 3. Integration: Add Dynamic Checklist editing/summary
        active_fields = get_active_audit_fields()
        
        # Determine if current user has elevated privileges (DLA or ADMIN)
        username_upper = str(st.session_state.get("username", "")).strip().upper()
        is_dla_or_admin = username_upper in ["DLA", "ADMIN"]
        
        if is_dla_or_admin:
            # Elevated Privilege Mode: Editable Form
            prev_responses = get_audit_responses(selected_code) if selected_code else {}
            comment_bank = get_comment_bank()
            
            with st.expander("📝 Edit Module Checklist", expanded=True):
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
                    new_mod_lead = st.text_input("👤 Module Lead Name:", value=mod_lead)
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
                                responses_input[fid] = st.checkbox(label, value=def_val, help=desc)
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
                                    
                                sel_tags = st.multiselect(
                                    "Select Standard Comments (Tags):",
                                    options=comment_bank,
                                    default=[t for t in prev_tags if t in comment_bank],
                                    key=f"rc_tags_{fid}"
                                )
                                custom_text = st.text_area(
                                    "Additional Custom Comments:",
                                    value=prev_custom,
                                    key=f"rc_custom_{fid}"
                                )
                                responses_input[fid] = {"type": "text", "tags_key": f"rc_tags_{fid}", "custom_key": f"rc_custom_{fid}"}
                                
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
                                    c_val = st.session_state.get(input_info["custom_key"], "")
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
            if selected_code in checklist_sums:
                sum_entry = checklist_sums[selected_code]
                responses = sum_entry.get('Responses', {})
                
                with st.expander(f"Module Checklist Status: {sum_entry.get('Status', 'Yes')}", expanded=True):
                    if not active_fields:
                        st.info("No active checklist fields are defined.")
                    else:
                        for field in active_fields:
                            fid = field['id']
                            label = field['label']
                            ftype = field['field_type']
                            
                            val = responses.get(fid, None)
                            if ftype == 'boolean':
                                status_icon = "✅" if str(val).upper() == 'TRUE' else "❌"
                                st.write(f"**{label}** : {status_icon}")
                            else:
                                st.markdown(f"**{label}** :")
                                if val:
                                    try:
                                        data = json.loads(val)
                                        if isinstance(data, dict) and ("tags" in data or "custom" in data):
                                            tags = data.get("tags", [])
                                            custom = data.get("custom", "")
                                            
                                            if tags:
                                                tag_htmls = []
                                                for tag in tags:
                                                    tag_htmls.append(f'<span style="background-color:#EEF2F6;color:#1E293B;padding:4px 8px;border-radius:16px;font-size:12px;margin-right:5px;border:1px solid #CBD5E1;display:inline-block;margin-bottom:5px">{tag}</span>')
                                                st.markdown(''.join(tag_htmls), unsafe_allow_html=True)
                                                
                                            if custom.strip():
                                                st.write(custom)
                                        else:
                                            st.write(val)
                                    except Exception:
                                        st.write(val)
                                else:
                                    st.caption("*No details provided*")
                    st.caption(f"Last updated: {sum_entry.get('Timestamp', 'Never')} by {sum_entry.get('Auditor', 'Unknown')}")
            else:
                with st.expander("Module Checklist Status: ❌ Incomplete", expanded=True):
                    st.write("No checklist responses submitted yet.")
                    st.caption("Last updated: Never")
        
        # 4. Integration: SITS Assessment Strategy
        if df_assess is not None and not df_assess.empty and 'CIS unit code' in df_assess.columns:
            module_assess = df_assess[df_assess['CIS unit code'] == selected_code]
            if not module_assess.empty:
                with st.expander("📝 SITS Assessment Strategy", expanded=True):
                    cols = st.columns(min(len(module_assess), 3))
                    for idx, (_, row) in enumerate(module_assess.iterrows()):
                        col = cols[idx % len(cols)]
                        with col:
                            title = row.get('Assessment title', 'Assessment')
                            weight = row.get('Assessment weighting', 'N/A')
                            atype = row.get('Assessment type', 'Other')
                            wcount = row.get('Word Count', '')
                            duration = row.get('Exam duration (per hour)', '')
                            is_final = row.get('Final assessment flag', '')
                            reassess = row.get('Reassessment', '')
                            q_mark = row.get('Qualifying mark', '')
                            
                            w_str = f"{weight}%" if str(weight).strip().isdigit() else f"{weight}"
                            
                            with st.container(border=True):
                                st.markdown(f"#### **{title}**")
                                st.markdown(f"**Weighting:** `{w_str}` | **Type:** {atype}")
                                
                                details = []
                                if wcount and str(wcount).strip():
                                    details.append(f"📝 {wcount} words")
                                if duration and str(duration).strip():
                                    details.append(f"⏱️ {duration} hours")
                                if is_final and str(is_final).strip().lower() == 'yes':
                                    details.append("🏁 Final Component")
                                if reassess and str(reassess).strip():
                                    details.append(f"🔄 Reassessment: {reassess}")
                                if q_mark and str(q_mark).strip():
                                    details.append(f"⚠️ Qual. Mark: {q_mark}")
                                    
                                if details:
                                    st.markdown("  \n".join(details))
            else:
                with st.expander("📝 SITS Assessment Strategy", expanded=False):
                    st.info("No SITS assessment strategy records found for this module.")
                    

