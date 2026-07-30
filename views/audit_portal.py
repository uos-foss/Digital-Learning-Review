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

def view_audit_portal(df_aut, df_spr, checklist_sums, df_assess=None):
    user_caps = st.session_state.get("capabilities", [])
    if "edit_checklist" not in [c.lower() for c in user_caps]:
        st.error("Access Denied: You do not have permission to access the Audit Portal.")
        st.stop()
        
    user_role = str(st.session_state.get("user_role", "")).strip().upper()
    is_sa = (user_role == "SA")
    is_dla_or_admin = user_role in ("ADMIN", "DLA")
    
    # In fallback or unmapped situations, default to simple view if not specifically elevated
    is_full_view = is_dla_or_admin

    module_mapping = get_module_mapping(df_aut, df_spr)
    combined_options = sorted([f"{code} - {name}" for code, name in module_mapping.items()])
    
    schools_list = ["ALA", "ECN", "EDC", "GPL", "IJC", "MGT", "SPR"]
    
    # Default layouts & minified toggles
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
            [data-testid="stSidebar"], [data-testid="collapsedControl"] {
                display: none !important;
            }
            [data-testid="stHeader"], .stAppHeader {
                display: none !important;
            }
            div.block-container {
                padding-top: 1rem !important;
                padding-left: 1rem !important;
                padding-right: 1rem !important;
                padding-bottom: 1rem !important;
            }
            div[data-testid="stForm"] {
                padding: 12px !important;
            }
            </style>
        """, unsafe_allow_html=True)

    # Context title based on role
    role_badge = "School Auditor" if is_sa else ("DLA" if user_role == "DLA" else "Administrator")
    title_suffix = f" <span style='font-size: 16px; vertical-align: middle; background-color: rgba(16, 185, 129, 0.1); color: #10b981; padding: 4px 10px; border-radius: 12px; margin-left: 12px; border: 1px solid rgba(16, 185, 129, 0.2);'>{role_badge} View</span>"
    
    if not minified_mode:
        st.markdown(f"<h1>VLE Review Audit Portal{title_suffix}</h1>", unsafe_allow_html=True)
    else:
        st.markdown(f"### VLE Audit Portal ({role_badge})")
        
    # School-level filtering
    only_own_school = any(c.lower() == "view_school" for c in user_caps) and not any(c.lower() == "view_all" for c in user_caps)
    if only_own_school:
        combined_options = [opt for opt in combined_options if opt.startswith(st.session_state.saved_school)]
    else:
        if not minified_mode:
            if st.session_state.saved_school != "All":
                filter_by_school = st.checkbox(f"Focus on my school ({st.session_state.saved_school})", value=True, key="ap_focus_school")
                if filter_by_school:
                    combined_options = [opt for opt in combined_options if opt.startswith(st.session_state.saved_school)]
                else:
                    selected_school = st.selectbox("Select School to Focus", ["All Schools"] + schools_list, key="ap_school_select")
                    if selected_school != "All Schools":
                        combined_options = [opt for opt in combined_options if opt.startswith(selected_school)]
            else:
                selected_school = st.selectbox("Filter by School", ["All Schools"] + schools_list, key="ap_school_select_all")
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
        if st.session_state.ap_unified_search:
            st.session_state.selected_module_code = st.session_state.ap_unified_search.split(" - ")[0]
        else:
            st.session_state.selected_module_code = ""

    col_search, col_mini = st.columns([3, 1])
    with col_search:
        st.selectbox(
            "Select Module to Audit", 
            options=[""] + combined_options, 
            index=current_idx, 
            key="ap_unified_search",
            on_change=on_module_change
        )
    with col_mini:
        st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
        minified_val = st.toggle("Minified View", value=minified_mode, key="ap_minified_mode_toggle")
        if minified_val != minified_mode:
            st.session_state.minified_mode = minified_val
            st.rerun()

    selected_code = st.session_state.selected_module_code
    if selected_code:
        aut_m = df_aut[df_aut['New module code'] == selected_code] if not df_aut.empty else pd.DataFrame()
        spr_m = df_spr[df_spr['New module code'] == selected_code] if not df_spr.empty else pd.DataFrame()
        active_row = spr_m.iloc[0] if not spr_m.empty else (aut_m.iloc[0] if not aut_m.empty else None)
        
        mod_lead = "Unknown Lead"
        ug_pg = "UG"
        url = ""
        
        leganto_missing = False
        if not aut_m.empty and 'Leganto Missing' in aut_m.columns:
            if aut_m.iloc[0]['Leganto Missing'] is True:
                leganto_missing = True
        if not spr_m.empty and 'Leganto Missing' in spr_m.columns:
            if spr_m.iloc[0]['Leganto Missing'] is True:
                leganto_missing = True

        if active_row is not None:
            raw_mod_lead = str(active_row.get('Mod. lead', '')).strip()
            mod_lead = title_case_name(raw_mod_lead) if (raw_mod_lead and raw_mod_lead.lower() != 'nan') else "--"
            ug_pg = str(active_row.get('UG/ PG/ Other', '')).strip()
            ug_pg = ug_pg if (ug_pg and ug_pg != 'nan') else "--"
            url = str(active_row.get('URL', '')).strip()
            if url == 'nan': url = ''
            
            sa_status = checklist_sums.get(selected_code, {}).get('Status', "❌ No Submission")
            
            # Module Metadata Header
            with st.container(border=True):
                if minified_mode:
                    c1, c2 = st.columns(2)
                    with c1:
                        if url:
                            st.markdown(f"🔗 **[Open Blackboard Site 🌐]({url})**")
                        else:
                            st.markdown("⚠️ **VLE Link Missing**")
                    with c2:
                        st.markdown(f"Status: **{sa_status}**")
                else:
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

        # Retrieve snapshot date and local ally details
        ally_score = None
        ally_files = 0
        if active_row is not None:
            ally_score = active_row.get('Ally 25/26 All', None)
            if pd.isna(ally_score): ally_score = active_row.get('Ally Weighted', None)
            if pd.isna(ally_score): ally_score = active_row.get('Ally Measured', None)
            
            ally_files = active_row.get('Total Files', 0)
            if pd.isna(ally_files) or ally_files == 0:
                ally_files = active_row.get('Ally 25/26 Files', 0)

        snapshot_date_str = None
        df_ally_local = st.session_state.get("df_ally_local", pd.DataFrame())
        if not df_ally_local.empty and 'module_code' in df_ally_local.columns:
            module_rows = df_ally_local[df_ally_local['module_code'].astype(str).str.strip().str.upper() == selected_code.strip().upper()]
            if not module_rows.empty and 'snapshot_date' in module_rows.columns:
                raw_date = str(module_rows.sort_values('snapshot_date').iloc[-1]['snapshot_date'])
                try:
                    parsed_dt = pd.to_datetime(raw_date, errors='coerce')
                    snapshot_date_str = parsed_dt.strftime('%d-%m-%Y') if not pd.isna(parsed_dt) else raw_date
                except:
                    snapshot_date_str = raw_date

        st.markdown(" ")

        # Conditionally render Ally accessibility profile card (only for admins/DLAs)
        if is_full_view and not minified_mode:
            with st.container(border=True):
                st.subheader("Ally Accessibility (DLA/Admin-only Info)", help="Adjusted via the Asymptotic Credibility Model.")
                if pd.notna(ally_score):
                    score_val = float(ally_score)
                    files_val = int(ally_files) if pd.notna(ally_files) else 0
                    col_score, col_progress, col_files = st.columns([1.3, 1.7, 1.0])
                    
                    if files_val == 0:
                        with col_score:
                            st.markdown(f"""
                            <div style="text-align: center; border-radius: 10px; padding: 12px 8px; background-color: #6B728010; border: 1px solid #6B728033; box-shadow: 0 2px 6px #6B728008; margin-top: 5px;">
                                <span style="font-size: 10px; font-weight: 700; color: #6B7280; text-transform: uppercase; letter-spacing: 0.8px; display: block; margin-bottom: 2px;">Ally Score</span>
                                <h2 style="margin: 0; color: #6B7280; font-size: 26px; font-weight: 800; font-family: system-ui, -apple-system, sans-serif; padding: 6px 0;">N/A</h2>
                            </div>
                            """, unsafe_allow_html=True)
                        with col_progress:
                            st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)
                            st.markdown("**Ally Score Over Time:**")
                            st.caption("No files scanned to evaluate.")
                    else:
                        with col_score:
                            if score_val >= 1.0:
                                color, level = "#047857", "Perfect"
                            elif score_val >= 0.67:
                                color, level = "#10B981", "High"
                            elif score_val >= 0.34:
                                color, level = "#F59E0B", "Medium"
                            else:
                                color, level = "#EF4444", "Low"
                            
                            st.markdown(f"""
                            <div style="text-align: center; border-radius: 10px; padding: 12px 8px; background-color: {color}10; border: 1px solid {color}33; box-shadow: 0 2px 6px {color}08; margin-top: 5px;">
                                <span style="font-size: 10px; font-weight: 700; color: {color}; text-transform: uppercase; letter-spacing: 0.8px; display: block; margin-bottom: 2px;">{level} (Weighted)</span>
                                <h2 style="margin: 0; color: {color}; font-size: 34px; font-weight: 800; font-family: system-ui, -apple-system, sans-serif;">{score_val:.1%}</h2>
                            </div>
                            """, unsafe_allow_html=True)
                            if snapshot_date_str:
                                st.markdown(f"<div style='text-align: center; margin-top: 5px; font-size: 11px; color: #6B7280;'>Snapshot Date: <b>{snapshot_date_str}</b></div>", unsafe_allow_html=True)
                        
                        with col_progress:
                            st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)
                            st.markdown("**Ally Score Over Time:**")
                            if not df_ally_local.empty and 'snapshot_date' in df_ally_local.columns:
                                module_history = df_ally_local[df_ally_local['module_code'] == selected_code].copy()
                                if not module_history.empty and len(module_history) > 1:
                                    module_history['snapshot_date'] = pd.to_datetime(module_history['snapshot_date'])
                                    module_history = module_history.sort_values('snapshot_date').set_index('snapshot_date')
                                    st.line_chart(module_history['weighted'], height=100)
                                else:
                                    st.progress(score_val)
                            else:
                                st.progress(score_val)
                                
                    with col_files:
                        st.metric("Files Scanned", f"{files_val}")
                else:
                    st.info("No Ally accessibility score data is available for this module.")
            st.markdown("---")

        # Checklist Fields Setup
        active_fields = get_active_audit_fields()
        prev_responses = get_audit_responses(selected_code)
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

        expander_title = f"📝 Edit Checklist ({audit_status} | {actionable} Actionable)"
        parent_container = st.container() if minified_mode else st.expander(expander_title, expanded=True)
        
        with parent_container:
            if minified_mode:
                st.markdown(f"#### 📝 Audit Checklist ({audit_status})")
            
            # Show last auditor updates
            last_updated = None
            last_auditor = None
            if prev_responses:
                ts_vals = [r['timestamp'] for r in prev_responses.values() if r['timestamp']]
                auditor_vals = [r['auditor'] for r in prev_responses.values() if r['auditor']]
                if ts_vals: last_updated = max(ts_vals)
                if auditor_vals: last_auditor = auditor_vals[-1]
            
            if last_updated:
                st.info(f"Last updated: {last_updated} by {last_auditor}.")
            else:
                st.info("No checklist details submitted yet.")

            with st.form("audit_portal_checklist_form"):
                new_mod_lead = st.text_input("Module Lead Name:", value=mod_lead, key=f"ap_mod_lead_{selected_code}")
                st.markdown("---")
                
                # Reading list indicator
                leganto_label = "Leganto Reading List: OK / Connected" if not leganto_missing else "Leganto Reading List: Missing List"
                st.checkbox(
                    f"**{leganto_label}**",
                    value=not leganto_missing,
                    disabled=True,
                    help="Determined automatically. Links must be set up inside Blackboard Leganto.",
                    key=f"ap_chk_leganto_{selected_code}"
                )
                st.markdown("---")

                responses_input = {}
                if not active_fields:
                    st.warning("No active audit fields are defined. Contact an administrator.")
                else:
                    for field in active_fields:
                        fid = field['id']
                        label = field['label']
                        desc = field['description']
                        ftype = field['field_type']
                        
                        prev_val = prev_responses.get(fid, {}).get('value', None)
                        
                        # Render Booleans / Yes-No for everyone
                        if ftype == 'boolean':
                            def_val = str(prev_val).upper() == 'TRUE' if prev_val is not None else False
                            responses_input[fid] = st.checkbox(label, value=def_val, help=desc, key=f"ap_chk_{selected_code}_{fid}")
                        elif ftype == 'yes/no':
                            options = ["—", "Yes", "No"]
                            if prev_val is not None:
                                p_val_upper = str(prev_val).strip().upper()
                                def_idx = 1 if p_val_upper == 'YES' else (2 if p_val_upper == 'NO' else 0)
                            else:
                                def_idx = 0
                            responses_input[fid] = st.selectbox(label, options=options, index=def_idx, help=desc, key=f"ap_sel_{selected_code}_{fid}")
                        
                        # Text Observations (Tags, Custom Obs) - conditionally handled
                        elif ftype == 'text':
                            if is_full_view:
                                # DLAs & Admins get standard multiselect tags & custom rows
                                prev_tags = []
                                prev_custom_obs = []
                                if prev_val:
                                    try:
                                        data = json.loads(prev_val)
                                        if isinstance(data, dict) and ("tags" in data or "custom" in data):
                                            prev_tags = data.get("tags", [])
                                            prev_custom_obs = parse_custom_observations(data.get("custom", ""))
                                        else:
                                            prev_custom_obs = parse_custom_observations(prev_val)
                                    except:
                                        prev_custom_obs = parse_custom_observations(prev_val)
                                        
                                st.markdown(f"**{label}**")
                                if desc: st.caption(desc)
                                
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
                                            prev_custom_obs.append({"observation": pt, "action": ""})
                                
                                sel_tags = st.multiselect(
                                    "Select Standard Comments (Tags):",
                                    options=cb_options,
                                    default=mapped_prev_tags,
                                    format_func=format_cb,
                                    key=f"ap_tags_{selected_code}_{fid}"
                                )
                                
                                st.markdown("##### Additional Custom Observations")
                                num_obs = len(prev_custom_obs) + 1
                                for i in range(num_obs):
                                    obs_val = prev_custom_obs[i]['observation'] if i < len(prev_custom_obs) else ""
                                    act_val = prev_custom_obs[i]['action'] if i < len(prev_custom_obs) else ""
                                    col_obs, col_act = st.columns(2)
                                    with col_obs:
                                        st.text_area(
                                            f"Observation #{i+1}" if i < len(prev_custom_obs) else "Add New Observation",
                                            value=obs_val,
                                            height=85,
                                            key=f"ap_custom_obs_{selected_code}_{fid}_{i}"
                                        )
                                    with col_act:
                                        st.text_area(
                                            f"Action #{i+1}" if i < len(prev_custom_obs) else "Add New Action / Recommendation",
                                            value=act_val,
                                            height=85,
                                            key=f"ap_custom_act_{selected_code}_{fid}_{i}"
                                        )
                                responses_input[fid] = {
                                    "type": "text",
                                    "tags_key": f"ap_tags_{selected_code}_{fid}",
                                    "num_obs": num_obs,
                                    "fid": fid
                                }
                            else:
                                # For SAs, completely hide inputs from UI but preserve in logic
                                # By not putting it in responses_input, it is not overwritten during database write.
                                pass

                st.markdown("---")
                
                # Write-in Confidential notes for Admins, DLAs, SAs
                prev_notes = prev_responses.get('auditor_notes', {}).get('value', '')
                auditor_notes_val = st.text_area(
                    "🔒 **Auditor Notes (Internal/Confidential):**", 
                    value=prev_notes, 
                    help="These comments are strictly visible to admins, DLAs, and School Auditors, and are hidden from standard users (like Module Leads).",
                    placeholder="Provide internal auditor context, reminders, or observations here...",
                    key=f"ap_auditor_notes_{selected_code}"
                )

                prev_audited = str(prev_responses.get('system_audit_complete', {}).get('value', 'False')).upper() == 'TRUE'
                responses_input['system_audit_complete'] = st.checkbox(
                    "**Mark this module as officially audited**", 
                    value=prev_audited, 
                    help="Mark this module as completely reviewed and validated.",
                    key=f"ap_sys_audit_{selected_code}"
                )

                submitted = st.form_submit_button("Save VLE Audit Updates")
                if submitted:
                    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    username_upper = str(st.session_state.get("username", "")).strip().upper()
                    try:
                        # Save module lead update if changed
                        if new_mod_lead.strip() != mod_lead and new_mod_lead.strip() != "--":
                            update_module_lead_sqlite(selected_code, new_mod_lead)

                        # Save standard inputs
                        for fid, input_info in responses_input.items():
                            if isinstance(input_info, dict) and input_info.get("type") == "text":
                                t_val = st.session_state.get(input_info["tags_key"], [])
                                custom_obs_list = []
                                c_fid = input_info["fid"]
                                for i in range(input_info["num_obs"]):
                                    obs_val = st.session_state.get(f"ap_custom_obs_{selected_code}_{c_fid}_{i}", "").strip()
                                    act_val = st.session_state.get(f"ap_custom_act_{selected_code}_{c_fid}_{i}", "").strip()
                                    if obs_val or act_val:
                                        custom_obs_list.append({"observation": obs_val, "action": act_val})
                                
                                combined_val = json.dumps({"tags": t_val, "custom": custom_obs_list})
                                save_audit_response(selected_code, fid, combined_val, username_upper, timestamp)
                            else:
                                val_str = str(input_info)
                                if val_str == "—": val_str = ""
                                save_audit_response(selected_code, fid, val_str, username_upper, timestamp)

                        # Save internal auditor notes
                        save_audit_response(selected_code, 'auditor_notes', auditor_notes_val, username_upper, timestamp)

                        st.cache_data.clear()
                        logging.info(f"✅ VLE Audit updated successfully for '{selected_code}' by '{username_upper}'.")
                        st.success("VLE Audit saved successfully!")
                        st.rerun()
                    except Exception as e:
                        logging.error(f"❌ Error updating audit portal checklist for '{selected_code}': {e}")
                        st.error(f"Error saving updates: {e}")
