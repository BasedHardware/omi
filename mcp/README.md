# mcp-server-omi: A OMI MCP server

## Overview

A Model Context Protocol server for Omi interaction and automation. This server provides tools to read, search, and manipulate Memories and Conversations.

### Tools
1. `get_memories`
   - Retrieve a list of user memories
   - Inputs:
     - `limit` (number, optional): Maximum number of memories to retrieve (default: 100)
     - `offset` (number, optional): Offset for pagination (default: 0)
     - `categories` (array of MemoryFilterOptions, optional): Categories of memories to retrieve (default: [])
   - Returns: JSON object containing list of memories

2. `create_memory`
   - Create a new memory
   - Inputs:
     - `content` (string): Content of the memory
     - `category` (MemoryFilterOptions): Category of the memory
   - Returns: Created memory object

3. `delete_memory`
   - Delete a memory by ID
   - Inputs:
     - `memory_id` (string): ID of the memory to delete
   - Returns: Status of the operation

4. `edit_memory`
   - Edit a memory's content
   - Inputs:
     - `memory_id` (string): ID of the memory to edit
     - `content` (string): New content for the memory
   - Returns: Status of the operation

5. `get_conversations`
   - Retrieve a list of user conversations
   - Inputs:
     - `start_date` (string, optional): Filter conversations after this date (yyyy-mm-dd)
     - `end_date` (string, optional): Filter conversations before this date (yyyy-mm-dd)
     - `categories` (array of ConversationCategory, optional): Categories of conversations to retrieve
     - `limit` (number, optional): Maximum number of conversations to retrieve (default: 20)
     - `offset` (number, optional): Offset for pagination (default: 0)
   - Returns: List of conversation objects containing transcripts, timestamps, geolocation and structured summaries

6. `get_conversation_by_id`
   - Retrieve a single conversation by ID, including transcript segments
   - Inputs:
     - `conversation_id` (string): ID of the conversation to retrieve
   - Returns: Conversation object including transcript segments

7. `get_action_items`
   - Retrieve a list of action items (tasks/to-dos)
   - Inputs:
     - `limit` (number, optional): Maximum number of action items to retrieve (default: 50)
     - `offset` (number, optional): Offset for pagination (default: 0)
     - `completed` (boolean, optional): Filter by completion status
     - `conversation_id` (string, optional): Filter by conversation ID
     - `start_date` (string, optional): Filter by creation start date (ISO 8601)
     - `end_date` (string, optional): Filter by creation end date (ISO 8601)
     - `due_start_date` (string, optional): Filter by due start date (ISO 8601)
     - `due_end_date` (string, optional): Filter by due end date (ISO 8601)
   - Returns: JSON object containing list of action items

8. `create_action_item`
   - Create a new action item (task/to-do)
   - Inputs:
     - `description` (string): Action item description
     - `completed` (boolean, optional): Whether the item is completed (default: false)
     - `due_at` (string, optional): Due date (ISO 8601)
     - `conversation_id` (string, optional): Associated conversation ID
   - Returns: Created action item object

9. `update_action_item`
   - Update an existing action item
   - Inputs:
     - `action_item_id` (string): ID of the action item to update
     - `description` (string, optional): Updated description
     - `completed` (boolean, optional): Updated completion status
     - `due_at` (string, optional): Updated due date (ISO 8601, set to null to clear)
   - Returns: Updated action item object

10. `delete_action_item`
    - Delete an action item by ID
    - Inputs:
      - `action_item_id` (string): ID of the action item to delete
    - Returns: Status of the operation

## Configuration

### API Key

To use the Omi MCP server, you need an API key. You can generate one in the Omi app under `Settings > Developer > MCP`. The API key can be provided with each tool call. If not provided, the server will use the `OMI_API_KEY` environment variable as a fallback.

### Usage with Claude Desktop

Add this to your `claude_desktop_config.json`:

<details>
<summary>Using docker</summary>

Install docker, https://orbstack.dev/ is great.

Replace `your_api_key_here` with the key you generated in the Omi app.

```json
"mcpServers": {
  "omi": {
    "command": "docker",
    "args": ["run", "--rm", "-i", "-e", "OMI_API_KEY=your_api_key_here", "omiai/mcp-server"]
  }
}
```
</details>

<!-- <details>
<summary>Using pip installation</summary>

Requires python >= 3.11.6. 
- Check `python --version`, and `brew list --versions | grep python` (you might have other versions of python installed)
- Get the path of the python version (`which python`) or with brew

```json
"mcpServers": {
  "omi": {
    "command": "/opt/homebrew/bin/python3.12",
    "args": ["-m", "mcp_server_omi"]
  }
}
```
</details> -->

## Debugging

You can use the MCP inspector to debug the server. For uvx installations:

```
npx @modelcontextprotocol/inspector uvx mcp-server-omi
```

Or if you've installed the package in a specific directory or are developing on it:

```
cd path/to/servers/src/omi
npx @modelcontextprotocol/inspector uv run mcp-server-omi
```

Running `tail -n 20 -f ~/Library/Logs/Claude/mcp-server-omi.log` will show the logs from the server and may
help you debug any issues.

## Advanced

### Custom Backend URL

If you are self-hosting the Omi backend, you can specify the API endpoint by setting the `OMI_API_BASE_URL` environment variable.

```bash
export OMI_API_BASE_URL="https://your-backend-url.com"
```

## License

This MCP server is licensed under the MIT License. This means you are free to use, modify, and distribute the software, subject to the terms and conditions of the MIT License. For more details, please see the LICENSE file in the project repository.
