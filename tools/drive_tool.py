from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

def list_files(token_data: dict | str):
    """
    Lists the most recent files from Google Drive (non-trashed).
    """
    try:
        service = _get_drive_service(token_data)
        
        # Default query: not trashed
        q = "trashed = false"
        
        results = service.files().list(
            q=q, pageSize=10, fields="nextPageToken, files(id, name, mimeType, webViewLink)"
        ).execute()
        
        return results.get('files', [])
    except Exception as e:
        return f"Error listing Drive files: {str(e)}"

def search_files(token_data: dict | str, query: str):
    """
    Searches for files in Google Drive using a query.
    """
    try:
        service = _get_drive_service(token_data)
        
        q = "trashed = false"
        
        # Handle common aliases (both type:document and type = 'document')
        if 'type:document' in query or "type = 'document'" in query or "type='document'" in query:
            query = "mimeType = 'application/vnd.google-apps.document'"
        elif 'type:folder' in query or "type = 'folder'" in query or "type='folder'" in query:
            query = "mimeType = 'application/vnd.google-apps.folder'"
        elif 'type:spreadsheet' in query or "type = 'spreadsheet'" in query or "type='spreadsheet'" in query:
            query = "mimeType = 'application/vnd.google-apps.spreadsheet'"
        
        # If query looks like a filter (has : or =), use it directly
        if ':' in query or '=' in query:
            advanced_q = q + f" and ({query})"
            try:
                results = service.files().list(
                    q=advanced_q, pageSize=10, fields="nextPageToken, files(id, name, mimeType, webViewLink)"
                ).execute()
                return results.get('files', [])
            except Exception as e:
                print(f"DEBUG: Advanced query failed: {e}. Falling back to name search.")
                # Fallback to name search
                q += f" and name contains '{query}'"
        else:
            q += f" and name contains '{query}'"
        
        results = service.files().list(
            q=q, pageSize=10, fields="nextPageToken, files(id, name, mimeType, webViewLink)"
        ).execute()
        
        return results.get('files', [])
    except Exception as e:
        return f"Error searching Drive files: {str(e)}"

def _get_drive_service(token_data: dict | str):
    if isinstance(token_data, str):
        creds = Credentials(token=token_data)
    else:
        creds = Credentials(
            token=token_data.get('token'),
            refresh_token=token_data.get('refresh_token'),
            token_uri=token_data.get('token_uri'),
            client_id=token_data.get('client_id'),
            client_secret=token_data.get('client_secret'),
            scopes=token_data.get('scopes')
        )
    return build('drive', 'v3', credentials=creds)
