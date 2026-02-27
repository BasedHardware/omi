---
name: sentry-triage
description: "Process Sentry feedback tasks and user bug reports. Use when the prompt starts with '# Task' and contains '[Sentry Feedback]', or when triaging a Sentry issue ID (OMI-COMPUTER-XXX). Handles: parsing the task, fetching Sentry event details, looking up the user, investigating code, and drafting a response."
---

# Sentry Triage

## Overview

Processes structured Sentry feedback tasks that arrive in the format `# Task: [Sentry Feedback] OMI-COMPUTER-XXX: description`. Runs a standard investigation pipeline: parse task, fetch event data, look up user, search code, diagnose, fix, and notify.

## Config

- **Sentry org**: `mediar-n5`
- **Sentry project**: `omi-computer`
- **Issue ID format**: `OMI-COMPUTER-XXX` (XXX is base-36 short ID)
- **Auth**: `source .env` in repo root for `$SENTRY_AUTH_TOKEN`

## Workflow

### Step 1: Parse the Task

Extract from the task body:
- **Sentry issue ID**: e.g. `OMI-COMPUTER-14Z`
- **User email** (if provided)
- **Description / crash summary**
- **Category** (crash, UI freeze, permission error, audio issue, etc.)
- **Priority** (from task metadata)

### Step 2: Resolve the Numeric Issue ID

The API requires the numeric ID, not the short ID. Look it up:

```bash
source .env && curl -s -H "Authorization: Bearer $SENTRY_AUTH_TOKEN" \
  "https://sentry.io/api/0/projects/mediar-n5/omi-computer/issues/?query=OMI-COMPUTER-XXX" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(d[0]['id']) if d else print('NOT FOUND')"
```

### Step 3: Check If Already Resolved

Before deep investigation, check the issue status. If resolved in a newer version, note it and skip to Step 8.

```bash
source .env && curl -s -H "Authorization: Bearer $SENTRY_AUTH_TOKEN" \
  "https://sentry.io/api/0/issues/{NUMERIC_ID}/" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'Status: {d[\"status\"]}  Version: {d.get(\"firstRelease\",{}).get(\"version\",\"?\")} -> {d.get(\"lastRelease\",{}).get(\"version\",\"?\")}')"
```

### Step 4: Fetch Sentry Event Details

Get the latest event with full stack trace:

```bash
source .env && curl -s -H "Authorization: Bearer $SENTRY_AUTH_TOKEN" \
  "https://sentry.io/api/0/issues/{NUMERIC_ID}/events/latest/"
```

Key fields to extract: `exception.values[].stacktrace.frames[]` (file, function, lineno), `contexts` (OS, device, app version), `tags`.

### Step 5: Get User Impact

```bash
source .env && curl -s -H "Authorization: Bearer $SENTRY_AUTH_TOKEN" \
  "https://sentry.io/api/0/issues/{NUMERIC_ID}/tags/user/"
```

This shows how many users are affected and who they are.

### Step 6: Look Up User (if email available)

Run the user-logs skill for full crash history:

```bash
./scripts/sentry-logs.sh <email>
```

This gives additional context on whether this user has a pattern of crashes or if this is isolated.

### Step 7: Investigate Code

1. **Search codebase** for the crashing file paths and function names from the stack trace
2. **Check recent changes** on affected files:
   ```bash
   git log --oneline --since="1 week ago" -- <file>
   ```
3. **Read the crashing code** at the specific line numbers from the stack trace
4. **Diagnose root cause** and determine if a fix is straightforward

### Step 8: Fix or Document

- If the fix is straightforward: implement it, do NOT build/run (let user test)
- If the fix is complex: document the root cause, proposed solution, and any risks
- If already fixed in a newer version: note which version contains the fix

### Step 9: Notify User

If a user email is available and meaningful results exist, use the omi-email skill:

```bash
node ../omi-analytics/scripts/send-email.js \
  --to "<user-email>" \
  --subject "Re: OMI crash report" \
  --body "<what was found, what was fixed, next steps like 'update the app'>"
```

Write as Matt, keep it casual and concise. The user already has context from submitting the report.

## Common Categories

| Category | Typical Root Cause | Where to Look |
|----------|-------------------|---------------|
| Crash on delete | Force-unwrap on nil after deletion | Conversation/memory deletion handlers |
| UI freeze | Main thread blocking | Audio processing, network calls on main thread |
| Permission errors | Missing entitlements or user denial | Microphone/accessibility/screen recording permissions |
| Audio issues | Device switching, sample rate mismatch | AudioManager, recording pipeline |
