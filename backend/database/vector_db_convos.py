import json
import gzip
import zlib
import base64
from typing import List, Dict, Any, Optional
from datetime import datetime

import database.chat_convo as chat_convo_db
from models.conversation import Conversation
from models.transcript_segment import TranscriptSegment


def get_conversation_context(uid: str, conversation_id: str) -> Dict[str, Any]:
    """
    Get all relevant context for a conversation chat.
    Returns transcript, summary, memories, and action items for the specific conversation.
    """
    print(f"Getting conversation context for {conversation_id}")

    # Get base conversation data
    conversation_data = chat_convo_db.get_conversation_data(uid, conversation_id)
    if not conversation_data:
        return {'transcript': '', 'summary': '', 'memories': [], 'action_items': [], 'context_text': ''}

    # Extract transcript
    transcript_text = _extract_transcript_text(conversation_data)

    # Get summary - check both direct and structured locations
    summary = conversation_data.get('overview', '')
    if not summary and 'structured' in conversation_data:
        summary = conversation_data['structured'].get('overview', '')

    # Get associated memories
    memories = chat_convo_db.get_conversation_memories(uid, conversation_id)

    # Get associated action items
    action_items = chat_convo_db.get_conversation_action_items(uid, conversation_id)

    # Compile all context into searchable text
    context_text = _compile_context_text(transcript_text, summary, memories, action_items)

    return {
        'transcript': transcript_text,
        'summary': summary,
        'memories': memories,
        'action_items': action_items,
        'context_text': context_text,
        'conversation_id': conversation_id,
        'conversation_title': (
            conversation_data.get('title')
            or (conversation_data.get('structured', {}).get('title'))
            or 'Untitled Conversation'
        ),
    }


def _extract_transcript_text(conversation_data: Dict[str, Any]) -> str:
    """Extract and decompress transcript text from conversation data"""

    # Check if transcript_segments exist and are compressed
    if conversation_data.get('transcript_segments_compressed', False):
        # Handle compressed transcript segments
        transcript_segments_data = conversation_data.get('transcript_segments')
        if transcript_segments_data:
            try:
                # Handle both string and bytes cases
                if isinstance(transcript_segments_data, bytes):
                    # If it's bytes, it's already the compressed data (Firebase client decoded base64 for us)
                    compressed_data = transcript_segments_data
                else:
                    # If it's string, it's base64 that we need to decode first
                    compressed_data = base64.b64decode(transcript_segments_data)

                # Try zlib first (most common), then gzip as fallback
                try:
                    decompressed_data = zlib.decompress(compressed_data)
                except Exception:
                    try:
                        decompressed_data = gzip.decompress(compressed_data)
                    except Exception as e:
                        print(f"Error decompressing transcript: {e}")
                        return ""

                segments_data = json.loads(decompressed_data.decode('utf-8'))

                # Convert to TranscriptSegment objects and extract text
                if isinstance(segments_data, list):
                    segments = [TranscriptSegment(**segment) for segment in segments_data]
                    return TranscriptSegment.segments_as_string(segments)

            except Exception as e:
                print(f"Error processing transcript: {e}")
                return ""

    # Fall back to regular transcript field if available
    transcript = conversation_data.get('transcript', '')
    if transcript:
        return transcript

    # If no transcript found, try to extract from structured data
    transcript_segments = conversation_data.get('transcript_segments', [])
    if isinstance(transcript_segments, list):
        try:
            segments = [TranscriptSegment(**segment) for segment in transcript_segments]
            return TranscriptSegment.segments_as_string(segments)
        except Exception as e:
            print(f"Error processing transcript segments: {e}")
            return ""

    return ""


def _compile_context_text(
    transcript: str, summary: str, memories: List[Dict[str, Any]], action_items: List[Dict[str, Any]]
) -> str:
    """Compile all context into a single searchable text"""

    context_parts = []

    # Add summary
    if summary:
        context_parts.append(f"CONVERSATION SUMMARY:\n{summary}")

    # Add transcript
    if transcript:
        context_parts.append(f"CONVERSATION TRANSCRIPT:\n{transcript}")

    # Add memories
    if memories:
        memories_text = "RELATED MEMORIES:\n"
        for memory in memories:
            title = memory.get('title', 'Untitled Memory')
            overview = memory.get('overview', '')
            memories_text += f"- {title}: {overview}\n"
        context_parts.append(memories_text)

    # Add action items
    if action_items:
        action_items_text = "ACTION ITEMS:\n"
        for item in action_items:
            description = item.get('description', '')
            status = "Completed" if item.get('completed', False) else "Pending"
            due_at = item.get('due_at')
            due_text = f" (Due: {due_at.strftime('%Y-%m-%d')})" if due_at else ""
            action_items_text += f"- [{status}] {description}{due_text}\n"
        context_parts.append(action_items_text)

    return "\n\n".join(context_parts)


def search_conversation_context(
    uid: str, conversation_id: str, query: str = "", include_memories: bool = True, include_action_items: bool = True
) -> Dict[str, Any]:
    """
    Search within conversation context.
    Since we're dealing with a single conversation, we return all relevant context.
    The query parameter can be used for future filtering if needed.
    """

    context = get_conversation_context(uid, conversation_id)

    # For now, return all context since it's scoped to one conversation
    # Future enhancement: could implement keyword filtering based on query

    result = {
        'context_text': context['context_text'],
        'transcript': context['transcript'],
        'summary': context['summary'],
        'conversation_title': context['conversation_title'],
        'conversation_id': conversation_id,
        'memories_found': context['memories'] if include_memories else [],
        'action_items_found': context['action_items'] if include_action_items else [],
        'total_context_length': len(context['context_text']),
    }

    print(f"Conversation context search returned {len(result['context_text'])} characters of context")
    return result


def get_conversation_summary_for_chat(uid: str, conversation_id: str) -> str:
    """Get a formatted summary of the conversation for chat context"""

    context = get_conversation_context(uid, conversation_id)

    summary_parts = []

    if context['summary']:
        summary_parts.append(f"Summary: {context['summary']}")

    if context['memories']:
        summary_parts.append(f"Related memories: {len(context['memories'])} items")

    if context['action_items']:
        pending_items = sum(1 for item in context['action_items'] if not item.get('completed', False))
        completed_items = len(context['action_items']) - pending_items
        summary_parts.append(f"Action items: {pending_items} pending, {completed_items} completed")

    transcript_length = len(context['transcript'])
    if transcript_length > 0:
        summary_parts.append(f"Transcript: {transcript_length} characters")

    return " | ".join(summary_parts) if summary_parts else "No additional context available"


def validate_conversation_context(uid: str, conversation_id: str) -> bool:
    """Validate that conversation has sufficient context for chat"""

    context = get_conversation_context(uid, conversation_id)

    # Check if we have at least some content
    has_transcript = bool(context['transcript'])
    has_summary = bool(context['summary'])
    has_memories = bool(context['memories'])
    has_action_items = bool(context['action_items'])

    # Conversation should have at least transcript or summary to be chatworthy
    return has_transcript or has_summary or has_memories or has_action_items
