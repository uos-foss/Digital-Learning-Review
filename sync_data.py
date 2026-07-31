import os
import sys
import pandas as pd
from database import cache_dataframe_to_sqlite, init_db, save_checklist_record, get_db_connection


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

def sync_assessment_data():
    print("🔄 Pulling SITS Assessment Data...")
    from data_manager import get_spreadsheet_data
    sheet_id = os.getenv("ASSESSMENT_SPREADSHEET_ID")
    if sheet_id:
        try:
            ss, _ = get_spreadsheet_data(sheet_id)
            sheet = ss.worksheet("All Schools 2026/27")
            data = sheet.get_all_values()
            if len(data) > 1:
                df = pd.DataFrame(data[1:], columns=data[0])
                if 'CIS unit code' in df.columns:
                    df['CIS unit code'] = df['CIS unit code'].astype(str).str.strip().str.upper()
                if 'Module code' in df.columns:
                    df['Module code'] = df['Module code'].astype(str).str.strip().str.upper()
                cache_dataframe_to_sqlite(df, "sits_assessment_2026_27")
            print("✅ Assessment Data synced.")
        except Exception as e:
            print(f"❌ Error syncing Assessment Data: {e}")

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

def sync_ai_responses():
    print("🔄 Pulling AI Responses...")
    from data_manager import get_spreadsheet_data
    sheet_id = os.getenv("AI_RESPONSES_SPREADSHEET_ID")
    if sheet_id:
        try:
            ss, _ = get_spreadsheet_data(sheet_id)
            # Fetch data from the first worksheet
            worksheet = ss.get_worksheet(0)
            data = worksheet.get_all_values()
            if len(data) > 1:
                df_responses = pd.DataFrame(data[1:], columns=data[0])
                cache_dataframe_to_sqlite(df_responses, "ai_audit_responses")
            print("✅ AI Responses synced.")
        except Exception as e:
            print(f"❌ Error syncing AI Responses: {e}")

def sync_comment_bank():
    print("🔄 Syncing Comment Bank bidirectionally (Pull & Push)...")
    import logging
    from data_manager import get_spreadsheet_data
    sheet_id = os.getenv("DATA_SHEET_ID")
    if not sheet_id:
        msg = "DATA_SHEET_ID is not configured in the environment variables."
        logging.error(msg)
        print(f"❌ {msg}")
        raise ValueError(msg)
        
    try:
        # 1. Fetch remote data from Google Sheets
        ss, _ = get_spreadsheet_data(sheet_id)
        try:
            sheet = ss.worksheet("Comment_Bank")
        except Exception:
            # If the sheet doesn't exist, create it with correct headers
            sheet = ss.add_worksheet(title="Comment_Bank", rows=100, cols=6)
            sheet.update('A1', [['id', 'category', 'comment', 'advice', 'resource_url', 'resource_text']])
            
        data = sheet.get_all_values()
        
        # 2. Fetch local data from SQLite
        with get_db_connection() as conn:
            try:
                df_local = pd.read_sql_query("SELECT id, category, comment, advice, resource_url, resource_text FROM comment_bank", conn)
            except Exception:
                df_local = pd.DataFrame(columns=['id', 'category', 'comment', 'advice', 'resource_url', 'resource_text'])
                
        # 3. Parse remote data
        if len(data) > 1:
            df_remote = pd.DataFrame(data[1:], columns=data[0])
            df_remote.columns = [c.strip().lower() for c in df_remote.columns]
            if 'tag' in df_remote.columns and 'comment' not in df_remote.columns:
                df_remote = df_remote.rename(columns={'tag': 'comment'})
            if 'resources' in df_remote.columns and 'resource_url' not in df_remote.columns:
                df_remote = df_remote.rename(columns={'resources': 'resource_url'})
                
            # Add missing fields
            for col in ['id', 'category', 'comment', 'advice', 'resource_url', 'resource_text']:
                if col not in df_remote.columns:
                    df_remote[col] = ""
            df_remote = df_remote[['id', 'category', 'comment', 'advice', 'resource_url', 'resource_text']]
        else:
            df_remote = pd.DataFrame(columns=['id', 'category', 'comment', 'advice', 'resource_url', 'resource_text'])
            
        # 4. Standardize local dataframe
        if not df_local.empty:
            df_local.columns = [c.strip().lower() for c in df_local.columns]
            df_local = df_local[['id', 'category', 'comment', 'advice', 'resource_url', 'resource_text']]
            
        # 5. Merge remote and local (remote updates win for rows matching by ID)
        df_remote['id'] = pd.to_numeric(df_remote['id'], errors='coerce')
        df_remote_with_id = df_remote[df_remote['id'].notna()].copy()
        df_remote_with_id['id'] = df_remote_with_id['id'].astype(int)
        
        df_remote_no_id = df_remote[df_remote['id'].isna()].copy()
        
        # Standardize local IDs
        df_local['id'] = pd.to_numeric(df_local['id'], errors='coerce').fillna(0).astype(int)
        
        # Merge rows with matching IDs (remote edits win for the same ID)
        df_merged_ids = pd.concat([df_local, df_remote_with_id], ignore_index=True)
        df_merged_ids = df_merged_ids.drop_duplicates(subset=['id'], keep='last')
        
        # Now handle new remote rows without IDs (assign new auto-incremented IDs)
        if not df_remote_no_id.empty:
            max_id = df_merged_ids['id'].max()
            if pd.isna(max_id) or max_id < 0:
                max_id = 0
            next_id = int(max_id) + 1
            
            new_rows = []
            for _, row in df_remote_no_id.iterrows():
                # Avoid duplicate comment text
                comment_str = str(row['comment']).strip()
                if comment_str and comment_str not in df_merged_ids['comment'].astype(str).str.strip().values:
                    new_rows.append({
                        'id': next_id,
                        'category': str(row['category']).strip(),
                        'comment': comment_str,
                        'advice': str(row['advice']).strip(),
                        'resource_url': str(row['resource_url']).strip(),
                        'resource_text': str(row['resource_text']).strip()
                    })
                    next_id += 1
            if new_rows:
                df_new = pd.DataFrame(new_rows)
                df_merged = pd.concat([df_merged_ids, df_new], ignore_index=True)
            else:
                df_merged = df_merged_ids
        else:
            df_merged = df_merged_ids
            
        # Ensure we drop any rows where comment is empty
        df_merged['comment'] = df_merged['comment'].astype(str).str.strip()
        df_merged = df_merged[df_merged['comment'] != ""]
        
        # Sort by category and comment to keep it clean
        df_merged = df_merged.sort_values(by=['category', 'comment']).reset_index(drop=True)
        df_merged = df_merged[['id', 'category', 'comment', 'advice', 'resource_url', 'resource_text']]
        
        # 7. Save merged data back to SQLite
        cache_dataframe_to_sqlite(df_merged, "comment_bank")
        init_db()
        
        # 8. Push merged data back to Google Sheets (making them perfectly in sync)
        sheet.clear()
        df_push = df_merged.fillna("")
        headers = df_push.columns.tolist()
        rows_to_push = [headers] + df_push.values.tolist()
        
        try:
            sheet.update(range_name='A1', values=rows_to_push)
        except TypeError:
            sheet.update('A1', rows_to_push)
            
        print("✅ Comment Bank synced bidirectionally (SQLite & Google Sheets updated).")
    except Exception as e:
        logging.error(f"Error syncing Comment Bank: {e}")
        print(f"❌ Error syncing Comment Bank: {e}")
        raise e


def push_comment_bank_to_sheets():
    """Pushes the local comment_bank table from SQLite to Google Sheets (overwriting it)."""
    import logging
    from data_manager import get_spreadsheet_data
    sheet_id = os.getenv("DATA_SHEET_ID")
    if not sheet_id:
        return
        
    try:
        ss, _ = get_spreadsheet_data(sheet_id)
        try:
            sheet = ss.worksheet("Comment_Bank")
        except Exception:
            sheet = ss.add_worksheet(title="Comment_Bank", rows=100, cols=6)
            
        with get_db_connection() as conn:
            df_local = pd.read_sql_query("SELECT id, category, comment, advice, resource_url, resource_text FROM comment_bank", conn)
            
        if not df_local.empty:
            sheet.clear()
            df_push = df_local.fillna("")
            headers = df_push.columns.tolist()
            rows_to_push = [headers] + df_push.values.tolist()
            try:
                sheet.update(range_name='A1', values=rows_to_push)
            except TypeError:
                sheet.update('A1', rows_to_push)
            print("✅ Comment Bank successfully pushed to Google Sheets.")
    except Exception as e:
        logging.error(f"Error pushing Comment Bank to Google Sheets: {e}")
        print(f"❌ Error pushing Comment Bank to Google Sheets: {e}")



def sync_checklist_fields():
    print("🔄 Syncing Checklist Fields bidirectionally (Pull & Push)...")
    import logging
    from data_manager import get_spreadsheet_data
    sheet_id = os.getenv("DATA_SHEET_ID")
    if not sheet_id:
        msg = "DATA_SHEET_ID is not configured in the environment variables."
        logging.error(msg)
        print(f"❌ {msg}")
        raise ValueError(msg)
        
    try:
        # 1. Fetch remote data from Google Sheets
        ss, _ = get_spreadsheet_data(sheet_id)
        try:
            sheet = ss.worksheet("Checklist_Fields")
        except Exception:
            # If the sheet doesn't exist, create it with correct headers
            sheet = ss.add_worksheet(title="Checklist_Fields", rows=100, cols=7)
            sheet.update('A1', [['id', 'label', 'action_label', 'description', 'field_type', 'is_active', 'display_order']])
            
        data = sheet.get_all_values()
        
        # 2. Fetch local data from SQLite
        with get_db_connection() as conn:
            try:
                df_local = pd.read_sql_query("SELECT id, label, action_label, description, field_type, is_active, display_order FROM audit_fields", conn)
            except Exception:
                df_local = pd.DataFrame(columns=['id', 'label', 'action_label', 'description', 'field_type', 'is_active', 'display_order'])
                
        # 3. Parse remote data
        if len(data) > 1:
            df_remote = pd.DataFrame(data[1:], columns=data[0])
            df_remote.columns = [c.strip() for c in df_remote.columns]
            
            # Map column names case-insensitively
            rename_map = {}
            for col in df_remote.columns:
                for target_col in ['id', 'label', 'action_label', 'description', 'field_type', 'is_active', 'display_order']:
                    if col.lower().strip() == target_col.lower():
                        rename_map[col] = target_col
            df_remote = df_remote.rename(columns=rename_map)
            
            # Add missing fields
            for col in ['id', 'label', 'action_label', 'description', 'field_type', 'is_active', 'display_order']:
                if col not in df_remote.columns:
                    df_remote[col] = ""
            df_remote = df_remote[['id', 'label', 'action_label', 'description', 'field_type', 'is_active', 'display_order']]
        else:
            df_remote = pd.DataFrame(columns=['id', 'label', 'action_label', 'description', 'field_type', 'is_active', 'display_order'])
            
        # 4. Standardize local dataframe
        if not df_local.empty:
            df_local.columns = [c.strip() for c in df_local.columns]
            df_local = df_local[['id', 'label', 'action_label', 'description', 'field_type', 'is_active', 'display_order']]
            
        # 5. Merge remote and local (remote wins for matching ID)
        df_remote['id'] = df_remote['id'].astype(str).str.strip().str.lower()
        df_local['id'] = df_local['id'].astype(str).str.strip().str.lower()
        
        df_merged = pd.concat([df_local, df_remote], ignore_index=True)
        df_merged = df_merged.drop_duplicates(subset=['id'], keep='last')
        df_merged = df_merged[df_merged['id'] != ""]
        
        # Ensure correct datatypes
        df_merged['is_active'] = df_merged['is_active'].apply(lambda x: 1 if str(x).upper() in ['TRUE', '1', 'YES'] or x is True else 0)
        df_merged['display_order'] = pd.to_numeric(df_merged['display_order'], errors='coerce').fillna(10).astype(int)
        df_merged['label'] = df_merged['label'].astype(str).str.strip()
        df_merged['action_label'] = df_merged['action_label'].astype(str).str.strip()
        df_merged['description'] = df_merged['description'].astype(str).str.strip()
        df_merged['field_type'] = df_merged['field_type'].astype(str).str.strip().str.lower()
        
        # Fallback action_label
        df_merged['action_label'] = df_merged.apply(lambda r: r['action_label'] if r['action_label'] else r['label'], axis=1)
        
        # Sort by display order
        df_merged = df_merged.sort_values(by=['display_order']).reset_index(drop=True)
        
        # 7. Save merged data back to SQLite
        cache_dataframe_to_sqlite(df_merged, "audit_fields")
        init_db()
        
        # 8. Push merged data back to Google Sheets
        sheet.clear()
        df_push = df_merged.fillna("")
        headers = df_push.columns.tolist()
        rows_to_push = [headers] + df_push.values.tolist()
        
        try:
            sheet.update(range_name='A1', values=rows_to_push)
        except TypeError:
            sheet.update('A1', rows_to_push)
            
        print("✅ Checklist Fields synced bidirectionally (SQLite & Google Sheets updated).")
    except Exception as e:
        logging.error(f"Error syncing Checklist Fields: {e}")
        print(f"❌ Error syncing Checklist Fields: {e}")
        raise e


def push_checklist_fields_to_sheets():
    """Pushes the local audit_fields table from SQLite to Google Sheets (overwriting it)."""
    import logging
    from data_manager import get_spreadsheet_data
    sheet_id = os.getenv("DATA_SHEET_ID")
    if not sheet_id:
        return
        
    try:
        ss, _ = get_spreadsheet_data(sheet_id)
        try:
            sheet = ss.worksheet("Checklist_Fields")
        except Exception:
            sheet = ss.add_worksheet(title="Checklist_Fields", rows=100, cols=7)
            
        with get_db_connection() as conn:
            df_local = pd.read_sql_query("SELECT id, label, action_label, description, field_type, is_active, display_order FROM audit_fields", conn)
            
        if not df_local.empty:
            sheet.clear()
            df_push = df_local.fillna("")
            headers = df_push.columns.tolist()
            rows_to_push = [headers] + df_push.values.tolist()
            try:
                sheet.update(range_name='A1', values=rows_to_push)
            except TypeError:
                sheet.update('A1', rows_to_push)
            print("✅ Checklist Fields successfully pushed to Google Sheets.")
    except Exception as e:
        logging.error(f"Error pushing Checklist Fields to Google Sheets: {e}")
        print(f"❌ Error pushing Checklist Fields to Google Sheets: {e}")


def sync_blackboard_links_from_csv(df: pd.DataFrame, academic_year: str = "2026-27"):
    """Process Blackboard links from a dataframe (used by admin panel CSV import)."""
    try:
        # Normalize column names
        df.columns = [c.strip().lower() for c in df.columns]

        # Map column variations
        module_col = None
        url_col = None

        for col in df.columns:
            if col in ['module_code', 'module code', 'course_code', 'course code', 'course_id', 'course id']:
                module_col = col
            elif col in ['url', 'link', 'blackboard_url', 'blackboard_link', 'blackboard url', 'blackboard link']:
                url_col = col

        if module_col is None:
            module_col = df.columns[0]
        if url_col is None:
            url_col = df.columns[1] if len(df.columns) > 1 else df.columns[0]

        # Extract and clean data
        df_clean = df[[module_col, url_col]].copy()
        df_clean.columns = ['module_code', 'blackboard_link']

        # Clean module codes and URLs
        df_clean['module_code'] = df_clean['module_code'].astype(str).str.strip().str.upper()
        df_clean['blackboard_link'] = df_clean['blackboard_link'].astype(str).str.strip()

        # Remove empty rows
        df_clean = df_clean[(df_clean['module_code'] != '') & (df_clean['blackboard_link'] != '')]

        # Validate that links contain 'http' (basic URL check)
        df_clean = df_clean[df_clean['blackboard_link'].str.contains('http', case=False, na=False)]

        if len(df_clean) == 0:
            raise ValueError("No valid URLs found. Ensure the URL column contains full Blackboard URLs (starting with http/https).")

        # Add metadata columns
        import datetime
        now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        df_clean['academic_year'] = academic_year
        df_clean['import_date'] = now
        df_clean['last_updated'] = now

        # Keep only required columns
        df_clean = df_clean[['module_code', 'blackboard_link', 'academic_year', 'import_date', 'last_updated']]

        # Write to SQLite (replace old year's data)
        with get_db_connection() as conn:
            cursor = conn.cursor()
            # Clear existing links for this academic year
            cursor.execute("DELETE FROM blackboard_links WHERE academic_year = ?", (academic_year,))

            # Insert new links
            for _, row in df_clean.iterrows():
                cursor.execute("""
                    INSERT OR REPLACE INTO blackboard_links
                    (module_code, blackboard_link, academic_year, import_date, last_updated)
                    VALUES (?, ?, ?, ?, ?)
                """, (row['module_code'], row['blackboard_link'], academic_year, now, now))

            conn.commit()

        return len(df_clean), df_clean.iloc[0] if len(df_clean) > 0 else None

    except Exception as e:
        raise e


def run_synchronization():
    """ETL pipeline extracting Google Sheets data and writing to SQLite."""
    print("🔄 Starting Data Synchronization...")
    try:
        init_db()
        sync_main_audit()
        sync_assessment_data()
        sync_users_and_roles()
        sync_checklists()
        sync_ai_responses()
        try:
            sync_comment_bank()
        except Exception as e:
            print(f"⚠️ Skipping Comment Bank sync due to error: {e}")
        try:
            sync_checklist_fields()
        except Exception as e:
            print(f"⚠️ Skipping Checklist Fields sync due to error: {e}")
        try:
            sync_blackboard_links()
        except Exception as e:
            print(f"⚠️ Skipping Blackboard Links sync due to error: {e}")
        print("✅ Full Sync Process Completed.")
    except Exception as e:
        print(f"❌ Synchronisation failed: {str(e)}", file=sys.stderr)

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv(override=True)
    run_synchronization()

