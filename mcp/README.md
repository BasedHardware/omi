# mcp-server-omi: A OMI MCP server

## Overview

A Model Context Protocol server for Omi interaction and automation. This server provides tools to read, search, and manipulate Memories and Conversations.

### Tools
1. `get_memories`
   - Retrieve a list of user memories
   - Inputs:
     - `uid` (string): The user's unique identifier
     - `limit` (number, optional): Maximum number of memories to retrieve (default: 100)
     - `categories` (array of MemoryFilterOptions, optional): Categories of memories to retrieve (default: [])
   - Returns: JSON object containing list of memories

2. `create_memory`
   - Create a new memory
   - Inputs:
     - `uid` (string): The user's unique identifier
     - `content` (string): Content of the memory
     - `category` (MemoryFilterOptions): Category of the memory
   - Returns: Created memory object

3. `delete_memory`
   - Delete a memory by ID
   - Inputs:
     - `uid` (string): The user's unique identifier
     - `memory_id` (string): ID of the memory to delete
   - Returns: Status of the operation

4. `edit_memory`
   - Edit a memory's content
   - Inputs:
     - `uid` (string): The user's unique identifier
     - `memory_id` (string): ID of the memory to edit
     - `content` (string): New content for the memory
   - Returns: Status of the operation

5. `get_conversations`
   - Retrieve a list of user conversations
   - Inputs:
     - `uid` (string): The user's unique identifier
     - `include_discarded` (boolean, optional): Whether to include discarded conversations (default: false)
     - `limit` (number, optional): Maximum number of conversations to retrieve (default: 25)
   - Returns: List of conversation objects containing transcripts, timestamps, geolocation and structured summaries

## Configuration

### Usage with Claude Desktop

Add this to your `claude_desktop_config.json`:

<details>
<summary>Using uvx</summary>

When using [uv](https://docs.astral.sh/uv/) no specific installation is needed.

We will use [uvx](https://docs.astral.sh/uv/guides/tools/) to directly run *mcp-server-omi*.

| If having issues instead of `"command": "uvx"`, put your whole package path (`which uvx`), then `"command": "$path"`.

```json
"mcpServers": {
  "omi": {
    "command": "uvx",
    "args": ["mcp-server-omi"]
  }
}
```

</details>

<details>
<summary>Using docker</summary>

Install docker, https://orbstack.dev/ is great.

```json
"mcpServers": {
  "omi": {
    "command": "docker",
    "args": ["run", "--rm", "-i", "josancamon19/mcp-server-omi"]
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

## License

This MCP server is licensed under the MIT License. This means you are free to use, modify, and distribute the software, subject to the terms and conditions of the MIT License. For more details, please see the LICENSE file in the project repository.
