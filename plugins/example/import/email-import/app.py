"""
Email Importer Plugin for OMI

This Flask application provides a simple interface for fetching email
messages from an IMAP mailbox, extracting actionable memories and
submitting them to the OMI API.  It is inspired by the existing
manual‑import plugin but tailored specifically for email integration.

Endpoints:

* `GET /` – Serves the frontend interface (index.html).
* `POST /fetch-emails` – Connects to an IMAP server and returns the
  most recent messages.  If the `SAMPLE_EMAIL_FILE` environment
  variable is set, the server reads messages from a local .eml file
  instead of connecting to IMAP (useful for offline testing).
* `POST /submit-memories` – Takes raw email bodies and a user ID,
  extracts concise memories from each email and optionally submits
  them to the OMI API.  Responses include per‑memory status codes.

Environment variables read by this module:

* `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_USER`, `EMAIL_PASS` – Default
  IMAP credentials.  These may be overridden in the POST payload.
* `SAMPLE_EMAIL_FILE` – Path to a `.eml` file to use when no IMAP
  connection is configured (for testing without network access).
* `APP_ID`, `API_KEY` – OMI integration credentials.  If either is
  missing the plugin will still extract memories but will not send
  them to the API.
* `OMI_API_URL` – Base URL for the OMI API (defaults to
  `https://api.omi.me`).
"""

import os
import re
import time
import json
import imaplib
import email
from email.policy import default as default_policy
from flask import Flask, request, jsonify, send_from_directory
import requests
from dotenv import load_dotenv

# Load environment variables from .env if present
load_dotenv()

app = Flask(__name__)

# Default configuration from environment
DEFAULT_EMAIL_HOST = os.getenv('EMAIL_HOST')
DEFAULT_EMAIL_PORT = int(os.getenv('EMAIL_PORT', '993'))
DEFAULT_EMAIL_USER = os.getenv('EMAIL_USER')
DEFAULT_EMAIL_PASS = os.getenv('EMAIL_PASS')
SAMPLE_EMAIL_FILE = os.getenv('SAMPLE_EMAIL_FILE')

APP_ID = os.getenv('APP_ID')
API_KEY = os.getenv('API_KEY')
OMI_API_URL = os.getenv('OMI_API_URL', 'https://api.omi.me')

# Maximum length for a single memory (mirrors manual‑import)
MAX_MEMORY_LENGTH = 500


@app.route('/')
def index():
    """Serve the frontend interface."""
    return send_from_directory('.', 'index.html')


@app.route('/fetch-emails', methods=['POST'])
def fetch_emails():
    """
    Fetch the latest email messages from an IMAP mailbox or a local .eml file.

    The request JSON may contain the following keys:

    * `host` – IMAP server hostname (falls back to `EMAIL_HOST`).
    * `port` – IMAP server port (defaults to 993 for SSL).
    * `username` – IMAP login username (falls back to `EMAIL_USER`).
    * `password` – IMAP login password (falls back to `EMAIL_PASS`).
    * `count` – Number of messages to fetch (defaults to 5).  Maximum 20.

    Returns a JSON array of objects with `subject` and `body` keys.
    """
    try:
        data = request.get_json() or {}

        host = data.get('host') or DEFAULT_EMAIL_HOST
        port = int(data.get('port') or DEFAULT_EMAIL_PORT)
        username = data.get('username') or DEFAULT_EMAIL_USER
        password = data.get('password') or DEFAULT_EMAIL_PASS
        count = int(data.get('count', 5))
        if count < 1:
            count = 1
        if count > 20:
            count = 20  # limit to avoid huge responses

        messages = []

        # Use local sample file if provided and no host/user specified
        if SAMPLE_EMAIL_FILE and not (host and username and password):
            if not os.path.isfile(SAMPLE_EMAIL_FILE):
                return jsonify({"error": f"Sample file {SAMPLE_EMAIL_FILE} not found"}), 400
            with open(SAMPLE_EMAIL_FILE, 'rb') as f:
                raw = f.read()
            msg = email.message_from_bytes(raw, policy=default_policy)
            messages.append({
                'subject': msg.get('Subject', '(No subject)'),
                'body': extract_text_from_email(msg)
            })
            return jsonify({"messages": messages, "sample": True})

        # Validate IMAP credentials
        if not all([host, username, password]):
            return jsonify({"error": "Missing IMAP credentials and no sample file specified"}), 400

        # Connect and fetch messages
        try:
            imap = imaplib.IMAP4_SSL(host, port) if port == 993 else imaplib.IMAP4(host, port)
            imap.login(username, password)
            imap.select('INBOX')

            # Search for all messages, then fetch the latest ones
            typ, data_ids = imap.search(None, 'ALL')
            if typ != 'OK':
                raise Exception('Failed to search mailbox')
            ids = data_ids[0].split()
            # Get the last `count` message IDs
            ids = ids[-count:]

            for msg_id in reversed(ids):  # reverse to get newest first
                typ, msg_data = imap.fetch(msg_id, '(RFC822)')
                if typ != 'OK':
                    continue
                raw = msg_data[0][1]
                msg = email.message_from_bytes(raw, policy=default_policy)
                messages.append({
                    'subject': msg.get('Subject', '(No subject)'),
                    'body': extract_text_from_email(msg)
                })
            imap.close()
            imap.logout()
        except Exception as e:
            return jsonify({"error": f"IMAP error: {str(e)}"}), 500

        return jsonify({"messages": messages})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


def extract_text_from_email(msg):
    """
    Extract the plain‑text body from an `email.message.EmailMessage`.  If no
    text part is found, attempts to extract from HTML and strip tags.  As
    a fallback returns an empty string.
    """
    # Prefer text/plain parts
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get('Content-Disposition'))
            if content_type == 'text/plain' and 'attachment' not in content_disposition:
                try:
                    return part.get_content().strip()
                except Exception:
                    return part.get_payload(decode=True).decode(part.get_content_charset('utf-8'), errors='replace').strip()
        # If no plain text, try HTML
        for part in msg.walk():
            if part.get_content_type() == 'text/html':
                html_content = part.get_content()
                return strip_html_tags(html_content).strip()
    else:
        if msg.get_content_type() == 'text/plain':
            return msg.get_content().strip()
        if msg.get_content_type() == 'text/html':
            return strip_html_tags(msg.get_content()).strip()
    return ''


def strip_html_tags(html):
    """
    Very simple HTML tag stripper.  For more complex email bodies consider
    using beautifulsoup4, but to avoid external dependencies we keep
    this implementation minimal.
    """
    # Remove script and style content
    html = re.sub(r'<(script|style).*?>.*?</\1>', '', html, flags=re.DOTALL | re.IGNORECASE)
    # Remove all remaining tags
    text = re.sub(r'<[^>]+>', '', html)
    # Replace HTML entities
    text = (text.replace('&nbsp;', ' ').replace('&amp;', '&')
                .replace('&lt;', '<').replace('&gt;', '>'))
    # Collapse whitespace
    return re.sub(r'\s+', ' ', text)


def extract_memories_from_text(body):
    """
    Extract a list of memory strings from a raw email body.  The
    extraction is rule based:

    * Lines that begin with typical action prefixes (e.g. `TODO`, `Action`,
      bullet points like `-`, `•`, `*` or numbered lists) become separate
      memories.
    * If no such lines exist, the entire body (up to 500 characters) is
      returned as a single memory.
    * Each memory is truncated at `MAX_MEMORY_LENGTH` characters.
    """
    memories = []
    lines = body.splitlines()
    action_pattern = re.compile(r'^\s*(?:\d+[\).]|[-*\u2022]|todo|action[:\-])', re.IGNORECASE)

    for line in lines:
        cleaned = line.strip()
        if not cleaned:
            continue
        if action_pattern.match(cleaned):
            # Strip the prefix and any colon/parentheses
            text = re.sub(r'^\s*(?:\d+[\).]|[-*\u2022]|todo|action[:\-])\s*', '', cleaned, flags=re.IGNORECASE)
            if text:
                # Remove lingering TODO or Action prefixes
                text = re.sub(r'^\s*(?:todo|action)[:\-]\s*', '', text, flags=re.IGNORECASE)
                memories.append(text[:MAX_MEMORY_LENGTH])

    # Fallback: use the whole body if no memories extracted
    if not memories and body:
        truncated = body.strip()[:MAX_MEMORY_LENGTH]
        memories.append(truncated)

    return memories[:5]  # limit to at most 5 memories per email


@app.route('/submit-memories', methods=['POST'])
def submit_memories():
    """
    Extract memories from raw email bodies and optionally submit them
    to the OMI API.  The request JSON must include:

    * `uid` – User ID to assign the memories to.
    * `messages` – List of strings (email bodies) to process.
    * `use_api` – Optional boolean; if false, skip sending to OMI even
      when API credentials are present.

    Returns JSON indicating success and a list of per‑memory results.
    """
    try:
        data = request.get_json() or {}
        uid = data.get('uid')
        raw_messages = data.get('messages') or []
        use_api = data.get('use_api', True)

        if not uid:
            return jsonify({"error": "Missing 'uid' in request"}), 400
        if not raw_messages:
            return jsonify({"error": "No messages provided"}), 400

        all_memories = []
        for body in raw_messages:
            memories = extract_memories_from_text(body)
            all_memories.extend(memories)

        # Prepare results container
        results = []
        success_count = 0
        error_count = 0

        # Determine if we can call the API
        api_available = APP_ID and API_KEY and use_api

        for memory in all_memories:
            # Ensure memory not empty and within max length
            mem = memory.strip()[:MAX_MEMORY_LENGTH]
            if not mem:
                continue

            result = {
                'memory': mem
            }

            if api_available:
                # Construct the endpoint
                endpoint = f"{OMI_API_URL}/v2/integrations/{APP_ID}/user/facts?uid={uid}"
                headers = {
                    'Authorization': f'Bearer {API_KEY}',
                    'Content-Type': 'application/json'
                }
                payload = {
                    'text': mem,
                    'text_source': 'email',
                    'text_source_spec': 'import'
                }
                try:
                    resp = requests.post(endpoint, headers=headers, data=json.dumps(payload))
                    result['status_code'] = resp.status_code
                    result['success'] = resp.status_code == 200
                    if resp.status_code == 200:
                        success_count += 1
                    else:
                        error_count += 1
                        result['error'] = resp.text
                except Exception as e:
                    result['status_code'] = None
                    result['success'] = False
                    result['error'] = str(e)
                    error_count += 1
            else:
                # API not available: simulate success
                result['status_code'] = None
                result['success'] = False
                result['error'] = 'OMI API credentials not configured or API disabled'
                error_count += 1

            results.append(result)

        all_success = (error_count == 0)
        return jsonify({
            'success': all_success,
            'total_memories': len(all_memories),
            'success_count': success_count,
            'error_count': error_count,
            'results': results,
            'api_used': api_available
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    port = int(os.getenv('PORT', '5002'))
    print("Starting Email Importer server...")
    print(f" Listening on http://localhost:{port}")
    if APP_ID and API_KEY:
        print(f" OMI API configured: App ID {APP_ID}")
    else:
        print(" Warning: OMI API credentials not set – memories will not be submitted")
    app.run(host='0.0.0.0', port=port, debug=True)
