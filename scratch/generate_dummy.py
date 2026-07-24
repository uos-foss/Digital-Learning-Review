import sqlite3
import pandas as pd
import random
import os

db_path = "data/database.sqlite"
if not os.path.exists(db_path):
    print("Database not found in data/database.sqlite")
    codes = [f"ALA{100+i}" for i in range(5)] + [f"ECN{200+i}" for i in range(5)]
else:
    conn = sqlite3.connect(db_path)
    try:
        df = pd.read_sql_query("SELECT module_code FROM ally_scores", conn)
        codes = df['module_code'].tolist()
    except Exception as e:
        print(f"Error fetching codes: {e}")
        codes = [f"ALA{100+i}" for i in range(5)] + [f"ECN{200+i}" for i in range(5)]
    conn.close()

if not codes:
    codes = [f"ALA{100+i}" for i in range(5)] + [f"ECN{200+i}" for i in range(5)]

def generate_data(filename, month_offset):
    data = []
    for code in codes:
        # random baseline
        base = random.uniform(0.5, 0.8)
        # add offset (progress over time)
        measured = min(1.0, base + (month_offset * 0.05))
        weighted = min(1.0, measured + 0.05)
        files = random.randint(10, 500)
        data.append({
            "module_code": code,
            "measured": measured,
            "weighted": weighted,
            "files": files
        })
    df = pd.DataFrame(data)
    df.to_csv(filename, index=False)
    print(f"Generated {filename}")

generate_data("15-09-24_Ally Data.csv", 0)
generate_data("15-10-24_Ally Data.csv", 1)
generate_data("15-11-24_Ally Data.csv", 2)
