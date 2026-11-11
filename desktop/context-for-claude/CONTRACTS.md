# Context for Claude — build contracts

Every agent building a piece of this package codes against this file. It is the only coordination
mechanism: stay inside your assigned files, implement the signatures below exactly, and the pieces
will link.

## Ground rules

1. **Only touch the files assigned to you.** Another agent owns every other file. Do not create
   files outside your assignment, do not edit `Package.swift`, `Models.swift`, `Paths.swift`, or
   this document.
2. **Do not run `swift build`.** The package does not compile until every agent has landed; a build
   attempt only produces misleading errors and fights other agents for the SPM lock. Integration and
   the build-fix loop happen centrally afterwards.
3. Swift language mode is **v5** (not strict-concurrency v6). Platform floor is **macOS 14.4**.
   Target the SDK in Xcode 26.2 / Swift 6.2.
4. Style: match the surrounding Omi desktop code. Comments explain *why*, never *what*. No purple in
   any UI, ever (`INV-UI-1`).
5. Log via `ContextLog.info/error(...)` (owned by the support agent). Never `print()` in
   `ContextApp`; **never write anything to stdout in `ContextMCP`** except JSON-RPC frames — stdout
   is the protocol channel there, so diagnostics go to stderr only.

## Already written — read, do not edit

- `Sources/ContextCore/Models.swift` — `Session`, `SegmentSource`, `Segment`, `Frame`, `Hit`,
  `SessionSummary`, `ActivityBlock`, `CapabilityReport`, `StatusInfo`, `ContextTime`.
- `Sources/ContextCore/Paths.swift` — `ContextPaths`, `CaptureState`.
- `Package.swift` — targets `ContextCore`, `ContextMCPKit`, `ContextMCP`, `ContextApp`, and two test
  targets.

## Target boundaries

| Target | May import | Purpose |
|---|---|---|
| `ContextCore` | Foundation, GRDB | Storage, queries, and pure policy. **No AppKit, no SwiftUI, no AVFoundation** — it has to link into the MCP binary. |
| `ContextMCPKit` | Foundation, ContextCore | JSON-RPC + tool dispatch. No UI, no capture. |
| `ContextMCP` | ContextMCPKit | `main.swift` only: wire stdin/stdout to `MCPServer`. |
| `ContextApp` | everything | The app: capture, transcription, UI, integration. |

---

## ContextCore

### `Sources/ContextCore/Store.swift` — owner: **store agent**

```swift
public final class ContextStore: @unchecked Sendable {
    /// Opens (creating if needed) the database at `url` and runs migrations.
    /// `readOnly` opens a WAL reader that never blocks the writer — this is what `context-for-claude-mcp` uses.
    public init(url: URL = ContextPaths.databaseURL, readOnly: Bool = false) throws

    public func read<T>(_ body: (Database) throws -> T) throws -> T
    public func write<T>(_ body: (Database) throws -> T) throws -> T   // throws if readOnly

    // Writes
    public func openSession(at: Double, appHint: String?) throws -> Int64
    public func closeSession(_ id: Int64, at: Double) throws
    public func insertSegment(_ segment: Segment) throws -> Int64
    public func insertFrame(_ frame: Frame) throws -> Int64

    /// Deletes frames (and their JPEGs) older than `days`. Transcripts are never pruned.
    @discardableResult
    public func pruneFrames(olderThanDays days: Int) throws -> Int
}

public enum ContextStoreError: Error { case readOnly, notInitialized }
```

Schema, created by GRDB `DatabaseMigrator` migration `"v1"`:

```sql
CREATE TABLE sessions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  startedAt DOUBLE NOT NULL, endedAt DOUBLE, appHint TEXT);
CREATE INDEX idx_sessions_startedAt ON sessions(startedAt);

CREATE TABLE segments (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  sessionId INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
  startedAt DOUBLE NOT NULL, endedAt DOUBLE NOT NULL,
  source TEXT NOT NULL, speaker TEXT NOT NULL, text TEXT NOT NULL,
  confidence DOUBLE, speakerLabel TEXT, personId TEXT);
CREATE INDEX idx_segments_startedAt ON segments(startedAt);
CREATE INDEX idx_segments_sessionId ON segments(sessionId, startedAt);

CREATE TABLE frames (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  capturedAt DOUBLE NOT NULL, appName TEXT, windowTitle TEXT, ocrText TEXT, imagePath TEXT);
CREATE INDEX idx_frames_capturedAt ON frames(capturedAt);
CREATE INDEX idx_frames_app ON frames(appName, capturedAt);
-- Partial, and the predicates are the point. `imagePath IS NOT NULL` is the "showable" set every
-- timeline read is about (8.7% of captured rows never had a picture); `bundleId IS NOT NULL` skips
-- every row written before v7 added the column. Measured on a year of capture: coverage 581ms -> 0ms,
-- the app->bundle map 779ms -> 148ms, both of which ran on the main actor when the timeline opened.
CREATE INDEX idx_frames_showable ON frames(capturedAt) WHERE imagePath IS NOT NULL;
CREATE INDEX idx_frames_bundle_by_app ON frames(appName, id) WHERE bundleId IS NOT NULL;
```

Plus FTS5 external-content tables `segments_fts(text)` and `frames_fts(ocrText, windowTitle, appName)`
with `content=` pointing at the base tables and the three standard sync triggers each
(`ai`, `ad`, `au`). Use `tokenize='porter unicode61'`.

PRAGMAs on open: `journal_mode=WAL`, `synchronous=NORMAL`, `foreign_keys=ON`, `busy_timeout=5000`.

`readOnly` mode must not attempt migrations and must not fail when the file does not exist —
throw `ContextStoreError.notInitialized` so callers can report "not capturing yet".

### `Sources/ContextCore/Queries.swift` — owner: **queries agent**

```swift
public enum Queries {
    public static func recall(_ store: ContextStore, query: String, since: Double? = nil,
                              until: Double? = nil, limit: Int = 40) throws -> [Hit]
    public static func recent(_ store: ContextStore, minutes: Int = 30, limit: Int = 120) throws -> [Hit]
    public static func sessions(_ store: ContextStore, since: Double? = nil, until: Double? = nil,
                                limit: Int = 30) throws -> [SessionSummary]
    public static func transcript(_ store: ContextStore, sessionId: Int64) throws -> [Hit]
    public static func screen(_ store: ContextStore, since: Double? = nil, until: Double? = nil,
                              app: String? = nil, limit: Int = 60) throws -> [Hit]
    public static func activity(_ store: ContextStore, since: Double, until: Double) throws -> [ActivityBlock]
    public static func status(_ store: ContextStore) throws -> StatusInfo
}
```

Behaviour that matters:
- `recall` searches **both** `segments_fts` and `frames_fts`, merges, sorts newest-first, caps at
  `limit`. Sanitize the user query into a safe FTS5 MATCH expression (quote each term, join with
  `OR`, drop FTS operators) — an unsanitized quote or `*` must never throw.
- `Hit.kind` is `"said"` for `source == mic`, `"heard"` for `source == system`, `"screen"` for frames.
- Screen hits collapse OCR whitespace and truncate to ~600 characters; the window title is the
  signal, the OCR is the detail.
- `activity` collapses consecutive frames of the same app into one block, closing a block when the
  app changes or a gap exceeds 120 s.
- `status` reads `CaptureState.read()`; if it is nil or `isStale`, report `capturing: false` with
  `pausedReason: "Context for Claude is not running"`.

### `Sources/ContextCore/Policy.swift` — owner: **policy agent**

```swift
/// Decides when one conversation ends and the next begins.
public struct SessionPolicy {
    public static let gapSeconds: Double = 300
    public init(gapSeconds: Double = SessionPolicy.gapSeconds)
    /// Given the end of the last stored segment and the start of a new one, should a new session open?
    public func shouldOpenNewSession(lastSegmentEndedAt: Double?, nextSegmentStartedAt: Double) -> Bool
}

/// Rejects the noise a streaming transducer emits when nobody is talking.
public enum TranscriptFilter {
    /// Trimmed text, or nil if the line should not be stored.
    public static func clean(_ raw: String) -> String?
    /// True when a window is below the speech floor and should never reach the model.
    public static func isSilent(rms: Float, floor: Float = 0.004) -> Bool
}

/// 16-bit PCM helpers, pure and unit-testable.
public enum PCM {
    public static func rms(int16LE data: Data) -> Float
    public static func downmixToMono(interleaved samples: [Float], channels: Int) -> [Float]
    public static func int16LE(from samples: [Float]) -> Data
    public static func floatSamples(int16LE data: Data) -> [Float]
}
```

`TranscriptFilter.clean` drops: empty/whitespace-only text, text with no letter or digit (a silent
window makes Parakeet emit "…"), and single repeated tokens like "AND AND AND" (≥4 identical
consecutive words).

### `Sources/ContextCore/ClaudeConfig.swift` — owner: **registrar agent (pure half)**

```swift
public enum ClaudeConfig {
    public static let serverName = "context-for-claude"

    public static var claudeCodeConfigURL: URL      // ~/.claude.json
    public static var claudeDesktopConfigURL: URL   // ~/Library/Application Support/Claude/claude_desktop_config.json

    /// Merges an `context-for-claude` stdio entry into an existing config document without disturbing
    /// anything else in it. Returns the new document.
    public static func merged(into existing: [String: Any], mcpBinaryPath: String) -> [String: Any]

    /// True when `existing` already points `context-for-claude` at exactly `mcpBinaryPath`.
    public static func isRegistered(in existing: [String: Any], mcpBinaryPath: String) -> Bool

    public static func removed(from existing: [String: Any]) -> [String: Any]
}
```

The entry written into `mcpServers` is exactly:
```json
{ "type": "stdio", "command": "<absolute path>", "args": [], "env": {} }
```
Both surfaces use the same top-level `mcpServers` key. **`~/.claude.json` is a large document with
the user's whole project history in it — merge, never rewrite, and always write atomically via a
temp file + replace so a crash cannot truncate it.** Preserve unknown keys verbatim.

---

## ContextMCPKit

### `Sources/ContextMCPKit/JSONRPC.swift` — owner: **mcp protocol agent**

Line-delimited JSON-RPC 2.0 over stdio (one JSON object per line; that is what Claude Code and
Claude Desktop speak to stdio servers).

```swift
public struct RPCRequest: Sendable { public let id: JSONValue?; public let method: String; public let params: JSONValue? }
public enum JSONValue: Codable, Sendable { case null, bool(Bool), number(Double), string(String),
                                           array([JSONValue]), object([String: JSONValue]) }
public extension JSONValue {
    var stringValue: String? { get }
    var intValue: Int? { get }
    var doubleValue: Double? { get }
    subscript(key: String) -> JSONValue? { get }
}

public enum RPC {
    public static func decode(line: String) -> RPCRequest?
    public static func result(id: JSONValue?, _ value: JSONValue) -> String   // encoded response line
    public static func error(id: JSONValue?, code: Int, message: String) -> String
}
```

### `Sources/ContextMCPKit/Tools.swift` — owner: **mcp tools agent**

```swift
public struct ToolDefinition: Sendable {
    public let name: String
    public let description: String
    public let inputSchema: JSONValue
}

public struct ToolImage: Sendable, Equatable {
    public let base64: String
    public let mimeType: String
}

/// What one call produced: prose, and — for `look` alone — the pixels behind it.
public struct ToolOutput: Sendable, Equatable {
    public var text: String
    public var images: [ToolImage]
}

public enum Tools {
    public static let all: [ToolDefinition]
    /// Executes a tool against the store and returns the payload for the MCP content blocks.
    public static func call(name: String, arguments: JSONValue?, store: ContextStore?) throws -> ToolOutput
}
```

Twelve tools, exact names and parameters:

| name | params |
|---|---|
| `recall` | `query` (string, required), `since` (string, ISO date or relative like `"2 days ago"`), `until` (string), `limit` (int, default 40) |
| `recent` | `minutes` (int, default 30) |
| `conversations` | `since` (string), `until` (string), `limit` (int, default 30) |
| `transcript` | `session_id` (int, required) |
| `screen` | `since` (string), `until` (string), `app` (string), `limit` (int, default 60) |
| `look` | `at` (string, defaults to now), `app` (string), `count` (int, default 1, capped at 3) |
| `activity` | `since` (string, required), `until` (string) |
| `status` | none |
| `get_memories` | `limit` (int), `offset` (int), `sort` (string), `categories` (array) |
| `create_memory` | `content` (string, required), `category` (string) |
| `edit_memory` | `memory_id` (string, required), `content` (string, required) |
| `delete_memory` | `memory_id` (string, required) |

Descriptions must be written **for Claude**, stating when to reach for the tool, e.g.
`recall`: *"Search everything the user has said, heard, or had on screen. Use this whenever the user
refers to people, plans, decisions, or things they have discussed that you have no record of."*

Date parsing: accept ISO-8601, `yyyy-MM-dd`, and relative English (`"30 minutes ago"`, `"2 days ago"`,
`"last week"`, `"today"`, `"yesterday"`). Unparseable input is an explicit tool error, not a silent
`nil`. Put the parser in this file as `public enum DateArg { public static func parse(_ s: String) -> Double? }`.

Output is human-readable **Markdown**, not raw JSON — Claude consumes it far better. Group by day,
one line per hit, prefixed with time and speaker/app. When a result set is empty, say so and say what
the coverage window is, so Claude can distinguish "never happened" from "not captured".

When `store` is nil (database missing), every tool returns a plain sentence explaining that Omi
Context for Claude has not captured anything yet — never an exception.

`look` is the only tool that fills `ToolOutput.images`, and it holds three rules the others cannot
break for it:

- **The stored frame is HEIC and is re-encoded as JPEG** (`FrameImages`), bounded to 1568 px on the
  longest edge. No Claude surface accepts `image/heic`, so an unconverted frame is a rejected
  request, and an unbounded one is a reply with no room left for prose.
- **The prose always states the frame's age**, because MCP's `image` block carries no timestamp. A
  stale frame read as the live screen is the one way this tool can mislead.
- **A frame whose stored text contains `Redaction.marker` is served without its picture**, and says
  so. `Redaction.scrub` has only ever touched text; the screenshot beside a scrubbed string still
  shows the credential in full.

Reads go through `RewindQueries.newestFrames`, keeping that file the only place `frames.imagePath`
is selected. The path is converted into pixels and never leaves the process as a string.

### `Sources/ContextMCPKit/MCPServer.swift` — owner: **mcp protocol agent**

```swift
public final class MCPServer {
    public init(store: ContextStore?)
    /// Reads lines from `input`, writes response lines to `output`. Returns when input closes.
    public func run(input: FileHandle = .standardInput, output: FileHandle = .standardOutput)
    /// Testable single-message path.
    public func handle(line: String) -> String?
}
```

A tool result's `content` array is the text block first, then one `image` block per
`ToolOutput.images` entry (`{"type":"image","data":<base64>,"mimeType":"image/jpeg"}` — raw base64,
never a `data:` URI). Text first is load-bearing: an image block has nowhere to put a timestamp.

Implements `initialize` (`serverInfo` name `"context-for-claude"`, version `"1.0.0"`, capabilities
`{"tools":{}}`, plus one `icons` entry — the app mark as a 128×128 PNG `data:` URI, see
`ServerIcon.swift`), `notifications/initialized` (no response), `tools/list`, `tools/call`, and
`ping`. Unknown methods return JSON-RPC error `-32601`.

`protocolVersion` echoes the client's request when it is one of `"2025-11-25"`, `"2025-06-18"`,
`"2025-03-26"` or `"2024-11-05"`, and falls back to `"2024-11-05"` for anything else or for an
`initialize` that names no version.

### `Sources/ContextMCP/main.swift` — owner: **mcp protocol agent**

Opens `ContextStore(readOnly: true)`, tolerating `notInitialized` by passing `nil`, then
`MCPServer(store:).run()`. Nothing else.

---

## ContextApp

### `Sources/ContextApp/Support/Log.swift` — owner: **support agent**

```swift
public enum ContextLog {
    static func info(_ message: String, _ category: String = "app")
    static func error(_ message: String, _ category: String = "app")
}
```
`os.Logger` with subsystem `ContextPaths.bundleIdentifier` — `com.omi.context-for-claude` for a
release build, `com.omi.context-for-claude.dev` for a developer one, so the two do not interleave
under one predicate — plus a mirror to `/tmp/context-for-claude.log` when
`CONTEXT_DEBUG=1` — that file is how the build/verify loop sees what happened.

### `Sources/ContextApp/Capture/AudioSource.swift` — owner: **mic agent**

```swift
protocol AudioSource: AnyObject {
    /// Chunks are 16 kHz mono Int16 little-endian PCM.
    func start(onChunk: @escaping @Sendable (Data) -> Void, onLevel: @escaping @Sendable (Float) -> Void) async throws
    func stop()
    var isRunning: Bool { get }
}
enum AudioCaptureError: LocalizedError { case noInputDevice, formatUnavailable, ioProcFailed(OSStatus), tapFailed(OSStatus), aggregateFailed(OSStatus) }
```

### `Sources/ContextApp/Capture/MicCapture.swift` — owner: **mic agent**

`final class MicCapture: AudioSource`. Port the approach in
`desktop/macos/Desktop/Sources/AudioCaptureService.swift`: CoreAudio
`AudioDeviceCreateIOProcIDWithBlock` on `kAudioHardwarePropertyDefaultInputDevice` — **not**
`AVAudioEngine**, whose implicit aggregate device degrades Bluetooth A2DP. Downmix stereo to mono by
averaging, `AVAudioConverter` to 16 kHz, clamp to Int16. Install property listeners for default-device
and format changes and rebuild on either. Include the silent-mic watchdog (1 s peak windows; sustained
silence on a live device rebuilds the stack).

Also expose `static func checkPermission() -> Bool` and `static func requestPermission() async -> Bool`
over `AVCaptureDevice` `.audio`.

### `Sources/ContextApp/Capture/SystemAudioCapture.swift` — owner: **system audio agent**

`@available(macOS 14.4, *) final class SystemAudioCapture: AudioSource`. Port
`desktop/macos/Desktop/Sources/SystemAudioCaptureService.swift`: `CATapDescription(stereoGlobalTapButExcludeProcesses: [])`,
`muteBehavior = .unmuted`, `AudioHardwareCreateProcessTap`, then a **private** aggregate device with
`kAudioAggregateDeviceTapListKey` and `kAudioSubTapDriftCompensationKey = 1` (mandatory — without it
all system audio crackles) at `kAudioAggregateDriftCompensationMaxQuality`, `TapAutoStart = true`.
Same 16 kHz mono Int16 output contract. Include `static func primePermission() -> Bool` which creates
and immediately tears down the identical tap so consent fires during onboarding rather than mid-call.

### `Sources/ContextApp/Capture/ScreenWatcher.swift` — owner: **screen agent**

```swift
@MainActor final class ScreenWatcher {
    var onFrame: ((Frame) -> Void)?
    func start(interval: TimeInterval = 3.0)
    func stop()
    var isRunning: Bool { get }
    static func hasPermission() -> Bool
    static func requestPermission()
}
```
ScreenCaptureKit capture of the **active window** (`SCShareableContent.excludingDesktopWindows`,
cached — WindowServer queries are expensive; refresh the cache at most every 5 s), Vision
`VNRecognizeTextRequest` (`.accurate`, `usesLanguageCorrection = true`) for OCR. dHash the frame and
skip OCR when it matches the previous hash — an idle screen must cost nothing. Skip capture when the
frontmost app is a screenshot tool, Mission Control is up, or the screen is locked. Write a JPEG
(quality 0.5, longest side ≤ 1600) into `ContextPaths.framesDirectory(for:)` and set `imagePath`.
Record `appName` and `windowTitle` on every frame even when OCR is skipped.

### `Sources/ContextApp/Transcribe/Transcriber.swift` — owner: **transcription agent**

```swift
actor Transcriber {
    init(source: SegmentSource)
    var onLine: (@Sendable (String, Double, Double) -> Void)?   // text, startEpoch, endEpoch
    func setOnLine(_ handler: @escaping @Sendable (String, Double, Double) -> Void)
    func start() async throws
    func append(_ data: Data)       // 16 kHz mono Int16 LE
    func finish() async
}
```
FluidAudio Parakeet TDT, on-device — **Apple Silicon only**. `Engine` consults
`CaptureHostPolicy.usesLocalSTT` / `HostArchitecture.usesLocalSTT` and never constructs a
`Transcriber` on Intel (cloud `/v4/listen` is the sole ASR there). When local STT is enabled:
`AsrModels.downloadAndLoad(version:)` — `.v2` for English, `.v3` otherwise. Fixed-size windows
drained by a 1 s pump. **A fresh `TdtDecoderState()` per window** — persisting it across windows
makes the transducer loop and Title-Case everything. Use `TranscriptFilter.isSilent(rms:)` to skip
dead windows before the model and `TranscriptFilter.clean` on the output. Model download is ~600 MB
on first run: expose `static var isModelReady: Bool` and `static func prepareModels() async throws`
so onboarding can warm it with progress on Silicon; **Intel onboarding must skip `prepareModels`**.

### `Sources/ContextCore/CaptureHostPolicy.swift` — owner: **engine / platform agent**

```swift
public struct CaptureHostPolicy: Equatable, Sendable {
    public init(isAppleSilicon: Bool)
    public var usesLocalSTT: Bool
    public var screenCaptureInterval: TimeInterval  // 3.0 Silicon / 9.0 Intel
    public static let localSTTFailureStopsCapture: Bool  // always false
    public static func resolvedCloudTranscriptionState(
        socket: CloudSocketSnapshot, isSignedIn: Bool) -> CloudTranscriptionState
    public static func outboundPCMAction(
        phase: CloudOutboundPCMPhase, wantsConnection: Bool, hasLiveTask: Bool)
        -> CloudOutboundPCMAction  // idle+wantsConnection buffers; airgapped always drops
    public static func cloudTranscriptionGapReason(
        usesLocalSTT: Bool, isSignedIn: Bool, cloud: CloudTranscriptionState) -> String?
}
public struct AudioCaptureDecision: Equatable, Sendable {
    public let startLocalSTT: Bool
    public let teardownCaptureOnLocalSTTFailure: Bool  // always false
    public static func make(usesLocalSTT: Bool) -> AudioCaptureDecision
}
```

### `Sources/ContextApp/Engine.swift` — owner: **engine agent**

```swift
@MainActor final class Engine: ObservableObject {
    static let shared: Engine
    @Published private(set) var isCapturing: Bool
    @Published private(set) var pausedReason: String?
    @Published private(set) var capabilities: [CapabilityReport]
    @Published private(set) var todaySeconds: Double
    @Published private(set) var lastLine: String?

    func start()
    func pause()
    func resume()
    func refreshCapabilities()
}
```
Owns `MicCapture`, `SystemAudioCapture`, optional Silicon `Transcriber`s, `ListenSocket` cloud ASR,
`ScreenWatcher`, and the `ContextStore` writer. Starts audio capture **without** awaiting Parakeet;
local STT failure must not tear down devices or the cloud pump. Screen interval from
`HostArchitecture.screenCaptureInterval` (3 s / 9 s). Applies `SessionPolicy` to decide session
boundaries, sets `appHint` from the frontmost app when opening one, and writes `CaptureState` to
the heartbeat file every 30 s and on every state change. `capabilities` is **grouped for the menu
bar and per-TCC-record on the wire**: the published `CaptureState` carries `Permissions.report()`,
never the grouped rows, because a group verdict written under a stream's name is read downstream as
that stream's grant. **Each source fails independently** — a
dead mic must not stop screen capture; record the reason in `pausedReason` and keep the rest alive.
Prunes frames older than 30 days on launch.

### `Sources/ContextApp/Permissions.swift` — owner: **permissions agent**

```swift
enum Capability: String, CaseIterable { case microphone, systemAudio, screen }
extension Capability { var title: String { get }   // the first-person onboarding sentence
                       var settingsPane: String { get } }
enum Permissions {
    static func check(_ c: Capability) -> Bool
    static func request(_ c: Capability) async -> Bool
    static func openSettings(for c: Capability)
    static func report() -> [CapabilityReport]
}
```
Two-stage macOS behaviour: the first request raises the system TCC prompt; a second tap opens the
exact System Settings pane (`x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone`
/ `Privacy_ScreenCapture`). Screen Recording only takes effect after a relaunch — surface that.

### `Sources/ContextApp/Onboarding/SettingsSpotlight.swift` + `PermissionChoreography.swift` — owner: **onboarding agent**

The overlay that guides the user through System Settings: a white dotted boundary around the whole
settings area, a glow on the control to act on, and an animated arrow into it.

```swift
struct ScreenSpace { func appKit(from global: CGRect) -> CGRect?      // CG top-left ⇄ AppKit bottom-left
                     func display(holding: CGRect) -> DisplayGeometry? }
struct ArrowPlan   { static func pointing(at:keepClearOf:within:) -> ArrowPlan
                     static func dragging(from:to:) -> ArrowPlan }
enum PermissionGuidance { case pointing(SettingsSpotlightTarget)   // area + control + gesture
                          case framing(SettingsWindowFrame)        // window only, contents unreadable
                          case instruction(String) }               // words only
enum PermissionOverlay { static func show(for:caption:resolve:); static func confirmGranted(_:); static func hide() }
```

Rules this surface must keep — each of them cost a real defect:

- **Precision degrades; presence does not.** Row → window → words. An arrow is only ever drawn with a
  measured control at the end of it; `PermissionGuidance` is what makes "point approximately"
  unrepresentable. There is no `AXScrollToVisible` on these rows, so a scrolled-away row hides the
  highlight rather than moving it.
- **The Accessibility step cannot use the Accessibility API** — reading the row that grants
  Accessibility requires Accessibility. It runs in `framing`, off `CGWindowListCopyWindowInfo`, which
  needs no grant. Never retry the AX walk while untrusted.
- **Find once, track cheaply.** A full walk is ~270 ms and must run **off the main actor**; the
  tracker re-reads only the window frame and translates. `SpotlightTrackPolicy` owns the schedule.
- **The window rect is the only trustworthy bound.** System Settings answers stale inner frames after
  a resize; clamp every derived rect to the window. `AXWindows` is not promised to contain windows —
  filter on `AXWindow`.
- **White and neutral only, never the accent.** `controlAccentColor` is whatever the user picked and
  can be purple (`INV-UI-1`). Every stroke is white over a dark ribbon so it reads on a light *and* a
  dark System Settings window.
- **Click-through, non-activating, `sharingType = .none`.** The overlay covers a whole display
  including the switch it points at, and this app records the screen.
  `CONTEXT_SPOTLIGHT_CAPTURABLE=1` lifts the capture exclusion for verifying the overlay itself.
- **Reduce Motion** freezes the phase at the still frame rather than removing the guidance.

### `Sources/ContextApp/Integration/ClaudeRegistrar.swift` — owner: **registrar agent (I/O half)**

```swift
enum ClaudeRegistrar {
    struct Result { let claudeCode: Bool; let claudeDesktop: Bool; let message: String }
    static var mcpBinaryPath: String { get }        // Bundle.main/Contents/MacOS/context-for-claude-mcp
    static func register() -> Result
    static func status() -> (claudeCode: Bool, claudeDesktop: Bool)
}
```
Uses `ClaudeConfig` for all document manipulation. Creates the Claude Desktop config directory and
file if absent. Never throws out — a failure becomes `false` plus an explanatory `message`.

`register()` also installs the Claude Code skill and `unregister()` removes it, through
`ClaudeSkill`. Neither may fail the connection over it: the connector works without the skill, and
a `~/.claude/skills` permission problem must not be reported as "I couldn't connect to Claude Code".

### `Sources/ContextCore/ClaudeSkill.swift` — owner: **registrar agent (pure half)**

```swift
public enum ClaudeSkill {
    public static let name: String            // "context-for-claude"
    public static var directoryURL: URL       // ~/.claude/skills/context-for-claude
    public static var documentURL: URL        // .../SKILL.md
    public static let document: String        // YAML frontmatter + Markdown body
    public static var isInstalled: Bool       // content equality, not mere presence
    @discardableResult public static func install() throws -> Bool
    @discardableResult public static func remove() throws -> Bool
}
```

The server's `instructions` reach the main loop; this reaches a **subagent**, which is handed a task
and none of the conversation behind it. Frontmatter `name` must equal the directory name. `install()`
returns false when the document is already current, so registering on every launch does not churn the
file. `remove()` deletes the whole directory, and neither ever touches anything else under
`~/.claude`.

### `Sources/ContextApp/Integration/LoginItem.swift` — owner: **registrar agent**

```swift
enum LoginItem {
    static var isEnabled: Bool { get }
    static func enable() -> Bool     // SMAppService.mainApp.register()
    static func disable()
}
```

### `Sources/ContextApp/ContextApp.swift` — owner: **app shell agent**

`@main struct ContextApp: App` with a single `MenuBarExtra` scene, `.menuBarExtraStyle(.window)`.
`LSUIElement` is **false** in Info.plist: the app launches as a regular app with a Dock icon, and
`ContextAppDelegate` demotes it to `.accessory` at launch for a user who turned the "Show Dock Icon"
row off (`DockPresence` in `Settings/SettingsPreferences.swift`, default **on**). Promotion is the
transition that misbehaves — a promoted app has no menu bar until it is deactivated and reactivated —
so the plist declares the majority shape and only the minority case transitions. The status item is
unaffected either way, so the app has two homes and never loses both. Clicking the Dock icon runs
`applicationShouldHandleReopen`: an unfinished onboarding run first, otherwise the timeline. There is
still no main window and no `WindowGroup`; the scene's `.commands` point ⌘, at `SettingsWindow` and
⌘Q at the same `TerminationOrigin.userAskedToQuit()` + `terminate` pair the menu bar's Quit uses. An
`NSApplicationDelegateAdaptor` registers the bundled fonts (`CTFontManagerRegisterFontsForURL` over
`Contents/Resources/Fonts`), starts `Engine.shared`, and opens `OnboardingWindow` when
`UserDefaults.standard.bool(forKey: "context.onboarded")` is false. Menu bar icon: the eight-dot Omi
mark drawn in code (see `Ink.swift`), faintly animated while capturing.

### `Sources/ContextApp/MenuBar/StatusView.swift` — owner: **menu bar agent**

The whole popover, ~320 pt wide: one status line ("Listening · 3h 12m today" / "Paused"), three
capability rows with live state that open Settings when tapped, a pause/resume button, a line saying
which Claude surfaces are connected, and Quit. Uses `Ink` for every colour and font. No tabs, no
lists, no settings page. That is the entire non-onboarding UI.

### Onboarding — owner: **onboarding agents (three of them)**

- `Sources/ContextApp/Onboarding/Ink.swift` — **design system agent.** Colours, fonts, the stadium
  button, the permission row, the eight-dot mark. Exact values in `docs/design-system.md`.
- `Sources/ContextApp/Onboarding/Backdrop.swift` + `RandomizedText.swift` — **atmosphere agent.**
  The nine-blob gradient and the word-by-word reveal.
- `Sources/ContextApp/Onboarding/OnboardingWindow.swift` + `OnboardingView.swift` — **flow agent.**
  The borderless floating window, the elliptical paper surface it paints, and the four steps.

### `scripts/build.sh` — owner: **build agent**

`swift build -c release` both products, assemble the app bundle, copy `context-for-claude-mcp` into
`Contents/MacOS/`, copy `Resources/Fonts`, generate `Info.plist` (`LSUIElement`, usage strings,
`CFBundleIdentifier`), sign with the resolved identity and the entitlements — **never ad-hoc, which
resets Screen Recording for every Omi app on this machine** — then install to `/Applications`.
Idempotent, and it must not touch `/Applications/Omi.app` or `Omi Beta.app`.

**Which identifiers the build claims follows from which certificate signs it**, and
`scripts/build-identity.sh` is the single owner of that mapping (`scripts/test-build-identity.sh`
drives it; the `context-for-claude-build-identity` manifest check runs it in CI). A Developer ID
Application certificate produces the release identity — `com.omi.context-for-claude`,
`Context for Claude.app`, MCP server `context-for-claude`. Anything else produces the developer
identity — `com.omi.context-for-claude.dev`, `Context for Claude Dev.app`, MCP server
`context-for-claude-dev` — written into the *built* `Info.plist` only, alongside
`CFBundleExecutable`, `CFBundleName` and `CFBundleDisplayName`, which must move with it. The
template keeps the production identifier.

This is not cosmetic. macOS pins the signing certificate inside every TCC grant, so a developer
build answering to the release identifier writes permission records the notarized build can never
satisfy — the System Settings switch reads on while the app is denied, repairable only by
`tccutil reset`. Release-time defence in depth lives in `package-dmg.sh`, whose
`assert_release_signing_authority()` reads the authority chain off the signed bundle, because every
other gate in the pipeline only tests the certificate's *name*.
