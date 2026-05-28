import os
import sys
import pandas as pd
from database import cache_dataframe_to_sqlite, init_db, save_checklist_record

def sync_main_audit():
    print("🔄 Pulling Main Audit Data...")
    from data_manager import get_spreadsheet_data
    from processing import get_processed_audit_data
    main_id = os.getenv("MAIN_SPREADSHEET_ID")
    if main_id:
        try:
            ss, _ = get_spreadsheet_data(main_id)
            df_aut = get_processed_audit_data(ss, "All Schools Aut")
            df_spr = get_processed_audit_data(ss, "All Schools SPR")
            cache_dataframe_to_sqlite(df_aut, "main_vle_audit_aut")
            cache_dataframe_to_sqlite(df_spr, "main_vle_audit_spr")
            print("✅ Main Audit Data synced.")
        except Exception as e:
            print(f"❌ Error syncing Main Audit Data: {e}")

def sync_users_and_roles():
    print("🔄 Pulling Users and Roles...")
    from data_manager import get_spreadsheet_data
    sheet_id = os.getenv("USERS_SPREADSHEET_ID")
    if sheet_id:
        try:
            ss, _ = get_spreadsheet_data(sheet_id)
            # Users
            users_sheet = ss.worksheet("Users")
            users_data = users_sheet.get_all_values()
            if len(users_data) > 1:
                df_users = pd.DataFrame(users_data[1:], columns=users_data[0])
                cache_dataframe_to_sqlite(df_users, "users")
            # Roles
            roles_sheet = ss.worksheet("Roles")
            roles_data = roles_sheet.get_all_values()
            if len(roles_data) > 1:
                df_roles = pd.DataFrame(roles_data[1:], columns=roles_data[0])
                cache_dataframe_to_sqlite(df_roles, "roles")
            print("✅ Users and Roles synced.")
        except Exception as e:
            print(f"❌ Error syncing Users/Roles: {e}")

def sync_checklists():
    print("🔄 Pulling Checklists...")
    from data_manager import get_gspread_client
    checklist_id = os.getenv("CHECKLIST_SPREADSHEET_ID")
    if checklist_id:
        try:
            client = get_gspread_client()
            spreadsheet = client.open_by_key(checklist_id)
            worksheet = spreadsheet.worksheet("Sheet1")
            data = worksheet.get_all_values()
            if len(data) > 1:
                for row in data[1:]:
                    if len(row) > 1:
                        # Assuming Module Code is at index 1
                        module_code = row[1]
                        # Use module_code as ID to keep the latest entry per module
                        record_id = module_code.strip().upper()
                        save_checklist_record(record_id, row)
            print("✅ Checklists synced.")
        except Exception as e:
            print(f"❌ Error syncing Checklists: {e}")

def run_synchronization():
    """ETL pipeline extracting Google Sheets data and writing to SQLite."""
    print("🔄 Starting Data Synchronization...")
    try:
        init_db()
        sync_main_audit()
        sync_users_and_roles()
        sync_checklists()
        print("✅ Full Sync Process Completed.")
    except Exception as e:
        print(f"❌ Synchronisation failed: {str(e)}", file=sys.stderr)

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    run_synchronization()
