import os
from pymongo import MongoClient
from bson import ObjectId
from datetime import datetime

# Connect to MongoDB
MONGODB_URI = os.getenv("MONGODB_URI", "mongodb+srv://next13:next13@cluster1.k4rnwsw.mongodb.net/lyzr_db")
client = MongoClient(MONGODB_URI)
db = client.get_database()

def get_user_tokens(user_id: str):
    """
    Retrieves access tokens for the given user_id (Clerk ID) from MongoDB.
    """
    tokens = {}
    try:
        # 1. Find the user document using the Clerk ID
        user_doc = db.users.find_one({"clerkId": user_id})
        if not user_doc:
            print(f"User not found for Clerk ID: {user_id}")
            return tokens
            
        # 2. Get the internal MongoDB ObjectId
        user_oid = user_doc['_id']
        print(f"Found user ObjectId: {user_oid} for Clerk ID: {user_id}")
        
        # 3. Query services using the ObjectId
        
        # Google Drive
        drive_data = db.googledrives.find_one({"userId": user_oid})
        if drive_data:
            # Return full object to handle refresh
            tokens['google_drive'] = {
                'token': drive_data.get('accessToken'),
                'refresh_token': drive_data.get('refreshToken'),
                'token_uri': "https://oauth2.googleapis.com/token",
                'client_id': os.getenv("GOOGLE_CLIENT_ID"), 
                'client_secret': os.getenv("GOOGLE_CLIENT_SECRET"),
                'scopes': drive_data.get('scope')
            }

        # Slack
        slack_data = db.slacks.find_one({"userId": user_oid})
        if slack_data:
            tokens['slack'] = slack_data.get('accessToken')

        # GitHub
        github_data = db.githubs.find_one({"userId": user_oid})
        if github_data:
            tokens['github'] = github_data.get('accessToken')

        # Gmail
        gmail_data = db.gmails.find_one({"userId": user_oid})
        if gmail_data:
            tokens['gmail'] = {
                'token': gmail_data.get('accessToken'),
                'refresh_token': gmail_data.get('refreshToken'),
                'token_uri': "https://oauth2.googleapis.com/token",
                'client_id': os.getenv("GOOGLE_CLIENT_ID"),
                'client_secret': os.getenv("GOOGLE_CLIENT_SECRET"),
                'scopes': gmail_data.get('scope')
            }

        # Google Chat
        chat_data = db.googlechats.find_one({"userId": user_oid})
        if chat_data:
            tokens['google_chat'] = {
                'token': chat_data.get('accessToken'),
                'refresh_token': chat_data.get('refreshToken'),
                'token_uri': "https://oauth2.googleapis.com/token",
                'client_id': os.getenv("GOOGLE_CLIENT_ID"),
                'client_secret': os.getenv("GOOGLE_CLIENT_SECRET"),
                'scopes': chat_data.get('scope')
            }

    except Exception as e:
        print(f"Error fetching tokens: {e}")
        import traceback
        traceback.print_exc()

    return tokens

def create_chat_session(user_id: str, title: str = "New Chat"):
    """
    Creates a new chat session for the user.
    """
    try:
        user_doc = db.users.find_one({"clerkId": user_id})
        if not user_doc:
            return None
            
        session = {
            "userId": user_doc['_id'],
            "title": title,
            "createdAt": datetime.utcnow(),
            "updatedAt": datetime.utcnow(),
            "messages": []
        }
        result = db.chat_sessions.insert_one(session)
        return str(result.inserted_id)
    except Exception as e:
        print(f"Error creating session: {e}")
        return None

def add_message_to_session(session_id: str, role: str, content: str):
    """
    Adds a message to a chat session.
    """
    try:
        message = {
            "role": role,
            "content": content,
            "timestamp": datetime.utcnow()
        }
        db.chat_sessions.update_one(
            {"_id": ObjectId(session_id)},
            {
                "$push": {"messages": message},
                "$set": {"updatedAt": datetime.utcnow()}
            }
        )
        return True
    except Exception as e:
        print(f"Error adding message: {e}")
        return False

def get_user_sessions(user_id: str):
    """
    Retrieves all chat sessions for a user.
    """
    try:
        user_doc = db.users.find_one({"clerkId": user_id})
        if not user_doc:
            return []
            
        sessions = db.chat_sessions.find(
            {"userId": user_doc['_id']},
            {"messages": 0} # Exclude messages for list view
        ).sort("updatedAt", -1)
        
        return [{**s, "_id": str(s["_id"]), "userId": str(s["userId"])} for s in sessions]
    except Exception as e:
        print(f"Error fetching sessions: {e}")
        return []

def get_session_messages(session_id: str):
    """
    Retrieves full session with messages.
    """
    try:
        session = db.chat_sessions.find_one({"_id": ObjectId(session_id)})
        if session:
            session["_id"] = str(session["_id"])
            session["userId"] = str(session["userId"])
            return session
        return None
    except Exception as e:
        print(f"Error fetching session messages: {e}")
        return None
