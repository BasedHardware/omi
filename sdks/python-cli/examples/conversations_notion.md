# Export conversations to Notion API block payloads

Use this recipe to convert Omi conversation transcripts and summaries into structured Notion API block payloads. The output conforms to Notion's `POST /v1/pages` format, creating rich pages with callout overviews, headings, and bulleted dialogue blocks with speaker attribution.

It automatically handles Notion's 2,000-character block length restriction, chunking text cleanly without dropping characters or corrupting unicode.

## Exporting Conversations

Fetch conversations with `omi-cli`:

```bash
omi --json conversation list --limit 50 > conversations.json
```

Or fetch a single conversation:

```bash
omi --json conversation get <conversation-id> > conversation.json
```

## Running the Exporter

Convert a conversation export to a Notion page payload:

```bash
python conversations_to_notion.py conversation.json -o notion_page.json
```

Target a specific Notion database by providing its parent ID:

```bash
python conversations_to_notion.py conversation.json -o notion_page.json --parent-id "12345678-abcd-1234-abcd-1234567890ab"
```

Export individual Notion payloads for each conversation into a directory:

```bash
python conversations_to_notion.py conversations.json --output-dir ./notion_pages/
```

## Submitting Directly to Notion via Curl

```bash
curl -X POST 'https://api.notion.com/v1/pages' \
  -H 'Authorization: Bearer '"$NOTION_API_KEY"'' \
  -H 'Notion-Version: 2022-06-28' \
  -H 'Content-Type: application/json' \
  --data @notion_page.json
```
