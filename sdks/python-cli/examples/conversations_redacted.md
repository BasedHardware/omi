# Sanitize and redact PII from Omi conversation exports

Use this recipe to strip Personally Identifiable Information (PII) and sensitive secrets from your Omi conversations before sharing, publishing, or uploading to external AI models.

## What gets redacted?

- **Email addresses**: Replaced with `[REDACTED_EMAIL]`
- **Phone numbers**: Replaced with `[REDACTED_PHONE]`
- **Credit card numbers**: Replaced with `[REDACTED_CARD]`
- **API keys and secrets**: Common token formats (e.g. `sk-...`, `ghp-...`) replaced with `[REDACTED_SECRET]`
- **IP addresses**: Replaced with `[REDACTED_IP]`

## Prerequisites

- Python 3.10+ (standard library only)
- An authenticated `omi-cli` installation

## Usage

Export and sanitize in one pipeline:

```sh
omi --json conversation list --limit 100 | python conversations_to_redacted.py - -o clean_conversations.json --summary
```

Or process an existing export file:

```sh
python conversations_to_redacted.py raw_conversations.json -o redacted_conversations.json --summary
```

Output:
```
Redacted 25 conversations. Elements redacted: [cards: 1, emails: 4, ips: 2, phones: 3, secrets: 2]
```

## Features

- **Multi-layer scrubbing**: Scans conversation titles, structured overviews, raw transcripts, and all transcript segment utterances.
- **Privacy by Default**: Ensures sensitive client data, credentials, and contact details are masked prior to external distribution.
- **Pure Standard Library**: Zero external dependencies required.
