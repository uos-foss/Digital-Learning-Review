import streamlit as st
import pandas as pd
import os
import datetime
import extra_streamlit_components as stx
from data_manager import get_spreadsheet_data, get_latest_checklist_entry, initialize_checklist_headers, append_row_to_sheet, get_all_checklist_entries
from processing import get_processed_audit_data, aggregate_faculty_stats, get_module_mapping, calculate_compliance_gap, get_checklist_summaries

# Page configuration
st.set_page_config(
    page_title="Digital Learning Review Dashboard",
    page_icon="📊",
    layout="wide"
)

from auth import check_password

# Secure Authentication & Session Persistence
if not check_password():
    st.stop()

# Sidebar Navigation (Accessible only after login)
st.sidebar.title("Navigation")
page = st.sidebar.radio("Go to", ["Faculty Overview", "School Dashboard", "Module Report Card", "Module Lead Checklist"])

st.sidebar.divider()

# Saved School View / Multi-Tenancy Preferences
st.sidebar.subheader("👤 User Session")
st.sidebar.write(f"Logged in as: **{st.session_state.username}**")

schools_list = ["ALA", "ECN", "EDC", "GPL", "IJC", "MGT", "SPR"]

saved_school_idx = 0
if st.session_state.saved_school in schools_list:
    saved_school_idx = schools_list.index(st.session_state.saved_school) + 1

selected_saved_school = st.sidebar.selectbox(
    "Active School View",
    ["All Schools"] + schools_list,
    index=saved_school_idx,
    help="Default school view for team-level ownership without data siloing."
)

if selected_saved_school == "All Schools":
    st.session_state.saved_school = "All"
else:
    st.session_state.saved_school = selected_saved_school

# Semester Selector (Moved to User Session area)
selected_semester = st.sidebar.radio(
    "Select Semester", 
    ["Autumn", "Spring"], 
    index=0 if st.session_state.semester == "Autumn" else 1,
    help="Active semester filter for school and module-level data."
)
st.session_state.semester = selected_semester

if st.sidebar.button("Log Out", use_container_width=True):
    st.session_state.logged_in = False
    st.session_state.saved_school = "All"
    st.session_state.username = ""
    st.session_state.logged_out_this_session = True
    st.session_state.logout_pending = True
    st.rerun()

st.sidebar.divider()
st.sidebar.info("Aggregating VLE Review audit data across semesters.")

# Data Loading
@st.cache_data(ttl=3600)
def load_audit_data():
    main_id = os.getenv("MAIN_SPREADSHEET_ID")
    ss, _ = get_spreadsheet_data(main_id)
    df_aut = get_processed_audit_data(ss, "All Schools Aut")
    df_spr = get_processed_audit_data(ss, "All Schools SPR")
    return df_aut, df_spr

@st.cache_data(ttl=3600)
def load_checklist_data():
    checklist_id = os.getenv("CHECKLIST_SPREADSHEET_ID")
    return get_checklist_summaries(checklist_id)

# Load the data
with st.spinner("Fetching data from Google Sheets..."):
    df_aut, df_spr = load_audit_data()
    checklist_sums = load_checklist_data()

# Main App Logic
if page == "Faculty Overview":
    st.title("🏛️ Faculty Overview")
    
    stats = aggregate_faculty_stats(df_aut, df_spr)
    
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("Autumn Modules", stats.get('Autumn Module Count', 0))
    with col2:
        st.metric("Autumn Avg Ally", f"{stats.get('Autumn Avg Ally', 0):.1%}")
    with col3:
        st.metric("Spring Modules", stats.get('Spring Module Count', 0))
    with col4:
        st.metric("Spring Avg Ally", f"{stats.get('Spring Avg Ally', 0):.1%}")
    with col5:
        st.metric("Self-Audits Done", len(checklist_sums))

    st.divider()
    
    col_a, col_b = st.columns(2)
    
    with col_a:
        st.subheader("Latest Ally Scores (25/26)")
        if not df_aut.empty:
            chart_data = df_aut[['Module name', 'Ally 25/26 All']].sort_values('Ally 25/26 All', ascending=False).head(20)
            st.bar_chart(chart_data, x='Module name', y='Ally 25/26 All')
        else:
            st.warning("No data found for Autumn.")
            
    with col_b:
        st.subheader("Compliance Gap Analysis")
        gaps = calculate_compliance_gap(df_aut)
        if gaps:
            gap_df = pd.DataFrame(list(gaps.items()), columns=['Category', 'Compliance %']).sort_values('Compliance %')
            st.bar_chart(gap_df, x='Category', y='Compliance %', horizontal=True)
        else:
            st.write("No compliance data available.")

    st.divider()
    
    st.subheader("⚠️ Priority List (Ally < 70%)")
    if not df_aut.empty:
        priority_df = df_aut[df_aut['Ally 25/26 All'] < 0.7].sort_values('Ally 25/26 All')
        if not priority_df.empty:
            st.warning(f"Found {len(priority_df)} modules with Ally scores below 70%.")
            st.dataframe(priority_df[['New module code', 'Module name', 'Mod. lead', 'Ally 25/26 All']], width='stretch')
            
            csv = priority_df.to_csv(index=False).encode('utf-8')
            st.download_button("📥 Download Priority List (CSV)", csv, "priority_list.csv", "text/csv")
        else:
            st.success("No modules found below the 70% threshold.")

elif page == "School Dashboard":
    st.title("🏫 School Dashboard")
    
    schools = sorted(list(set([s.split(' ')[0] for s in ["ALA", "ECN", "EDC", "GPL", "IJC", "MGT", "SPR"]])))
    
    # If saved_school is "All", let them select which school to view directly on the page
    if st.session_state.saved_school == "All":
        school = st.selectbox("Select School to View", schools, help="You have 'All Schools' active. Please select a specific school to view its dashboard.")
    else:
        school = st.session_state.saved_school
        
    semester = st.session_state.semester
    st.header(f"{school} - {semester} Semester")
    
    target_df = df_aut if semester == "Autumn" else df_spr
    
    if not target_df.empty:
        school_df = target_df[target_df['New module code'].str.startswith(school, na=False)].copy()
        
        if not school_df.empty:
            # Integration: Add self-audit status
            def get_audit_status(code):
                if code in checklist_sums:
                    return checklist_sums[code]['Status']
                return "❌ No"
            
            school_df['Self-Audited?'] = school_df['New module code'].apply(get_audit_status)
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total Modules", len(school_df))
            with col2:
                avg_ally = school_df['Ally 25/26 All'].mean() if 'Ally 25/26 All' in school_df.columns else 0
                st.metric("Avg Ally Score", f"{avg_ally:.1%}")
            with col3:
                audited_count = school_df['Self-Audited?'].apply(lambda x: x != "❌ No").sum()
                st.metric("Self-Audit Participation", f"{(audited_count / len(school_df)):.1%}")
            
            st.divider()
            st.subheader("Module Audit Status")
            st.dataframe(school_df[['New module code', 'Module name', 'Mod. lead', 'Ally 25/26 All', 'Self-Audited?']], width='stretch')
            
            csv_school = school_df.to_csv(index=False).encode('utf-8')
            st.download_button(f"📥 Export {school} {semester} Data", csv_school, f"{school}_{semester}_audit.csv", "text/csv")
        else:
            st.warning(f"No modules found for {school} in {semester}.")
    else:
        st.error(f"Data for {semester} is not available.")

elif page == "Module Report Card":
    st.title("📋 Module Report Card")
    
    module_mapping = get_module_mapping(df_aut, df_spr)
    combined_options = sorted([f"{code} - {name}" for code, name in module_mapping.items()])
    
    # Optional multi-tenant school filter to focus without siloing
    if st.session_state.saved_school != "All":
        filter_by_school = st.checkbox(f"Focus on my school ({st.session_state.saved_school})", value=True)
        if filter_by_school:
            combined_options = [opt for opt in combined_options if opt.startswith(st.session_state.saved_school)]
            
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
        st.header(f"Report Card: {selected_code}")
        st.subheader(module_mapping.get(selected_code, "Unknown Module"))
        
        # Integration: Add Self-Audit summary
        if selected_code in checklist_sums:
            sum_entry = checklist_sums[selected_code]
            status_emoji = sum_entry.get('Status', '✅').split(' ')[0]
            with st.expander(f"Latest Self-Audit Status: {sum_entry.get('Status', 'Yes')}", expanded=True):
                c1, c2, c3, c4 = st.columns(4)
                c1.write(f"**Welcome:** {'✅' if sum_entry['Q1'] else '❌'}")
                c2.write(f"**Staff:** {'✅' if sum_entry['Q2'] else '❌'}")
                c3.write(f"**Outline:** {'✅' if sum_entry['Q3'] else '❌'}")
                c4.write(f"**Assessment:** {'✅' if sum_entry['Q4'] else '❌'}")
                st.write(f"**Comments:** {sum_entry['Comments']}")
                st.caption(f"Last updated: {sum_entry['Timestamp']}")
        
        aut_m, spr_m = df_aut[df_aut['New module code'] == selected_code], df_spr[df_spr['New module code'] == selected_code]
        
        if not aut_m.empty or not spr_m.empty:
            col1, col2 = st.columns(2)
            with col1:
                st.subheader("🍂 Autumn Audit")
                if not aut_m.empty:
                    st.json(aut_m.iloc[0].to_dict())
                else:
                    st.write("No Autumn data.")
            with col2:
                st.subheader("🌱 Spring Audit")
                if not spr_m.empty:
                    st.json(spr_m.iloc[0].to_dict())
                else:
                    st.write("No Spring data.")
        else:
            st.warning("Module code not found.")

elif page == "Module Lead Checklist":
    st.title("✅ Module Lead Checklist")
    st.write("Use this form to self-audit your module and submit findings.")
    
    module_mapping = get_module_mapping(df_aut, df_spr)
    combined_options = sorted([f"{code} - {name}" for code, name in module_mapping.items()])
    
    # Optional multi-tenant school filter to focus without siloing
    if st.session_state.saved_school != "All":
        filter_by_school = st.checkbox(f"Focus on my school ({st.session_state.saved_school})", value=True, key="cl_focus_school")
        if filter_by_school:
            combined_options = [opt for opt in combined_options if opt.startswith(st.session_state.saved_school)]
            
    if 'selected_module_code' not in st.session_state:
        st.session_state.selected_module_code = ""

    current_idx = 0
    if st.session_state.selected_module_code:
        for i, opt in enumerate(combined_options):
            if opt.startswith(st.session_state.selected_module_code + " -"):
                current_idx = i + 1
                break

    def on_cl_module_change():
        if st.session_state.cl_unified_search:
            st.session_state.selected_module_code = st.session_state.cl_unified_search.split(" - ")[0]
        else:
            st.session_state.selected_module_code = ""

    st.selectbox(
        "Search by Module Code or Name", 
        options=[""] + combined_options, 
        index=current_idx, 
        key="cl_unified_search",
        on_change=on_cl_module_change
    )

    selected_code = st.session_state.selected_module_code
    matched_name = module_mapping.get(selected_code, "")
    
    checklist_id = os.getenv("CHECKLIST_SPREADSHEET_ID")
    initialize_checklist_headers(checklist_id, "Sheet1")
    
    latest_entry = None
    if selected_code:
        latest_entry = get_latest_checklist_entry(checklist_id, "Sheet1", selected_code)

    with st.form("checklist_form"):
        if latest_entry:
            st.info(f"Last updated: {latest_entry[0]}. Showing your previous progress below.")
        else:
            st.info(f"Auditing: **{selected_code} - {matched_name}**" if selected_code else "Please select a module above.")
        
        st.divider()
        def_q1 = latest_entry[3] == "TRUE" if latest_entry and len(latest_entry) > 3 else False
        def_q2 = latest_entry[4] == "TRUE" if latest_entry and len(latest_entry) > 4 else False
        def_q3 = latest_entry[5] == "TRUE" if latest_entry and len(latest_entry) > 5 else False
        def_q4 = latest_entry[6] == "TRUE" if latest_entry and len(latest_entry) > 6 else False
        def_comm = latest_entry[7] if latest_entry and len(latest_entry) > 7 else ""

        q1 = st.checkbox("Welcome message present?", value=def_q1)
        q2 = st.checkbox("Key staff contacts complete?", value=def_q2)
        q3 = st.checkbox("Module outline visible?", value=def_q3)
        q4 = st.checkbox("Assessment overview consistent with SITS?", value=def_q4)
        comments = st.text_area("Additional Comments", value=def_comm)
        submitted = st.form_submit_button("Submit Update")
        
        if submitted:
            if selected_code and matched_name:
                timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                row = [timestamp, selected_code, matched_name, q1, q2, q3, q4, comments]
                try:
                    append_row_to_sheet(checklist_id, "Sheet1", row)
                    load_checklist_data.clear()
                    st.success(f"Audit trail updated for {selected_code}!")
                    st.balloons()
                    st.rerun()
                except Exception as e:
                    st.error(f"Error submitting checklist: {e}")
            else:
                st.warning("Please select a Module Code and Name from the dropdowns above.")

    if selected_code:
        st.divider()
        st.subheader(f"📜 Version History: {selected_code}")
        history_df = get_all_checklist_entries(checklist_id, "Sheet1", selected_code)
        if not history_df.empty:
            st.write("Below are all previous updates for this module.")
            st.dataframe(history_df.drop(columns=['Module Code', 'Module Name']), width='stretch')
        else:
            st.info("No previous history found for this module.")
