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


## Appending Blocks to Notion Page
To append converted blocks to a Notion page via the Notion API:

```sh
export NOTION_TOKEN="secret_..."
PAGE_ID="your_page_id"

curl -X PATCH "https://api.notion.com/v1/blocks/${PAGE_ID}/children" \
  -H "Authorization: Bearer ${NOTION_TOKEN}" \
  -H "Content-Type: application/json" \
  -H "Notion-Version: 2022-06-28" \
  -d @notion_blocks.json
```


## Uploading to Notion API
To append the generated blocks to your target Notion page:

```sh
export NOTION_TOKEN="secret_..."
PAGE_ID="your_target_page_id"

# Extract each batch and append to page children
jq -c '.batches[]' notion_blocks.json | while read -r batch; do
  curl -s -X PATCH "https://api.notion.com/v1/blocks/${PAGE_ID}/children" \
    -H "Authorization: Bearer ${NOTION_TOKEN}" \
    -H "Content-Type: application/json" \
    -H "Notion-Version: 2022-06-28" \
    -d "{\"children\": $batch}"
done
```
