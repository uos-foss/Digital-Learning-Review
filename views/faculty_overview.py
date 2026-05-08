import streamlit as st
import pandas as pd
from processing import aggregate_faculty_stats, calculate_compliance_gap

def view_faculty_overview(df_aut, df_spr, checklist_sums):
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
