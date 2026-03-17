import json
import logging
import os
import threading
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

import database.action_items as action_items_db
import database.memories as memories_db
import database.users as users_db
from database.vector_db import upsert_memory_vector
from models.memories import Memory, MemoryDB, MemoryCategory
from utils.llm.clients import llm_mini
from utils.other import endpoints as auth
from utils.retrieval.tools.calendar_tools import get_google_calendar_events
from utils.retrieval.tools.google_utils import refresh_google_token

logger = logging.getLogger(__name__)

router = APIRouter()


class CalendarSyncRequest(BaseModel):
    server_auth_code: Optional[str] = None


@router.post('/v1/calendar/sync-memories', tags=['calendar', 'onboarding'])
def calendar_sync_memories(
    request: CalendarSyncRequest = CalendarSyncRequest(),
    uid: str = Depends(auth.get_current_user_uid),
):
    """Sync Google Calendar events into memories and tasks.

    Two modes:
    - With server_auth_code: exchange code for tokens, store integration, then sync (mobile onboarding)
    - Without: use existing stored google_calendar integration tokens (desktop, post-OAuth)
    """
    threading.Thread(
        target=_background_calendar_sync,
        args=(uid, request.server_auth_code),
        daemon=True,
    ).start()
    return {'status': 'accepted', 'message': 'Calendar sync started'}


def _background_calendar_sync(uid: str, server_auth_code: Optional[str] = None):
    try:
        if server_auth_code:
            # Mobile flow: exchange auth code for tokens
            existing = users_db.get_integration(uid, 'google_calendar')
            if existing and existing.get('connected'):
                logger.info(
                    f"Calendar sync: user {uid} already has google_calendar integration, skipping code exchange"
                )
            else:
                tokens = _exchange_auth_code(server_auth_code)
                if not tokens:
                    logger.info(f"Calendar sync: code exchange failed for {uid}")
                    return

                integration_data = {
                    'connected': True,
                    'access_token': tokens['access_token'],
                    'source': 'onboarding',
                }
                if tokens.get('refresh_token'):
                    integration_data['refresh_token'] = tokens['refresh_token']
                users_db.set_integration(uid, 'google_calendar', integration_data)
                logger.info(f"Calendar sync: stored google_calendar integration for {uid}")

        # Get stored integration tokens
        integration = users_db.get_integration(uid, 'google_calendar')
        if not integration or not integration.get('connected'):
            logger.info(f"Calendar sync: no google_calendar integration for {uid}")
            return

        access_token = integration.get('access_token')
        if not access_token:
            logger.info(f"Calendar sync: no access_token for {uid}")
            return

        # Fetch calendar events (last 30 days + next 14 days)
        now = datetime.now(timezone.utc)
        try:
            events = get_google_calendar_events(
                access_token=access_token,
                time_min=now - timedelta(days=30),
                time_max=now + timedelta(days=14),
                max_results=100,
            )
        except Exception as e:
            error_msg = str(e)
            if '401' in error_msg:
                # Token expired, try refresh
                new_token = refresh_google_token(uid, integration)
                if new_token:
                    try:
                        events = get_google_calendar_events(
                            access_token=new_token,
                            time_min=now - timedelta(days=30),
                            time_max=now + timedelta(days=14),
                            max_results=100,
                        )
                    except Exception as e2:
                        logger.warning(f"Calendar sync: failed after token refresh for {uid}: {e2}")
                        return
                else:
                    logger.warning(f"Calendar sync: token refresh failed for {uid}")
                    return
            else:
                logger.warning(f"Calendar sync: failed to fetch events for {uid}: {e}")
                return

        if not events:
            logger.info(f"Calendar sync: no events found for {uid}")
            return

        logger.info(f"Calendar sync: fetched {len(events)} events for {uid}")

        # Format events for LLM
        events_text = _format_events(events)

        # Synthesize memories + tasks via LLM
        synthesis = _synthesize_events(events_text)
        if not synthesis:
            logger.warning(f"Calendar sync: LLM synthesis failed for {uid}")
            return

        # Save memories and tasks
        _save_memories_and_tasks(uid, synthesis)

        memory_count = len(synthesis.get('memories', []))
        task_count = len(synthesis.get('tasks', []))
        logger.info(f"Calendar sync: created {memory_count} memories and {task_count} tasks for {uid}")

    except Exception as e:
        logger.error(f"Calendar sync error for {uid}: {e}")


def _exchange_auth_code(server_auth_code: str) -> dict | None:
    import requests

    client_id = os.getenv('GOOGLE_CLIENT_ID')
    client_secret = os.getenv('GOOGLE_CLIENT_SECRET')

    if not all([client_id, client_secret]):
        logger.error("Calendar sync: GOOGLE_CLIENT_ID or GOOGLE_CLIENT_SECRET not set")
        return None

    try:
        response = requests.post(
            'https://oauth2.googleapis.com/token',
            data={
                'code': server_auth_code,
                'client_id': client_id,
                'client_secret': client_secret,
                'grant_type': 'authorization_code',
                'redirect_uri': '',
            },
            timeout=10.0,
        )

        if response.status_code != 200:
            logger.error(f"Calendar sync: token exchange failed {response.status_code}: {response.text[:200]}")
            return None

        return response.json()
    except Exception as e:
        logger.error(f"Calendar sync: token exchange error: {e}")
        return None


def _format_events(events: list) -> str:
    lines = []
    for event in events:
        summary = event.get('summary', 'Untitled')
        start = event.get('start', {}).get('dateTime') or event.get('start', {}).get('date', '')
        end = event.get('end', {}).get('dateTime') or event.get('end', {}).get('date', '')
        attendees = [a.get('email', '') for a in event.get('attendees', []) if not a.get('self')]
        location = event.get('location', '')
        description = (event.get('description', '') or '')[:200]

        parts = [f"- {summary} ({start} to {end})"]
        if attendees:
            parts.append(f"  With: {', '.join(attendees[:5])}")
        if location:
            parts.append(f"  Location: {location}")
        if description:
            parts.append(f"  Notes: {description}")
        lines.append('\n'.join(parts))

    return '\n'.join(lines)


def _synthesize_events(events_text: str) -> dict | None:
    prompt = f"""You are analyzing a new user's Google Calendar events to help personalize their experience with Omi, an AI companion.

Here are the user's calendar events from the past 30 days and next 14 days:

{events_text}

Today's date: {datetime.now().strftime('%Y-%m-%d')}

Based on these events, create:

1. MEMORIES (5-10): Facts about this person that Omi should remember. Each memory should be a single sentence capturing something meaningful about the user's life, work, relationships, habits, or interests. Write in third person about "the user" (e.g., "The user has weekly 1-on-1 meetings with their manager Sarah"). Focus on patterns, not one-off events.

2. TASKS (2-3): Actionable items the user likely needs to do based on upcoming events. Each task should have a description and a due date (ISO format). Only create tasks for events in the future.

Respond in this exact JSON format:
{{
  "memories": [
    "Memory text here",
    "Another memory text"
  ],
  "tasks": [
    {{"description": "Task description", "due_at": "2024-01-15T09:00:00Z"}},
    {{"description": "Another task", "due_at": "2024-01-16T14:00:00Z"}}
  ]
}}

Rules:
- Memories should reveal PATTERNS (recurring meetings, regular gym sessions, work schedule) not individual events
- Memories should be personal and useful for an AI companion (preferences, relationships, routines)
- Tasks should only reference FUTURE events
- If there are very few events, create fewer memories (minimum 3)
- Write memories as factual statements, not observations
- Do not include sensitive medical or financial details"""

    try:
        response = llm_mini.invoke(prompt)
        content = response.content

        # Extract JSON from response (handle markdown code blocks)
        if '```json' in content:
            content = content.split('```json')[1].split('```')[0]
        elif '```' in content:
            content = content.split('```')[1].split('```')[0]

        return json.loads(content.strip())
    except Exception as e:
        logger.error(f"Calendar sync: LLM synthesis error: {e}")
        return None


def _save_memories_and_tasks(uid: str, synthesis: dict):
    # Save memories
    for memory_text in synthesis.get('memories', [])[:10]:
        try:
            memory = Memory(
                content=memory_text,
                category=MemoryCategory.manual,
                visibility='private',
                tags=['calendar', 'onboarding'],
            )
            memory_db = MemoryDB.from_memory(memory, uid, None, True)
            memories_db.create_memory(uid, memory_db.dict())
            upsert_memory_vector(uid, memory_db.id, memory_db.content, memory_db.category.value)
        except Exception as e:
            logger.error(f"Calendar sync: failed to create memory for {uid}: {e}")

    # Save tasks
    for task in synthesis.get('tasks', [])[:3]:
        try:
            action_items_db.create_action_item(
                uid,
                {
                    'description': task['description'],
                    'completed': False,
                    'due_at': task.get('due_at'),
                    'source': 'calendar_onboarding',
                },
            )
        except Exception as e:
            logger.error(f"Calendar sync: failed to create task for {uid}: {e}")
