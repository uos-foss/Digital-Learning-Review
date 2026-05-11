import os
import sys
# Add workspace root to python path to allow local imports
sys.path.append(os.getcwd())
import pandas as pd
from data_manager import get_spreadsheet_data
from processing import get_processed_audit_data
from dotenv import load_dotenv

# Load environment to ensure credentials are loaded
load_dotenv()

def inspect_unique_values():
    main_id = os.getenv("MAIN_SPREADSHEET_ID")
    if not main_id:
        print("ERROR: MAIN_SPREADSHEET_ID not found in .env file.")
        return
        
    print(f"Connecting to Google Sheets ID: {main_id}")
    ss, _ = get_spreadsheet_data(main_id)
    
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
    
    print("Fetching Autumn and Spring data...")
    df_aut = get_processed_audit_data(ss, "All Schools Aut")
    df_spr = get_processed_audit_data(ss, "All Schools SPR")
    
    combined_df = pd.concat([df_aut, df_spr], ignore_index=True)
    print(f"Successfully combined datasets ({len(combined_df)} total rows).\n")
    
    unique_values = set()
    
    print("--- ANALYSIS PER COLUMN ---")
    for col in audit_cols:
        if col in combined_df.columns:
            vals = combined_df[col].dropna().astype(str).str.strip()
            # Filter out completely empty strings
            vals = vals[vals != '']
            unique_col_vals = sorted(list(vals.unique()))
            print(f"\nColumn: {col}")
            for v in unique_col_vals:
                print(f"  - {v}")
                unique_values.add(v)
        else:
            print(f"\nColumn '{col}' not found in the combined dataset.")
            
    print("\n====================================================")
    print("FULL LIST OF UNIQUE NON-EMPTY VALUES FOR ALL COLUMNS")
    print("====================================================")
    for val in sorted(list(unique_values)):
        print(val)

if __name__ == "__main__":
    inspect_unique_values()
