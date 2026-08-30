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
`LocalMcpStore+OAuth` runs the full native-app flow locally — discovery,
dynamic client registration, PKCE, loopback redirect on 127.0.0.1, code
exchange — and stores tokens under the entry's `auth` key.
`refreshExpiredTokens()` runs at agent-runtime start, so a session never begins
with a stale token.

Discovery follows RFC 9728: the resource's
`/.well-known/oauth-protected-resource` names its authorization servers, which
are routinely on another host, and the canonical `resource` it returns is sent
as the RFC 8707 `resource` parameter on both the authorization and token
requests. Probing only the resource's own `oauth-authorization-server` — and
omitting `resource` — fails every hosted provider.

## Marketplace

`ExtensionCatalog` / `ExtensionCatalogService` read browsable catalogs. Sources
live in ~/.omi/catalogs.json and default to two per kind:

```json
{ "catalogs": [
  { "kind": "mcp",   "type": "smithery",     "url": "https://registry.smithery.ai" },
  { "kind": "mcp",   "type": "mcp-registry", "url": "https://registry.modelcontextprotocol.io" },
  { "kind": "skill", "type": "github-skills", "repo": "anthropics/skills", "ref": "main" }
] }
```

A file that configures one kind leaves the other on its defaults. Feeds are
resolved by type, never by position.

The official registry publishes no popularity, rating, or curation signal — its
only query params are cursor/limit/search/version — and a vendor namespace only
proves the publisher owns *some* domain. So with no query the MCP section shows
`featuredMcpServers`, a curated list of names confirmed present under their
brand's DNS-verified namespace, followed by Smithery's verified and ranked
entries; typing searches both. Install data always comes from the registry.

Logos come only from publisher-controlled URLs — the registry's declared
`icons` (HTTPS only), else the GitHub owner avatar, else the site's favicon,
else a symbol. No third-party favicon proxy, which would leak which servers a
user browses. `ExtensionLogo` decodes with `NSImage` rather than `AsyncImage`
because many publishers serve SVG, which SwiftUI's decoder rejects.

## Server status

`McpServerProbe` replaces an unconditional "Active in chat" badge. Remote
servers get a real MCP `initialize` (2xx healthy, 401/403 "Needs sign-in").
Local commands are resolved against a PATH that includes Homebrew and
`~/.local/bin`, since a bundled app inherits none of a login shell's — they are
not launched, because `npx` installs on first run and a status badge must not
have that side effect. A local server therefore reads "Ready" (its command
exists), never a claim that it is serving tools; the authoritative tool count
lives in the runtime, which already logs `registered N tools`.

## Skills

`LocalSkillsStore` saves `~/.omi/skills/<slug>/SKILL.md` with normalized Agent
Skills frontmatter, plus ~/.omi/.claude-plugin/plugin.json for the ACP lane.
A hand-dropped skill folder works the same as one created in the UI. Imported
files — dropped or picked — must carry SKILL.md frontmatter with a
`description`; that string is what the model matches a request against, so a
README imported without one is a skill that can never be selected. Text typed
or pasted into the editor is still normalized, because there the user is
authoring the skill rather than claiming a file already is one.

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
