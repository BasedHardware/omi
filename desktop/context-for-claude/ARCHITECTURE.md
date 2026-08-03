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

## Targets

| Target | Kind | Depends on | Contains |
|---|---|---|---|
| `ContextCore` | library | GRDB | Storage, queries, and every pure policy. No AppKit, no AVFoundation — it has to link into the MCP binary. |
| `ContextMCPKit` | library | ContextCore | JSON-RPC framing, the seven tools, MCP handshake. |
| `ContextMCP` | executable | ContextMCPKit | `main.swift`. Opens the store read-only, pumps stdio. |
| `ContextApp` | executable | ContextCore, FluidAudio | Capture, transcription, menu bar, onboarding, Claude registration. |
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

Cloud mixes both channels so the backend can diarize. Local fallback (Silicon) approximates
attribution as "mic is the user, system is everyone else" with two separate Parakeet instances.

`Engine` owns the only writer. Each source runs in its own task and fails independently — a dead mic
must not stop screen capture — and the reason surfaces in the menu bar *and* in the MCP `status`
tool, so Claude can report a gap instead of fabricating over it. On Intel, when cloud ASR is not
live, a dedicated transcription gap reason is published the same way.

## Storage

`~/Library/Application Support/ContextForClaude/`

```
context.db              sessions, segments, frames + two FTS5 indexes
Frames/YYYY-MM-DD/      screen JPEGs, pruned after 30 days
capture-state.json      heartbeat: capturing / paused reason / capabilities
```

A session is a contiguous run of speech; a gap over five minutes starts a new one
(`SessionPolicy`). Transcripts are kept forever; frames are the expensive part and are the only
thing pruned.

## The MCP surface

Seven tools — `recall`, `recent`, `conversations`, `transcript`, `screen`, `activity`, `status` —
returning Markdown rather than JSON, because Claude reads prose better than it reads a dump. Tool
descriptions are written to tell Claude *when to reach for them*; they are the product's real
interface and deserve more care than the code behind them.

`status` exists so that "I have no record of that" can be distinguished from "that never happened".

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
                         Support/    Log
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
