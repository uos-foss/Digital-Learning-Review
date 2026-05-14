import os
import sys
# Add workspace root to python path to allow local imports
sys.path.append(os.getcwd())
from data_manager import get_spreadsheet_data
from dotenv import load_dotenv

load_dotenv()

def inspect_leganto():
    leganto_id = os.getenv("LEGANTO_NOLIST_ID")
    if not leganto_id:
        print("ERROR: LEGANTO_NOLIST_ID not found in .env file.")
        return
        
    print(f"Connecting to Leganto Google Sheet ID: {leganto_id}")
    try:
        ss, worksheets = get_spreadsheet_data(leganto_id)
        print(f"Found {len(worksheets)} worksheets.")
        for ws in worksheets:
            print(f"\nWorksheet: {ws.title}")
            data = ws.get_all_values()
            if data:
                print(f"Headers: {data[0]}")
                if len(data) > 1:
                    print(f"First row sample: {data[1]}")
                print(f"Total rows: {len(data)}")
            else:
                print("Sheet is empty")
    except Exception as e:
        print(f"Error fetching data: {e}")

if __name__ == "__main__":
    inspect_leganto()
