# gmail_server.py
"""
Gmail MCP Server using FastMCP with direct Google API (no toolkit)
Install: pip install mcp google-auth google-auth-oauthlib google-api-python-client
"""

from mcp.server.fastmcp import FastMCP
import base64
from email.mime.text import MIMEText
from typing import Optional
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from pathlib import Path
import os

CREDS_DIR = Path(__file__).resolve().parent.parent / 'credentials'
TOKEN_PATH = CREDS_DIR / 'token.json'

# Initialize FastMCP server
mcp = FastMCP("gmail")

# Gmail API scopes
SCOPES = [
    'https://www.googleapis.com/auth/gmail.compose',
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.modify'
]

# Global Gmail service instance
_gmail_service = None


def get_gmail_service():
    """Initialize and return Gmail service (singleton pattern)"""
    global _gmail_service
    
    if _gmail_service is None:
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
        
        # Refresh token if expired
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            # Save refreshed token
            with open(str(TOKEN_PATH), 'w') as token:
                token.write(creds.to_json())
        
        _gmail_service = build('gmail', 'v1', credentials=creds)
    
    return _gmail_service


@mcp.tool()
def search_gmail(query: str, max_results: int = 10) -> str:
    """
    Search Gmail messages using Gmail search syntax.
    
    Args:
        query: Gmail search query (e.g., 'from:example@gmail.com', 'is:unread', 'subject:meeting')
        max_results: Maximum number of results to return (default: 10)
    
    Returns:
        Search results as formatted string with subject, from, and snippet
    """
    try:
        service = get_gmail_service()
        
        results = service.users().messages().list(
            userId='me',
            q=query,
            maxResults=max_results
        ).execute()
        
        messages = results.get('messages', [])
        
        if not messages:
            return "No messages found matching your query."
        
        email_list = []
        for msg in messages:
            message = service.users().messages().get(
                userId='me',
                id=msg['id'],
                format='metadata',
                metadataHeaders=['Subject', 'From', 'Date']
            ).execute()
            
            headers = message['payload']['headers']
            subject = next((h['value'] for h in headers if h['name'] == 'Subject'), 'No Subject')
            from_email = next((h['value'] for h in headers if h['name'] == 'From'), 'Unknown')
            date = next((h['value'] for h in headers if h['name'] == 'Date'), 'Unknown')
            snippet = message.get('snippet', '')
            message_id = msg['id']
            
            email_list.append(
                f"Message ID: {message_id}\n"
                f"Date: {date}\n"
                f"From: {from_email}\n"
                f"Subject: {subject}\n"
                f"Snippet: {snippet}\n"
            )
        
        return "\n" + "="*60 + "\n".join(email_list)
        
    except Exception as e:
        return f"❌ Error searching emails: {str(e)}"


@mcp.tool()
def get_gmail_message(message_id: str) -> str:
    """
    Get the full content of a specific Gmail message by ID.
    
    Args:
        message_id: The unique Gmail message ID
    
    Returns:
        Full message content including headers, body, and metadata
    """
    try:
        service = get_gmail_service()
        
        message = service.users().messages().get(
            userId='me',
            id=message_id,
            format='full'
        ).execute()
        
        headers = message['payload']['headers']
        subject = next((h['value'] for h in headers if h['name'] == 'Subject'), 'No Subject')
        from_email = next((h['value'] for h in headers if h['name'] == 'From'), 'Unknown')
        to_email = next((h['value'] for h in headers if h['name'] == 'To'), 'Unknown')
        date = next((h['value'] for h in headers if h['name'] == 'Date'), 'Unknown')
        
        # Get message body
        body = ""
        if 'parts' in message['payload']:
            for part in message['payload']['parts']:
                if part['mimeType'] == 'text/plain':
                    if 'data' in part['body']:
                        body = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8')
                        break
        else:
            if 'body' in message['payload'] and 'data' in message['payload']['body']:
                body = base64.urlsafe_b64decode(message['payload']['body']['data']).decode('utf-8')
        
        result = (
            f"Message ID: {message_id}\n"
            f"Date: {date}\n"
            f"From: {from_email}\n"
            f"To: {to_email}\n"
            f"Subject: {subject}\n"
            f"\n{'='*60}\n"
            f"Body:\n{body}\n"
            f"{'='*60}\n"
        )
        
        return result
        
    except Exception as e:
        return f"❌ Error getting message: {str(e)}"


@mcp.tool()
def send_gmail_message(to: str, subject: str, message: str, cc: Optional[str] = None, bcc: Optional[str] = None) -> str:
    """
    Send an email through Gmail.
    
    Args:
        to: Recipient email address (comma-separated for multiple)
        subject: Email subject line
        message: Email body content
        cc: CC recipients (optional, comma-separated)
        bcc: BCC recipients (optional, comma-separated)
    
    Returns:
        Confirmation message with sent email details
    """
    try:
        service = get_gmail_service()
        
        email_message = MIMEText(message)
        email_message['to'] = to
        email_message['subject'] = subject
        
        if cc:
            email_message['cc'] = cc
        if bcc:
            email_message['bcc'] = bcc
        
        raw_message = base64.urlsafe_b64encode(email_message.as_bytes()).decode('utf-8')
        sent_message = service.users().messages().send(
            userId='me',
            body={'raw': raw_message}
        ).execute()
        
        return f"✅ Email sent successfully!\nMessage ID: {sent_message['id']}\nTo: {to}\nSubject: {subject}"
        
    except Exception as e:
        return f"❌ Error sending email: {str(e)}"


@mcp.tool()
def create_gmail_draft(to: str, subject: str, message: str) -> str:
    """
    Create a draft email in Gmail (not sent automatically).
    
    Args:
        to: Recipient email address
        subject: Email subject line
        message: Email body content
    
    Returns:
        Confirmation with draft ID
    """
    try:
        service = get_gmail_service()
        
        email_message = MIMEText(message)
        email_message['to'] = to
        email_message['subject'] = subject
        
        raw_message = base64.urlsafe_b64encode(email_message.as_bytes()).decode('utf-8')
        draft = service.users().drafts().create(
            userId='me',
            body={'message': {'raw': raw_message}}
        ).execute()
        
        return f"✅ Draft created successfully!\nDraft ID: {draft['id']}\nTo: {to}\nSubject: {subject}"
        
    except Exception as e:
        return f"❌ Error creating draft: {str(e)}"


@mcp.tool()
def get_gmail_thread(thread_id: str) -> str:
    """
    Get an entire Gmail conversation thread by thread ID.
    
    Args:
        thread_id: The unique Gmail thread ID
    
    Returns:
        Complete thread with all messages in the conversation
    """
    try:
        service = get_gmail_service()
        
        thread = service.users().threads().get(
            userId='me',
            id=thread_id,
            format='full'
        ).execute()
        
        messages = thread.get('messages', [])
        
        if not messages:
            return "No messages found in this thread."
        
        thread_content = []
        thread_content.append(f"Thread ID: {thread_id}")
        thread_content.append(f"Total Messages: {len(messages)}\n")
        thread_content.append("="*60 + "\n")
        
        for idx, message in enumerate(messages, 1):
            headers = message['payload']['headers']
            subject = next((h['value'] for h in headers if h['name'] == 'Subject'), 'No Subject')
            from_email = next((h['value'] for h in headers if h['name'] == 'From'), 'Unknown')
            date = next((h['value'] for h in headers if h['name'] == 'Date'), 'Unknown')
            snippet = message.get('snippet', '')
            
            thread_content.append(
                f"Message {idx}:\n"
                f"Date: {date}\n"
                f"From: {from_email}\n"
                f"Subject: {subject}\n"
                f"Snippet: {snippet}\n"
            )
            thread_content.append("-"*60 + "\n")
        
        return "\n".join(thread_content)
        
    except Exception as e:
        return f"❌ Error getting thread: {str(e)}"


@mcp.tool()
def get_latest_gmail_messages(count: int = 5) -> str:
    """
    Get the latest emails from inbox.
    
    Args:
        count: Number of latest emails to retrieve (default: 5, max: 20)
    
    Returns:
        List of latest emails with details
    """
    try:
        service = get_gmail_service()
        
        # Limit to reasonable max
        count = min(count, 20)
        
        results = service.users().messages().list(
            userId='me',
            maxResults=count,
            labelIds=['INBOX']
        ).execute()
        
        messages = results.get('messages', [])
        
        if not messages:
            return "No messages found in inbox."
        
        email_list = []
        for msg in messages:
            message = service.users().messages().get(
                userId='me',
                id=msg['id'],
                format='metadata',
                metadataHeaders=['Subject', 'From', 'Date']
            ).execute()
            
            headers = message['payload']['headers']
            subject = next((h['value'] for h in headers if h['name'] == 'Subject'), 'No Subject')
            from_email = next((h['value'] for h in headers if h['name'] == 'From'), 'Unknown')
            date = next((h['value'] for h in headers if h['name'] == 'Date'), 'Unknown')
            snippet = message.get('snippet', '')
            message_id = msg['id']
            
            email_list.append(
                f"Message ID: {message_id}\n"
                f"Date: {date}\n"
                f"From: {from_email}\n"
                f"Subject: {subject}\n"
                f"Snippet: {snippet}\n"
            )
        
        return "\n" + "="*60 + "\n".join(email_list)
        
    except Exception as e:
        return f"❌ Error getting latest emails: {str(e)}"


if __name__ == "__main__":
    mcp.run(transport="stdio")