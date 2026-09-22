# Conversations → HTML Report

This recipe turns a JSON conversation file into a self‑contained, styled HTML
report that can be opened in any browser.

## Input format

The input file must be a JSON array of objects, each containing at least
the following keys:

| Key     | Type   | Description                     |
|---------|--------|---------------------------------|
| `role`  | string | The speaker role (e.g. `user`, `assistant`). |
| `content` | string | The message text. |

Example (`convo.json`):

