# mcp-server-omi: A OMI MCP server

> **Deprecated — use the hosted server at `https://api.omi.me/v1/mcp`.**
> The hosted endpoint (Streamable HTTP) exposes the full tool surface with OAuth
> or MCP-key auth and requires no local process. This package remains published
> for clients that genuinely need a local stdio bridge, and is no longer the
> recommended setup.
>
> **Migrating from this package:**
> 1. Create an MCP key in the Omi app: **Settings → Developer Settings → MCP
>    Server → API Keys** (or **Use omi memory anywhere → Manual installation**
>    in the macOS app). The `omi_mcp_...` value is shown once.
> 2. Point your client at `https://api.omi.me/v1/mcp` with the header
>    `Authorization: Bearer omi_mcp_...` — most clients accept this natively
>    (see `claude mcp add --transport http`, Cursor `mcp.json`, Codex
>    `[mcp_servers.omi]` in `~/.codex/config.toml`).
> 3. For cloud clients that support OAuth connectors (claude.ai, ChatGPT),
>    add the URL and approve Omi's OAuth consent — no key needed.

## Overview

A Model Context Protocol server for Omi interaction and automation. This server provides tools to read, search, and manipulate Memories and Conversations.

**0.2.0:** deprecated in favor of the hosted endpoint above; no functional
changes beyond this notice and a startup warning.

### Tools
1. `get_memories`
   - Retrieve a list of user memories
   - Inputs:
     - `limit` (number, optional): Maximum number of memories to retrieve (default: 100)
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
     - `include_discarded` (boolean, optional): Whether to include discarded conversations (default: false)
     - `limit` (number, optional): Maximum number of conversations to retrieve (default: 25)
   - Returns: List of conversation objects containing transcripts, timestamps, geolocation and structured summaries

## Configuration

### API Key

This local stdio server uses an MCP API key. In the current Omi macOS app, choose a
key-based destination under `Use omi memory anywhere` and expand `Manual installation` to
copy the generated key. In the cross-platform app, open `Settings > Developer Settings`,
scroll to `MCP Server`, and create a key in the `API Keys` list. Copy the complete
`omi_mcp_...` value when it is created.

The key can be provided with each tool call. If it is omitted, the server uses the
`OMI_API_KEY` environment variable. The hosted Omi MCP endpoint also supports OAuth for
registered cloud clients; this local stdio package uses the manual-key path.

### Usage with Claude Desktop

Add this to your `claude_desktop_config.json`:

<details>
<summary>Using uvx (recommended)</summary>

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) first. No separate
package installation is needed; `uvx` downloads and runs the published server:

```json
"mcpServers": {
  "omi": {
    "command": "uvx",
    "args": ["mcp-server-omi"],
    "env": {
      "OMI_API_KEY": "omi_mcp_YOUR_KEY_HERE"
    }
  }
}
```
</details>

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

<details>
<summary>Using pip</summary>

Requires Python 3.11.6 or newer:

```bash
pip install mcp-server-omi
```

```json
"mcpServers": {
  "omi": {
    "command": "mcp-server-omi",
    "env": {
      "OMI_API_KEY": "omi_mcp_YOUR_KEY_HERE"
    }
  }
}
```
</details>

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

To follow Claude Desktop logs while debugging:

```bash
# macOS
tail -n 20 -f ~/Library/Logs/Claude/mcp-server-omi.log
```

```powershell
# Windows PowerShell
Get-Content "$env:APPDATA\Claude\logs\mcp-server-omi.log" -Tail 20 -Wait
```

## Advanced

### Custom Backend URL

If you are self-hosting the Omi backend, point `OMI_API_BASE_URL` at your
deployment's REST MCP base. The package appends REST segments (`memories`,
`conversations/...`) directly, so the value **must end with `/v1/mcp/`**:

```bash
export OMI_API_BASE_URL="https://your-backend-url.com/v1/mcp/"
```

This is the *REST base*, distinct from the hosted MCP endpoint remote clients
connect to (`https://api.omi.me/v1/mcp`, no trailing slash).

## License

This MCP server is licensed under the MIT License. This means you are free to use, modify, and distribute the software, subject to the terms and conditions of the MIT License. For more details, please see the LICENSE file in the project repository.
