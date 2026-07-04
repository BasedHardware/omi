"""
Tools for accessing Gmail messages.
"""

import base64
import traceback
from email.utils import parsedate_to_datetime
from typing import Any, Dict, List, Optional, cast

from langchain_core.tools import tool  # type: ignore[reportUnknownVariableType]  # langchain @tool decorator partially typed
from langchain_core.runnables import RunnableConfig

from utils.executors import db_executor, run_blocking
from utils.retrieval.tools.integration_base import (
    ensure_capped,
    prepare_access,
    retry_on_auth_async,
)

# Import shared Google utilities
from utils.retrieval.tools.google_utils import refresh_google_token, google_api_request
import logging

logger = logging.getLogger(__name__)


async def get_gmail_messages(
    access_token: str,
    query: Optional[str] = None,
    max_results: int = 10,
    label_ids: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Fetch messages from Gmail API.

    Args:
        access_token: Google access token (from google_calendar integration)
        query: Optional Gmail search query (e.g., "from:example@gmail.com", "subject:meeting")
        max_results: Maximum number of messages to return
        label_ids: Optional list of label IDs to filter by (e.g., ['INBOX', 'UNREAD'])

    Returns:
        List of message metadata
    """
    params: Dict[str, Any] = {
        'maxResults': min(max_results, 50),  # Gmail API limit is 50
    }

    if query:
        params['q'] = query

    # Gmail API expects labelIds as a comma-separated string
    if label_ids:
        params['labelIds'] = label_ids

    message_ids: List[Any] = []
    page_token = None

    while True:
        page_params = dict(params)
        if page_token:
            page_params['pageToken'] = page_token

        data = await google_api_request(
            "GET",
            'https://www.googleapis.com/gmail/v1/users/me/messages',
            access_token,
            params=page_params,
        )

        ids = [msg['id'] for msg in data.get('messages', [])]
        message_ids.extend(ids)

        if len(message_ids) >= max_results:
            message_ids = message_ids[:max_results]
            break

        page_token = data.get('nextPageToken')
        if not page_token:
            break

    messages: List[Dict[str, Any]] = []
    for msg_id in message_ids:
        msg_data = await google_api_request(
            "GET",
            f'https://www.googleapis.com/gmail/v1/users/me/messages/{msg_id}',
            access_token,
            params={'format': 'full'},
        )
        messages.append(msg_data)

    return messages


def parse_gmail_message(message: Dict[str, Any]) -> Dict[str, Any]:
    """
    Parse a Gmail message object into a readable format.

    Args:
        message: Gmail API message object

    Returns:
        Parsed message dict with subject, from, to, date, snippet, body
    """
    payload = message.get('payload', {})
    headers = payload.get('headers', [])

    # Extract headers
    header_dict = {h['name']: h['value'] for h in headers}

    # Extract body
    body_text = ''
    if 'parts' in payload:
        # Multipart message
        for part in payload['parts']:
            if part.get('mimeType') == 'text/plain':
                data = part.get('body', {}).get('data', '')
                if data:
                    body_text = base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
                    break
            elif part.get('mimeType') == 'text/html':
                # Fallback to HTML if plain text not available
                data = part.get('body', {}).get('data', '')
                if data:
                    body_text = base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
                    break
    else:
        # Single part message
        if payload.get('mimeType') == 'text/plain':
            data = payload.get('body', {}).get('data', '')
            if data:
                body_text = base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
    date_str: str = header_dict.get('Date', '')
    # Parse date
    date_parsed = None
    if date_str:
        try:
            date_parsed = parsedate_to_datetime(date_str)
        except Exception:
            pass

    return {
        'id': message.get('id'),
        'threadId': message.get('threadId'),
        'subject': header_dict.get('Subject', '(No subject)'),
        'from': header_dict.get('From', 'Unknown'),
        'to': header_dict.get('To', 'Unknown'),
        'date': date_parsed.isoformat() if date_parsed else date_str,
        'snippet': message.get('snippet', ''),
        'body': body_text,
    }


@tool
async def get_gmail_messages_tool(
    query: Optional[str] = None,
    max_results: int = 10,
    label: Optional[str] = None,
    config: RunnableConfig = None,  # type: ignore[reportAssignmentType]  # langchain injects at runtime; None default for direct calls
) -> str:
    """
    Retrieve emails from the user's Gmail inbox.

    Use this tool when:
    - User asks "show me my emails" or "what emails do I have?"
    - User asks about emails from a specific person (e.g., "emails from John")
    - User asks about emails with a specific subject (e.g., "emails about meeting")
    - User asks "do I have any unread emails?" or "show me unread emails"
    - User mentions checking their email or inbox
    - **ALWAYS use this tool when the user asks about their Gmail or emails**

    Query examples:
    - "from:example@gmail.com" - emails from a specific sender
    - "subject:meeting" - emails with "meeting" in subject
    - "is:unread" - unread emails
    - "is:read" - read emails
    - "has:attachment" - emails with attachments
    - "after:2024/1/1" - emails after a date
    - "before:2024/1/31" - emails before a date
    - "from:john subject:meeting" - combination of filters

    Label examples:
    - "INBOX" - inbox emails
    - "SENT" - sent emails
    - "DRAFT" - draft emails
    - "UNREAD" - unread emails (will be converted to "is:unread" query)

    Args:
        query: Optional Gmail search query (e.g., "from:example@gmail.com", "subject:meeting", "is:unread")
        max_results: Maximum number of emails to return (default: 10, max: 50)
        label: Optional label to filter by (e.g., "INBOX", "SENT", "DRAFT"). "UNREAD" is handled as a query operator. Can be combined with query.

    Returns:
        Formatted list of emails with their details.
    """
    uid, integration, access_token, access_err = await run_blocking(
        db_executor,
        prepare_access,
        cast(Optional[Dict[str, Any]], config),
        'google_calendar',
        'Gmail',
        'Gmail is not connected. Please connect your Google account from settings to view your emails.',
        'Gmail access token not found. Please reconnect your Google account from settings.',
        'Error checking Gmail connection',
    )
    if access_err:
        return access_err
    assert uid is not None
    assert integration is not None
    assert access_token is not None

    try:
        max_results = ensure_capped(max_results, 50, "⚠️ get_gmail_messages_tool - max_results capped from {} to {}")

        # Build label_ids if label is provided
        # Note: "UNREAD" is a search operator, not a label, so handle it in query
        label_ids = None
        if label:
            label_upper = label.upper()
            # If label is UNREAD, add it to query instead
            if label_upper == 'UNREAD':
                if query:
                    query = f"{query} is:unread"
                else:
                    query = "is:unread"
            else:
                # Valid labels: INBOX, SENT, DRAFT, TRASH, SPAM, etc.
                label_ids = [label_upper]

        # Fetch messages
        messages, err = await retry_on_auth_async(
            get_gmail_messages,
            {
                'access_token': access_token,
                'query': query,
                'max_results': max_results,
                'label_ids': label_ids,
            },
            refresh_google_token,
            uid,
            integration,
            "Google authentication expired. Please reconnect your Google account from settings.",
            (
                "Authentication failed",
                "401",
                "token may be expired",
                "Google API error 401",
            ),
        )
        if err:
            return err

        if not messages:
            query_info = f" matching '{query}'" if query else ""
            label_info = f" in {label}" if label else ""
            return f"No emails found{query_info}{label_info}."

        # Format messages
        result = f"Gmail Messages ({len(messages)} found):\n\n"

        for i, message in enumerate(messages, 1):
            parsed = parse_gmail_message(message)

            result += f"{i}. {parsed['subject']}\n"
            result += f"   From: {parsed['from']}\n"
            result += f"   To: {parsed['to']}\n"
            if parsed['date']:
                result += f"   Date: {parsed['date']}\n"
            if parsed['snippet']:
                snippet = parsed['snippet'][:200] + '...' if len(parsed['snippet']) > 200 else parsed['snippet']
                result += f"   Preview: {snippet}\n"
            result += "\n"

        return result.strip()
    except Exception as e:
        logger.error(f"❌ Unexpected error in get_gmail_messages_tool: {e}")
        traceback.print_exc()
        return f"Unexpected error fetching Gmail messages: {str(e)}"
