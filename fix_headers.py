import os
import gspread
from data_manager import get_gspread_client

def fix_checklist_headers():
    checklist_id = os.getenv("CHECKLIST_SPREADSHEET_ID")
    client = get_gspread_client()
    spreadsheet = client.open_by_key(checklist_id)
    worksheet = spreadsheet.worksheet("Sheet1")
    
    headers = [
        "Timestamp", "Module Code", "Module Name", 
        "Welcome message present?", "Key staff contacts complete?", 
        "Module outline visible?", "Assessment overview consistent with SITS?", 
        "Comments"
    ]
    
    data = worksheet.get_all_values()
    if not data or data[0] != headers:
        print("Inserting headers...")
        worksheet.insert_row(headers, index=1)
        print("Done.")
    else:
        print("Headers already present.")

if __name__ == "__main__":
    fix_checklist_headers()
