"""
Tools for accessing user conversations.
"""

from datetime import datetime, timezone
from typing import List, Optional
from zoneinfo import ZoneInfo

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

import database.conversations as conversations_db
import database.users as users_db
from models.conversation import Conversation
from models.other import Person
from utils.conversations.search import search_conversations


@tool
def get_conversations_tool(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
    include_discarded: bool = False,
    statuses: Optional[str] = "processing,completed",
    max_transcript_segments: int = 0,
    include_transcript: bool = True,
    include_timestamps: bool = False,
    config: RunnableConfig = None,
) -> str:
    """
    Retrieve user conversations with complete details including transcripts, summaries, and metadata.

    Use this tool when:
    - User asks about recent conversations or specific time periods
    - You need conversation transcripts to answer questions
    - User wants to review what they discussed

    **IMPORTANT for summarization queries:**
    When user asks for weekly, monthly, or yearly summaries/overviews:
    - Set limit=5000 to retrieve ALL conversations in that period
    - Set max_transcript_segments=0 to exclude transcripts (reduce context size)
    - This prevents missing conversations and avoids context overflow from transcripts
    Examples: "summarize my week", "what did I do this month", "recap my year"

    Time filtering guidance:
    - **IMPORTANT**: Use the current datetime from <current_datetime_utc> in the system prompt to calculate all relative times
    - For exact date queries ("October 16th", "yesterday"), use YYYY-MM-DD format - dates are interpreted in user's timezone
    - For relative time queries at hour/minute level ("2 hours ago", "30 minutes ago", "5 minutes ago"):
      * Calculate the exact datetime by subtracting from current time (from system prompt)
      * Use ISO format without timezone (YYYY-MM-DDTHH:MM:SS) - will be interpreted in user's timezone
      * Example: If current time is 2024-01-15 14:00:00 UTC and user asks "2 hours ago", calculate 14:00 - 2 hours = 12:00, then convert to user's timezone and use start_date="2024-01-15T12:00:00"
      * Example: If current time is 2024-01-15 14:30:00 UTC and user asks "5 minutes ago", calculate 14:30 - 5 minutes = 14:25, then convert to user's timezone and use start_date="2024-01-15T14:25:00"
    - For time-of-day queries ("this morning", "this afternoon", "tonight"):
      * Use the current date from <current_datetime_utc> to build the date string
      * "this morning": start_date="YYYY-MM-DDT06:00:00", end_date="YYYY-MM-DDT12:00:00"
      * "this afternoon": start_date="YYYY-MM-DDT12:00:00", end_date="YYYY-MM-DDT18:00:00"
      * "tonight": start_date="YYYY-MM-DDT18:00:00", end_date="YYYY-MM-DDT23:59:59"
    - Combine start_date and end_date to create precise time windows
    - All dates without explicit timezone are assumed to be in the user's local timezone

    Transcript retrieval guidance:
    - By default (max_transcript_segments=0), no transcript segments are included
    - Only increase max_transcript_segments when user explicitly needs transcript content
    - Use reasonable limits (10-50 segments) for most queries - this usually covers key parts
    - Set max_transcript_segments=100 only when user needs extensive transcript details
    - AVOID max_transcript_segments=-1 (full transcript) unless absolutely critical:
      * User explicitly asks for "full transcript" or "complete unabridged transcript"
      * User needs to analyze the entire conversation word-by-word
      * WARNING: -1 can return thousands of segments and flood context
    - Prefer using conversation summaries/overviews when possible instead of full transcripts
    - Maximum allowed is 1000 segments to prevent context overflow

    To include transcripts efficiently:
    - Start with max_transcript_segments=20 for basic transcript needs
    - Use max_transcript_segments=50 for detailed questions
    - Only use max_transcript_segments=-1 as last resort when complete transcript is explicitly required

    Args:
        start_date: Filter conversations after this date (YYYY-MM-DD for days, YYYY-MM-DDTHH:MM:SSZ for hours/minutes)
        end_date: Filter conversations before this date (YYYY-MM-DD for days, YYYY-MM-DDTHH:MM:SSZ for hours/minutes)
        limit: Number of conversations to retrieve (default: 20, max: 100)
        offset: Pagination offset (default: 0)
        include_discarded: Include deleted conversations (default: False)
        statuses: Filter by status, comma-separated (default: all)
        max_transcript_segments: Limit transcript segments (default: 0=none, suggest 20-50 for normal use, avoid -1 except when critical, max: 1000)
        include_transcript: Include full transcript (default: True)
        include_timestamps: Add timestamps to transcript segments (default: False)

    Returns:
        Formatted string with conversation details including title, overview, transcript, photos,
        action items, events, and attendees.
    """
    print(f"🔧 get_conversations_tool called with params:")
    print(f"   start_date: {start_date}")
    print(f"   end_date: {end_date}")
    print(f"   limit: {limit}")
    print(f"   offset: {offset}")
    print(f"   include_discarded: {include_discarded}")
    print(f"   statuses: {statuses}")
    print(f"   max_transcript_segments: {max_transcript_segments}")
    print(f"   include_transcript: {include_transcript}")
    print(f"   include_timestamps: {include_timestamps}")
    # print(f"   config: {config}")

    uid = config['configurable'].get('user_id')
    if not uid:
        print(f"❌ get_conversations_tool - no user_id in config")
        return "Error: User ID not found in configuration"
    print(f"✅ get_conversations_tool - uid: {uid}")

    # Cap max_transcript_segments at 1000 to prevent flooding LLM context
    if max_transcript_segments != -1:
        max_transcript_segments = min(max_transcript_segments, 1000)
        print(f"📊 max_transcript_segments capped at: {max_transcript_segments}")

    # Get user timezone from config, default to UTC
    user_timezone_str = config['configurable'].get('timezone', 'UTC')
    try:
        user_tz = ZoneInfo(user_timezone_str)
    except Exception:
        user_tz = ZoneInfo('UTC')
    print(f"🌍 get_conversations_tool - user timezone: {user_timezone_str}")

    # Parse dates if provided
    start_dt = None
    end_dt = None

    if start_date:
        try:
            if len(start_date) == 10:  # YYYY-MM-DD - treat as user's local date
                # Parse as naive datetime and localize to user's timezone
                naive_dt = datetime.strptime(start_date, '%Y-%m-%d')
                start_dt = naive_dt.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=user_tz)
                print(f"📅 Parsed start_date '{start_date}' as {start_dt} in {user_timezone_str}")
            else:
                # Parse ISO format - if no timezone, assume user's timezone
                start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                if start_dt.tzinfo is None:
                    start_dt = start_dt.replace(tzinfo=user_tz)
        except ValueError:
            return f"Error: Invalid start_date format: {start_date}"

    if end_date:
        try:
            if len(end_date) == 10:  # YYYY-MM-DD - treat as user's local date
                # Parse as naive datetime and localize to user's timezone (end of day)
                naive_dt = datetime.strptime(end_date, '%Y-%m-%d')
                end_dt = naive_dt.replace(hour=23, minute=59, second=59, microsecond=999999, tzinfo=user_tz)
                print(f"📅 Parsed end_date '{end_date}' as {end_dt} in {user_timezone_str}")
            else:
                # Parse ISO format - if no timezone, assume user's timezone
                end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                if end_dt.tzinfo is None:
                    end_dt = end_dt.replace(tzinfo=user_tz)
        except ValueError:
            return f"Error: Invalid end_date format: {end_date}"

    # Limit to reasonable max
    limit = min(limit, 5000)

    # Parse statuses if provided
    status_list = []
    if statuses:
        status_list = [s.strip() for s in statuses.split(',') if s.strip()]

    # Get conversations
    conversations_data = conversations_db.get_conversations(
        uid,
        limit=limit,
        offset=offset,
        start_date=start_dt,
        end_date=end_dt,
        include_discarded=include_discarded,
        statuses=status_list,
    )

    print(f"📊 get_conversations_tool - found {len(conversations_data) if conversations_data else 0} conversations")

    if not conversations_data:
        date_info = ""
        if start_dt and end_dt:
            date_info = f" between {start_dt.strftime('%Y-%m-%d')} and {end_dt.strftime('%Y-%m-%d')}"
        elif start_dt:
            date_info = f" after {start_dt.strftime('%Y-%m-%d')}"
        elif end_dt:
            date_info = f" before {end_dt.strftime('%Y-%m-%d')}"

        msg = f"No conversations found{date_info}. The user may not have recorded any conversations yet, or the date range may be outside their conversation history."
        print(f"⚠️ get_conversations_tool - {msg}")
        return msg

    try:
        # Get all person IDs from all conversations
        all_person_ids = []
        for conv_data in conversations_data:
            segments = conv_data.get('transcript_segments', [])
            all_person_ids.extend([s.get('person_id') for s in segments if s.get('person_id')])

        print(f"🔍 get_conversations_tool - Found {len(all_person_ids)} person IDs")

        # Fetch people data
        people = []
        if all_person_ids:
            people_data = users_db.get_people_by_ids(uid, list(set(all_person_ids)))
            people = [Person(**p) for p in people_data]
            print(f"🔍 get_conversations_tool - Loaded {len(people)} people")

        # Convert to Conversation objects
        conversations = []
        for conv_data in conversations_data:
            try:
                conversation = Conversation(**conv_data)

                # Limit transcript segments if needed (mimicking integration.py pattern)
                if (
                    max_transcript_segments != -1
                    and conversation.transcript_segments
                    and len(conversation.transcript_segments) > max_transcript_segments
                ):
                    conversation.transcript_segments = conversation.transcript_segments[:max_transcript_segments]

                conversations.append(conversation)
            except Exception as e:
                print(f"Error parsing conversation {conv_data.get('id')}: {str(e)}")
                continue

        print(f"🔍 get_conversations_tool - Converted {len(conversations)} conversation objects")

        # Store conversations in config for citation tracking (as lightweight dicts)
        conversations_collected = config['configurable'].get('conversations_collected', [])
        for conv in conversations:
            conv_dict = conv.dict()
            # Remove heavy fields to reduce memory usage
            conv_dict.pop('transcript_segments', None)
            conv_dict.pop('photos', None)
            conv_dict.pop('audio_files', None)
            conversations_collected.append(conv_dict)
        print(
            f"📚 get_conversations_tool - Added {len(conversations)} conversations to collection (total: {len(conversations_collected)})"
        )

        # Return formatted string
        result = Conversation.conversations_to_string(
            conversations, use_transcript=include_transcript, include_timestamps=include_timestamps, people=people
        )
        print(f"🔍 get_conversations_tool - Generated result string, length: {len(result)}")
        return result

    except Exception as e:
        error_msg = f"Error formatting conversations: {str(e)}"
        print(f"❌ get_conversations_tool - {error_msg}")
        import traceback

        traceback.print_exc()
        return f"Found {len(conversations_data)} conversations but encountered an error formatting them: {str(e)}"


@tool
def search_conversations_tool(
    query: str,
    per_page: int = 10,
    page: int = 1,
    include_discarded: bool = False,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    max_transcript_segments: int = 0,
    include_transcript: bool = True,
    include_timestamps: bool = False,
    config: RunnableConfig = None,
) -> str:
    """
    Search user conversations using semantic similarity search.

    Performs vector-based search to find conversations by meaning, not just keywords.
    Returns conversations ranked by relevance with complete details.

    Use this tool when:
    - User asks about specific topics or discussions
    - You need to find conversations containing certain information
    - User wants conversations with specific people or about specific subjects

    **IMPORTANT for summarization queries:**
    When user asks for weekly, monthly, or yearly summaries about a specific topic:
    - Set per_page=100 (maximum) to retrieve more results per query
    - Set max_transcript_segments=0 to exclude transcripts (reduce context size)
    - Use multiple pages if needed to cover the full time period
    Examples: "summarize work discussions this month", "recap health topics this year"

    Time filtering guidance:
    - **IMPORTANT**: Use the current datetime from <current_datetime_utc> in the system prompt to calculate all relative times
    - For exact date queries ("October 16th", "yesterday"), use YYYY-MM-DD format - dates are interpreted in user's timezone
    - For relative time queries ("2 hours ago", "5 minutes ago", "this morning"), calculate exact datetime in user's timezone and use ISO format
    - Use ISO datetime format (YYYY-MM-DDTHH:MM:SS) for hour/minute-level queries (no Z suffix)
    - Combine start_date and end_date to create time windows for precise time ranges
    - All dates without timezone info are assumed to be in the user's local timezone

    Transcript retrieval guidance:
    - By default (max_transcript_segments=0), no transcript segments are included
    - Only increase max_transcript_segments when user explicitly needs transcript content
    - Use reasonable limits (10-50 segments) for most queries - this usually covers key parts
    - Set max_transcript_segments=100 only when user needs extensive transcript details
    - AVOID max_transcript_segments=-1 (full transcript) unless absolutely critical:
      * User explicitly asks for "full transcript" or "complete unabridged transcript"
      * User needs to analyze the entire conversation word-by-word
      * WARNING: -1 can return thousands of segments and flood context
    - Prefer using conversation summaries/overviews when possible instead of full transcripts
    - Maximum allowed is 1000 segments to prevent context overflow

    To include transcripts efficiently:
    - Start with max_transcript_segments=20 for basic transcript needs
    - Use max_transcript_segments=50 for detailed questions
    - Only use max_transcript_segments=-1 as last resort when complete transcript is explicitly required

    Args:
        query: Natural language search query (required)
        per_page: Results per page (default: 10, max: 100)
        page: Page number starting at 1 (default: 1)
        include_discarded: Include deleted conversations (default: False)
        start_date: Filter conversations after this date (YYYY-MM-DD for days, YYYY-MM-DDTHH:MM:SSZ for hours/minutes)
        end_date: Filter conversations before this date (YYYY-MM-DD for days, YYYY-MM-DDTHH:MM:SSZ for hours/minutes)
        max_transcript_segments: Limit transcript segments (default: 0=none, suggest 20-50 for normal use, avoid -1 except when critical, max: 1000)
        include_transcript: Include full transcript (default: True)
        include_timestamps: Add timestamps to transcript segments (default: False)

    Returns:
        Formatted string with matching conversations ranked by relevance, including transcripts,
        summaries, action items, events, and pagination info.
    """
    print(f"🔧 search_conversations_tool called - query: {query}, config: {config}")
    uid = config['configurable'].get('user_id')
    if not uid:
        print(f"❌ search_conversations_tool - no user_id in config")
        return "Error: User ID not found in configuration"
    print(f"✅ search_conversations_tool - uid: {uid}, query: {query}, per_page: {per_page}, page: {page}")

    # Cap max_transcript_segments at 1000 to prevent flooding LLM context
    if max_transcript_segments != -1:
        max_transcript_segments = min(max_transcript_segments, 1000)
        print(f"📊 max_transcript_segments capped at: {max_transcript_segments}")

    # Get user timezone from config, default to UTC
    user_timezone_str = config['configurable'].get('timezone', 'UTC')
    try:
        user_tz = ZoneInfo(user_timezone_str)
    except Exception:
        user_tz = ZoneInfo('UTC')
    print(f"🌍 search_conversations_tool - user timezone: {user_timezone_str}")

    # Parse dates to timestamps if provided
    start_timestamp = None
    end_timestamp = None

    if start_date:
        try:
            if len(start_date) == 10:  # YYYY-MM-DD - treat as user's local date
                # Parse as naive datetime and localize to user's timezone
                naive_dt = datetime.strptime(start_date, '%Y-%m-%d')
                dt = naive_dt.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=user_tz)
                print(f"📅 Parsed start_date '{start_date}' as {dt} in {user_timezone_str}")
            else:
                # Parse ISO format - if no timezone, assume user's timezone
                dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=user_tz)
            start_timestamp = int(dt.timestamp())
        except ValueError:
            return f"Error: Invalid start_date format: {start_date}"

    if end_date:
        try:
            if len(end_date) == 10:  # YYYY-MM-DD - treat as user's local date
                # Parse as naive datetime and localize to user's timezone (end of day)
                naive_dt = datetime.strptime(end_date, '%Y-%m-%d')
                dt = naive_dt.replace(hour=23, minute=59, second=59, microsecond=999999, tzinfo=user_tz)
                print(f"📅 Parsed end_date '{end_date}' as {dt} in {user_timezone_str}")
            else:
                # Parse ISO format - if no timezone, assume user's timezone
                dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=user_tz)
            end_timestamp = int(dt.timestamp())
        except ValueError:
            return f"Error: Invalid end_date format: {end_date}"

    # Limit to reasonable max and convert to 0-based page index
    per_page = min(per_page, 5000)
    page_index = max(0, page - 1)  # Convert 1-based to 0-based

    # Search conversations
    search_results = search_conversations(
        query=query,
        page=page_index,
        per_page=per_page,
        uid=uid,
        include_discarded=include_discarded,
        start_date=start_timestamp,
        end_date=end_timestamp,
    )

    print(f"📊 search_conversations_tool - found {len(search_results.get('items', []))} results for query: '{query}'")

    if not search_results.get('items'):
        msg = f"No conversations found matching '{query}'. The user may not have discussed this topic yet, or it may not be in their recorded conversation history."
        print(f"⚠️ search_conversations_tool - {msg}")
        return msg

    try:
        # Get conversation IDs
        conversation_ids = [conv.get('id') for conv in search_results['items']]
        print(f"🔍 search_conversations_tool - Retrieved {len(conversation_ids)} conversation IDs")

        # Get full conversation data
        conversations_data = conversations_db.get_conversations_by_id(uid, conversation_ids)

        if not conversations_data:
            return f"No conversations found matching query: '{query}'"

        print(f"🔍 search_conversations_tool - Loaded {len(conversations_data)} full conversations")

        # Get all person IDs
        all_person_ids = []
        for conv_data in conversations_data:
            segments = conv_data.get('transcript_segments', [])
            all_person_ids.extend([s.get('person_id') for s in segments if s.get('person_id')])

        print(f"🔍 search_conversations_tool - Found {len(all_person_ids)} person IDs")

        # Fetch people data
        people = []
        if all_person_ids:
            people_data = users_db.get_people_by_ids(uid, list(set(all_person_ids)))
            people = [Person(**p) for p in people_data]
            print(f"🔍 search_conversations_tool - Loaded {len(people)} people")

        # Convert to Conversation objects
        conversations = []
        for conv_data in conversations_data:
            try:
                conversation = Conversation(**conv_data)

                # Limit transcript segments if needed (mimicking integration.py pattern)
                if (
                    max_transcript_segments != -1
                    and conversation.transcript_segments
                    and len(conversation.transcript_segments) > max_transcript_segments
                ):
                    conversation.transcript_segments = conversation.transcript_segments[:max_transcript_segments]

                conversations.append(conversation)
            except Exception as e:
                print(f"Error parsing conversation {conv_data.get('id')}: {str(e)}")
                continue

        print(f"🔍 search_conversations_tool - Converted {len(conversations)} conversation objects")

        # Return formatted string with pagination info
        total_pages = search_results.get('total_pages', 1)
        current_page = page  # User-facing page number

        result = (
            f"Found {len(conversations)} conversations matching '{query}' (Page {current_page} of {total_pages}):\n\n"
        )
        result += Conversation.conversations_to_string(
            conversations, use_transcript=include_transcript, include_timestamps=include_timestamps, people=people
        )

        if current_page < total_pages:
            result += f"\n\nNote: There are more results. Use page={current_page + 1} to see the next page."

        # Store conversations in config for citation tracking (as lightweight dicts)
        conversations_collected = config['configurable'].get('conversations_collected', [])
        for conv in conversations:
            conv_dict = conv.dict()
            # Remove heavy fields to reduce memory usage
            conv_dict.pop('transcript_segments', None)
            conv_dict.pop('photos', None)
            conv_dict.pop('audio_files', None)
            conversations_collected.append(conv_dict)
        print(
            f"📚 search_conversations_tool - Added {len(conversations)} conversations to collection (total: {len(conversations_collected)})"
        )

        print(f"🔍 search_conversations_tool - Generated result string, length: {len(result)}")

        return result

    except Exception as e:
        error_msg = f"Error processing search results: {str(e)}"
        print(f"❌ search_conversations_tool - {error_msg}")
        import traceback

        traceback.print_exc()
        return f"Found search results but encountered an error processing them: {str(e)}"
