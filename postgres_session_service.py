"""
PostgreSQL-based session service for Google ADK.
Implements persistent session storage across server restarts.
Based on: https://google.github.io/adk-docs/sessions/
"""

import os
import json
import time
from datetime import datetime
from typing import Optional, List
from sqlalchemy import create_engine, Column, String, Text, DateTime, Integer
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session as DBSession
from sqlalchemy.exc import OperationalError
from google.adk.sessions.base_session_service import BaseSessionService
from google.adk.sessions.session import Session
from google.adk.events.event import Event
from google.genai import types

Base = declarative_base()


class SessionRecord(Base):
    """Database model for storing ADK sessions."""
    __tablename__ = 'adk_sessions'

    id = Column(String, primary_key=True)  # Format: app_name:user_id:session_id
    app_name = Column(String, nullable=False, index=True)
    user_id = Column(String, nullable=False, index=True)
    session_id = Column(String, nullable=False, index=True)
    events_json = Column(Text, nullable=False, default='[]')
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<SessionRecord(id={self.id}, user_id={self.user_id}, session_id={self.session_id})>"


class PostgresSessionService(BaseSessionService):
    """PostgreSQL-based implementation of ADK BaseSessionService."""

    def __init__(self, database_url: str):
        """
        Initialize PostgreSQL session service.

        Args:
            database_url: PostgreSQL connection URL
        """
        # Configure connection pooling for production with SSL
        self.engine = create_engine(
            database_url,
            pool_size=10,  # Maximum number of permanent connections
            max_overflow=20,  # Maximum number of overflow connections
            pool_pre_ping=True,  # Verify connections before using them
            pool_recycle=3600,  # Recycle connections after 1 hour
            connect_args={
                "connect_timeout": 10,
                "keepalives": 1,
                "keepalives_idle": 30,
                "keepalives_interval": 10,
                "keepalives_count": 5,
            }
        )
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine, autocommit=False, autoflush=False)
        print(f"PostgresSessionService initialized with database and connection pooling")

    def _get_db(self) -> DBSession:
        """Get database session."""
        return self.SessionLocal()

    def _retry_on_connection_error(self, func, max_retries=3, delay=1):
        """Retry a function on connection errors."""
        for attempt in range(max_retries):
            try:
                return func()
            except OperationalError as e:
                if "SSL connection has been closed" in str(e) or "connection" in str(e).lower():
                    if attempt < max_retries - 1:
                        print(f"Connection error, retrying in {delay}s... (attempt {attempt + 1}/{max_retries})")
                        time.sleep(delay)
                        # Dispose and recreate engine on connection errors
                        try:
                            self.engine.dispose()
                        except:
                            pass
                        continue
                raise
        return None

    def _make_session_key(self, app_name: str, user_id: str, session_id: str) -> str:
        """Create unique session key."""
        return f"{app_name}:{user_id}:{session_id}"

    def _serialize_event(self, event: Event) -> dict:
        """Serialize an Event to a JSON-serializable dict."""
        event_dict = {
            'author': event.author,
            'content': None
        }

        if event.content:
            parts = []
            for part in event.content.parts:
                part_dict = {}
                if part.text:
                    part_dict['text'] = part.text
                elif part.function_call:
                    part_dict['function_call'] = {
                        'name': part.function_call.name,
                        'args': part.function_call.args
                    }
                    # Add ID if present (critical for LiteLLM/OpenAI compatibility)
                    if hasattr(part.function_call, 'id') and part.function_call.id:
                        part_dict['function_call']['id'] = part.function_call.id
                elif part.function_response:
                    # Handle function response carefully - extract value from Result objects
                    response_data = part.function_response.response

                    # Check if it's a Result object (has a 'value' attribute)
                    if hasattr(response_data, 'value'):
                        response_data = response_data.value

                    # If still an object, try to convert to dict
                    if hasattr(response_data, '__dict__') and not isinstance(response_data, (str, int, float, bool, list, dict, type(None))):
                        try:
                            response_data = {k: v for k, v in response_data.__dict__.items() if not k.startswith('_')}
                        except:
                            response_data = str(response_data)

                    # Final check: ensure it's JSON-serializable
                    try:
                        json.dumps(response_data)
                    except (TypeError, ValueError):
                        # If still not serializable, convert to string
                        response_data = str(response_data)

                    part_dict['function_response'] = {
                        'id': part.function_response.id,
                        'name': part.function_response.name,
                        'response': response_data
                    }
                parts.append(part_dict)

            event_dict['content'] = {
                'role': event.content.role,
                'parts': parts
            }

        return event_dict

    def _deserialize_event(self, event_dict: dict) -> Event:
        """Deserialize a dict to an Event."""
        content = None
        if event_dict.get('content'):
            content_data = event_dict['content']
            parts = []

            for part_dict in content_data.get('parts', []):
                if 'text' in part_dict:
                    parts.append(types.Part(text=part_dict['text']))
                elif 'function_call' in part_dict:
                    fc = part_dict['function_call']
                    parts.append(types.Part(
                        function_call=types.FunctionCall(
                            name=fc['name'],
                            args=fc['args']
                        )
                    ))
                    # Restore ID if present
                    if 'id' in fc and hasattr(parts[-1].function_call, 'id'):
                        try:
                            parts[-1].function_call.id = fc['id']
                        except:
                            pass
                elif 'function_response' in part_dict:
                    fr = part_dict['function_response']
                    parts.append(types.Part(
                        function_response=types.FunctionResponse(
                            id=fr['id'],
                            name=fr['name'],
                            response=fr['response']
                        )
                    ))

            content = types.Content(
                role=content_data['role'],
                parts=parts
            )

        return Event(
            author=event_dict['author'],
            content=content
        )

    async def create_session(
        self,
        app_name: str,
        user_id: str,
        session_id: str
    ) -> Session:
        """Create a new session in PostgreSQL."""
        db = self._get_db()
        try:
            session_key = self._make_session_key(app_name, user_id, session_id)

            # Check if session already exists
            existing = db.query(SessionRecord).filter_by(id=session_key).first()
            if existing:
                print(f"Session {session_key} already exists, returning existing")
                # Convert to Session object
                events = [self._deserialize_event(e) for e in json.loads(existing.events_json)]
                return Session(
                    app_name=app_name,
                    user_id=user_id,
                    id=session_id,
                    events=events
                )

            # Create new session
            record = SessionRecord(
                id=session_key,
                app_name=app_name,
                user_id=user_id,
                session_id=session_id,
                events_json='[]'
            )
            db.add(record)
            db.commit()

            print(f"Created new session in PostgreSQL: {session_key}")
            return Session(
                app_name=app_name,
                user_id=user_id,
                id=session_id,
                events=[]
            )
        finally:
            db.close()

    async def get_session(
        self,
        app_name: str,
        user_id: str,
        session_id: str
    ) -> Optional[Session]:
        """Retrieve a session from PostgreSQL with retry logic."""
        def _get_session_inner():
            db = self._get_db()
            try:
                session_key = self._make_session_key(app_name, user_id, session_id)
                record = db.query(SessionRecord).filter_by(id=session_key).first()

                if not record:
                    print(f"Session not found in PostgreSQL: {session_key}")
                    return None

                # Deserialize events
                events = [self._deserialize_event(e) for e in json.loads(record.events_json)]

                print(f"Retrieved session from PostgreSQL: {session_key} with {len(events)} events")
                return Session(
                    app_name=app_name,
                    user_id=user_id,
                    id=session_id,
                    events=events
                )
            finally:
                db.close()

        return self._retry_on_connection_error(_get_session_inner)

    async def delete_session(
        self,
        app_name: str,
        user_id: str,
        session_id: str
    ) -> None:
        """Delete a session from PostgreSQL."""
        db = self._get_db()
        try:
            session_key = self._make_session_key(app_name, user_id, session_id)
            record = db.query(SessionRecord).filter_by(id=session_key).first()

            if record:
                db.delete(record)
                db.commit()
                print(f"Deleted session from PostgreSQL: {session_key}")
            else:
                print(f"Session not found for deletion: {session_key}")
        finally:
            db.close()

    async def append_event(
        self,
        session: Session,
        event: Event
    ) -> None:
        """Append an event to a session in PostgreSQL."""
        db = self._get_db()
        try:
            session_key = self._make_session_key(
                session.app_name,
                session.user_id,
                session.id
            )
            record = db.query(SessionRecord).filter_by(id=session_key).first()

            if not record:
                raise ValueError(f"Session not found: {session_key}")

            # Get existing events
            events = json.loads(record.events_json)

            # Serialize and append new event
            events.append(self._serialize_event(event))

            # Update record
            record.events_json = json.dumps(events)
            record.updated_at = datetime.utcnow()
            db.commit()

            # Update the in-memory session object
            session.events.append(event)

            print(f"Appended event to session: {session_key}, total events: {len(events)}")
        finally:
            db.close()

    async def list_sessions(
        self,
        app_name: str,
        user_id: str
    ) -> List[Session]:
        """List all sessions for a user in an app."""
        db = self._get_db()
        try:
            records = db.query(SessionRecord).filter_by(
                app_name=app_name,
                user_id=user_id
            ).all()

            sessions = []
            for record in records:
                events = [self._deserialize_event(e) for e in json.loads(record.events_json)]
                sessions.append(Session(
                    app_name=record.app_name,
                    user_id=record.user_id,
                    id=record.session_id,
                    events=events
                ))

            print(f"Listed {len(sessions)} sessions for user {user_id} in app {app_name}")
            return sessions
        finally:
            db.close()
