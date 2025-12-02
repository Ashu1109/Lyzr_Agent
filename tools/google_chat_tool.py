from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

def list_spaces(token_data: dict | str):
    """
    Lists the spaces (rooms/DMs) the user is in.
    """
    try:
        service = _get_chat_service(token_data)
        
        results = service.spaces().list().execute()
        
        spaces = results.get('spaces', [])
        return spaces
    except Exception as e:
        return f"Error listing spaces: {str(e)}"

def list_messages(token_data: dict | str, space_name: str):
    """
    Lists messages in a specific space.
    space_name should be in the format 'spaces/AAAAAAAAAAA'
    """
    try:
        service = _get_chat_service(token_data)
        
        results = service.spaces().messages().list(
            parent=space_name
        ).execute()
        
        messages = results.get('messages', [])
        return messages
    except Exception as e:
        return f"Error listing messages: {str(e)}"

def _get_chat_service(token_data: dict | str):
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
    return build('chat', 'v1', credentials=creds)
