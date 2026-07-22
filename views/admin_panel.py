import streamlit as st
import pandas as pd
import altair as alt
import os
import re
import logging
import datetime
from database import (
    get_db_connection,
    get_audit_fields,
    save_audit_field,
    delete_audit_field,
    save_user_sqlite,
    update_user_field_sqlite,
    delete_user_sqlite,
    save_role_sqlite,
    update_role_field_sqlite,
    delete_role_sqlite,
    init_db
)

def parse_log_line(line):
    """
    Parses a single log line into a dictionary with Timestamp, Level, and Message.
    Format: 2026-05-20 13:42:15 [INFO] message content
    """
    log_pattern = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) \[(\w+)\] (.*)$")
    match = log_pattern.match(line.strip())
    if match:
        return {
            "Timestamp": match.group(1),
            "Level": match.group(2),
            "Message": match.group(3)
        }
    return None

def load_users_from_db():
    """Fetches user registry directly from the SQLite database."""
    with get_db_connection() as conn:
        return pd.read_sql_query("SELECT * FROM users", conn)

def load_roles_from_db():
    """Fetches roles directory directly from the SQLite database."""
    with get_db_connection() as conn:
        return pd.read_sql_query("SELECT * FROM roles", conn)

def read_parsed_logs():
    """Reads app.log and parses it into a Pandas DataFrame."""
    log_path = "app.log"
    if not os.path.exists(log_path):
        return pd.DataFrame(columns=["Timestamp", "Level", "Message"])
    
    try:
        with open(log_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        
        parsed_entries = []
        current_entry = None
        
        for line in lines:
            parsed = parse_log_line(line)
            if parsed:
                if current_entry:
                    parsed_entries.append(current_entry)
                current_entry = parsed
            else:
                # Handle multi-line log entries (e.g., exceptions stack traces)
                if current_entry:
                    current_entry["Message"] += "\n" + line.strip()
                else:
                    # Log entries before any valid formatted line
                    current_entry = {
                        "Timestamp": "",
                        "Level": "UNKNOWN",
                        "Message": line.strip()
                    }
        
        if current_entry:
            parsed_entries.append(current_entry)
            
        return pd.DataFrame(parsed_entries)
    except Exception as e:
        st.error(f"Error reading log file: {e}")
        return pd.DataFrame(columns=["Timestamp", "Level", "Message"])

def get_dataframe_size_kb(df):
    """Calculates memory usage of a Pandas DataFrame in Kilobytes."""
    if df is None or df.empty:
        return 0.0
    try:
        return df.memory_usage(deep=True).sum() / 1024.0
    except Exception:
        return 0.0

def view_admin_panel(df_aut, df_spr, checklist_sums, df_assess=None):
    # Strict lockdown verification
    if st.session_state.get("username") != "ADMIN":
        st.error("🚫 Access Denied: This console is strictly reserved for administrative users.")
        st.stop()
        
    st.title("🔧 Admin Control Panel")
    st.write("System diagnostics, app logging streams, checklist audit fields, user management, and manual data imports/exports.")
    
    st.markdown("---")
    
    # Sub-navigation using Segmented Control
    admin_options = [
        "📊 System Dashboard", 
        "💬 Feedback Explorer", 
        "📋 Log Viewer", 
        "👤 User Control",
        "📋 Audit Field Manager",
        "📂 Data Import/Export",
        "⚙️ System Maintenance"
    ]
    
    selected_tab = st.segmented_control(
        "Admin Tabs:",
        options=admin_options,
        default=admin_options[0],
        key="admin_tab_segmented_control",
        label_visibility="collapsed"
    )
    
    st.markdown("---")
    
    # ----------------------------------------------------
    # TAB 1: SYSTEM DASHBOARD
    # ----------------------------------------------------
    if selected_tab == "📊 System Dashboard":
        st.subheader("System Architecture & Data Summary")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Autumn Row Count", len(df_aut) if not df_aut.empty else 0)
        with col2:
            st.metric("Spring Row Count", len(df_spr) if not df_spr.empty else 0)
        with col3:
            st.metric("SITS Assessments", len(df_assess) if df_assess is not None else 0)
            
        st.divider()
        st.subheader("Local SQLite Database Overview")
        
        # Calculate database stats
        with get_db_connection() as conn:
            # Query tables count
            tables_df = pd.read_sql_query("SELECT name FROM sqlite_master WHERE type='table';", conn)
            tables_list = tables_df['name'].tolist() if not tables_df.empty else []
            
        st.markdown(f"**SQLite File Path:** `{os.path.abspath(os.path.join('data', 'audit_cache.db'))}`")
        st.markdown(f"**Total Tables Found:** `{len(tables_list)}`")
        
        table_stats = []
        with get_db_connection() as conn:
            for tname in tables_list:
                try:
                    cnt_df = pd.read_sql_query(f"SELECT COUNT(*) as count FROM {tname}", conn)
                    rows_count = cnt_df.iloc[0]['count']
                except Exception:
                    rows_count = "Error"
                table_stats.append({
                    "Table Name": tname,
                    "Total Records": rows_count
                })
                
        st.dataframe(pd.DataFrame(table_stats), width="stretch", hide_index=True)
        
    # ----------------------------------------------------
    # TAB 2: FEEDBACK EXPLORER
    # ----------------------------------------------------
    elif selected_tab == "💬 Feedback Explorer":
        st.subheader("User Feedback Stream")
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='feedback'")
            has_feedback_table = cursor.fetchone() is not None
            
            if has_feedback_table:
                df_feed = pd.read_sql_query("SELECT * FROM feedback", conn)
            else:
                df_feed = pd.DataFrame()
                
        if df_feed.empty:
            st.info("No user feedback records are stored in the SQLite database yet. Upload feedback via CSV or submit feedback using the App Feedback view.")
        else:
            try:
                # Convert ratings to numeric
                if "Rating" in df_feed.columns:
                    df_feed["Rating"] = pd.to_numeric(df_feed["Rating"], errors="coerce")
                    
                total_feedback = len(df_feed)
                avg_rating = df_feed["Rating"].mean() if "Rating" in df_feed.columns else 0.0
                
                c1, c2, c3 = st.columns(3)
                with c1:
                    st.metric("Total Submissions", total_feedback)
                with c2:
                    st.metric("Average App Rating", f"{avg_rating:.2f} / 5.0" if avg_rating > 0 else "N/A")
                with c3:
                    bug_count = len(df_feed[df_feed["Category"] == "Bug Report"]) if "Category" in df_feed.columns else 0
                    st.metric("Reported Bugs", bug_count)
                    
                st.divider()
                
                grid_col1, grid_col2 = st.columns([3, 2])
                
                with grid_col2:
                    st.markdown("##### **Filter Feedback**")
                    all_cats = ["All Categories"] + list(df_feed["Category"].unique()) if "Category" in df_feed.columns else ["All Categories"]
                    sel_cat = st.selectbox("Category Filter:", all_cats)
                    
                    all_ratings = ["All Ratings", "5 Stars", "4 Stars", "3 Stars", "2 Stars", "1 Star"]
                    sel_rating = st.selectbox("Rating Filter:", all_ratings)
                    
                    search_q = st.text_input("Search Comments:", placeholder="Search keywords...")
                    
                # Filter dataframe
                filtered_df = df_feed.copy()
                if sel_cat != "All Categories" and "Category" in filtered_df.columns:
                    filtered_df = filtered_df[filtered_df["Category"] == sel_cat]
                    
                if sel_rating != "All Ratings" and "Rating" in filtered_df.columns:
                    rating_map = {"5 Stars": 5, "4 Stars": 4, "3 Stars": 3, "2 Stars": 2, "1 Star": 1}
                    filtered_df = filtered_df[filtered_df["Rating"] == rating_map[sel_rating]]
                    
                if search_q.strip() and "Comments" in filtered_df.columns:
                    filtered_df = filtered_df[filtered_df["Comments"].str.contains(search_q, case=False, na=False)]
                    
                with grid_col1:
                    st.markdown("##### **Rating Distribution**")
                    if "Rating" in df_feed.columns and not df_feed.empty:
                        rating_dist = df_feed["Rating"].value_counts().reset_index()
                        rating_dist.columns = ["Rating", "Count"]
                        
                        chart = alt.Chart(rating_dist).mark_bar(cornerRadiusEnd=3, height=20).encode(
                            y=alt.Y("Rating:O", title="Rating (Stars)"),
                            x=alt.X("Count:Q", title="Number of Reviews"),
                            color=alt.value("#4F46E5")
                        ).properties(height=180)
                        st.altair_chart(chart, use_container_width=True)
                    else:
                        st.write("No rating data available.")
                        
                st.divider()
                st.markdown(f"##### **Feedback Records ({len(filtered_df)} matches)**")
                
                if "Timestamp" in filtered_df.columns:
                    filtered_df = filtered_df.sort_values(by="Timestamp", ascending=False)
                    
                st.dataframe(
                    filtered_df.reset_index(drop=True),
                    column_config={
                        "Timestamp": st.column_config.TextColumn("Timestamp", width="medium"),
                        "User": st.column_config.TextColumn("User Code", width="small"),
                        "School": st.column_config.TextColumn("School", width="small"),
                        "Category": st.column_config.TextColumn("Category", width="small"),
                        "Rating": st.column_config.NumberColumn("Rating", format="%d ⭐"),
                        "Comments": st.column_config.TextColumn("User Comments", width="large")
                    },
                    width="stretch",
                    hide_index=True
                )
            except Exception as e:
                st.error(f"Error listing feedback records: {e}")
                
    # ----------------------------------------------------
    # TAB 3: LOG VIEWER
    # ----------------------------------------------------
    elif selected_tab == "📋 Log Viewer":
        st.subheader("System Logs Viewer (`app.log`)")
        
        df_logs = read_parsed_logs()
        
        if df_logs.empty:
            st.info("Log file is empty or does not exist.")
        else:
            c1, c2, c3 = st.columns([1, 1, 2])
            with c1:
                level_options = ["ALL SEVERITIES"] + list(df_logs["Level"].unique())
                sel_level = st.selectbox("Log Level:", level_options)
            with c2:
                tail_limit = st.number_input("Max Lines to Show:", min_value=10, max_value=2000, value=250, step=50)
            with c3:
                log_search = st.text_input("Filter log text:", placeholder="Search log messages...")
                
            filtered_logs = df_logs.copy()
            if sel_level != "ALL SEVERITIES":
                filtered_logs = filtered_logs[filtered_logs["Level"] == sel_level]
            if log_search.strip():
                filtered_logs = filtered_logs[filtered_logs["Message"].str.contains(log_search, case=False, na=False)]
                
            filtered_logs = filtered_logs.tail(int(tail_limit))
            
            view_mode = st.radio("Log Layout Style:", ["Grid View (Interactive Table)", "Console View (Terminal Style)"], horizontal=True, label_visibility="collapsed")
            
            st.divider()
            
            if view_mode == "Grid View (Interactive Table)":
                st.dataframe(
                    filtered_logs.sort_values(by="Timestamp", ascending=False).reset_index(drop=True),
                    column_config={
                        "Timestamp": st.column_config.TextColumn("Timestamp", width="medium"),
                        "Level": st.column_config.TextColumn("Level", width="small"),
                        "Message": st.column_config.TextColumn("Log Message", width="large")
                    },
                    width="stretch",
                    hide_index=True
                )
            else:
                console_text = ""
                for _, row in filtered_logs.iterrows():
                    ts = row["Timestamp"]
                    lvl = row["Level"]
                    msg = row["Message"]
                    
                    color = "#38BDF8"
                    if lvl == "WARNING":
                        color = "#F59E0B"
                    elif lvl == "ERROR":
                        color = "#EF4444"
                    elif lvl == "CRITICAL":
                        color = "#DC2626"
                        
                    console_text += f'<span style="color:#6B7280">{ts}</span> [<span style="color:{color};font-weight:bold">{lvl}</span>] {msg}\n'
                    
                st.markdown(
                    f'<pre style="background-color:#0F172A;color:#E2E8F0;padding:15px;border-radius:8px;font-family:monospace;max-height:500px;overflow-y:scroll;line-height:1.4">{console_text}</pre>',
                    unsafe_allow_html=True
                )
                
            csv = df_logs.to_csv(index=False).encode("utf-8")
            st.download_button(
                label="📥 Download Full Logs (CSV)",
                data=csv,
                file_name="app_diagnostics_logs.csv",
                mime="text/csv",
                key="btn_download_logs"
            )
            
    # ----------------------------------------------------
    # TAB 4: USER CONTROL (SQLite Direct)
    # ----------------------------------------------------
    elif selected_tab == "👤 User Control":
        st.subheader("👤 Portal Access & User Control")
        
        try:
            # Load users and roles from db
            df_users = load_users_from_db()
            df_roles = load_roles_from_db()
            
            if df_users.empty:
                st.info("The SQLite Users table is currently empty. Seed users or import via the CSV Import tab.")
            elif df_roles.empty:
                st.info("The SQLite Roles table is empty. Create role definitions to assign them.")
            else:
                roles_list = sorted(df_roles["Role"].unique().tolist())
                schools_list = ["All", "ALA", "ECN", "EDC", "GPL", "IJC", "MGT", "SPR"]
                available_caps = ["View Faculty Overview", "View only own school", "view module checklist", "complete module checklist"]
                
                sub_tabs = st.tabs(["👤 User Accounts", "🛡️ Role Capabilities"])
                
                with sub_tabs[0]:
                    search_query = st.text_input("🔍 Search registry (Username, Role, School):", placeholder="Enter username, role, or school code to filter...", key="search_user_accounts")
                    
                    filtered_df = df_users.copy()
                    if search_query.strip():
                        q = search_query.strip().lower()
                        filtered_df = filtered_df[
                            filtered_df["Username"].str.lower().str.contains(q, na=False) |
                            filtered_df["Role"].str.lower().str.contains(q, na=False) |
                            filtered_df["School"].str.lower().str.contains(q, na=False)
                        ]
                    
                    st.markdown("##### **Active User Registry (Stored in SQLite)**")
                    display_df = filtered_df.copy()
                    if "PasswordHash" in display_df.columns:
                        display_df["PasswordHash"] = "••••••••"
                    
                    user_cols = [c for c in display_df.columns if c != "Capabilities"]
                    display_df_view = display_df[user_cols]
                    
                    selection_users = st.dataframe(
                        display_df_view,
                        column_config={
                            "Username": st.column_config.TextColumn("Username", width="small"),
                            "PasswordHash": st.column_config.TextColumn("Password (Hashed)", width="small"),
                            "Role": st.column_config.TextColumn("System Role", width="medium"),
                            "School": st.column_config.TextColumn("School Code", width="small"),
                            "Status": st.column_config.TextColumn("Access Status", width="small")
                        },
                        use_container_width=True,
                        hide_index=True,
                        on_select="rerun",
                        selection_mode="single-row",
                        key="admin_user_registry_dataframe"
                    )
                    
                    st.divider()
                    st.markdown("##### **Access Control Actions**")
                    c1, c2 = st.columns(2)
                    
                    with c1:
                        st.markdown("**Update Existing User Profile**")
                        selected_user = None
                        if selection_users.selection.rows:
                            selected_idx = selection_users.selection.rows[0]
                            if selected_idx < len(display_df_view):
                                selected_user = display_df_view.iloc[selected_idx]["Username"]
                                
                        if not selected_user:
                            st.info("💡 **Select a user row** in the Active User Registry table above to edit their profile details.")
                        else:
                            st.markdown(f"Editing Profile: **{selected_user}**")
                            u_row = df_users[df_users["Username"] == selected_user].iloc[0]
                            u_role = u_row["Role"]
                            u_school = u_row["School"]
                            u_status = u_row["Status"]
                            
                            role_default = u_role if u_role in roles_list else roles_list[0]
                            school_default = u_school if u_school in schools_list else schools_list[0]
                            status_default = "Active" if str(u_status).upper() == "ACTIVE" else "Disabled"
                            
                            new_role = st.selectbox("Assign System Role:", roles_list, index=roles_list.index(role_default), key=f"edit_role_{selected_user}")
                            new_school = st.selectbox("Assign School Context:", schools_list, index=schools_list.index(school_default), key=f"edit_school_{selected_user}")
                            new_status = st.segmented_control("Access Status:", ["Active", "Disabled"], default=status_default, key=f"edit_status_{selected_user}")
                            
                            new_pwd = st.text_input("Reset Password (leave empty to keep current):", type="password", key=f"reset_pwd_{selected_user}")
                            
                            if st.button("Update User Profile", type="primary", use_container_width=True, key=f"btn_update_{selected_user}"):
                                try:
                                    update_user_field_sqlite(selected_user, "Role", new_role)
                                    update_user_field_sqlite(selected_user, "School", new_school)
                                    update_user_field_sqlite(selected_user, "Status", new_status)
                                    
                                    if new_pwd.strip():
                                        import hashlib
                                        pass_hash = hashlib.sha256(new_pwd.strip().encode("utf-8")).hexdigest()
                                        update_user_field_sqlite(selected_user, "PasswordHash", pass_hash)
                                        
                                    logging.info(f"👤 User profile updated for '{selected_user}' directly in SQLite.")
                                    st.success(f"User '{selected_user}' updated successfully in local database!")
                                    st.cache_data.clear()
                                    st.rerun()
                                except Exception as ex:
                                    st.error(f"Error updating user profile: {ex}")
                                    
                            if st.button("❌ Delete User Account", type="secondary", use_container_width=True, key=f"btn_del_{selected_user}"):
                                try:
                                    delete_user_sqlite(selected_user)
                                    logging.info(f"👤 User account deleted: '{selected_user}' from SQLite.")
                                    st.success(f"User '{selected_user}' deleted successfully!")
                                    st.cache_data.clear()
                                    st.rerun()
                                except Exception as ex:
                                    st.error(f"Error deleting user: {ex}")
                                    
                    with c2:
                        st.markdown("**Create New User Account**")
                        add_username = st.text_input("New Username (e.g. school code or email prefix):", placeholder="e.g. MAT", key="new_user_uname").strip()
                        add_pwd = st.text_input("Account Password:", type="password", placeholder="Enter strong password...", key="new_user_pwd")
                        add_role = st.selectbox("Select Account Role:", roles_list, index=0, key="new_user_role")
                        add_school = st.selectbox("Select Allowed School:", schools_list, index=0, key="new_user_school")
                        
                        if st.button("Create Account Registry", type="primary", use_container_width=True, key="btn_create_user"):
                            if not add_username:
                                st.warning("Please enter a username.")
                            elif not add_pwd.strip():
                                st.warning("Please enter a password.")
                            elif add_username.upper() in df_users["Username"].str.upper().unique():
                                st.error(f"Username '{add_username}' already exists in SQLite registry.")
                            else:
                                try:
                                    import hashlib
                                    pass_hash = hashlib.sha256(add_pwd.strip().encode("utf-8")).hexdigest()
                                    save_user_sqlite(add_username.upper(), pass_hash, add_role, add_school, "", "Active")
                                    logging.info(f"👤 Created new user account '{add_username.upper()}' directly in SQLite.")
                                    st.success(f"User account '{add_username.upper()}' created successfully in SQLite database!")
                                    st.cache_data.clear()
                                    st.rerun()
                                except Exception as ex:
                                    st.error(f"Error creating user account: {ex}")
                                    
                with sub_tabs[1]:
                    st.markdown("##### **Role Capabilities Directory**")
                    st.dataframe(df_roles, use_container_width=True, hide_index=True)
                    
                    st.divider()
                    st.markdown("##### **Role Configuration Actions**")
                    rc1, rc2 = st.columns(2)
                    
                    with rc1:
                        st.markdown("**Update Role Capabilities**")
                        selected_edit_role = st.selectbox("Select Role to Configure:", roles_list, key="edit_role_select_box")
                        
                        match_row = df_roles[df_roles["Role"] == selected_edit_role]
                        if not match_row.empty:
                            role_caps_str = match_row.iloc[0]["Capabilities"]
                        else:
                            role_caps_str = ""
                            
                        role_caps_list = [c.strip() for c in role_caps_str.split(",") if c.strip()]
                        resolved_role_caps = []
                        for c in role_caps_list:
                            if c == "view_all":
                                resolved_role_caps.extend(["View Faculty Overview", "complete module checklist"])
                            elif c == "view_school":
                                resolved_role_caps.extend(["View only own school", "complete module checklist"])
                            else:
                                resolved_role_caps.append(c)
                        resolved_role_caps = list(set(resolved_role_caps))
                        
                        st.markdown("**Assigned Capabilities:**")
                        role_caps_edit = []
                        for cap in available_caps:
                            is_checked = cap in resolved_role_caps
                            if st.checkbox(
                                cap,
                                value=is_checked,
                                key=f"chk_edit_{selected_edit_role}_{cap.replace(' ', '_')}"
                            ):
                                role_caps_edit.append(cap)
                                
                        if st.button("Save Role Capabilities", type="primary", use_container_width=True, key="btn_save_role_caps"):
                            try:
                                new_caps_str = ", ".join(role_caps_edit)
                                save_role_sqlite(selected_edit_role, new_caps_str)
                                logging.info(f"🛡️ Capabilities updated for role '{selected_edit_role}' directly in SQLite.")
                                st.success(f"Capabilities for role '{selected_edit_role}' saved successfully!")
                                st.cache_data.clear()
                                st.rerun()
                            except Exception as ex:
                                st.error(f"Error saving role capabilities: {ex}")
                                
                        if st.button("❌ Delete System Role", type="secondary", use_container_width=True, key=f"btn_del_role_{selected_edit_role}"):
                            try:
                                delete_role_sqlite(selected_edit_role)
                                logging.info(f"🛡️ System role deleted: '{selected_edit_role}' from SQLite.")
                                st.success(f"Role '{selected_edit_role}' deleted successfully!")
                                st.cache_data.clear()
                                st.rerun()
                            except Exception as ex:
                                st.error(f"Error deleting role: {ex}")
                                
                    with rc2:
                        st.markdown("**Create New System Role**")
                        new_role_name = st.text_input("New Role Name:", placeholder="e.g. Guest Observer", key="new_role_name_input").strip()
                        
                        st.markdown("**Select Initial Capabilities:**")
                        new_role_caps = []
                        for cap in available_caps:
                            if st.checkbox(
                                cap,
                                value=False,
                                key=f"chk_new_{cap.replace(' ', '_')}"
                            ):
                                new_role_caps.append(cap)
                                
                        if st.button("Create Role", type="primary", use_container_width=True, key="btn_create_role"):
                            if not new_role_name:
                                st.warning("Please enter a role name.")
                            elif new_role_name.lower() in [r.lower() for r in roles_list]:
                                st.error(f"Role '{new_role_name}' already exists.")
                            else:
                                try:
                                    new_caps_str = ", ".join(new_role_caps)
                                    save_role_sqlite(new_role_name, new_caps_str)
                                    logging.info(f"🛡️ Created new role '{new_role_name}' in SQLite.")
                                    st.success(f"Role '{new_role_name}' created successfully in SQLite database!")
                                    st.cache_data.clear()
                                    st.rerun()
                                except Exception as ex:
                                    st.error(f"Error creating role: {ex}")
        except Exception as e:
            st.error(f"Error querying SQLite users database: {e}")

    # ----------------------------------------------------
    # TAB 5: AUDIT FIELD MANAGER (SQLite Direct)
    # ----------------------------------------------------
    elif selected_tab == "📋 Audit Field Manager":
        st.subheader("📋 Audit Field Definitions Manager")
        st.write("Configure the fields (questions) that appear in the module auditing checklist directly in the table below.")
        
        try:
            field_tabs = st.tabs(["📋 Checklist Fields", "💬 Quick Comment Bank"])
            
            with field_tabs[0]:
                fields = get_audit_fields()
                df_fields = pd.DataFrame(fields)
                
                if df_fields.empty:
                    df_fields = pd.DataFrame(columns=["id", "label", "description", "field_type", "is_active", "display_order"])
                else:
                    # Ensure types align correctly for Streamlit's editor
                    df_fields['is_active'] = df_fields['is_active'].apply(lambda x: bool(x))
                    df_fields['display_order'] = pd.to_numeric(df_fields['display_order'], errors='coerce').fillna(10).astype(int)
                    
                st.markdown("##### **Audit Fields Configuration Table**")
                st.caption("💡 **How to edit:** Double-click a cell to edit. Use the controls at the bottom of the table to add new rows. Select a row and press **Delete** on your keyboard to delete it.")
                
                edited_df = st.data_editor(
                    df_fields,
                    num_rows="dynamic",
                    column_config={
                        "id": st.column_config.TextColumn("Field ID (Slug)", help="Unique ID: lowercase letters and underscores only. E.g. welcome_message", required=True),
                        "label": st.column_config.TextColumn("Question / Label", help="Text shown to auditors in checklist.", required=True),
                        "description": st.column_config.TextColumn("Tooltip Description", help="Instructional details/tips."),
                        "field_type": st.column_config.SelectboxColumn("Field Type", options=["boolean", "text"], required=True),
                        "is_active": st.column_config.CheckboxColumn("Active?", default=True),
                        "display_order": st.column_config.NumberColumn("Display Order", min_value=1, max_value=100, default=10, format="%d")
                    },
                    use_container_width=True,
                    hide_index=True,
                    key="audit_fields_data_editor"
                )
                
                st.divider()
                c1, c2 = st.columns([1, 4])
                with c1:
                    save_changes = st.button("💾 Save Table Changes", type="primary", use_container_width=True, key="save_fields_btn")
                    
                if save_changes:
                    # Validate inputs
                    errors = []
                    valid_rows = []
                    seen_ids = set()
                    
                    for idx, row in edited_df.iterrows():
                        fid = str(row.get('id', '')).strip().lower()
                        label = str(row.get('label', '')).strip()
                        desc = str(row.get('description', '') or '').strip()
                        ftype = str(row.get('field_type', '')).strip()
                        is_act = 1 if row.get('is_active') else 0
                        
                        try:
                            order = int(row.get('display_order', 10))
                        except Exception:
                            order = 10
                            
                        if not fid or not re.match(r"^[a-z0-9_]+$", fid):
                            errors.append(f"Row {idx+1}: Field ID '{fid}' is invalid. Use lowercase letters, numbers, and underscores only.")
                        elif fid in seen_ids:
                            errors.append(f"Row {idx+1}: Duplicate Field ID '{fid}' found.")
                        elif not label:
                            errors.append(f"Row {idx+1}: Question Label cannot be empty.")
                        elif ftype not in ["boolean", "text"]:
                            errors.append(f"Row {idx+1}: Field Type must be either 'boolean' or 'text'.")
                        else:
                            seen_ids.add(fid)
                            valid_rows.append((fid, label, desc, ftype, is_act, order))
                            
                    if errors:
                        for err in errors:
                            st.error(err)
                    else:
                        # Perform sync transaction
                        with get_db_connection() as conn:
                            cursor = conn.cursor()
                            # Backup previous IDs to detect deleted ones for response cleanups
                            cursor.execute("SELECT id FROM audit_fields")
                            prev_ids = {r[0] for r in cursor.fetchall()}
                            
                            # Wipe table and re-insert
                            cursor.execute("DELETE FROM audit_fields")
                            cursor.executemany(
                                "INSERT INTO audit_fields (id, label, description, field_type, is_active, display_order) VALUES (?, ?, ?, ?, ?, ?)",
                                valid_rows
                            )
                            
                            # Clean up orphaned responses for deleted fields
                            deleted_ids = prev_ids - seen_ids
                            if deleted_ids:
                                placeholders = ','.join(['?'] * len(deleted_ids))
                                cursor.execute(f"DELETE FROM audit_responses WHERE field_id IN ({placeholders})", list(deleted_ids))
                                
                            conn.commit()
                            
                        st.cache_data.clear()
                        st.success("Audit fields configuration saved and synchronized successfully!")
                        st.balloons()
                        st.rerun()

            with field_tabs[1]:
                st.markdown("##### **Audit Comments Bank (Predefined Tags)**")
                st.write("Configure the library of quick comments available for auditors to pick as tags.")
                
                with get_db_connection() as conn:
                    df_tags = pd.read_sql_query("SELECT tag FROM comment_bank ORDER BY tag", conn)
                    
                edited_tags_df = st.data_editor(
                    df_tags,
                    num_rows="dynamic",
                    column_config={
                        "tag": st.column_config.TextColumn("Standard Comment / Tag", help="A predefined common feedback tag.", required=True)
                    },
                    use_container_width=True,
                    hide_index=True,
                    key="comment_bank_data_editor"
                )
                
                st.divider()
                tc1, tc2 = st.columns([1, 4])
                with tc1:
                    save_tags = st.button("💾 Save Comment Bank", type="primary", use_container_width=True, key="save_tags_btn")
                    
                if save_tags:
                    valid_tags = []
                    for idx, row in edited_tags_df.iterrows():
                        tag_val = str(row.get('tag', '')).strip()
                        if tag_val:
                            valid_tags.append((tag_val,))
                            
                    with get_db_connection() as conn:
                        cursor = conn.cursor()
                        cursor.execute("DELETE FROM comment_bank")
                        cursor.executemany("INSERT INTO comment_bank (tag) VALUES (?)", valid_tags)
                        conn.commit()
                        
                    st.cache_data.clear()
                    st.success("Quick comment bank tags updated successfully!")
                    st.balloons()
                    st.rerun()
                    
        except Exception as e:
            st.error(f"Error managing audit fields/comment bank: {e}")

    # ----------------------------------------------------
    # TAB 6: DATA IMPORT/EXPORT HUB
    # ----------------------------------------------------
    elif selected_tab == "📂 Data Import/Export":
        st.subheader("📂 Local Database Import / Export Hub")
        st.write("Perform manual backup exports or update system tables directly by importing CSV files.")
        
        tables_map = {
            "SITS 2026/27 Assessments": "sits_assessment_2026_27",
            "Audit Fields Config": "audit_fields",
            "Audit Responses Data": "audit_responses",
            "User Accounts": "users",
            "User Roles": "roles",
            "VLE Ally Scores": "ally_scores",
            "Leganto No-Lists": "leganto_nolist",
            "Legacy Audit Baseline (Autumn 25/26)": "main_vle_audit_aut",
            "Legacy Audit Baseline (Spring 25/26)": "main_vle_audit_spr"
        }
        
        selected_label = st.selectbox("Select Target Dataset / Table:", list(tables_map.keys()))
        target_table = tables_map[selected_label]
        
        st.divider()
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (target_table,))
            table_exists = cursor.fetchone() is not None
            
        c1, c2 = st.columns(2)
        
        # --- EXPORT SECTION ---
        with c1:
            st.markdown(f"#### 📤 Export `{selected_label}`")
            st.write(f"Download the current SQLite records in `{target_table}` table as a CSV file.")
            
            if not table_exists:
                st.warning(f"No records exist yet in `{target_table}`. Create them or perform an import first.")
            else:
                try:
                    with get_db_connection() as conn:
                        df_export = pd.read_sql_query(f"SELECT * FROM {target_table}", conn)
                        
                    st.metric("Records to export", len(df_export))
                    
                    csv = df_export.to_csv(index=False).encode('utf-8')
                    st.download_button(
                        label=f"📥 Download {selected_label} (CSV)",
                        data=csv,
                        file_name=f"{target_table}_export_{datetime.datetime.now().strftime('%Y%m%d')}.csv",
                        mime="text/csv",
                        key=f"export_btn_{target_table}"
                    )
                except Exception as ex:
                    st.error(f"Error preparing export: {ex}")
                    
        # --- IMPORT SECTION ---
        with c2:
            st.markdown(f"#### 📥 Import CSV to `{selected_label}`")
            st.write(f"Upload a CSV file to update or replace rows in the `{target_table}` SQLite table.")
            
            uploaded_file = st.file_uploader(f"Choose CSV for {selected_label}", type="csv", key=f"uploader_{target_table}")
            
            if uploaded_file is not None:
                try:
                    df_import = pd.read_csv(uploaded_file)
                    st.markdown("**Uploaded Data Preview:**")
                    st.dataframe(df_import.head(3), use_container_width=True)
                    st.metric("Records parsed from CSV", len(df_import))
                    
                    import_mode = st.radio(
                        "Import Method:",
                        ["Merge / Upsert (Keep existing rows and update matching primary keys)", "Replace entire table (Delete existing data and replace with CSV)"],
                        key=f"import_mode_{target_table}"
                    )
                    
                    confirm_import = st.checkbox("Confirm: I want to write this CSV to the database table.")
                    
                    if st.button("🚀 Execute Import", type="primary", disabled=not confirm_import, key=f"exec_btn_{target_table}"):
                        with st.spinner("Writing records to SQLite..."):
                            with get_db_connection() as conn:
                                if import_mode.startswith("Replace"):
                                    # Write directly using replace mode
                                    df_import.to_sql(target_table, conn, if_exists='replace', index=False)
                                    init_db()
                                else:
                                    if table_exists:
                                        df_existing = pd.read_sql_query(f"SELECT * FROM {target_table}", conn)
                                        
                                        pk_map = {
                                            "sits_assessment_2026_27": None,
                                            "audit_fields": "id",
                                            "audit_responses": ["module_code", "field_id"],
                                            "users": "Username",
                                            "roles": "Role",
                                            "ally_scores": "module_code",
                                            "leganto_nolist": "module_code",
                                            "main_vle_audit_aut": None,
                                            "main_vle_audit_spr": None
                                        }
                                        
                                        pk = pk_map.get(target_table, None)
                                        if pk is None:
                                            df_import.to_sql(target_table, conn, if_exists='append', index=False)
                                        else:
                                            df_merged = pd.concat([df_existing, df_import], ignore_index=True)
                                            df_merged = df_merged.drop_duplicates(subset=pk, keep='last')
                                            df_merged.to_sql(target_table, conn, if_exists='replace', index=False)
                                            init_db()
                                    else:
                                        df_import.to_sql(target_table, conn, if_exists='replace', index=False)
                                        init_db()
                                        
                            st.cache_data.clear()
                            logging.info(f"📂 CSV import executed successfully on table '{target_table}' ({len(df_import)} rows).")
                            st.success("CSV imported successfully! Streamlit cache purged.")
                            st.balloons()
                            st.rerun()
                except Exception as ex:
                    st.error(f"Failed to parse or write CSV: {ex}")

    # ----------------------------------------------------
    # TAB 7: SYSTEM MAINTENANCE
    # ----------------------------------------------------
    elif selected_tab == "⚙️ System Maintenance":
        st.subheader("System Maintenance & Diagnostics")
        
        st.markdown("##### **Cache & Diagnostics Operations**")
        with st.container(border=True):
            st.write("Force-clearing Streamlit caches will force the application to fetch fresh data records from local SQLite on the next page interaction.")
            if st.button("🗑️ Purge Memory Cache (st.cache_data.clear)", use_container_width=True):
                st.cache_data.clear()
                logging.info("♻️ System cache was cleared manually via the Admin Panel.")
                st.success("Memory cache successfully purged! All data will reload on next render.")
                st.balloons()
            
            st.divider()
            st.write("Ensure database tables and columns align with current parameters.")
            if st.button("🩺 Run Database Schemas Verification", use_container_width=True):
                try:
                    init_db()
                    logging.info("🩺 Database schemas verified and initialized.")
                    st.success("Database schemas checked and verified! All structures are intact.")
                except Exception as e:
                    st.error(f"Schema verification failed: {e}")
                    
        st.markdown("##### **Diagnostics Logs Control**")
        with st.container(border=True):
            st.write("Safely clear the `app.log` contents to free up space. This action is irreversible.")
            confirm_trunc = st.checkbox("Confirm: I want to wipe all logs inside `app.log` permanently.")
            if st.button("🗑️ Truncate app.log File", use_container_width=True, disabled=not confirm_trunc):
                try:
                    open("app.log", "w").close()
                    logging.info("🗑️ System logs were truncated via the Admin Panel.")
                    st.success("Logs file truncated successfully!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed to truncate logs: {e}")
                    
    # ----------------------------------------------------
    # TAB 8: DATABASE EXPLORER
    # ----------------------------------------------------
    elif selected_tab == "🗄️ Database Explorer":
        st.subheader("🗄️ SQLite Database Explorer")
        st.write("Directly query and view the contents of your SQLite database tables.")
        
        try:
            with get_db_connection() as conn:
                tables_df = pd.read_sql_query("SELECT name FROM sqlite_master WHERE type='table';", conn)
                
                if tables_df.empty:
                    st.info("The local database has no tables yet. Run schema verification or data import.")
                else:
                    tables_list = tables_df['name'].tolist()
                    selected_table = st.selectbox("Select Table to View:", tables_list, key="db_explorer_select_table")
                    
                    st.divider()
                    st.markdown(f"##### **Table: `{selected_table}`**")
                    
                    table_data = pd.read_sql_query(f"SELECT * FROM {selected_table}", conn)
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        st.metric("Total Rows", len(table_data))
                    with col2:
                        st.metric("Total Columns", len(table_data.columns))
                        
                    st.dataframe(table_data, use_container_width=True, hide_index=True)
                    
                    csv = table_data.to_csv(index=False).encode("utf-8")
                    st.download_button(
                        label=f"📥 Download '{selected_table}' as CSV",
                        data=csv,
                        file_name=f"{selected_table}_export.csv",
                        mime="text/csv",
                    )
        except Exception as e:
            st.error(f"Error querying SQLite database: {e}")
