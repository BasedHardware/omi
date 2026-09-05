# Desktop user MCP servers and skills (`~/.omi`)

User-managed agent extensions for the macOS app. Everything is on disk under
`~/.omi`, hand-editable, and never touches the backend.

**Scope.** User skills and user MCP tools are available wherever chat turns run
through the kernel agent runtime — typed chat (main, floating, and notch),
task chat, and onboarding. They are deliberately **not** part of the PTT
realtime voice session: Gemini Live is offered the fixed realtime tool
manifest (`RealtimeHubTools`), and neither the `mcp_tools_info` / `mcp_call`
proxies nor the skill catalog is registered there. That is the current
design, not a known bug.

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
broken session), and because the refresh writes through the same
save-and-notify seam as any other change (see "Applying changes" below), so
the desktop respawns the runtime and the fresh token applies without waiting
for a later session.

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

Tool results are rendered as text: non-text blocks are *named*, never inlined —
an image block used to leave the join empty and fall through to
`JSON.stringify(result)`, which put its whole base64 payload in the context.
`structuredContent` answers when a tool returns data and no prose.

### Progressive disclosure (pi-mono lane only)

The ACP lane hands servers to the Claude Code harness at `session/new`; the
harness manages its own tools and caching, so nothing in this section applies
to it. On the pi-mono lane, servers are **not** registered tool-by-tool — a
user with a handful of servers would put hundreds of verbatim descriptions and
JSON schemas into the default tools payload before the model expressed any
interest in one of them. Exactly two proxy tools are registered instead:

- `mcp_tools_info` — discovery. The stable, sorted index of server names and
  tool names (plus each server's one-line description from its `initialize`
  `instructions`/`title`) is embedded in **its** description, so identifying
  a candidate needs no extra turn; each embedded name is clipped to 64
  characters and the server lines are capped at 20, because the text is
  frozen at registration and a hostile name must not bloat every turn.
  Calling it — with no arguments, with `server`, or with `server` + `tool` —
  returns the live index (with real names and live status), full descriptions
  and JSON input schemas for one server, or a single tool's contract.
- `mcp_call` — dispatch. Runs a server's tool by its **real** names and
  returns the result content faithfully, with readable errors for an unknown
  server or tool, a server that is still connecting, and a server that is
  unavailable. Its description carries server names only — the tool index is
  paid once, in `mcp_tools_info`'s description, not duplicated per turn.

There is no `mcp_<server>_<tool>` mangling and no collision-suffix race: the
model passes real names. A server's published prompts fold into the same
pattern — listed by `mcp_tools_info`, dispatched by `mcp_call` — because this
chat has no slash-command surface to offer them through. Everything a server
returns is untrusted tool-result data: it is handed back as tool output,
never interpolated into system instructions.

`notifications/tools/list_changed` is still not acted on; pi's extension API
has `registerTool` with no counterpart. Elicitation, sampling and roots
are likewise unimplemented — the client declares no capabilities of its own.
MCP **resources** are unsupported too: only tools and published prompts are
discovered and exposed. The client never declares the resources capability,
a server's resources are ignored, and `mcp_call` dispatches tools and prompts
only.

### Spawning and lifecycle

A stdio server is spawned on a small **allowlist environment** — `PATH`,
`HOME`, `TMPDIR`, `USER`, `LOGNAME`, `SHELL`, `LANG`, with Homebrew and
system fallback PATH entries so `npx` and `python3` resolve even when the app
was launched from the GUI with a bare PATH. It never inherits the runtime's
full environment, which carries `OMI_AUTH_TOKEN`, `OMI_BRIDGE_PIPE`, BYOK
provider keys, and Firebase credentials. The server's own `env` entries from
mcp.json are applied on top and may extend or override the allowlist — it is
the user's server.

An SSE server's event stream is its only reply channel, and a drop used to
fail the server for the rest of the session silently. A drop is now repaired
with bounded backoff (3 attempts at 1s, 5s, 15s); requests issued while the
repair is in flight wait for it (bounded by the call's own timeout), and a
server whose attempts are exhausted is marked down with a clear "server is
down for this session" error that surfaces through `mcp_tools_info` and
`mcp_call`.

Registration is **deterministic** and **non-blocking for the first turn**.
Servers are sorted by name and their tools and prompts by name before
anything is built, so the tools payload is stable across launches. Remote
servers connect concurrently under their own budgets (10s), while stdio
starts share a bound of 8 child-process spawns at a time (a big config used
to fire every `npx` spawn in one instant); the budgets are connection
timeouts, not prompt-blocking gates: the turn path waits at most
a short global budget (`OMI_MCP_FIRST_TURN_BUDGET_MS`, default 3s), and
servers still connecting keep connecting in the background — pi's
`registerTool` cannot revise a description after the fact, but the proxies
read live state, so a late server becomes callable without re-registration
and the live index reports `connecting` / `unavailable` per server.

### Applying changes

The pi-mono extension reads `mcp.json` in `~/.omi` **once per process spawn**
(when it registers the proxy tools), so a change to the file does not reach a
running session by itself. The desktop closes that gap: every write to the
file — a save, a removal, a key change, an OAuth sign-in, and the unawaited
token refresh — posts `.omiUserMcpDidChange`, and ChatProvider respawns the
shared runtime in response. The respawn is debounced (a marketplace-install
burst, or one refresh sweeping several tokens, costs one restart) and never
lands mid-turn: a change noticed while a reply is streaming stays pending
until the next turn's bridge-readiness check, which is the safe point between
turns. The runtime's own restart refuses while requests are active (a
background agent mid-run, for example), which defers the respawn the same
way — so the change lands right away when the app is idle, and with the next
message when it is not. Hand-edits are caught without a filesystem watcher:
the Apps page stats the file each time the server section appears
(`LocalMcpStore.checkForExternalChanges()`), and a stat is also how the store
tells its own writes from an outside one. The ACP lane needs none of this —
its harness re-reads the config per session — and skills need no respawn at
all, because the compact catalog is rebuilt from disk when a skill changes
and at every prompt-context warm-up.

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
| `CuaControlGate` | the switch, bound to the account that granted it; the sticky kill switch; the per-tool permission check. `@MainActor` so a check and the event it guards cannot be separated by an account switch |
| `CuaPermission` | the four grants, each checked with the API that answers for it |
| `CuaAppleScript` | `osascript` in a child process, with a timeout |
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

**"Accessibility" is two grants.** `kTCCServiceAccessibility` (`AXIsProcessTrusted`) lets Omi *read* another app's UI tree; `kTCCServicePostEvent` (`CGPreflightPostEventAccess`) lets it *synthesise* a click or a keystroke. They share a System Settings pane and nothing else, and a process can hold either without the other — gating input on `AXIsProcessTrusted` posts events the window server then silently drops, which reads to a model as a click that worked. Each tool names the grants it needs, so a missing one refuses only what depends on it, and a grant the user has never been asked for is requested at the point of use rather than described in a sentence.

**AppleScript runs out of process.** `NSAppleScript` has no timeout, and a model-written script that opens a dialog waits for a click nobody will make. In process that freezes the main thread, which is where the Stop button and the kill switch live. `osascript` is spawned instead and killed on timeout; TCC still holds Omi responsible, so the Automation prompt names Omi.

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
lives in the runtime, which logs `discovered N tools, M prompts` per server.

## Skills

`LocalSkillsStore` saves `~/.omi/skills/<slug>/SKILL.md` with normalized Agent
Skills frontmatter, plus ~/.omi/.claude-plugin/plugin.json for the ACP lane.
A hand-dropped skill folder works the same as one created in the UI. Imported
files — dropped or picked — must carry SKILL.md frontmatter with a
`description`; that string is what the model matches a request against, so a
README imported without one is a skill that can never be selected. Text typed
or pasted into the editor is still normalized, because there the user is
authoring the skill rather than claiming a file already is one.

A skill the user disables (`OMI_DISABLED_SKILLS`, exported to the runtime) is
refused by `load_skill` / `search_skills` and filtered from the compact
catalog, so the toggle binds the tools and not just the prompt text. The
compact catalog has **one source per lane**: on pi-mono it rides the prompt
(also indexing task-chat workspaces), while the ACP lane receives skills
natively through the plugin — and the catalog is withheld there, so the model
never sees the same index twice.

## Runtime contract

`AgentRuntimeProcess` exports `OMI_USER_SKILLS_DIR` (`~/.omi`),
`OMI_LOCAL_MCP_FILE`, and `OMI_DISABLED_SKILLS`.

| Lane | MCP servers | Skills |
|---|---|---|
| ACP | `buildMcpServers()` (stdio and `type: "http"` shapes), re-read per session and handed to the harness at `session/new` — harness-managed, no progressive disclosure | plugin-only (`plugins` option, gated on `plugin.json` under `.claude-plugin/`) |
| pi-mono | progressive disclosure via the `mcp_tools_info` / `mcp_call` proxy tools, registered in `pi-mono-extension` at startup over `McpHttpClient` / `McpSseClient` / `McpStdioClient` (10s http cap per server, 30s stdio cap for npx cold starts), non-blocking for the first prompt behind a short global budget | native catalog (`PI_CODING_AGENT_DIR` = `~/.omi`), `search_skills` / `load_skill` — which returns the overview (table of contents plus first section) by default and pages sections through `part` — and the compact catalog in `ChatProvider.loadClaudeConfigFromDisk` |

## Failure behavior

Fail-open throughout: a missing or invalid file, a bad entry, or an unreachable
server means those extensions are absent, never a broken chat. A saved server
reaches the pi lane through the `.omiUserMcpDidChange` respawn (right away
when idle, with the next message when a turn is in flight — see "Applying
changes" above) and the ACP lane on its next session; a skill reaches the
prompt catalog on its next rebuild.
