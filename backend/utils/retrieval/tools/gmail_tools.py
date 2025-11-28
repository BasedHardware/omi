"""
Tools for accessing Gmail messages.
"""

import contextvars
from datetime import datetime, timedelta, timezone
from typing import Optional, List

from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig

import database.users as users_db
import requests

# Import shared Google utilities
from utils.retrieval.tools.google_utils import refresh_google_token

# Import the context variable from agentic module
try:
    from utils.retrieval.agentic import agent_config_context
except ImportError:
    # Fallback if import fails
    agent_config_context = contextvars.ContextVar('agent_config', default=None)


def get_gmail_messages(
    access_token: str,
    query: Optional[str] = None,
    max_results: int = 10,
    label_ids: Optional[List[str]] = None,
) -> List[dict]:
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
    params = {
        'maxResults': min(max_results, 50),  # Gmail API limit is 50
    }

    if query:
        params['q'] = query

    # Gmail API expects labelIds as a comma-separated string
    if label_ids:
        params['labelIds'] = ','.join(label_ids)

    print(f"📧 Calling Gmail API with query: {query}, max_results: {max_results}")

    try:
        response = requests.get(
            'https://www.googleapis.com/gmail/v1/users/me/messages',
            headers={'Authorization': f'Bearer {access_token}'},
            params=params,
            timeout=10.0,
        )

        print(f"📧 Gmail API response status: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            message_ids = [msg['id'] for msg in data.get('messages', [])]
            print(f"📧 Gmail API returned {len(message_ids)} message IDs")

            # Fetch full message details for each message ID
            messages = []
            for msg_id in message_ids[:max_results]:
                try:
                    msg_response = requests.get(
                        f'https://www.googleapis.com/gmail/v1/users/me/messages/{msg_id}',
                        headers={'Authorization': f'Bearer {access_token}'},
                        params={'format': 'full'},
                        timeout=10.0,
                    )

                    if msg_response.status_code == 200:
                        messages.append(msg_response.json())
                    else:
                        print(f"⚠️ Failed to fetch message {msg_id}: {msg_response.status_code}")
                except Exception as e:
                    print(f"⚠️ Error fetching message {msg_id}: {e}")

            return messages
        elif response.status_code == 401:
            print(f"❌ Gmail API 401 - token expired")
            raise Exception("Authentication failed - token may be expired")
        else:
            error_body = response.text[:200] if response.text else "No error body"
            print(f"❌ Gmail API error {response.status_code}: {error_body}")
            raise Exception(f"Gmail API error: {response.status_code} - {error_body}")
    except requests.exceptions.RequestException as e:
        print(f"❌ Network error fetching Gmail messages: {e}")
        raise
    except Exception as e:
        print(f"❌ Error fetching Gmail messages: {e}")
        raise


def parse_gmail_message(message: dict) -> dict:
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
                    import base64

                    body_text = base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
                    break
            elif part.get('mimeType') == 'text/html':
                # Fallback to HTML if plain text not available
                data = part.get('body', {}).get('data', '')
                if data:
                    import base64

                    body_text = base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
                    break
    else:
        # Single part message
        if payload.get('mimeType') == 'text/plain':
            data = payload.get('body', {}).get('data', '')
            if data:
                import base64

                body_text = base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')

    # Parse date
    date_str = header_dict.get('Date', '')
    date_parsed = None
    if date_str:
        try:
            from email.utils import parsedate_to_datetime

            date_parsed = parsedate_to_datetime(date_str)
        except:
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
def get_gmail_messages_tool(
    query: Optional[str] = None,
    max_results: int = 10,
    label: Optional[str] = None,
    config: RunnableConfig = None,
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
    print(f"🔧 get_gmail_messages_tool called - query: {query}, " f"max_results: {max_results}, label: {label}")

    # Get config from parameter or context variable
    if config is None:
        try:
            config = agent_config_context.get()
            if config:
                print(f"🔧 get_gmail_messages_tool - got config from context variable")
        except LookupError:
            print(f"❌ get_gmail_messages_tool - config not found in context variable")
            config = None

    if config is None:
        print(f"❌ get_gmail_messages_tool - config is None")
        return "Error: Configuration not available"

    try:
        uid = config['configurable'].get('user_id')
    except (KeyError, TypeError) as e:
        print(
            f"❌ get_gmail_messages_tool - error accessing config: {e}, config keys: {list(config.keys()) if isinstance(config, dict) else 'not a dict'}"
        )
        return "Error: Configuration not available"

    if not uid:
        print(f"❌ get_gmail_messages_tool - no user_id in config")
        return "Error: User ID not found in configuration"
    print(f"✅ get_gmail_messages_tool - uid: {uid}, max_results: {max_results}")

    try:
        # Cap at 50 per call
        if max_results > 50:
            print(f"⚠️ get_gmail_messages_tool - max_results capped from {max_results} to 50")
            max_results = 50

        # Check if user has Google Calendar connected (which includes Gmail access)
        print(f"📧 Checking Google connection for user {uid}...")
        try:
            integration = users_db.get_integration(uid, 'google_calendar')
            print(f"📧 Integration data retrieved: {integration is not None}")
            if integration:
                print(f"📧 Integration connected status: {integration.get('connected')}")
                print(f"📧 Integration has access_token: {bool(integration.get('access_token'))}")
            else:
                print(f"❌ No integration found for user {uid}")
                return "Google is not connected. Please connect your Google account from settings to view your emails."
        except Exception as e:
            print(f"❌ Error checking Google integration: {e}")
            import traceback

            traceback.print_exc()
            return f"Error checking Google connection: {str(e)}"

        if not integration or not integration.get('connected'):
            print(f"❌ Google not connected for user {uid}")
            return "Google is not connected. Please connect your Google account from settings to view your emails."

        access_token = integration.get('access_token')
        if not access_token:
            print(f"❌ No access token found in integration data")
            return "Google access token not found. Please reconnect your Google account from settings."

        print(f"✅ Access token found, length: {len(access_token)}")

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
        try:
            messages = get_gmail_messages(
                access_token=access_token,
                query=query,
                max_results=max_results,
                label_ids=label_ids,
            )

            print(f"✅ Successfully fetched {len(messages)} messages")
        except Exception as e:
            error_msg = str(e)
            print(f"❌ Error fetching Gmail messages: {error_msg}")
            import traceback

            traceback.print_exc()

            # Try to refresh token if authentication failed
            if "Authentication failed" in error_msg or "401" in error_msg:
                print(f"🔄 Attempting to refresh Google token...")
                new_token = refresh_google_token(uid, integration)
                if new_token:
                    print(f"✅ Token refreshed, retrying...")
                    try:
                        messages = get_gmail_messages(
                            access_token=new_token,
                            query=query,
                            max_results=max_results,
                            label_ids=label_ids,
                        )
                        print(f"✅ Successfully fetched {len(messages)} messages after token refresh")
                    except Exception as retry_error:
                        print(f"❌ Error after token refresh: {str(retry_error)}")
                        import traceback

                        traceback.print_exc()
                        return f"Error fetching Gmail messages: {str(retry_error)}"
                else:
                    print(f"❌ Token refresh failed")
                    return "Google authentication expired. Please reconnect your Google account from settings."
            else:
                print(f"❌ Non-auth error: {error_msg}")
                return f"Error fetching Gmail messages: {error_msg}"

        messages_count = len(messages) if messages else 0
        print(f"📊 get_gmail_messages_tool - found {messages_count} messages")

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
        print(f"❌ Unexpected error in get_gmail_messages_tool: {e}")
        import traceback

        traceback.print_exc()
        return f"Unexpected error fetching Gmail messages: {str(e)}"
