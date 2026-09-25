# Context for Claude — architecture

A menu-bar-only macOS app that captures ambient audio and screen context, stores it locally, and
serves it to Claude over MCP. Standalone: it shares no code, no data, and no process with the Omi
desktop app in `desktop/macos/`.

## Why it is shaped this way

The product is one sentence — *Claude should already know what you have seen and said* — and every
structural decision follows from it:

- **Two processes, one database.** The app captures; a tiny `context-for-claude-mcp` binary answers Claude's
  questions. They never talk to each other. Claude spawns the MCP server per session, so it must
  work whether or not the app happens to be running; a shared SQLite file in WAL mode is the whole
  IPC mechanism, and a heartbeat JSON file carries live capture state.
- **No summarization layer.** Claude is the intelligence. Adding an LLM here would mean choosing what
  matters before knowing the question, which is exactly the mistake that makes ambient tools feel
  lossy.
- **Capture is ported, not reinvented.** The mic, system-audio and screen paths are lifted from the
  Omi desktop app because they encode years of real-world corrections (Bluetooth A2DP, tap drift
  compensation, transducer decoder state) that are invisible until they bite.
- **Updates use a shared micro-app platform, but retain product trust boundaries.** Sparkle is the
  same library used by Omi Desktop; the backend serves an identity-scoped Context feed, while this
  app keeps its own EdDSA key, bundle identifier, artifact namespace, and Developer ID continuity.
  The release helper publishes GitHub assets and metadata, so adding another micro-app does not
  require hand-editing an appcast. The hard part is that macOS keys this app's three TCC grants to
  its code signature, so an update signed by a different identity silently revokes every permission
  its users granted — `Update/UpdatePolicy.swift` and `docs/releasing.md` are both mostly about that
  one fact.

## Targets

| Target | Kind | Depends on | Contains |
|---|---|---|---|
| `ContextCore` | library | GRDB | Storage, queries, and every pure policy. No AppKit, no AVFoundation — it has to link into the MCP binary. |
| `ContextMCPKit` | library | ContextCore | JSON-RPC framing, the twelve tools, frame-to-JPEG conversion, MCP handshake, Omi memory reads and writes. |
| `ContextMCP` | executable | ContextMCPKit | `main.swift`. Opens the store read-only, pumps stdio. |
| `ContextApp` | executable | ContextCore, FluidAudio, Sparkle | Capture, transcription, menu bar, onboarding, Claude registration, auto-update. |
| `context_for_claude_windows_core_smoke` | Windows executable | `ContextForClaude::core`, swift-winrt | Calls the portable C ABI for a session decision and ranking score. |

The library/executable split exists so the protocol layer is testable without a bundle and so the
MCP binary stays free of every UI and capture dependency — it must start in milliseconds and hold no
permissions.

## Windows portable-core host

`windows/` is a Windows-only CMake build. It builds the same `core/` library as the macOS Swift
package, fetches swift-winrt at commit `79ffa65c`, and builds its generator alongside a native C++
smoke CLI. The CLI exercises the C ABI; it does not generate a Swift/WinRT projection because this
slice calls no WinRT API.

Windows support ends at that portable-core proof. Mic and system-audio capture, screen capture,
OCR, storage, MCP, and the macOS UI remain outside this slice.

## Data flow

```
MicCapture ──┐
             ├→ AudioMixer ─→ ListenSocket (/v4/listen) ──┐
SystemAudio ─┘     cloud ASR (all hosts)                   │
                                                           ├──→ Engine ──→ ContextStore ──→ context.db
MicCapture ──┐                                             │    session      GRDB, WAL,
             ├→ Transcriber (Parakeet)* ───────────────────┤    boundaries   FTS5
SystemAudio ─┘     Apple Silicon only                      │
                                                           │
ScreenWatcher ──────→ Vision OCR ──────────────────────────┘
  ScreenCaptureKit          (3 s Silicon / 9 s Intel)
```

`*` Local Parakeet is never constructed on Intel. Capture feeds the cloud mixer regardless; a local
model load failure on Silicon must not tear down the audio devices or the cloud pump
(`CaptureHostPolicy` / `AudioCaptureDecision`).

Audio flows as 16 kHz mono Int16 little-endian `Data` from capture to transcription — one format,
agreed once, so a source and a transcriber can be swapped independently.

Cloud mixes both channels so the backend can diarize. Local Parakeet (Silicon) runs in parallel
and approximates attribution as "mic is the user, system is everyone else" with two separate
instances — not full multi-speaker labels.

`Engine` owns the only writer. Each source runs in its own task and fails independently — a dead mic
must not stop screen capture — and the reason surfaces in the menu bar *and* in the MCP `status`
tool, so Claude can report a gap instead of fabricating over it. On Intel, when cloud ASR is not
live, a dedicated transcription gap reason is published the same way.

## Storage

`~/Library/Application Support/ContextForClaude/`

```
context.db              sessions, segments, frames + two FTS5 indexes, and the account cache
Frames/YYYY-MM-DD/      screen JPEGs, pruned after 30 days
capture-state.json      heartbeat: capturing / paused reason / capabilities
last-query.json         the MCP server's proof it served a tool call: tool name + time, nothing else
last-query.json.lock    flock target for the above, so concurrent MCP servers cannot lose a write
```

`capture-state.json` and `last-query.json` are the two halves of the same trick: the app and the MCP
server are separate processes with no IPC, so each writes a small atomic file the other reads. The
heartbeat carries live capture state *to* the server; the query stamp carries "Claude really called
us" back *to* the app, which is what lets the first-run tutorial's payoff beat be earned rather than
staged. Neither ever holds anything the user said, saw, or asked — see `QueryStamp`.

A session is a contiguous run of speech; a gap over five minutes starts a new one
(`SessionPolicy`). Transcripts are kept forever; frames are the expensive part and are the only
thing pruned.

`account_rows` is the one table in here that is **a copy and not an authority**: the last answer the
user's Omi account gave, bounded to one page per source, so the Activity panel paints real titles on
a cold launch instead of the untitled local sessions it used to show while three HTTP round trips
were in flight. Every row came off the wire and is rewritten by the wire; nothing reads it once a
real answer exists, and signing out empties it. See `AccountCacheQueries` and
`ActivityAccountCache`.

## The MCP surface

Twelve tools — `recall`, `recent`, `conversations`, `transcript`, `screen`, `look`, `activity`,
`status`, `get_memories`, `create_memory`, `edit_memory`, and `delete_memory` — return Markdown
rather than JSON, because Claude reads prose better than it reads a dump. Memory writes go through
Omi's canonical `/v1/mcp/memories` API using the provisioned MCP key; CFC does not create a second
local memory store. Tool descriptions are written to tell Claude *when to reach for them*; they are
the product's real interface and deserve more care than the code behind them.

`status` exists so that "I have no record of that" can be distinguished from "that never happened".

`look` is the only tool that returns pixels, and it is the reason `Tools.call` returns a
`ToolOutput` (prose plus images) rather than a string. Three rules hold it together: the text block
is emitted first and always carries the frame's age, because MCP's image block has no field for a
timestamp; the stored HEIC is re-encoded as JPEG, which is the only format the client accepts; and a
frame whose text `Redaction.scrub` marked is served **without** its picture, because the scrub has
never touched pixels. Reads go through `RewindQueries`, still the only module that selects
`frames.imagePath` — the file is converted to an image, never handed over as a path.

Beyond the connector, `ClaudeSkill` installs `~/.claude/skills/context-for-claude/SKILL.md` when the
user connects and deletes it when they disconnect. The server's `instructions` reach the main loop's
system prompt; the skill is what reaches a subagent, which starts with none of the conversation
behind its task.

## Files

```
Sources/ContextCore/     Models  Paths  Store  Queries  Policy  ClaudeConfig
Sources/ContextMCPKit/   JSONRPC  MCPServer  Tools
Sources/ContextMCP/      main
Sources/ContextApp/      ContextApp  Engine  Permissions
                         Capture/    AudioSource  MicCapture  SystemAudioCapture  ScreenWatcher
                         Transcribe/ Transcriber
                         MenuBar/    StatusView
                         Onboarding/ Ink  Backdrop  RandomizedText  OnboardingWindow  OnboardingView
                         Integration/ClaudeRegistrar  LoginItem
                         Shortcuts/  GlobalShortcuts  ShortcutConflicts
                         Activity/   ActivitySpine (the one process-lived store)  ActivityStore
                                     ActivityComposer  ActivityAccount  ActivityAccountCache
                                     ActivityLocalMemories  ActivitySurface  ActivityStream
                         Search/     SearchBarWindow  SearchBarView  SearchSurface
                                     SearchResultsModel  SearchResultsView  SearchRanking
                                     ClaudeRouter (tutorial + settings only, not the bar)
                         Support/    Log  Sound  Telemetry  WindowGlass (the NSWindow half of InkGlass)
                         Update/     UpdatePolicy  ContextUpdater  UpdateRelaunch  UpdatesSettingsRow
```

`CONTRACTS.md` holds the interface each file must satisfy; `docs/design-system.md` holds the
exact visual values. Both are load-bearing — this package was built by many hands at once, and those
two documents are what made the pieces fit.

## Building

```
scripts/build.sh            # build, bundle, sign, install to /Applications/Context for Claude.app
scripts/build.sh --run      # …and launch it
swift test --package-path desktop/context-for-claude
```

Windows validation is documented in `windows/README.md` and must run on Windows; configuring that
project on macOS intentionally fails before it fetches Windows-only dependencies.

Signed with the local `Omi Local Dev Signing` identity, never ad-hoc — ad-hoc signing resets Screen
Recording permission for every Omi app on the machine.
