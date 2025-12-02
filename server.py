
import os
import certifi

# Fix SSL context for Slack SDK and other tools - MUST be before other imports
os.environ['SSL_CERT_FILE'] = certifi.where()

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from agent import create_orchestrator
import uvicorn
import json
import asyncio
from dotenv import load_dotenv
from sse_starlette.sse import EventSourceResponse # This import was added in the instruction, but not used in the provided code. Keeping it for faithfulness.


load_dotenv()

api_key = os.getenv("OPENAI_API_KEY")
if api_key:
    print(f"OPENAI_API_KEY loaded: {api_key[:5]}...{api_key[-4:]}")
else:
    print("OPENAI_API_KEY NOT FOUND in environment")

app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],  # Next.js dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from database import create_chat_session, add_message_to_session, get_user_sessions, get_session_messages

class ChatRequest(BaseModel):
    user_id: str
    message: str
    session_id: Optional[str] = None

from google.adk.runners import Runner
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.genai import types
from google.adk.events.event import Event
from postgres_session_service import PostgresSessionService

# Initialize PostgreSQL session service for persistent context across restarts
POSTGRES_URL = os.getenv("POSTGRES_URL")
if POSTGRES_URL:
    print(f"Using PostgreSQL session service")
    session_service = PostgresSessionService(POSTGRES_URL)
else:
    print("WARNING: POSTGRES_URL not set, falling back to InMemorySessionService")
    session_service = InMemorySessionService()

async def stream_generator(agent, message, user_id, session_id):
    # Use the MongoDB session ID as the ADK session ID to align context
    adk_session_id = session_id

    print(f"DEBUG: Preparing session for user '{user_id}', session '{adk_session_id}'")

    # CRITICAL: Ensure session exists in PostgreSQL BEFORE creating the Runner
    # The Runner's run_async() will call get_session() and expects it to exist
    try:
        # Try to get existing session
        existing_session = await session_service.get_session(app_name="agents", user_id=user_id, session_id=adk_session_id)

        if existing_session:
            print(f"DEBUG: Found existing session in PostgreSQL with {len(existing_session.events)} events")
        else:
            # Session doesn't exist in PostgreSQL, create it
            print("DEBUG: Session not found in PostgreSQL, creating new session")
            existing_session = await session_service.create_session(app_name="agents", user_id=user_id, session_id=adk_session_id)

            # Hydrate from MongoDB if there are messages (e.g., after a restart when PostgreSQL was cleared)
            mongo_session = get_session_messages(adk_session_id)
            if mongo_session and "messages" in mongo_session and len(mongo_session["messages"]) > 0:
                print(f"DEBUG: Hydrating {len(mongo_session['messages'])} messages from MongoDB into PostgreSQL...")

                for idx, msg in enumerate(mongo_session["messages"]):
                    # Skip if content is empty
                    if not msg.get("content"):
                        print(f"DEBUG: Skipping empty message at index {idx}")
                        continue

                    # Create content object
                    content = types.Content(
                        role=msg["role"],
                        parts=[types.Part(text=msg["content"])]
                    )

                    # Create event
                    event = Event(
                        author=msg["role"],
                        content=content
                    )

                    await session_service.append_event(session=existing_session, event=event)
                    print(f"DEBUG: Hydrated message {idx + 1}/{len(mongo_session['messages'])}: {msg['role']}")

                print(f"DEBUG: Successfully hydrated {len(mongo_session['messages'])} messages from MongoDB to PostgreSQL")
            else:
                print("DEBUG: No messages to hydrate (new session)")

    except Exception as setup_error:
        print(f"ERROR: Failed to setup session: {setup_error}")
        import traceback
        traceback.print_exc()
        yield f"data: {json.dumps({'content': 'Error: Failed to initialize chat session.'})}\n\n"
        return

    # Now create the Runner - it will use the session we just ensured exists
    runner = Runner(agent=agent, session_service=session_service, app_name="agents")

    new_message = types.Content(role="user", parts=[types.Part(text=message)])

    try:
        print(f"DEBUG: Starting agent run with session {adk_session_id}...")
        async for event in runner.run_async(user_id=user_id, session_id=adk_session_id, new_message=new_message):
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if part.text:
                        yield f"data: {json.dumps({'content': part.text})}\n\n"
        print(f"DEBUG: Agent run completed successfully")
    except Exception as run_error:
        print(f"ERROR: Runner execution failed: {run_error}")
        import traceback
        traceback.print_exc()
        yield f"data: {json.dumps({'content': f'Error: {str(run_error)}'})}\n\n"

    yield "data: [DONE]\n\n"

# ... (keep existing imports and setup)

@app.post("/api/chat")
async def chat(request: ChatRequest):
    try:
        print(f"DEBUG: Received chat request - user_id: {request.user_id}, message: {request.message[:50]}..., session_id: {request.session_id}")

        session_id = request.session_id

        # Create new session if not provided
        if not session_id or session_id == "null":
            print("DEBUG: Creating new session...")
            session_id = create_chat_session(request.user_id, title=request.message[:30] + "...")
            if not session_id:
                raise HTTPException(status_code=500, detail="Failed to create chat session")
            print(f"DEBUG: Created new session: {session_id}")

        # Save user message
        add_message_to_session(session_id, "user", request.message)

        agent = create_orchestrator(request.user_id)
        
        async def stream_with_persistence():
            full_response = ""
            async for chunk in stream_generator(agent, request.message, request.user_id, session_id):
                if chunk.startswith("data: "):
                    try:
                        data = json.loads(chunk[6:])
                        if "content" in data:
                            full_response += data["content"]
                    except:
                        pass
                yield chunk
            
            # Save assistant message after streaming is complete
            if full_response:
                add_message_to_session(session_id, "assistant", full_response)
            
            # Send session_id to client
            yield f"data: {json.dumps({'session_id': session_id})}\n\n"

        return StreamingResponse(
            stream_with_persistence(),
            media_type="text/event-stream"
        )
    except Exception as e:
        import traceback
        print(f"ERROR in chat endpoint: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/history")
async def get_history(user_id: str):
    sessions = get_user_sessions(user_id)
    return sessions

@app.get("/api/history/{session_id}")
async def get_session(session_id: str):
    session = get_session_messages(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session

@app.get("/health")
def health_check():
    return {"status": "ok"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
