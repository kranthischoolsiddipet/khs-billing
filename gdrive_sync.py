import os
import json
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timedelta
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CLIENT_SECRET_FILE = os.path.join(BASE_DIR, "client_secret.json")
TOKEN_FILE = os.path.join(BASE_DIR, "token.json")
CONFIG_FILE = os.path.join(BASE_DIR, "gdrive_config.json")

SCOPES = ['https://www.googleapis.com/auth/drive.file']

def get_gdrive_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        except:
            pass
    return {"folder_id": "1nUH0mD0-L8-2K5uydOMnjlr8_FUz7Shc", "auto_sync_eod": True}

def save_gdrive_config(folder_id: str, auto_sync_eod: bool = True):
    config = {"folder_id": folder_id.strip(), "auto_sync_eod": auto_sync_eod}
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)
    return config

def get_credentials():
    creds = None
    if os.path.exists(TOKEN_FILE):
        try:
            creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
        except Exception:
            creds = None

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            with open(TOKEN_FILE, "w") as token:
                token.write(creds.to_json())
            return creds
        except Exception:
            creds = None

    if creds and creds.valid:
        return creds

    return None

def is_gdrive_configured():
    creds = get_credentials()
    if not creds:
        return False, "Not authenticated with Google. Please click 'Connect Google Drive' to authorize."
    config = get_gdrive_config()
    if not config.get("folder_id"):
        return False, "Google Drive target Folder ID not configured."
    return True, "Ready"

def upload_database_to_drive(db_path: str = None):
    creds = get_credentials()
    if not creds:
        return {"status": "error", "message": "Google Drive is not authenticated yet. Please complete the browser sign-in."}

    if not db_path:
        db_path = os.path.join(BASE_DIR, "khs_billing.db")

    if not os.path.exists(db_path):
        return {"status": "error", "message": "Database file khs_billing.db not found."}

    config = get_gdrive_config()
    folder_id = config.get("folder_id")

    try:
        service = build('drive', 'v3', credentials=creds)

        timestamp = datetime.now().strftime('%Y-%m-%d_%H%M%S')
        file_metadata = {
            'name': f"khs_billing_backup_{timestamp}.db",
            'parents': [folder_id]
        }
        media = MediaFileUpload(db_path, mimetype='application/x-sqlite3', resumable=False)

        drive_file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, name, webViewLink',
            supportsAllDrives=True
        ).execute()

        # Automatic 6-Month Retention Cleanup Policy (Purge backups older than 180 days)
        try:
            six_months_ago = (datetime.now() - timedelta(days=180)).isoformat() + "Z"
            old_files_query = f"'{folder_id}' in parents and mimeType != 'application/vnd.google-apps.folder' and createdTime < '{six_months_ago}' and trashed = false"
            old_files_resp = service.files().list(q=old_files_query, fields='files(id, name)').execute()
            for old_f in old_files_resp.get('files', []):
                service.files().delete(fileId=old_f['id']).execute()
                print(f"[GDRIVE RETENTION] Purged backup older than 6 months: {old_f['name']}")
        except Exception as cleane:
            print(f"[GDRIVE RETENTION NOTICE]: {cleane}")

        return {
            "status": "success",
            "file_id": drive_file.get('id'),
            "file_name": drive_file.get('name'),
            "drive_link": drive_file.get('webViewLink'),
            "message": f"Successfully backed up database to Google Drive! File: {drive_file.get('name')}"
        }
    except Exception as e:
        return {"status": "error", "message": f"Google Drive API upload failed: {str(e)}"}
