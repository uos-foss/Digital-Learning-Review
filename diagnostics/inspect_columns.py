import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from data_manager import get_spreadsheet_data

def inspect_columns():
    main_id = os.getenv("MAIN_SPREADSHEET_ID")
    ss, sheets = get_spreadsheet_data(main_id)
    
    targets = ["All Schools Aut", "Ally Data", "VLE Report Data"]
    
    for title in targets:
        try:
            sheet = ss.worksheet(title)
            # Get first 2 rows to see headers and data types
            data = sheet.get_all_values()
            if data:
                df = pd.DataFrame(data[1:], columns=data[0])
                print(f"\n--- Columns in {title} ---")
                print(df.columns.tolist())
                print("First row sample:")
                print(df.iloc[0].to_dict())
        except Exception as e:
            print(f"Could not inspect {title}: {e}")

if __name__ == "__main__":
    inspect_columns()
