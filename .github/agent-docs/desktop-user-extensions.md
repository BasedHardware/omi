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
`refreshExpiredTokens()` is kicked off at agent-runtime start, but **not
awaited** — it races the runtime spawn, so a session can begin on a token that
is still refreshing. That is deliberate: awaiting it would put a network round
trip per expired token in front of every launch. It is safe because the path
fails open (a stale token means one server answers 401 and is skipped, never a
broken session) and because the runtime re-reads mcp.json per session, so the
refreshed token applies from the next one.

Tokens are stored **in plaintext** in ~/.omi/mcp.json, under the server
entry's `auth` key — the same trust model as other local MCP clients, in a
user-owned file. Anything that can read the user's home directory can read
them; the Keychain would be the stricter home if that ever stops being enough.

PKCE verifiers and OAuth `state` come from `SecRandomCopyBytes`, base64url-encoded
per RFC 7636 §4.1. A failure to draw randomness aborts the flow rather than
falling back to a weaker generator.

Discovery follows RFC 9728: the resource's
`/.well-known/oauth-protected-resource` names its authorization servers, which
are routinely on another host, and the canonical `resource` it returns is sent
as the RFC 8707 `resource` parameter on both the authorization and token
requests. Probing only the resource's own `oauth-authorization-server` — and
omitting `resource` — fails every hosted provider.

## MCP client

`desktop/macos/agent/src/runtime/mcp-client.ts` holds the wire subset every user server is
driven through; each transport supplies `rpc` and the handshake:

| Transport | File | When |
|---|---|---|
| Streamable HTTP | `desktop/macos/agent/src/runtime/mcp-http-client.ts` | default for a `url` server |
| HTTP+SSE | `desktop/macos/agent/src/runtime/mcp-sse-client.ts` | `transport: "sse"` — the URL is an event stream, and POSTing to it is a 404 |
| stdio | `desktop/macos/agent/src/runtime/mcp-stdio-client.ts` | a `command` server |

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

## Computer control

`~/.omi` gains a second thing when the user turns on **Allow Omi to control this
Mac** (Apps ▸ MCP): an `omi-computer-use` entry in mcp.json pointing at
`http://127.0.0.1:47778/mcp`, and `~/.omi/omi-cua`, a 0700 shell shim for
clients that only speak stdio. Both are rewritten on every enable, because a
rotated token or a changed port leaves an entry that answers 401 to every call —
which a client shows as a server with no tools, not as an auth failure.

The endpoint is served by `LocalAgentAPIServer` on its existing loopback socket
and behind its existing bearer token; `Desktop/Sources/ComputerUse/` holds
everything else. It shares the token deliberately (a client the user already
trusted with the local API is the same client) but not the switch: driving the
pointer needs its own consent, held by `CuaControlGate`.

| Piece | Owns |
|---|---|
| `CuaControlGate` | the switch, bound to the account that granted it; the sticky kill switch; the Accessibility check. `@MainActor` so a check and the event it guards cannot be separated by an account switch |
| `CuaFrameGeometry` | every coordinate conversion. Global points (`CGDisplayBounds`, top-left origin — **not** `NSScreen.frame`), native pixels, and the delivered image are three different spaces |
| `CuaFrameRegistry` | the last four frames, so "click 412, 288" means the same thing to both sides |
| `CuaScreenObserver` | displays, windows, and ScreenCaptureKit capture at an explicit pixel size |
| `CuaAxReader` | the accessibility tree, on one serial queue, never against our own pid (`AccessibilityProcessBoundary`) |
| `CuaInputSynth` | `CGEvent` posting; `CuaKeyMap` resolves chords against the live keyboard layout |
| `CuaMcpEndpoint` | JSON-RPC only, no networking, so the wire contract is testable without a socket |

Captures are delivered at a **1568 px long edge**. The Claude API rejects an
oversized image inside a `tool_result` rather than downscaling it the way it does
for an ordinary message, so the scaling has to happen before the image is
returned, and 1568 is the standard-resolution tier every model accepts.

The endpoint is **dual-era**: `2026-07-28` removed the `initialize` handshake and
moved the protocol version into per-request `_meta`, but every client shipping
today still opens with `initialize`. So `initialize` selects legacy semantics,
`server/discover` and per-request `_meta` select modern, and an unknown version
returns `UnsupportedProtocolVersionError` (`-32022`) naming the supported list.

The kill switch is ⌃⌥⌘., registered by `GlobalShortcutManager` **only while
control is on**. A Carbon hotkey preempts the frontmost app for as long as it is
registered, so the chord is taken from every other app on the Mac; that is worth
it exactly while something else is moving the pointer the user would otherwise
reach a button with.

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
