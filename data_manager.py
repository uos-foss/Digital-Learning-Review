import os
import gspread
import pandas as pd
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from processing import sanitize_row_data

# Load environment variables from .env file
load_dotenv()

def get_gspread_client():
    """
    Reconstructs the Google Service Account credentials from environment variables
    and returns an authorized gspread client.
    """
    credentials_dict = {
        "type": os.getenv("GOOGLE_TYPE"),
        "project_id": os.getenv("GOOGLE_PROJECT_ID"),
        "private_key_id": os.getenv("GOOGLE_PRIVATE_KEY_ID"),
        "private_key": os.getenv("GOOGLE_PRIVATE_KEY").replace('\\n', '\n'),
        "client_email": os.getenv("GOOGLE_CLIENT_EMAIL"),
        "client_id": os.getenv("GOOGLE_CLIENT_ID"),
        "auth_uri": os.getenv("GOOGLE_AUTH_URI"),
        "token_uri": os.getenv("GOOGLE_TOKEN_URI"),
        "auth_provider_x509_cert_url": os.getenv("GOOGLE_AUTH_PROVIDER_X509_CERT_URL"),
        "client_x509_cert_url": os.getenv("GOOGLE_CLIENT_X509_CERT_URL"),
        "universe_domain": os.getenv("GOOGLE_UNIVERSE_DOMAIN")
    }
    
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    
    creds = Credentials.from_service_account_info(credentials_dict, scopes=scopes)
    return gspread.authorize(creds)

@retry(wait=wait_exponential(multiplier=1, min=2, max=10), stop=stop_after_attempt(5), retry=retry_if_exception_type(gspread.exceptions.APIError))
def get_spreadsheet_data(spreadsheet_id):
    """
    Fetches all worksheets from a spreadsheet and returns them as a dictionary of DataFrames.
    """
    client = get_gspread_client()
    spreadsheet = client.open_by_key(spreadsheet_id)
    worksheets = spreadsheet.worksheets()
    
    return spreadsheet, worksheets

@retry(wait=wait_exponential(multiplier=1, min=2, max=10), stop=stop_after_attempt(5), retry=retry_if_exception_type(gspread.exceptions.APIError))
def append_row_to_sheet(spreadsheet_id, worksheet_name, row_data):
    """
    Appends a row of data to a specific worksheet.
    """
    client = get_gspread_client()
    spreadsheet = client.open_by_key(spreadsheet_id)
    worksheet = spreadsheet.worksheet(worksheet_name)
    sanitized_data = sanitize_row_data(row_data)
    worksheet.append_row(sanitized_data)

@retry(wait=wait_exponential(multiplier=1, min=2, max=10), stop=stop_after_attempt(5), retry=retry_if_exception_type(gspread.exceptions.APIError))
def initialize_checklist_headers(spreadsheet_id, worksheet_name):
    """
    Ensures the checklist worksheet has the correct headers.
    """
    headers = [
        "Timestamp", "Module Code", "Module Name", 
        "Welcome message present?", "Key staff contacts complete?", 
        "Module outline visible?", "Assessment overview consistent with SITS?", 
        "Comments"
    ]
    client = get_gspread_client()
    spreadsheet = client.open_by_key(spreadsheet_id)
    try:
        worksheet = spreadsheet.worksheet(worksheet_name)
    except:
        worksheet = spreadsheet.add_worksheet(title=worksheet_name, rows=1000, cols=len(headers))
    
    data = worksheet.get_all_values()
    # If empty or first row is not the expected headers, insert them
    if not data or data[0] != headers:
        worksheet.insert_row(headers, index=1)

@retry(wait=wait_exponential(multiplier=1, min=2, max=10), stop=stop_after_attempt(5), retry=retry_if_exception_type(gspread.exceptions.APIError))
def initialize_feedback_headers(spreadsheet_id, worksheet_name):
    """
    Ensures the feedback worksheet has the correct headers.
    """
    headers = ["Timestamp", "User", "School", "Category", "Rating", "Comments"]
    client = get_gspread_client()
    spreadsheet = client.open_by_key(spreadsheet_id)
    try:
        worksheet = spreadsheet.worksheet(worksheet_name)
    except:
        worksheet = spreadsheet.add_worksheet(title=worksheet_name, rows=1000, cols=len(headers))
    
    data = worksheet.get_all_values()
    # If empty or first row is not the expected headers, insert them
    if not data or data[0] != headers:
        worksheet.insert_row(headers, index=1)

def get_latest_checklist_entry(spreadsheet_id, worksheet_name, module_code):
    """
    Fetches the most recent checklist entry for a given module code from SQLite.
    """
    try:
        from database import get_db_connection
        with get_db_connection() as conn:
            cursor = conn.cursor()
            # SQLite query returning the most recent row
            # Since self_audit_checklist keeps only the latest via UPSERT, we just select it.
            cursor.execute("SELECT timestamp, module_code, module_name, welcome_message, contacts_complete, outline_visible, assessment_overview, comments FROM self_audit_checklist WHERE module_code = ?", (module_code,))
            row = cursor.fetchone()
            if row:
                return [row['timestamp'], row['module_code'], row['module_name'], row['welcome_message'], row['contacts_complete'], row['outline_visible'], row['assessment_overview'], row['comments']]
        return None
    except Exception as e:
        print(f"Error fetching latest entry from SQLite: {e}")
        return None

def get_all_checklist_entries(spreadsheet_id, worksheet_name, module_code):
    """
    Fetches all checklist entries for a given module code.
    Since we upsert in SQLite, history is limited to the Google Sheets backup.
    For this view, we can just return the SQLite row as a DataFrame for now, 
    or query the full history from Google Sheets if explicitly requested.
    We'll return the SQLite row wrapped in a DataFrame to preserve the interface without hitting the API.
    """
    try:
        import pandas as pd
        row = get_latest_checklist_entry(spreadsheet_id, worksheet_name, module_code)
        if row:
            headers = ["Timestamp", "Module Code", "Module Name", "Welcome message present?", "Key staff contacts complete?", "Module outline visible?", "Assessment overview consistent with SITS?", "Comments"]
            df = pd.DataFrame([row], columns=headers)
            return df
        return pd.DataFrame()
    except Exception as e:
        print(f"Error fetching all entries: {e}")
        return pd.DataFrame()

@retry(wait=wait_exponential(multiplier=1, min=2, max=10), stop=stop_after_attempt(5), retry=retry_if_exception_type(gspread.exceptions.APIError))
def initialize_users_sheet(spreadsheet_id):
    """
    Ensures the users worksheet exists and has the correct headers.
    If it is newly created or empty, seeds it with default users from .env.
    """
    import hashlib
    import logging
    headers = ["Username", "PasswordHash", "Role", "School", "Capabilities", "Status"]
    client = get_gspread_client()
    spreadsheet = client.open_by_key(spreadsheet_id)
    
    # Try to open the sheet, create if missing
    try:
        worksheet = spreadsheet.worksheet("Users")
    except Exception:
        # Create sheet with appropriate columns
        worksheet = spreadsheet.add_worksheet(title="Users", rows=100, cols=len(headers))
        
    data = worksheet.get_all_values()
    
    # If empty or first row is not headers, set headers
    if not data or data[0] != headers:
        worksheet.insert_row(headers, index=1)
        data = [headers]
        
    # If there are no data rows, perform auto-seeding
    if len(data) <= 1:
        seed_rows = []
        
        env_users = {
            "ALA": (os.getenv("USER_ALA"), "School Module Lead", "ALA"),
            "ECN": (os.getenv("USER_ECN"), "School Module Lead", "ECN"),
            "EDC": (os.getenv("USER_EDC"), "School Module Lead", "EDC"),
            "GPL": (os.getenv("USER_GPL"), "School Module Lead", "GPL"),
            "IJC": (os.getenv("USER_IJC"), "School Module Lead", "IJC"),
            "MGT": (os.getenv("USER_MGT"), "School Module Lead", "MGT"),
            "SPR": (os.getenv("USER_SPR"), "School Module Lead", "SPR"),
            "FACULTY": (os.getenv("USER_FACULTY"), "Faculty Reviewer", "All"),
            "DLA": (os.getenv("USER_DLA"), "Digital Learning Advisor", "All"),
            "ADMIN": (os.getenv("USER_ADMIN"), "System Administrator", "All"),
        }
        
        for username, (password, role, school) in env_users.items():
            if password:
                # Hash password with SHA-256
                pass_hash = hashlib.sha256(str(password).strip().encode("utf-8")).hexdigest()
                # Capabilities string
                caps = "view_all" if role in ["System Administrator", "Digital Learning Advisor", "Faculty Reviewer"] else "view_school"
                seed_rows.append([username, pass_hash, role, school, caps, "Active"])
                
        if seed_rows:
            worksheet.append_rows(seed_rows)
            logging.info(f"🌱 Seeded {len(seed_rows)} default users from .env into Google Sheets database.")
            
    # Always ensure Roles sheet is initialized
    initialize_roles_sheet(spreadsheet_id)

@retry(wait=wait_exponential(multiplier=1, min=2, max=10), stop=stop_after_attempt(5), retry=retry_if_exception_type(gspread.exceptions.APIError))
def initialize_roles_sheet(spreadsheet_id):
    """
    Ensures that the 'Roles' worksheet exists in the spreadsheet.
    If it is newly created or empty, seeds it with default roles and capabilities.
    """
    import logging
    headers = ["Role", "Capabilities"]
    client = get_gspread_client()
    spreadsheet = client.open_by_key(spreadsheet_id)
    
    # Try to open the sheet, create if missing
    try:
        worksheet = spreadsheet.worksheet("Roles")
    except Exception:
        # Create sheet with appropriate columns
        worksheet = spreadsheet.add_worksheet(title="Roles", rows=50, cols=len(headers))
        
    data = worksheet.get_all_values()
    
    # If empty or first row is not headers, set headers
    if not data or data[0] != headers:
        worksheet.insert_row(headers, index=1)
        data = [headers]
        
    # If there are no data rows, perform auto-seeding
    if len(data) <= 1:
        seed_roles = [
            ["System Administrator", "View Faculty Overview, complete module checklist"],
            ["Digital Learning Advisor", "View Faculty Overview, complete module checklist"],
            ["Faculty Reviewer", "View Faculty Overview, complete module checklist"],
            ["School Module Lead", "View only own school, complete module checklist"],
            ["School Auditor", "View only own school, view module checklist"],
            ["School Leadership", "View Faculty Overview, View only own school, view module checklist"]
        ]
        worksheet.append_rows(seed_roles)
        logging.info(f"🌱 Seeded {len(seed_roles)} default roles into Google Sheets database.")

@retry(wait=wait_exponential(multiplier=1, min=2, max=10), stop=stop_after_attempt(5), retry=retry_if_exception_type(gspread.exceptions.APIError))
def update_role_row(spreadsheet_id, role_name, column_name, new_value):
    """
    Finds the row corresponding to the role_name and updates the specified column.
    """
    client = get_gspread_client()
    spreadsheet = client.open_by_key(spreadsheet_id)
    worksheet = spreadsheet.worksheet("Roles")
    data = worksheet.get_all_values()
    
    if not data:
        raise ValueError("Roles sheet is empty.")
        
    headers = data[0]
    if column_name not in headers:
        raise ValueError(f"Column '{column_name}' not found in sheet headers.")
        
    col_idx = headers.index(column_name) + 1
    
    # Locate role row index (1-based index)
    row_idx = -1
    for idx, row in enumerate(data):
        if len(row) > 0 and str(row[0]).strip().lower() == str(role_name).strip().lower():
            row_idx = idx + 1
            break
            
    if row_idx == -1:
        raise ValueError(f"Role '{role_name}' not found in database.")
        
    worksheet.update_cell(row_idx, col_idx, str(new_value))

@retry(wait=wait_exponential(multiplier=1, min=2, max=10), stop=stop_after_attempt(5), retry=retry_if_exception_type(gspread.exceptions.APIError))
def update_user_row(spreadsheet_id, username, column_name, new_value):
    """
    Finds the row corresponding to the username and updates the specified column.
    """
    client = get_gspread_client()
    spreadsheet = client.open_by_key(spreadsheet_id)
    worksheet = spreadsheet.worksheet("Users")
    data = worksheet.get_all_values()
    
    if not data:
        raise ValueError("Users sheet is empty.")
        
    headers = data[0]
    if column_name not in headers:
        raise ValueError(f"Column '{column_name}' not found in sheet headers.")
        
    col_idx = headers.index(column_name) + 1
    
    # Locate user row index (1-based index)
    row_idx = -1
    for idx, row in enumerate(data):
        if len(row) > 0 and str(row[0]).strip().upper() == str(username).strip().upper():
            row_idx = idx + 1
            break
            
    if row_idx == -1:
        raise ValueError(f"User '{username}' not found in database.")
        
    worksheet.update_cell(row_idx, col_idx, str(new_value))

if __name__ == "__main__":
    # Quick test to verify connection
    try:
        main_id = os.getenv("MAIN_SPREADSHEET_ID")
        ss, sheets = get_spreadsheet_data(main_id)
        print(f"Successfully connected to: {ss.title}")
        print("Worksheets found:")
        for sheet in sheets:
            print(f" - {sheet.title}")
    except Exception as e:
        print(f"Error connecting to Google Sheets: {e}")
