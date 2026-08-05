import threading
import time
import logging
import os
from sync_data import run_synchronization
from data_manager import append_row_to_sheet
from database import get_unsynced_checklists, mark_checklists_synced

def push_unsynced_checklists():
    """Pushes any locally unsynced checklists to Google Sheets in batches."""
    spreadsheet_id = os.getenv("CHECKLIST_SPREADSHEET_ID")
    if not spreadsheet_id:
        return
        
    unsynced = get_unsynced_checklists()
    if not unsynced:
        return
        
    logging.info(f"Pushing {len(unsynced)} unsynced checklists to Google Sheets...")
    synced_ids = []
    
    for record in unsynced:
        # Reconstruct the row layout expected by Google Sheets
        row_data = [
            record.get("timestamp", ""),
            record.get("module_code", ""),
            record.get("module_name", ""),
            record.get("welcome_message", ""),
            record.get("contacts_complete", ""),
            record.get("outline_visible", ""),
            record.get("assessment_overview", ""),
            record.get("comments", "")
        ]
        
        try:
            append_row_to_sheet(spreadsheet_id, "Sheet1", row_data)
            synced_ids.append(record["id"])
        except Exception as e:
            logging.error(f"❌ Failed to sync checklist {record.get('module_code')}: {e}")
            
    if synced_ids:
        mark_checklists_synced(synced_ids)
        logging.info(f"✅ Successfully synced {len(synced_ids)} checklists to Google Sheets.")

# There was a push_unsynced_ai_responses() here. It is deliberately gone: the
# ai_audit_queue is the satellite AI-Audit app's outbox, and that app pushes and
# then deletes those rows. This one only flagged them as synced, so if this
# module were ever re-enabled the two would fight and every submission would be
# posted twice. Do not reinstate it.

def background_sync_loop(interval_seconds=3600):
    """Loop that runs synchronization periodically."""
    logging.info(f"Background sync daemon started. Syncing every {interval_seconds} seconds.")
    while True:
        try:
            # First, push any local offline writes up to Google Sheets
            push_unsynced_checklists()

            # Then, run the ETL pull from Google Sheets to local SQLite
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
