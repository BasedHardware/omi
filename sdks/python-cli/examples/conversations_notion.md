# conversations_to_notion.py

A tiny helper script that turns a **conversation log** (JSON) into a list of
**Notion API‑compatible block objects**.  
The generated payload can be sent directly to the Notion `blocks` endpoint
(e.g., via `requests.post(..., json=payload)`).

## Why you might need this

* You have a chatbot, meeting‑notes exporter, or any system that produces a
  chronological list of speaker utterances.
* You want to push that transcript into a Notion page without writing a full
  integration yourself.
* The script handles the low‑level Notion block format for you and writes the
  result atomically, so you can safely chain it in CI pipelines.

## Input format

The script expects a JSON file that contains a **list** of conversation entries.
Each entry must have at least a `text` field and may optionally include:

| Key            | Type               | Description                                   |
|----------------|--------------------|-----------------------------------------------|
| `speaker`      | `string` (optional) | Name of the person speaking.                  |
| `text`         | `string` (required) | The utterance itself.                         |
| `action_items` | `list[string]` (optional) | Follow‑up tasks extracted from the utterance. |

Example `conversation.json`:

