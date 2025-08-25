# Email Importer Plugin

**Status:** Prototype plugin for importing emails into OMI.  
**Bounty:** Implements issue #1895 (Import data from email) by providing a self‑contained Python/Flask integration plugin.  

## Overview

This plugin demonstrates how to fetch email messages from an IMAP mailbox, extract actionable “memories” from each message and submit them to the OMI API.  
It follows the structure of the existing `manual‑import` plugin but adapts it to work with emails instead of arbitrary text.

### Features

* Connects to any standard IMAP server (e.g. Gmail, Outlook, ProtonMail).  
* Fetches the most recent N messages from the inbox and displays their subject and plain‑text body.  
* Allows the user to select which messages to import.  
* Extracts concise “memory” summaries from each selected message using a simple rule‑based approach (e.g. looks for lines beginning with `TODO`, `Action:`, bullet points or numbered lists).  
* Submits each extracted memory to the OMI API as a fact (requires an OMI App ID and private key).  
* Works offline with local `.eml` files for testing purposes when an IMAP connection is not available.

## Quick Start

1. **Install dependencies**

   ```bash
   # Within the email‑import directory
   pip install -r requirements.txt
   ```

2. **Prepare environment variables**

   Create a `.env` file in this directory or set the variables in your shell:

   ```bash
   # IMAP connection details
   EMAIL_HOST=imap.example.com
   EMAIL_PORT=993
   EMAIL_USER=your_email@example.com
   EMAIL_PASS=your_password

   # Optional: fallback to a local .eml file for testing
   SAMPLE_EMAIL_FILE=sample.eml

   # OMI API credentials
   APP_ID=YOUR_APP_ID
   API_KEY=YOUR_API_KEY
   # Base URL for the OMI API (defaults to https://api.omi.me)
   OMI_API_URL=https://api.omi.me
   ```

3. **Run the server**

   ```bash
   python app.py
   ```

   The plugin will start a Flask server on port 5002 by default.  
   Open your browser to `http://localhost:5002/?uid=YOUR_USER_ID` to access the UI.

4. **Fetch emails and submit memories**

   * Enter your IMAP credentials, number of messages to fetch and click **Fetch Emails**.  
   * Select one or more messages to import and click **Extract & Submit**.  
   * The plugin will display extracted memories and attempt to post them to the OMI API.  
   * If OMI credentials are not provided the memories will still be displayed but not submitted.

## How it Works

* The backend (`app.py`) exposes three endpoints:

  * `GET /` – serves the `index.html` UI.
  * `POST /fetch-emails` – logs into the IMAP server, fetches the requested number of messages, parses the subject and body (preferring plain‑text), and returns them as JSON.  If `SAMPLE_EMAIL_FILE` is set the message is read from that file instead of connecting to a remote server (useful for offline testing).
  * `POST /submit-memories` – takes a list of raw email bodies and a user ID, extracts memories with a rule‑based parser and, if OMI credentials are configured, posts each memory to the OMI API.  It returns a success flag and per‑memory status codes.

* The frontend (`index.html`) is a lightweight single‑page application that collects IMAP credentials from the user, calls the backend to fetch messages, allows selection of messages and then submits the selected contents for extraction and upload.

* **Memory extraction** uses a simple heuristic: lines beginning with common action prefixes (`TODO`, `Action:`, `•`, `-`, numbers) are treated as separate memories.  If none are found the entire email body (truncated to 500 characters) is used as a single memory.  This rule‑based approach avoids the need for OpenAI API keys but can be extended with AI in the future.

## Limitations & Next Steps

* OAuth–based providers (like Gmail) may require an application password or OAuth token.  To keep this example simple, the plugin uses plain IMAP authentication.  Advanced implementations should integrate OAuth flows and token refresh.
* HTML‑only emails are converted to plain text using Python’s `email` module; some formatting may be lost.  Consider using a library like **beautifulsoup4** for more robust HTML parsing if needed.
* At present there is no paging or stateful sync – each fetch loads the N latest messages.  A production‑ready plugin should remember which messages have already been imported and only process new ones.

This plugin is provided as a starting point for the email import bounty.  Feel free to extend and refine it to meet your personal needs or to contribute back improvements to the OMI ecosystem!
