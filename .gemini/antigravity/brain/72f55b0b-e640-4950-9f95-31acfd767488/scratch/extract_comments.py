import os
import sys
import pandas as pd
from dotenv import load_dotenv

# Add project root to path
sys.path.append(r"c:\Users\fs1hpc\Documents\GitHub\Digital-Learning-Review")

load_dotenv()

from data_manager import get_gspread_client

def extract_comments():
    print("Loading Google Sheets client...")
    try:
        client = get_gspread_client()
    except Exception as e:
        print(f"Error initializing sheets client: {e}")
        return
        
    spreadsheet_id = os.getenv("MAIN_SPREADSHEET_ID")
    print(f"Opening spreadsheet: {spreadsheet_id}")
    try:
        sh = client.open_by_key(spreadsheet_id)
    except Exception as e:
        print(f"Error opening spreadsheet: {e}")
        return
        
    worksheets = sh.worksheets()
    print(f"Worksheets: {[ws.title for ws in worksheets]}")
    
    all_comments = []
    
    for ws in worksheets:
        title = ws.title
        # Focus on "Aut" and "Spr" audit worksheets as they hold the comments
        if not ("Aut" in title or "Spr" in title or "Audit" in title):
            continue
            
        print(f"Processing worksheet: {title}...")
        try:
            values = ws.get_all_values()
            if not values or len(values) < 2:
                continue
            
            # Row index 1 is the actual column headers
            headers = [h.strip() for h in values[1]]
            rows = values[2:]
            
            # Find any columns with comments or improvements in their header name
            target_indices = []
            for idx, h in enumerate(headers):
                h_lower = h.lower()
                if "comments" in h_lower or "improvements" in h_lower:
                    target_indices.append((idx, h))
                    
            if target_indices:
                print(f"Found comments columns at indices: {target_indices} in {title}")
                for col_idx, col_name in target_indices:
                    for row in rows:
                        if col_idx < len(row):
                            val = row[col_idx].strip()
                            if val not in ["", "-", "N/A", "n/a", "none", "None", "Nil", "nil"]:
                                all_comments.append(val)
            else:
                print(f"No comments columns in {title}. Headers: {headers[:5]}")
        except Exception as e:
            print(f"Error reading worksheet {title}: {e}")
            
    print(f"\nExtracted {len(all_comments)} total non-empty comment strings.")
    if all_comments:
        df_comm = pd.DataFrame(all_comments, columns=["comment"])
        print("\n--- TOP 30 COMMON COMMENTS ---")
        counts = df_comm["comment"].value_counts().head(30)
        for val, cnt in counts.items():
            print(f"({cnt}) {val}")
    else:
        print("No comments found.")

if __name__ == "__main__":
    extract_comments()
