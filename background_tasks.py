import threading
import time
import logging
import os
from sync_data import run_synchronization
from data_manager import append_row_to_sheet
from database import get_unsynced_checklists, mark_checklists_synced, get_unsynced_ai_responses, mark_ai_responses_synced

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

def push_unsynced_ai_responses():
    """Pushes any locally unsynced AI responses to Google Sheets in batches."""
    spreadsheet_id = os.getenv("AI_RESPONSES_SPREADSHEET_ID")
    if not spreadsheet_id:
        return
        
    unsynced = get_unsynced_ai_responses()
    if not unsynced:
        return
        
    logging.info(f"Pushing {len(unsynced)} unsynced AI responses to Google Sheets...")
    synced_ids = []
    
    for record in unsynced:
        # Reconstruct the row layout expected by AI_RESPONSES_SPREADSHEET_ID
        row_data = [
            record.get("timestamp", ""),
            record.get("module_code", ""),
            record.get("module_title", ""),
            record.get("school", ""),
            record.get("user_id", ""),
            record.get("gen_ai_activity", ""),
            record.get("assessment_title", ""),
            record.get("assessment_type", ""),
            record.get("ai_usability", ""),
            record.get("ai_intended_use", ""),
            record.get("status", "")
        ]
        
        try:
            # Assuming AI Responses sheet uses the first tab "Form Responses 1" or "Sheet1"
            # It's safest to just append to the first worksheet if we don't know the exact name.
            # data_manager.append_row_to_sheet takes sheet_name, but it also has client.open_by_key logic.
            # We can use "Sheet1" or just wait... AI Audit `app.py` uses `get_worksheet(0)`.
            # Let's write a small helper inside data_manager or use append_row_to_sheet if it works.
            # Actually, `append_row_to_sheet(spreadsheet_id, "Sheet1", row_data)` might fail if name is not "Sheet1".
            # Let's just use append_row_to_sheet(spreadsheet_id, "Form Responses 1", row_data) or we might need to modify it.
            # I will pass None or just try "Form Responses 1" which is standard for forms.
            # Or wait, `data_manager.py` uses `worksheet = ss.worksheet(sheet_name)`. If we pass `sheet_name`, it needs to be exact.
            # Let's import get_gspread_client and do it directly to be safe.
            from data_manager import get_gspread_client
            client = get_gspread_client()
            ss = client.open_by_key(spreadsheet_id)
            worksheet = ss.get_worksheet(0)
            worksheet.append_row(row_data)
            synced_ids.append(record["id"])
        except Exception as e:
            logging.error(f"❌ Failed to sync AI response for {record.get('module_code')}: {e}")
            
    if synced_ids:
        mark_ai_responses_synced(synced_ids)
        logging.info(f"✅ Successfully synced {len(synced_ids)} AI responses to Google Sheets.")

def background_sync_loop(interval_seconds=3600):
    """Loop that runs synchronization periodically."""
    logging.info(f"Background sync daemon started. Syncing every {interval_seconds} seconds.")
    while True:
        try:
            # First, push any local offline writes up to Google Sheets
            push_unsynced_checklists()
            push_unsynced_ai_responses()
            
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
