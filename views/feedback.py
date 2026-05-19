import streamlit as st
import os
import datetime
import logging
from data_manager import initialize_feedback_headers, append_row_to_sheet

def view_feedback():
    st.title("💬 App Feedback & Suggestions")
    st.write(
        "We value your input! Please use the form below to report bugs, request new features, "
        "or provide suggestions to help improve the Digital Learning Review portal."
    )
    
    feedback_id = os.getenv("FEEDBACK_SPREADSHEET_ID")
    
    if not feedback_id:
        st.error("Feedback spreadsheet configuration is missing. Please contact the administrator.")
        return

    # Use a nice card-like container for the form
    with st.container(border=True):
        st.subheader("Submit Your Feedback")
        
        with st.form("app_feedback_form", clear_on_submit=True):
            category = st.selectbox(
                "Feedback Category", 
                ["Bug Report", "Feature Request", "App Layout / Look & Feel", "General Feedback", "Other"]
            )
            
            rating_label = st.select_slider(
                "Rate Your Experience",
                options=["1 - Poor", "2 - Fair", "3 - Good", "4 - Very Good", "5 - Excellent"],
                value="4 - Very Good",
                help="Let us know how the app is performing for you."
            )
            
            # Map rating label to numeric value for easier data analysis
            rating_map = {
                "1 - Poor": 1,
                "2 - Fair": 2,
                "3 - Good": 3,
                "4 - Very Good": 4,
                "5 - Excellent": 5
            }
            rating_value = rating_map.get(rating_label, 3)
            
            comments = st.text_area(
                "Your Feedback / Comments",
                placeholder="Describe the issue, request, or suggestion in detail...",
                height=150
            )
            
            submitted = st.form_submit_button("Submit Feedback", type="primary")
            
            if submitted:
                if not comments.strip():
                    st.warning("Please provide your comments before submitting.")
                else:
                    username = st.session_state.get("username", "Unknown")
                    school = st.session_state.get("saved_school", "All")
                    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    
                    row = [timestamp, username, school, category, rating_value, comments]
                    
                    try:
                        with st.spinner("Submitting your feedback..."):
                            # Lazy initialization of sheet headers
                            initialize_feedback_headers(feedback_id, "Sheet1")
                            append_row_to_sheet(feedback_id, "Sheet1", row)
                            
                        logging.info(
                            f"✅ Feedback submitted successfully by user '{username}' (School: '{school}'). "
                            f"Category: '{category}', Rating: {rating_value}."
                        )
                        st.success("Thank you! Your feedback has been recorded.")
                        st.balloons()
                    except Exception as e:
                        logging.error(
                            f"❌ Error submitting feedback from user '{username}': {e}"
                        )
                        st.error(f"Error submitting feedback to Google Sheets: {e}")
