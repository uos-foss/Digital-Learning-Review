import threading
import time
import logging
from sync_data import run_synchronization
from data_manager import append_row_to_sheet

def background_sync_loop(interval_seconds=3600):
    """Loop that runs synchronization periodically."""
    logging.info(f"Background sync daemon started. Syncing every {interval_seconds} seconds.")
    while True:
        try:
            run_synchronization()
        except Exception as e:
            logging.error(f"Background sync failed: {e}")
        time.sleep(interval_seconds)

def start_scheduler():
    """Starts the background scheduler thread if it's not already running."""
    import streamlit as st
    @st.cache_resource
    def _start_thread():
        thread = threading.Thread(target=background_sync_loop, args=(3600,), daemon=True)
        thread.start()
        return thread
    _start_thread()

def async_backup_checklist(spreadsheet_id, worksheet_name, row_data):
    """Pushes checklist to Google Sheets asynchronously."""
    def _backup():
        try:
            append_row_to_sheet(spreadsheet_id, worksheet_name, row_data)
            logging.info(f"✅ Async backup to Google Sheets completed for module: {row_data[1]}")
        except Exception as e:
            logging.error(f"❌ Async backup to Google Sheets failed: {e}")
            
    thread = threading.Thread(target=_backup, daemon=True)
    thread.start()
