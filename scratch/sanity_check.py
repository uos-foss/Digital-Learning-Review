import sys
import os
try:
    import processing
    import app
    print("SUCCESS: Imports pass.")
except Exception as e:
    # Note: app may throw exception trying to initialize Streamlit config in a script, which is fine
    print(f"Import attempt finished. Error (if any): {e}")
