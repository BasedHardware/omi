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

## MCP client

`agent/src/runtime/mcp-client.ts` holds the wire subset every user server is
driven through; each transport supplies `rpc` and the handshake:

| Transport | File | When |
|---|---|---|
| Streamable HTTP | `mcp-http-client.ts` | default for a `url` server |
| HTTP+SSE | `mcp-sse-client.ts` | `transport: "sse"` — the URL is an event stream, and POSTing to it is a 404 |
| stdio | `mcp-stdio-client.ts` | a `command` server |

`initialize` capabilities are recorded, so a server is never asked for prompts
it does not publish. `tools/list` and `prompts/list` are walked to the last
page, bounded by a page budget and by treating a repeated cursor as the end.
Prompts register as tools (`mcp_<server>_prompt_<name>`) because this chat has
no slash-command surface; a prompt's required arguments become the tool's.

Tool results are rendered as text: non-text blocks are *named*, never inlined —
an image block used to leave the join empty and fall through to
`JSON.stringify(result)`, which put its whole base64 payload in the context.
`structuredContent` answers when a tool returns data and no prose.

**Not supported:** `notifications/tools/list_changed`. Acting on it means
replacing a live tool set and pi's extension API has `registerTool` with no
counterpart; config and tools are read per session, so changes land on the next
one. Elicitation, sampling and roots are likewise unimplemented — the client
declares no capabilities of its own.

## Marketplace

`ExtensionCatalog` / `ExtensionCatalogService` read browsable catalogs. Sources
live in ~/.omi/catalogs.json and default to:

```json
{ "catalogs": [
  { "kind": "mcp",   "type": "mcp-registry", "url": "https://registry.modelcontextprotocol.io" },
  { "kind": "skill", "type": "github-skills", "repo": "anthropics/skills", "ref": "main" }
] }
```

A file that configures one kind leaves the other on its defaults. Feeds are
resolved by type, never by position, and an unrecognised `type` is dropped
rather than failing the file back to the defaults.

**MCP servers come only from the official registry.** It is the one index whose
namespaces are DNS-verified against the publisher's own domain, so an install
points at the vendor's own endpoint with the vendor's own OAuth. A broker
registry adds a second account and a second consent screen in front of a server
the user can reach directly — `excludedNamespaces` drops `ai.smithery/*` for the
same reason even though it is published to the official registry.

The registry publishes no popularity, rating, or curation signal — its only
query params are cursor/limit/search/version. So with no query the MCP section
shows `featuredMcpServers`, a curated list of names confirmed present under
their brand's DNS-verified namespace. Typing searches the whole registry, with
`io.github.<user>` namespaces ranked below branded ones (a GitHub namespace
proves only that someone holds a GitHub account). Install data always comes from
the registry, never from the curated list.

A package's declared arguments are replayed as published, named flags included
(`-t stdio`); an argument whose value is a `{placeholder}` is skipped, because
nothing here can fill it.

Skill catalogs are read as a **recursive git tree**, not a `skills/` folder
listing: a skill is a directory whose SKILL.md references `scripts/`,
`references/` and assets by relative path, and 22 of the 33 skills in the two
default catalogs ship such files. Install fetches the folder into a staging
directory and moves it into place once complete, so a failed download leaves no
half-written skill and a reinstall leaves no stale files. Paths are rejected
unless every component is a plain name, and the fetch is capped (200 files,
4 MB each, 32 MB total).

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
