import pandas as pd
import numpy as np

def clean_audit_dataframe(df):
    """
    General cleaning for audit dataframes.
    """
    # Remove rows that are completely empty or have no module name
    df = df.dropna(subset=['Module name'], how='all')
    df = df[df['Module name'] != '']
    
    # Convert numerical columns
    score_cols = [c for c in df.columns if 'Ally' in c and ('All' in c or 'Files' in c or 'Score' in c)]
    for col in score_cols:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    
    return df

def get_processed_audit_data(spreadsheet, worksheet_name):
    """
    Fetches and processes a specific audit worksheet.
    """
    try:
        sheet = spreadsheet.worksheet(worksheet_name)
        data = sheet.get_all_values()
        
        if not data or len(data) < 2:
            return pd.DataFrame()
            
        # Row 1 is the actual header
        headers = data[1]
        rows = data[2:]
        
        df = pd.DataFrame(rows, columns=headers)
        df = clean_audit_dataframe(df)
        
        return df
    except Exception as e:
        print(f"Error processing {worksheet_name}: {e}")
        return pd.DataFrame()

def aggregate_faculty_stats(df_aut, df_spr):
    """
    Calculates summary statistics at the faculty level.
    """
    stats = {}
    
    # Example: Average Ally Score (using 25/26 All as the latest)
    col_name = 'Ally 25/26 All'
    
    if not df_aut.empty and col_name in df_aut.columns:
        stats['Autumn Avg Ally'] = df_aut[col_name].mean()
        stats['Autumn Module Count'] = len(df_aut)
        
    if not df_spr.empty and col_name in df_spr.columns:
        stats['Spring Avg Ally'] = df_spr[col_name].mean()
        stats['Spring Module Count'] = len(df_spr)
        
    return stats

def get_module_history(df_aut, df_spr, module_code):
    """
    Retrieves history for a single module across semesters.
    """
    # Try to find in Autumn
    aut_data = df_aut[df_aut['New module code'] == module_code] if not df_aut.empty else pd.DataFrame()
    spr_data = df_spr[df_spr['New module code'] == module_code] if not df_spr.empty else pd.DataFrame()
    
    return aut_data, spr_data

def get_module_mapping(df_aut, df_spr):
    """
    Returns a dictionary mapping module codes to module names.
    Combines data from both semesters.
    """
    mapping = {}
    
    for df in [df_aut, df_spr]:
        if not df.empty and 'New module code' in df.columns and 'Module name' in df.columns:
            # Drop rows with missing values for these columns
            temp_df = df.dropna(subset=['New module code', 'Module name'])
            for _, row in temp_df.iterrows():
                code = str(row['New module code']).strip()
                name = str(row['Module name']).strip()
                if code and name:
                    mapping[code] = name
                    
    return mapping

def calculate_compliance_gap(df):
    """
    Calculates the percentage of 'Yes' (or positive indicators) for audit categories.
    """
    audit_cols = [
        'Welcome to your module message?', 
        'Key staff contacts complete?', 
        'Module outline complete?', 
        'How you will be assessed visible?',
        'Skills development (SGAs) visible?',
        'Accessibility statement visible?',
        'School handbook visible?',
        'Assessment overview - present and consistent with SITS?',
        'Assessment support and guidance visible to students?',
        'University help and study support visible to students?'
    ]
    
    gaps = {}
    for col in audit_cols:
        if col in df.columns:
            # Count 'Yes' or 'Teaching only' as positive for some, but let's stick to 'Yes' for simplicity or a regex
            # Let's count how many start with 'Yes'
            positive_count = df[col].str.startswith('Yes', na=False).sum()
            total_count = len(df)
            gaps[col] = (positive_count / total_count) if total_count > 0 else 0
            
    return gaps

def get_checklist_summaries(spreadsheet_id):
    """
    Fetches all checklist entries and returns a dictionary 
    mapping module codes to their latest audit status.
    """
    from data_manager import get_gspread_client
    import os
    client = get_gspread_client()
    try:
        spreadsheet = client.open_by_key(spreadsheet_id)
        worksheet = spreadsheet.worksheet("Sheet1")
        data = worksheet.get_all_values()
        if len(data) <= 1:
            return {}
        
        headers = data[0]
        summaries = {}
        # Iterate and keep the LATEST for each module (since they are in chronological order usually)
        for row in data[1:]:
            if len(row) > 1:
                m_code = row[1]
                q1 = row[3] == "TRUE"
                q2 = row[4] == "TRUE"
                q3 = row[5] == "TRUE"
                q4 = row[6] == "TRUE"
                
                q_states = [q1, q2, q3, q4]
                true_count = sum(q_states)
                
                if true_count == len(q_states):
                    status = "✅ Complete"
                elif true_count > 0:
                    status = "🟡 Partial"
                else:
                    status = "❌ Incomplete"

                summaries[m_code] = {
                    'Timestamp': row[0],
                    'Q1': q1,
                    'Q2': q2,
                    'Q3': q3,
                    'Q4': q4,
                    'Status': status,
                    'Comments': row[7] if len(row) > 7 else ""
                }
        return summaries
    except:
        return {}

def get_updated_ally_scores(spreadsheet_id):
    """
    Fetches the updated Ally overall scores from the external Ally spreadsheet
    and returns a mapping dictionary of {clean_module_code: overall_score}.
    """
    from data_manager import get_spreadsheet_data
    try:
        ss, _ = get_spreadsheet_data(spreadsheet_id)
        sheet = ss.worksheet("Sheet1")
        data = sheet.get_all_values()
        if len(data) <= 1:
            return {}
            
        mapping = {}
        for row in data[1:]:
            if len(row) >= 8:
                # Extract clean module code, e.g., 'GPL439' from 'GPL439.A.279588'
                raw_code = str(row[1]).split('.')[0].strip().upper()
                
                # Parse total files (column index 4) and measured score (column index 7)
                files = pd.to_numeric(row[4], errors='coerce')
                if pd.isna(files) or files < 0:
                    files = 0
                    
                measured_score = pd.to_numeric(row[7], errors='coerce')
                
                if raw_code and not pd.isna(measured_score):
                    # Asymptotic Credibility Model (k=0.15, baseline=0.50)
                    credibility = 1.0 - np.exp(-0.15 * files)
                    weighted_score = credibility * measured_score + (1.0 - credibility) * 0.50
                    mapping[raw_code] = {
                        'measured': measured_score,
                        'weighted': weighted_score,
                        'files': int(files)
                    }
                    
        return mapping
    except Exception as e:
        import logging
        logging.error(f"❌ Error loading updated Ally data: {e}")
        return {}
