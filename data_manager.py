import os
import gspread
import pandas as pd
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv

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

def get_spreadsheet_data(spreadsheet_id):
    """
    Fetches all worksheets from a spreadsheet and returns them as a dictionary of DataFrames.
    """
    client = get_gspread_client()
    spreadsheet = client.open_by_key(spreadsheet_id)
    worksheets = spreadsheet.worksheets()
    
    return spreadsheet, worksheets

def append_row_to_sheet(spreadsheet_id, worksheet_name, row_data):
    """
    Appends a row of data to a specific worksheet.
    """
    client = get_gspread_client()
    spreadsheet = client.open_by_key(spreadsheet_id)
    worksheet = spreadsheet.worksheet(worksheet_name)
    worksheet.append_row(row_data)

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
    Fetches the most recent checklist entry for a given module code.
    """
    client = get_gspread_client()
    spreadsheet = client.open_by_key(spreadsheet_id)
    try:
        worksheet = spreadsheet.worksheet(worksheet_name)
        data = worksheet.get_all_values()
        if len(data) <= 1:
            return None
        
        # Search from bottom to top for the most recent match
        for row in reversed(data):
            # Ensure row has enough columns
            if len(row) > 1 and row[1] == module_code: 
                return row
        return None
    except Exception as e:
        print(f"Error fetching latest entry: {e}")
        return None

def get_all_checklist_entries(spreadsheet_id, worksheet_name, module_code):
    """
    Fetches all checklist entries for a given module code.
    """
    client = get_gspread_client()
    spreadsheet = client.open_by_key(spreadsheet_id)
    try:
        worksheet = spreadsheet.worksheet(worksheet_name)
        data = worksheet.get_all_values()
        if len(data) <= 1:
            return pd.DataFrame()
        
        headers = data[0]
        # Filter rows by module code (index 1)
        matches = [row for row in data[1:] if len(row) > 1 and row[1] == module_code]
        
        if not matches:
            return pd.DataFrame()
            
        df = pd.DataFrame(matches, columns=headers)
        
        # Ensure Timestamp exists before sorting
        if "Timestamp" in df.columns:
            df = df.sort_values(by="Timestamp", ascending=False)
            
        return df
    except Exception as e:
        print(f"Error fetching all entries: {e}")
        return pd.DataFrame()

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
