# Convert conversations to Notion block payloads

Use this recipe to format Omi conversation transcripts, overviews, and action items into Notion API-compatible block batches (ready for the `/v1/blocks/{id}/children` endpoint).

Export conversations:

```sh
omi --json conversation list --include-transcript --limit 50 > conversations.json
```

Convert to Notion blocks:

```sh
python conversations_to_notion.py conversations.json notion_blocks.json
```
