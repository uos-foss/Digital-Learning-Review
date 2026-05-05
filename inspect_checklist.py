import os
import pandas as pd
from data_manager import get_spreadsheet_data

def inspect_checklist():
    checklist_id = os.getenv("CHECKLIST_SPREADSHEET_ID")
    client = get_spreadsheet_data(checklist_id)[0] # Get the spreadsheet object
    try:
        worksheet = client.worksheet("Sheet1")
        data = worksheet.get_all_values()
        print(f"Total rows in checklist: {len(data)}")
        if data:
            print("Headers:", data[0])
            if len(data) > 1:
                print("First data row:", data[1])
    except Exception as e:
        print(f"Error inspecting checklist: {e}")

if __name__ == "__main__":
    inspect_checklist()
