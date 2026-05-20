import streamlit as st
import pandas as pd
import altair as alt
import os
import re
import logging
from data_manager import get_spreadsheet_data, initialize_checklist_headers, initialize_feedback_headers

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
        "👤 User Control"
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
                    ss, _ = get_spreadsheet_data(feedback_id)
                    sheet = ss.worksheet("Sheet1")
                    raw_data = sheet.get_all_values()
                    
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
            st.write("Force-clearing streamlit caches will force the application to fetch fresh data records from Google Sheets on the next page interaction.")
            if st.button("🔄 Purge Data Cache (st.cache_data.clear)", type="primary", use_container_width=True):
                st.cache_data.clear()
                logging.info("♻️ System cache was cleared manually via the Admin Panel.")
                st.success("App cache successfully purged! All data will reload on next render.")
                st.balloons()
                
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
    # TAB 5: USER CONTROL (FUTURE ROADMAP)
    # ----------------------------------------------------
    elif selected_tab == "👤 User Control":
        st.subheader("👤 Portal Access & User Control")
        
        st.info("💡 **Roadmap Notice**: Dynamic user administration (adding/deactivating accounts and toggling user roles) is currently scheduled for the next release. The mock panel below illustrates how these controls will operate.")
        
        st.markdown("##### **Active User Registry**")
        
        # Load user credentials from environment variables for active visualization
        user_list = [
            {"Username": "ALA", "Default School": "ALA", "System Role": "School Module Lead", "Auth Source": "Environment (.env)", "Status": "Active"},
            {"Username": "ECN", "Default School": "ECN", "System Role": "School Module Lead", "Auth Source": "Environment (.env)", "Status": "Active"},
            {"Username": "EDC", "Default School": "EDC", "System Role": "School Module Lead", "Auth Source": "Environment (.env)", "Status": "Active"},
            {"Username": "GPL", "Default School": "GPL", "System Role": "School Module Lead", "Auth Source": "Environment (.env)", "Status": "Active"},
            {"Username": "IJC", "Default School": "IJC", "System Role": "School Module Lead", "Auth Source": "Environment (.env)", "Status": "Active"},
            {"Username": "MGT", "Default School": "MGT", "System Role": "School Module Lead", "Auth Source": "Environment (.env)", "Status": "Active"},
            {"Username": "SPR", "Default School": "SPR", "System Role": "School Module Lead", "Auth Source": "Environment (.env)", "Status": "Active"},
            {"Username": "FACULTY", "Default School": "All (Faculty Wide)", "System Role": "Faculty Reviewer", "Auth Source": "Environment (.env)", "Status": "Active"},
            {"Username": "DLA", "Default School": "All (Faculty Wide)", "System Role": "Digital Learning Advisor", "Auth Source": "Environment (.env)", "Status": "Active"},
            {"Username": "ADMIN", "Default School": "All (Faculty Wide)", "System Role": "System Administrator", "Auth Source": "Environment (.env)", "Status": "Active"}
        ]
        df_users = pd.DataFrame(user_list)
        st.dataframe(df_users, use_container_width=True, hide_index=True)
        
        st.divider()
        
        # Mock interactive controls
        st.markdown("##### **Access Control Actions (Mock Controls)**")
        
        c1, c2 = st.columns(2)
        with c1:
            st.selectbox("Select User account:", df_users["Username"])
            st.segmented_control("System Role:", ["School Module Lead", "Faculty Reviewer", "Digital Learning Advisor", "System Administrator"], default="School Module Lead")
            st.segmented_control("Access Status:", ["Active", "Suspended / Disabled"], default="Active")
            st.button("Update User Profile", disabled=True, use_container_width=True)
            
        with c2:
            st.text_input("New Username (School Code or Identifier):", placeholder="e.g. MAT")
            st.selectbox("Default School Context:", ["All (Faculty Wide)", "ALA", "ECN", "EDC", "GPL", "IJC", "MGT", "SPR"])
            st.text_input("Password:", type="password", placeholder="Enter strong password...")
            st.button("Create Account Registry", type="primary", disabled=True, use_container_width=True)
            
        st.markdown("---")
        st.markdown("##### **Feature Capability Toggles (Mock Controls)**")
        st.write("Administrators will be able to restrict specific feature subsets without deploying code modifications:")
        
        tc1, tc2 = st.columns(2)
        with tc1:
            st.toggle("Enable VLE Checklist self-audit form submissions", value=True, disabled=True)
            st.toggle("Enable Leganto missing lists warning checks", value=True, disabled=True)
            st.toggle("Allow feedback submissions from active users", value=True, disabled=True)
        with tc2:
            st.toggle("Maintenance Mode (Locks portal for all non-ADMIN accounts)", value=False, disabled=True)
            st.toggle("Enable SITS assessment integration analytics", value=True, disabled=True)
            st.toggle("Force HTTPS SSL Enforcement", value=True, disabled=True)
            
        st.caption("Capabilities and credentials management will be migrated to a secure database worksheet in Google Sheets in the upcoming update.")
