# Export conversations to Notion block children

Use this recipe to convert Omi conversation transcripts into structured Notion block objects ready for immediate upload to Notion pages via the Notion REST API.

## Requirements

- Python 3.10+ (standard library only)
- Notion API Integration Token and Target Page ID

## Workflow

### 1. Export conversations from Omi

```sh
omi --json conversation list > conversations.json
```

### 2. Convert to Notion blocks payload

```sh
# Using -o / --output flag
python sdks/python-cli/examples/conversations_to_notion.py conversations.json -o notion_blocks.json

# Or using positional arguments
python sdks/python-cli/examples/conversations_to_notion.py conversations.json notion_blocks.json
```

### 3. Append to Notion Page via REST API

The generated JSON file has the `{"children": [...]}` structure expected directly by the Notion API:

```sh
export NOTION_TOKEN="secret_your_notion_integration_token"
export PAGE_ID="your_target_page_id"

curl -s -X PATCH "https://api.notion.com/v1/blocks/${PAGE_ID}/children" \
  -H "Authorization: Bearer ${NOTION_TOKEN}" \
  -H "Content-Type: application/json" \
  -H "Notion-Version: 2022-06-28" \
  -d @notion_blocks.json
```

## Output Format

```json
{
  "children": [
    {
      "object": "block",
      "type": "heading_2",
      "heading_2": {
        "rich_text": [{"type": "text", "text": {"content": "Weekly Team Sync (2026-09-22)"}}]
      }
    },
    {
      "object": "block",
      "type": "paragraph",
      "paragraph": {
        "rich_text": [{"type": "text", "text": {"content": "Alice: The hardware build is on schedule."}}]
      }
    }
  ]
}
```
