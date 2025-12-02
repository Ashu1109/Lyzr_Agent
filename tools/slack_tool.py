from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
import os
import certifi
from datetime import datetime

# Fix SSL context
os.environ['SSL_CERT_FILE'] = certifi.where()

def list_channels(access_token: str):
    """
    Lists public channels in the Slack workspace.
    """
    try:
        client = WebClient(token=access_token)
        channels = client.conversations_list(limit=20, types="public_channel")['channels']
        return [
            {"name": c['name'], "id": c['id'], "members": c['num_members'], "is_member": c['is_member']} 
            for c in channels
        ]
    except SlackApiError as e:
        return f"Error listing channels: {e.response['error']}"

def search_messages(access_token: str, query: str):
    """
    Searches for messages in Slack by iterating through public channels.
    """
    try:
        client = WebClient(token=access_token)
        # Bots cannot use search.messages. We must iterate through channels.
        # 1. List public channels
        channels = client.conversations_list(limit=5, types="public_channel")['channels']
        all_messages = []
        
        for channel in channels:
            # Check if bot is a member, if not, try to join (only for public channels)
            if not channel['is_member']:
                try:
                    print(f"DEBUG: Bot not in {channel['name']}, attempting to join...")
                    client.conversations_join(channel=channel['id'])
                    print(f"DEBUG: Successfully joined {channel['name']}")
                except SlackApiError as e:
                    print(f"DEBUG: Failed to join {channel['name']}: {e}")
                    # Continue to next channel if join fails
                    continue

            # Fetch history
            try:
                history = client.conversations_history(channel=channel['id'], limit=10)
                messages = history['messages']
                
                for msg in messages:
                    text = msg.get('text', '').lower()
                    if query.lower() in text:
                        user = msg.get('user', 'unknown')
                        ts = float(msg.get('ts', 0))
                        time_str = datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
                        
                        all_messages.append({
                            'time': time_str,
                            'user': user,
                            'channel': channel['name'],
                            'message': msg.get('text', '')
                        })
            except SlackApiError as e:
                print(f"DEBUG: Error fetching history for {channel['name']}: {e}")
                continue
                
        return all_messages[:10]
    except SlackApiError as e:
        return f"Error searching Slack: {e.response['error']}"

