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
import database.vector_db as vector_db
from models.conversation import Conversation
from models.other import Person
from utils.conversations.search import search_conversations
from utils.llm.clients import embeddings


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
        start_date: Filter conversations after this date (ISO format in user's timezone: YYYY-MM-DDTHH:MM:SS+HH:MM, e.g. "2024-01-19T15:00:00-08:00")
        end_date: Filter conversations before this date (ISO format in user's timezone: YYYY-MM-DDTHH:MM:SS+HH:MM, e.g. "2024-01-19T23:59:59-08:00")
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

    # Get safety guard from config if available
    safety_guard = config['configurable'].get('safety_guard')

    # Cap max_transcript_segments at 1000 to prevent flooding LLM context
    if max_transcript_segments != -1:
        max_transcript_segments = min(max_transcript_segments, 1000)
        print(f"📊 max_transcript_segments capped at: {max_transcript_segments}")

    # Parse dates if provided (always in UTC)
    start_dt = None
    end_dt = None

    if start_date:
        try:
            # Parse ISO format with timezone - should be in user's timezone (YYYY-MM-DDTHH:MM:SS+HH:MM)
            start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            if start_dt.tzinfo is None:
                return f"Error: start_date must include timezone in user's timezone format YYYY-MM-DDTHH:MM:SS+HH:MM (e.g., '2024-01-19T15:00:00-08:00'): {start_date}"
            print(f"📅 Parsed start_date '{start_date}' as {start_dt.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        except ValueError as e:
            return f"Error: Invalid start_date format. Expected YYYY-MM-DDTHH:MM:SS+HH:MM in user's timezone: {start_date} - {str(e)}"

    if end_date:
        try:
            # Parse ISO format with timezone - should be in user's timezone (YYYY-MM-DDTHH:MM:SS+HH:MM)
            end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
            if end_dt.tzinfo is None:
                return f"Error: end_date must include timezone in user's timezone format YYYY-MM-DDTHH:MM:SS+HH:MM (e.g., '2024-01-19T23:59:59-08:00'): {end_date}"
            print(f"📅 Parsed end_date '{end_date}' as {end_dt.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        except ValueError as e:
            return f"Error: Invalid end_date format. Expected YYYY-MM-DDTHH:MM:SS+HH:MM in user's timezone: {end_date} - {str(e)}"

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
        # Only load people if transcripts will be included (people are used for speaker names in transcripts)
        people = []
        if include_transcript:
            # Get all person IDs from all conversations
            all_person_ids = set()
            for conv_data in conversations_data:
                segments = conv_data.get('transcript_segments', [])
                all_person_ids.update([s.get('person_id') for s in segments if s.get('person_id')])

            print(f"🔍 get_conversations_tool - Found {len(all_person_ids)} unique person IDs")

            # Fetch people data
            if all_person_ids:
                people_data = users_db.get_people_by_ids(uid, list(all_person_ids))
                people = [Person(**p) for p in people_data]
                print(f"🔍 get_conversations_tool - Loaded {len(people)} people")
        else:
            print(f"🔍 get_conversations_tool - Skipping people loading (transcript not included)")

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
        start_date: Filter conversations after this date (ISO format in user's timezone: YYYY-MM-DDTHH:MM:SS+HH:MM, e.g. "2024-01-19T15:00:00-08:00")
        end_date: Filter conversations before this date (ISO format in user's timezone: YYYY-MM-DDTHH:MM:SS+HH:MM, e.g. "2024-01-19T23:59:59-08:00")
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

    # Get safety guard from config if available
    safety_guard = config['configurable'].get('safety_guard')

    # Cap max_transcript_segments at 1000 to prevent flooding LLM context
    if max_transcript_segments != -1:
        max_transcript_segments = min(max_transcript_segments, 1000)
        print(f"📊 max_transcript_segments capped at: {max_transcript_segments}")

    # Parse dates to timestamps if provided (always in UTC)
    start_timestamp = None
    end_timestamp = None

    if start_date:
        try:
            # Parse ISO format with timezone - should be in user's timezone (YYYY-MM-DDTHH:MM:SS+HH:MM)
            dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            if dt.tzinfo is None:
                return f"Error: start_date must include timezone in user's timezone format YYYY-MM-DDTHH:MM:SS+HH:MM (e.g., '2024-01-19T15:00:00-08:00'): {start_date}"
            print(f"📅 Parsed start_date '{start_date}' as {dt.strftime('%Y-%m-%d %H:%M:%S %Z')}")
            start_timestamp = int(dt.timestamp())
        except ValueError as e:
            return f"Error: Invalid start_date format. Expected YYYY-MM-DDTHH:MM:SS+HH:MM in user's timezone: {start_date} - {str(e)}"

    if end_date:
        try:
            # Parse ISO format with timezone - should be in user's timezone (YYYY-MM-DDTHH:MM:SS+HH:MM)
            dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
            if dt.tzinfo is None:
                return f"Error: end_date must include timezone in user's timezone format YYYY-MM-DDTHH:MM:SS+HH:MM (e.g., '2024-01-19T23:59:59-08:00'): {end_date}"
            print(f"📅 Parsed end_date '{end_date}' as {dt.strftime('%Y-%m-%d %H:%M:%S %Z')}")
            end_timestamp = int(dt.timestamp())
        except ValueError as e:
            return f"Error: Invalid end_date format. Expected YYYY-MM-DDTHH:MM:SS+HH:MM in user's timezone: {end_date} - {str(e)}"

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

        # Only load people if transcripts will be included (people are used for speaker names in transcripts)
        people = []
        if include_transcript:
            # Get all person IDs
            all_person_ids = set()
            for conv_data in conversations_data:
                segments = conv_data.get('transcript_segments', [])
                all_person_ids.update([s.get('person_id') for s in segments if s.get('person_id')])

            print(f"🔍 search_conversations_tool - Found {len(all_person_ids)} unique person IDs")

            # Fetch people data
            if all_person_ids:
                people_data = users_db.get_people_by_ids(uid, list(all_person_ids))
                people = [Person(**p) for p in people_data]
                print(f"🔍 search_conversations_tool - Loaded {len(people)} people")
        else:
            print(f"🔍 search_conversations_tool - Skipping people loading (transcript not included)")

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


@tool
def vector_search_conversations_tool(
    query: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 5,
    max_transcript_segments: int = 0,
    include_transcript: bool = True,
    include_timestamps: bool = False,
    config: RunnableConfig = None,
) -> str:
    """
    Search conversations using semantic vector search based on meaning and context.

    This tool uses AI embeddings to find conversations that are semantically similar to your query,
    even if they don't contain the exact keywords. Perfect for conceptual/thematic searches.

    **When to use this tool:**
    - Searching for concepts, themes, or topics (e.g., "discussions about personal growth", "health-related talks")
    - Finding similar conversations even without exact keyword matches
    - Broad subject searches (e.g., "what have I talked about regarding relationships?")
    - Understanding overall themes or patterns in conversations

    **When NOT to use this tool:**
    - For exact keyword or phrase searches (use search_conversations_tool instead)
    - For searching specific names, dates, or factual data (use search_conversations_tool instead)
    - For precise location or entity matching (use search_conversations_tool instead)

    **Tip:** For best results, use descriptive phrases about the concept you're looking for rather than specific keywords.

    Transcript retrieval guidance (same as other conversation tools):
    - By default (max_transcript_segments=0), no transcript segments are included
    - Only increase when user explicitly needs transcript content
    - Use 20-50 segments for most queries
    - Avoid -1 (full transcript) unless absolutely critical
    - Maximum allowed is 1000 segments to prevent context overflow

    Args:
        query: Natural language description of the concept/topic to search for (required)
        start_date: Filter conversations after this date (ISO format in user's timezone: YYYY-MM-DDTHH:MM:SS+HH:MM)
        end_date: Filter conversations before this date (ISO format in user's timezone: YYYY-MM-DDTHH:MM:SS+HH:MM)
        limit: Number of conversations to retrieve (default: 5, max: 20)
        max_transcript_segments: Limit transcript segments (default: 0=none, suggest 20-50 for normal use, max: 1000)
        include_transcript: Include full transcript (default: True)
        include_timestamps: Add timestamps to transcript segments (default: False)

    Returns:
        Formatted string with semantically matching conversations ranked by relevance, including transcripts,
        summaries, action items, events, and metadata.
    """
    print(f"🔧 vector_search_conversations_tool called with query: {query}")
    uid = config['configurable'].get('user_id')
    if not uid:
        print(f"❌ vector_search_conversations_tool - no user_id in config")
        return "Error: User ID not found in configuration"
    print(f"✅ vector_search_conversations_tool - uid: {uid}, query: {query}, limit: {limit}")

    # Get safety guard from config if available
    safety_guard = config['configurable'].get('safety_guard')

    # Cap max_transcript_segments at 1000 to prevent flooding LLM context
    if max_transcript_segments != -1:
        max_transcript_segments = min(max_transcript_segments, 1000)
        print(f"📊 max_transcript_segments capped at: {max_transcript_segments}")

    # Parse dates to timestamps if provided
    starts_at = None
    ends_at = None

    if start_date:
        try:
            dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            if dt.tzinfo is None:
                return f"Error: start_date must include timezone in user's timezone format YYYY-MM-DDTHH:MM:SS+HH:MM (e.g., '2024-01-19T15:00:00-08:00'): {start_date}"
            print(f"📅 Parsed start_date '{start_date}' as {dt.strftime('%Y-%m-%d %H:%M:%S %Z')}")
            starts_at = int(dt.timestamp())
        except ValueError as e:
            return f"Error: Invalid start_date format. Expected YYYY-MM-DDTHH:MM:SS+HH:MM in user's timezone: {start_date} - {str(e)}"

    if end_date:
        try:
            dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
            if dt.tzinfo is None:
                return f"Error: end_date must include timezone in user's timezone format YYYY-MM-DDTHH:MM:SS+HH:MM (e.g., '2024-01-19T23:59:59-08:00'): {end_date}"
            print(f"📅 Parsed end_date '{end_date}' as {dt.strftime('%Y-%m-%d %H:%M:%S %Z')}")
            ends_at = int(dt.timestamp())
        except ValueError as e:
            return f"Error: Invalid end_date format. Expected YYYY-MM-DDTHH:MM:SS+HH:MM in user's timezone: {end_date} - {str(e)}"

    # Limit to reasonable max
    limit = min(limit, 20)

    try:
        # Perform vector search
        conversation_ids = vector_db.query_vectors(query=query, uid=uid, starts_at=starts_at, ends_at=ends_at, k=limit)

        print(f"📊 vector_search_conversations_tool - found {len(conversation_ids)} results for query: '{query}'")

        if not conversation_ids:
            date_info = ""
            if starts_at and ends_at:
                date_info = f" in the specified date range"
            elif starts_at:
                date_info = f" after the specified start date"
            elif ends_at:
                date_info = f" before the specified end date"

            msg = f"No conversations found matching the concept '{query}'{date_info}. The user may not have discussed this topic yet, or it may not be in their recorded conversation history."
            print(f"⚠️ vector_search_conversations_tool - {msg}")
            return msg

        # Get full conversation data
        conversations_data = conversations_db.get_conversations_by_id(uid, conversation_ids)

        if not conversations_data:
            return f"No conversations found matching query: '{query}'"

        print(f"🔍 vector_search_conversations_tool - Loaded {len(conversations_data)} full conversations")

        # Only load people if transcripts will be included
        people = []
        if include_transcript:
            # Get all person IDs
            all_person_ids = set()
            for conv_data in conversations_data:
                segments = conv_data.get('transcript_segments', [])
                all_person_ids.update([s.get('person_id') for s in segments if s.get('person_id')])

            print(f"🔍 vector_search_conversations_tool - Found {len(all_person_ids)} unique person IDs")

            # Fetch people data
            if all_person_ids:
                people_data = users_db.get_people_by_ids(uid, list(all_person_ids))
                people = [Person(**p) for p in people_data]
                print(f"🔍 vector_search_conversations_tool - Loaded {len(people)} people")
        else:
            print(f"🔍 vector_search_conversations_tool - Skipping people loading (transcript not included)")

        # Convert to Conversation objects
        conversations = []
        for conv_data in conversations_data:
            try:
                conversation = Conversation(**conv_data)

                # Limit transcript segments if needed
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

        print(f"🔍 vector_search_conversations_tool - Converted {len(conversations)} conversation objects")

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
            f"📚 vector_search_conversations_tool - Added {len(conversations)} conversations to collection (total: {len(conversations_collected)})"
        )

        # Return formatted string
        result = f"Found {len(conversations)} conversations semantically matching '{query}':\n\n"
        result += Conversation.conversations_to_string(
            conversations, use_transcript=include_transcript, include_timestamps=include_timestamps, people=people
        )

        print(f"🔍 vector_search_conversations_tool - Generated result string, length: {len(result)}")

        return result

    except Exception as e:
        error_msg = f"Error performing vector search: {str(e)}"
        print(f"❌ vector_search_conversations_tool - {error_msg}")
        import traceback

        traceback.print_exc()
        return f"Found vector search results but encountered an error processing them: {str(e)}"
