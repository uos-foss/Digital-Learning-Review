import os
import sys
sys.path.append(os.getcwd())

import sqlite3
import pandas as pd
from database import DB_PATH

def main():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT * FROM audit_fields", conn)
    print("Audit Fields Configuration:")
    print(df.to_string(index=False))
    conn.close()

if __name__ == "__main__":
    main()
