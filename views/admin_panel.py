import streamlit as st
import pandas as pd
import altair as alt
import os
import re
import logging
from data_manager import get_spreadsheet_data, initialize_checklist_headers, initialize_feedback_headers, update_user_row, append_row_to_sheet

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

@st.cache_data(ttl=60)
def load_feedback_records_cached(feedback_id):
    """Fetches feedback raw rows from Google Sheets, cached for 60 seconds."""
    ss, _ = get_spreadsheet_data(feedback_id)
    sheet = ss.worksheet("Sheet1")
    return sheet.get_all_values()

@st.cache_data(ttl=60)
def load_users_records_cached(users_sheet_id):
    """Fetches user registry raw rows from Google Sheets, cached for 60 seconds."""
    try:
        from data_manager import initialize_users_sheet
        initialize_users_sheet(users_sheet_id)
    except Exception:
        pass
    ss, _ = get_spreadsheet_data(users_sheet_id)
    sheet = ss.worksheet("Users")
    return sheet.get_all_values()

@st.cache_data(ttl=60)
def load_roles_records_cached(users_sheet_id):
    """Fetches roles registry raw rows from Google Sheets, cached for 60 seconds."""
    try:
        from data_manager import initialize_roles_sheet
        initialize_roles_sheet(users_sheet_id)
    except Exception:
        pass
    ss, _ = get_spreadsheet_data(users_sheet_id)
    sheet = ss.worksheet("Roles")
    return sheet.get_all_values()

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

def mask_key(val):
    """Masks a secret key for secure display (e.g., '12Ndr_CE...4VPQ')"""
    if not val:
        return "❌ NOT CONFIGURED"
    val_str = str(val).strip()
    if len(val_str) <= 12:
        return "*" * len(val_str)
    return f"{val_str[:6]}...{val_str[-6:]}"

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
    st.write("System diagnostics, app logging streams, feedback reviews, and maintenance operations.")
    
    st.markdown("---")
    
    # Sub-navigation using Segmented Control
    admin_options = [
        "📊 System Dashboard", 
        "💬 Feedback Explorer", 
        "📋 Log Viewer", 
        "⚙️ Operations Control",
        "👤 User Control",
        "🗄️ Database Explorer"
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
        st.subheader("Integration Coordinates")
        
        config_data = {
            "Setting / Spreadsheet Resource": [
                "Main Sheet ID (MAIN_SPREADSHEET_ID)",
                "Self-Audit Checklist ID (CHECKLIST_SPREADSHEET_ID)",
                "Ally Data ID (ALLY_SPREADSHEET_ID)",
                "Leganto No-List ID (LEGANTO_NOLIST_ID)",
                "Feedback Collector ID (FEEDBACK_SPREADSHEET_ID)",
                "SITS Assessment ID (ASSESSMENT_SPREADSHEET_ID)",
                "User Database ID (USERS_SPREADSHEET_ID)",
                "Google Client Email",
                "Google Project ID"
            ],
            "Configuration Value (Masked)": [
                mask_key(os.getenv("MAIN_SPREADSHEET_ID")),
                mask_key(os.getenv("CHECKLIST_SPREADSHEET_ID")),
                mask_key(os.getenv("ALLY_SPREADSHEET_ID")),
                mask_key(os.getenv("LEGANTO_NOLIST_ID")),
                mask_key(os.getenv("FEEDBACK_SPREADSHEET_ID")),
                mask_key(os.getenv("ASSESSMENT_SPREADSHEET_ID")),
                mask_key(os.getenv("USERS_SPREADSHEET_ID")),
                mask_key(os.getenv("GOOGLE_CLIENT_EMAIL")),
                os.getenv("GOOGLE_PROJECT_ID", "❌ NOT CONFIGURED")
            ],
            "Status": [
                "🟢 Active" if os.getenv("MAIN_SPREADSHEET_ID") else "🔴 Empty",
                "🟢 Active" if os.getenv("CHECKLIST_SPREADSHEET_ID") else "🔴 Empty",
                "🟢 Active" if os.getenv("ALLY_SPREADSHEET_ID") else "🟡 Unconfigured",
                "🟢 Active" if os.getenv("LEGANTO_NOLIST_ID") else "🟡 Unconfigured",
                "🟢 Active" if os.getenv("FEEDBACK_SPREADSHEET_ID") else "🔴 Empty",
                "🟢 Active" if os.getenv("ASSESSMENT_SPREADSHEET_ID") else "🟡 Unconfigured",
                "🟢 Active" if os.getenv("USERS_SPREADSHEET_ID") else "🔴 Empty",
                "🟢 Authenticated" if os.getenv("GOOGLE_CLIENT_EMAIL") else "🔴 Missing Credentials",
                "🟢 Bound" if os.getenv("GOOGLE_PROJECT_ID") else "🔴 Missing Credentials"
            ]
        }
        
        st.dataframe(pd.DataFrame(config_data), width="stretch", hide_index=True)
        
    # ----------------------------------------------------
    # TAB 2: FEEDBACK EXPLORER
    # ----------------------------------------------------
    elif selected_tab == "💬 Feedback Explorer":
        st.subheader("User Feedback Stream")
        feedback_id = os.getenv("FEEDBACK_SPREADSHEET_ID")
        
        if not feedback_id:
            st.error("Feedback spreadsheet ID is not configured in the environment variables.")
        else:
            try:
                with st.spinner("Fetching latest feedback records..."):
                    raw_data = load_feedback_records_cached(feedback_id)
                    
                if len(raw_data) <= 1:
                    st.info("No user feedback records have been submitted yet.")
                else:
                    headers = raw_data[0]
                    rows = raw_data[1:]
                    df_feed = pd.DataFrame(rows, columns=headers)
                    
                    # Convert ratings to numeric
                    if "Rating" in df_feed.columns:
                        df_feed["Rating"] = pd.to_numeric(df_feed["Rating"], errors="coerce")
                        
                    # Calculate summary metrics
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
                    
                    # Layout with chart on the left, filters on the right
                    grid_col1, grid_col2 = st.columns([3, 2])
                    
                    with grid_col2:
                        st.markdown("##### **Filter Feedback**")
                        # Category filter
                        all_cats = ["All Categories"] + list(df_feed["Category"].unique()) if "Category" in df_feed.columns else ["All Categories"]
                        sel_cat = st.selectbox("Category Filter:", all_cats)
                        
                        # Rating filter
                        all_ratings = ["All Ratings", "5 Stars", "4 Stars", "3 Stars", "2 Stars", "1 Star"]
                        sel_rating = st.selectbox("Rating Filter:", all_ratings)
                        
                        # Text search
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
                                color=alt.value("#4F46E5") # Premium Indigo
                            ).properties(height=180)
                            st.altair_chart(chart, use_container_width=True)
                        else:
                            st.write("No rating data available.")
                            
                    st.divider()
                    st.markdown(f"##### **Feedback Records ({len(filtered_df)} matches)**")
                    
                    # Sort by timestamp descending
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
                st.error(f"Error querying feedback spreadsheet: {e}")
                
    # ----------------------------------------------------
    # TAB 3: LOG VIEWER
    # ----------------------------------------------------
    elif selected_tab == "📋 Log Viewer":
        st.subheader("System Logs Viewer (`app.log`)")
        
        # Read and parse log lines
        df_logs = read_parsed_logs()
        
        if df_logs.empty:
            st.info("Log file is empty or does not exist.")
        else:
            # Control filters
            c1, c2, c3 = st.columns([1, 1, 2])
            with c1:
                level_options = ["ALL SEVERITIES"] + list(df_logs["Level"].unique())
                sel_level = st.selectbox("Log Level:", level_options)
            with c2:
                # Tail limit
                tail_limit = st.number_input("Max Lines to Show:", min_value=10, max_value=2000, value=250, step=50)
            with c3:
                log_search = st.text_input("Filter log text:", placeholder="Search log messages...")
                
            # Filter logs
            filtered_logs = df_logs.copy()
            if sel_level != "ALL SEVERITIES":
                filtered_logs = filtered_logs[filtered_logs["Level"] == sel_level]
            if log_search.strip():
                filtered_logs = filtered_logs[filtered_logs["Message"].str.contains(log_search, case=False, na=False)]
                
            # Apply limit
            filtered_logs = filtered_logs.tail(int(tail_limit))
            
            # Sub-navigation for presentation type
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
                # Console style text block with custom styling
                console_text = ""
                for _, row in filtered_logs.iterrows():
                    ts = row["Timestamp"]
                    lvl = row["Level"]
                    msg = row["Message"]
                    
                    # Highlight colors depending on severity
                    color = "#38BDF8" # Default Blue-Sky (INFO)
                    if lvl == "WARNING":
                        color = "#F59E0B" # Orange
                    elif lvl == "ERROR":
                        color = "#EF4444" # Red
                    elif lvl == "CRITICAL":
                        color = "#DC2626" # Deep Dark Red
                        
                    console_text += f'<span style="color:#6B7280">{ts}</span> [<span style="color:{color};font-weight:bold">{lvl}</span>] {msg}\n'
                    
                st.markdown(
                    f'<pre style="background-color:#0F172A;color:#E2E8F0;padding:15px;border-radius:8px;font-family:monospace;max-height:500px;overflow-y:scroll;line-height:1.4">{console_text}</pre>',
                    unsafe_allow_html=True
                )
                
            # Download logs button
            csv = df_logs.to_csv(index=False).encode("utf-8")
            st.download_button(
                label="📥 Download Full Logs (CSV)",
                data=csv,
                file_name="app_diagnostics_logs.csv",
                mime="text/csv",
                key="btn_download_logs"
            )
            
    # ----------------------------------------------------
    # TAB 4: OPERATIONS CONTROL
    # ----------------------------------------------------
    elif selected_tab == "⚙️ Operations Control":
        st.subheader("System Operations & Maintenance")
        
        st.markdown("##### **Data Sync & Cache Operations**")
        with st.container(border=True):
            st.write("Force an immediate synchronization of all data from Google Sheets into the local SQLite cache.")
            if st.button("🔄 Sync Data Now (Google Sheets → SQLite)", type="primary", use_container_width=True):
                with st.spinner("Synchronizing data..."):
                    from sync_data import run_synchronization
                    try:
                        run_synchronization()
                        st.cache_data.clear()
                        logging.info("♻️ Data sync forced manually via the Admin Panel.")
                        st.success("Data successfully synchronized! App cache purged.")
                        st.balloons()
                    except Exception as e:
                        st.error(f"Sync failed: {e}")
            
            st.divider()
            st.write("Force-clearing streamlit caches will force the application to fetch fresh data records from local caches on the next page interaction.")
            if st.button("🗑️ Purge Memory Cache (st.cache_data.clear)", use_container_width=True):
                st.cache_data.clear()
                logging.info("♻️ System cache was cleared manually via the Admin Panel.")
                st.success("Memory cache successfully purged! All data will reload on next render.")
                st.balloons()
                
        st.markdown("##### **Cache & Memory Footprint**")
        with st.container(border=True):
            # Calculate sizes
            aut_sz = get_dataframe_size_kb(df_aut)
            spr_sz = get_dataframe_size_kb(df_spr)
            assess_sz = get_dataframe_size_kb(df_assess)
            
            # Feedback size
            feed_sz = 0.0
            feedback_id = os.getenv("FEEDBACK_SPREADSHEET_ID")
            if feedback_id:
                try:
                    raw_feed = load_feedback_records_cached(feedback_id)
                    df_f = pd.DataFrame(raw_feed[1:], columns=raw_feed[0]) if len(raw_feed) > 1 else pd.DataFrame()
                    feed_sz = get_dataframe_size_kb(df_f)
                except Exception:
                    pass
            
            # Users size
            users_sz = 0.0
            users_sheet_id = os.getenv("USERS_SPREADSHEET_ID")
            if users_sheet_id:
                try:
                    raw_users = load_users_records_cached(users_sheet_id)
                    df_u = pd.DataFrame(raw_users[1:], columns=raw_users[0]) if len(raw_users) > 1 else pd.DataFrame()
                    users_sz = get_dataframe_size_kb(df_u)
                except Exception:
                    pass
            # Logs size
            log_sz_kb = 0.0
            if os.path.exists("app.log"):
                try:
                    log_sz_kb = os.path.getsize("app.log") / 1024.0
                except Exception:
                    pass
                    
            total_sz = aut_sz + spr_sz + assess_sz + feed_sz + users_sz
            
            c1, c2 = st.columns([2, 3])
            with c1:
                st.metric("Total Estimated Cache Size", f"{total_sz:.2f} KB")
                st.metric("System Log File (app.log)", f"{log_sz_kb:.2f} KB" if log_sz_kb < 1024.0 else f"{log_sz_kb/1024.0:.2f} MB")
            with c2:
                st.markdown(f"""
                - **Autumn Semester Review Data**: `{aut_sz:.2f} KB`
                - **Spring Semester Review Data**: `{spr_sz:.2f} KB`
                - **SITS Assessments Dataset**: `{assess_sz:.2f} KB`
                - **User Feedback Cache**: `{feed_sz:.2f} KB`
                - **Users Registry Cache**: `{users_sz:.2f} KB`
                - **Active Log File (`app.log`)**: `{log_sz_kb:.2f} KB`
                """)
                
        st.markdown("##### **Google Sheet Database Health Diagnostics**")
        with st.container(border=True):
            st.write("Ensure spreadsheet headers align with current schema columns (Checklist headers, Feedback collector columns).")
            if st.button("🩺 Run Headers Audit & Alignment Check", use_container_width=True):
                try:
                    checklist_id = os.getenv("CHECKLIST_SPREADSHEET_ID")
                    feedback_id = os.getenv("FEEDBACK_SPREADSHEET_ID")
                    
                    if checklist_id:
                        initialize_checklist_headers(checklist_id, "Sheet1")
                    if feedback_id:
                        initialize_feedback_headers(feedback_id, "Sheet1")
                        
                    logging.info("🩺 Run Headers Audit & Alignment Check succeeded.")
                    st.success("Headers alignment diagnostics completed successfully. Database structure is intact.")
                except Exception as e:
                    logging.error(f"❌ Headers alignment failed: {e}")
                    st.error(f"Failed to audit spreadsheet headers: {e}")
                    
        st.markdown("##### **App Log Truncation**")
        with st.container(border=True):
            st.write("Safely clear the `app.log` contents to free up space. This action is irreversible.")
            # Safety confirmation checkbox
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
    # TAB 5: USER CONTROL
    # ----------------------------------------------------
    elif selected_tab == "👤 User Control":
        st.subheader("👤 Portal Access & User Control")
        
        users_sheet_id = os.getenv("USERS_SPREADSHEET_ID")
        if not users_sheet_id:
            st.warning("⚠️ USERS_SPREADSHEET_ID is not configured in environment variables. User database cannot be accessed.")
        else:
            try:
                # Load users and roles from sheets
                with st.spinner("Loading active user & roles registry..."):
                    raw_users = load_users_records_cached(users_sheet_id)
                    raw_roles = load_roles_records_cached(users_sheet_id)
                
                if len(raw_users) <= 1:
                    st.info("The Users registry is empty or missing headers.")
                elif len(raw_roles) <= 1:
                    st.info("The Roles registry is empty or missing headers.")
                else:
                    headers = raw_users[0]
                    rows = raw_users[1:]
                    df_users = pd.DataFrame(rows, columns=headers)
                    
                    role_headers = raw_roles[0]
                    role_rows = raw_roles[1:]
                    df_roles = pd.DataFrame(role_rows, columns=role_headers)
                    
                    roles_list = sorted(df_roles["Role"].unique().tolist())
                    schools_list = ["All", "ALA", "ECN", "EDC", "GPL", "IJC", "MGT", "SPR"]
                    available_caps = ["View Faculty Overview", "View only own school", "view module checklist", "complete module checklist"]
                    
                    sub_tabs = st.tabs(["👤 User Accounts", "🛡️ Role Capabilities"])
                    
                    with sub_tabs[0]:
                        # User Accounts Management
                        # Search field to filter registry
                        search_query = st.text_input("🔍 Search registry (Username, Role, School):", placeholder="Enter username, role, or school code to filter...", key="search_user_accounts")
                        
                        filtered_df = df_users.copy()
                        if search_query.strip():
                            q = search_query.strip().lower()
                            filtered_df = filtered_df[
                                filtered_df["Username"].str.lower().str.contains(q, na=False) |
                                filtered_df["Role"].str.lower().str.contains(q, na=False) |
                                filtered_df["School"].str.lower().str.contains(q, na=False)
                            ]
                        
                        st.markdown("##### **Active User Registry**")
                        display_df = filtered_df.copy()
                        if "PasswordHash" in display_df.columns:
                            display_df["PasswordHash"] = "••••••••"
                        
                        # Strip Capabilities from user view display since it's role-based
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
                                status_default = "Active" if u_status.upper() == "ACTIVE" else "Disabled"
                                
                                new_role = st.selectbox("Assign System Role:", roles_list, index=roles_list.index(role_default), key=f"edit_role_{selected_user}")
                                new_school = st.selectbox("Assign School Context:", schools_list, index=schools_list.index(school_default), key=f"edit_school_{selected_user}")
                                new_status = st.segmented_control("Access Status:", ["Active", "Disabled"], default=status_default, key=f"edit_status_{selected_user}")
                                
                                new_pwd = st.text_input("Reset Password (leave empty to keep current):", type="password", key=f"reset_pwd_{selected_user}")
                                
                                if st.button("Update User Profile", type="primary", use_container_width=True, key=f"btn_update_{selected_user}"):
                                    try:
                                        update_user_row(users_sheet_id, selected_user, "Role", new_role)
                                        update_user_row(users_sheet_id, selected_user, "School", new_school)
                                        update_user_row(users_sheet_id, selected_user, "Status", new_status)
                                        
                                        if new_pwd.strip():
                                            import hashlib
                                            pass_hash = hashlib.sha256(new_pwd.strip().encode("utf-8")).hexdigest()
                                            update_user_row(users_sheet_id, selected_user, "PasswordHash", pass_hash)
                                            
                                        logging.info(f"👤 User profile updated for '{selected_user}' via Admin Panel.")
                                        st.success(f"User '{selected_user}' updated successfully!")
                                        st.cache_data.clear()
                                        st.rerun()
                                    except Exception as ex:
                                        st.error(f"Error updating user profile: {ex}")
                                        
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
                                    st.error(f"Username '{add_username}' already exists in registry.")
                                else:
                                    try:
                                        import hashlib
                                        pass_hash = hashlib.sha256(add_pwd.strip().encode("utf-8")).hexdigest()
                                        row_to_add = [add_username.upper(), pass_hash, add_role, add_school, "", "Active"]
                                        append_row_to_sheet(users_sheet_id, "Users", row_to_add)
                                        logging.info(f"👤 Created new user account '{add_username.upper()}' via Admin Panel.")
                                        st.success(f"User account '{add_username.upper()}' created successfully!")
                                        st.cache_data.clear()
                                        st.rerun()
                                    except Exception as ex:
                                        st.error(f"Error creating user account: {ex}")
                                        
                    with sub_tabs[1]:
                        # Role Capabilities Management
                        st.markdown("##### **Role Capabilities Directory**")
                        st.dataframe(df_roles, use_container_width=True, hide_index=True)
                        
                        st.divider()
                        st.markdown("##### **Role Configuration Actions**")
                        rc1, rc2 = st.columns(2)
                        
                        with rc1:
                            st.markdown("**Update Role Capabilities**")
                            selected_edit_role = st.selectbox("Select Role to Configure:", roles_list, key="edit_role_select_box")
                            role_caps_str = df_roles[df_roles["Role"] == selected_edit_role].iloc[0]["Capabilities"]
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
                            
                            # Checkbox configurator for capabilities
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
                                    from data_manager import update_role_row
                                    new_caps_str = ", ".join(role_caps_edit)
                                    update_role_row(users_sheet_id, selected_edit_role, "Capabilities", new_caps_str)
                                    logging.info(f"🛡️ Capabilities updated for role '{selected_edit_role}' via Admin Panel.")
                                    st.success(f"Capabilities for role '{selected_edit_role}' saved successfully!")
                                    st.cache_data.clear()
                                    st.rerun()
                                except Exception as ex:
                                    st.error(f"Error saving role capabilities: {ex}")
                                    
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
                                        from data_manager import append_row_to_sheet
                                        new_caps_str = ", ".join(new_role_caps)
                                        append_row_to_sheet(users_sheet_id, "Roles", [new_role_name, new_caps_str])
                                        logging.info(f"🛡️ Created new role '{new_role_name}' via Admin Panel.")
                                        st.success(f"Role '{new_role_name}' created successfully!")
                                        st.cache_data.clear()
                                        st.rerun()
                                    except Exception as ex:
                                        st.error(f"Error creating role: {ex}")
                                        
                    st.markdown("---")
                    st.markdown("##### **Feature Capability Toggles**")
                    st.write("Capability toggles let you enable or disable specific features dynamically across the portal:")
                    
                    tc1, tc2 = st.columns(2)
                    with tc1:
                        st.toggle("Enable VLE Checklist self-audit form submissions", value=True, disabled=True, key="tog_checklist")
                        st.toggle("Enable Leganto missing lists warning checks", value=True, disabled=True, key="tog_leganto")
                        st.toggle("Allow feedback submissions from active users", value=True, disabled=True, key="tog_feedback")
                    with tc2:
                        st.toggle("Maintenance Mode (Locks portal for all non-ADMIN accounts)", value=False, disabled=True, key="tog_maint")
                        st.toggle("Enable SITS assessment integration analytics", value=True, disabled=True, key="tog_sits")
                        st.toggle("Force HTTPS SSL Enforcement", value=True, disabled=True, key="tog_ssl")
                        
                    st.caption("Capabilities and credentials management are saved directly to your secure Users and Roles worksheets in Google Sheets.")
            except Exception as e:
                st.error(f"Error connecting to the Users spreadsheet database: {e}")

    # ----------------------------------------------------
    # TAB 6: DATABASE EXPLORER
    # ----------------------------------------------------
    elif selected_tab == "🗄️ Database Explorer":
        st.subheader("🗄️ SQLite Database Explorer")
        st.write("Directly query and view the contents of your local cache tables.")
        
        try:
            from database import get_db_connection
            with get_db_connection() as conn:
                # Get all table names
                tables_df = pd.read_sql_query("SELECT name FROM sqlite_master WHERE type='table';", conn)
                
                if tables_df.empty:
                    st.info("The local database is currently empty. Please run a data sync.")
                else:
                    tables_list = tables_df['name'].tolist()
                    selected_table = st.selectbox("Select Table to View:", tables_list)
                    
                    st.divider()
                    st.markdown(f"##### **Table: `{selected_table}`**")
                    
                    # Fetch data
                    table_data = pd.read_sql_query(f"SELECT * FROM {selected_table}", conn)
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        st.metric("Total Rows", len(table_data))
                    with col2:
                        st.metric("Total Columns", len(table_data.columns))
                        
                    st.dataframe(table_data, use_container_width=True, hide_index=True)
                    
                    # Download button
                    csv = table_data.to_csv(index=False).encode("utf-8")
                    st.download_button(
                        label=f"📥 Download '{selected_table}' as CSV",
                        data=csv,
                        file_name=f"{selected_table}_export.csv",
                        mime="text/csv",
                    )
        except Exception as e:
            st.error(f"Error querying SQLite database: {e}")
