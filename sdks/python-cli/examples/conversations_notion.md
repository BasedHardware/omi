# Convert Conversations to Notion Blocks

This recipe demonstrates how to transform a conversation JSON file into a
Notion API-compatible block payload. The resulting JSON can be sent to the
Notion API using the `blocks` endpoint to create a page or append to an
existing page.

## Input Format

The input file should be a JSON array of message objects:

