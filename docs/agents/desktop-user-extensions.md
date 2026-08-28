# Desktop user MCP servers and skills (`~/.omi`)

User-managed agent extensions for the macOS app. Everything is on disk under
`~/.omi`, hand-editable, and never touches the backend.

## MCP servers

~/.omi/mcp.json in the standard client format:

```json
{ "mcpServers": { "<name>": { "command": "...", "args": [], "env": {} } } }
{ "mcpServers": { "<name>": { "url": "https://...", "headers": {} } } }
```

`LocalMcpStore` writes it from the Apps page Add Server sheet. The remote lane
supports three auth shapes: no auth, API key (`token`), and OAuth.
`LocalMcpStore+OAuth` runs the full native-app flow locally — metadata
discovery, dynamic client registration, PKCE, loopback redirect on 127.0.0.1,
code exchange — and stores tokens under the entry's `auth` key.
`refreshExpiredTokens()` runs at agent-runtime start, so a session never begins
with a stale token.

## Skills

`LocalSkillsStore` saves `~/.omi/skills/<slug>/SKILL.md` with normalized Agent
Skills frontmatter, plus ~/.omi/.claude-plugin/plugin.json for the ACP lane.
A hand-dropped skill folder works the same as one created in the UI.

## Runtime contract

`AgentRuntimeProcess` exports `OMI_USER_SKILLS_DIR` (`~/.omi`) and
`OMI_LOCAL_MCP_FILE`.

| Lane | MCP servers | Skills |
|---|---|---|
| ACP | `buildMcpServers()` (stdio and `type: "http"` shapes) | `plugins` option |
| pi-mono | registered in `pi-mono-extension` at startup, awaited before the first prompt, via `McpHttpClient` / `McpStdioClient` (5s http cap per server, 30s stdio cap for npx cold starts) | native catalog (`PI_CODING_AGENT_DIR` = `~/.omi`), `search_skills` / `load_skill`, and the compact catalog in `ChatProvider.loadClaudeConfigFromDisk` |

## Failure behavior

Fail-open throughout: a missing or invalid file, a bad entry, or an unreachable
server means those extensions are absent, never a broken chat. New servers and
skills reach the pi lane on its next process spawn.
