import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from data_manager import get_spreadsheet_data

def inspect_all_schools():
    main_id = os.getenv("MAIN_SPREADSHEET_ID")
    ss, sheets = get_spreadsheet_data(main_id)
    
    title = "All Schools Aut"
    try:
        sheet = ss.worksheet(title)
        data = sheet.get_all_values()
        if data:
            print(f"\n--- First 5 rows of {title} ---")
            for i in range(5):
                print(f"Row {i}: {data[i]}")
    except Exception as e:
        print(f"Could not inspect {title}: {e}")

if __name__ == "__main__":
    inspect_all_schools()
