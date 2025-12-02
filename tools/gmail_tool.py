from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
import base64

def list_emails(token_data: dict | str, query: str = ""):
    """
    Lists the most recent emails from Gmail.
    """
    try:
        service = _get_gmail_service(token_data)
        
        # Default to inbox if no query
        q = query if query else "label:inbox"
        
        results = service.users().messages().list(
            userId='me', q=q, maxResults=10
        ).execute()
        
        messages = results.get('messages', [])
        
        email_list = []
        for msg in messages:
            # Fetch snippet for each message to give context
            detail = service.users().messages().get(userId='me', id=msg['id'], format='metadata').execute()
            email_list.append({
                "id": msg['id'],
                "snippet": detail.get('snippet'),
                "threadId": msg['threadId']
            })
            
        return email_list
    except Exception as e:
        return f"Error listing emails: {str(e)}"

def get_email_content(token_data: dict | str, message_id: str):
    """
    Gets the full content of a specific email.
    """
    try:
        service = _get_gmail_service(token_data)
        
        message = service.users().messages().get(userId='me', id=message_id, format='full').execute()
        
        payload = message.get('payload', {})
        headers = payload.get('headers', [])
        
        subject = next((h['value'] for h in headers if h['name'] == 'Subject'), 'No Subject')
        sender = next((h['value'] for h in headers if h['name'] == 'From'), 'Unknown')
        date = next((h['value'] for h in headers if h['name'] == 'Date'), 'Unknown')
        
        parts = payload.get('parts', [])
        body = ""
        
        if not parts:
            # Plain text email
            data = payload.get('body', {}).get('data')
            if data:
                body = base64.urlsafe_b64decode(data).decode()
        else:
            # Multipart email, look for text/plain
            for part in parts:
                if part['mimeType'] == 'text/plain':
                    data = part.get('body', {}).get('data')
                    if data:
                        body = base64.urlsafe_b64decode(data).decode()
                        break
        
        return {
            "id": message_id,
            "subject": subject,
            "from": sender,
            "date": date,
            "body": body
        }
    except Exception as e:
        return f"Error getting email content: {str(e)}"

def _get_gmail_service(token_data: dict | str):
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
    return build('gmail', 'v1', credentials=creds)
