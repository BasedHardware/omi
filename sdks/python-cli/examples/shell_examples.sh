#!/usr/bin/env bash
# omi-cli — runnable example snippets.
# Each block is self-contained. Pick what you need.

set -euo pipefail

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

# Interactive login (recommended — input is hidden, never lands in history):
#   omi auth login

# Headless / CI:
#   export OMI_API_KEY=omi_dev_...
#   omi auth status

# ---------------------------------------------------------------------------
# Memories
# ---------------------------------------------------------------------------

# List the 10 most recent:
omi memory list --limit 10

# Get just the IDs and content as JSON for further processing:
omi memory list --json --limit 50 | jq '.[] | {id, content}'

# Create a memory with a category and tags:
omi memory create "Wakes up at 6am most days" --category habits --tag morning --tag routine

# Update a memory's content:
omi memory update m_xyz --content "Wakes up at 6:30am most days"

# Delete (skipping the confirm prompt):
omi memory delete m_xyz --yes

# ---------------------------------------------------------------------------
# Conversations
# ---------------------------------------------------------------------------

# List with full transcripts:
omi conversation list --limit 5 --include-transcript

# Time-bounded query:
omi conversation list \
    --start-date 2026-04-01T00:00:00Z \
    --end-date 2026-04-26T00:00:00Z \
    --json | jq 'length'

# Create from raw text (stdin form):
echo "We agreed to ship the CLI on Friday." | omi conversation create --text - --text-source message

# Create from structured segments (file with {transcript_segments: [...]}):
omi conversation from-segments ./meeting_segments.json --source phone

# Mark discarded:
omi conversation update c_abc --discarded

# ---------------------------------------------------------------------------
# Action items
# ---------------------------------------------------------------------------

# All open items:
omi action-item list --open

# Filtered by date:
omi action-item list --open --start-date 2026-04-01T00:00:00Z

# Create with a due date:
omi action-item create "Renew domain" --due-at 2026-05-01T00:00:00Z

# Mark complete:
omi action-item complete a_xyz

# ---------------------------------------------------------------------------
# Goals
# ---------------------------------------------------------------------------

# Active goals (default):
omi goal list

# Including inactive:
omi goal list --include-inactive

# Create a numeric goal:
omi goal create "Drink 2L of water daily" --type numeric --target 2 --unit liters

# Update progress (shortcut):
omi goal progress g_xyz 1.5

# History over the last week:
omi goal history g_xyz --days 7
