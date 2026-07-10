/** Cap for PCM chunks queued while an audio lane is becoming ready (~5s of
 *  16kHz mono int16). Shared by BOTH pre-ready buffers — the renderer's
 *  pre-session queue (usePushToTalk) and the main process's pre-OPEN WebSocket
 *  buffer (omiListen) — so the two windows can't silently diverge. */
export const PCM_PENDING_MAX_BYTES = 16000 * 2 * 5

export type CaptureSource = {
  id: string
  name: string
  thumbnailDataUrl: string
}

export type TranscriptSegment = {
  text: string
  isFinal: boolean
  start: number
  end: number
}

/** One transcript segment as returned by Omi v4/listen. Snake_case to match
 * the wire format verbatim; the renderer maps these into TranscriptLine. */
export type BackendSegment = {
  id?: string
  text: string
  speaker?: string
  speaker_id?: number
  is_user: boolean
  person_id?: string
  start: number
  end: number
}

/** Non-segment messages the v4/listen socket may send (e.g. memory_creating,
 * last_audio_bytes). The renderer logs these; UI surfacing is out of scope. */
export type ListenEvent = {
  type: string
  raw: Record<string, unknown>
}

/** Source-agnostic transcript line used by the recorder UI. `speaker` is set
 * when the backend identifies one (v4/listen segments) and undefined otherwise. */
export type TranscriptLine = {
  /** Stable backend segment id (v4/listen). The same id is re-sent as a segment is
   *  refined / re-emitted around pauses, so consumers can upsert instead of append
   *  to avoid duplicating earlier speech. May be undefined for un-id'd lines. */
  id?: string
  speaker?: string
  text: string
  interim?: boolean
}

export type ConversationPayload = {
  startedAt: number
  endedAt: number
  transcript: string
  source: 'omi-windows'
}

export type ChatMessage = { id?: string; role: 'user' | 'assistant'; content: string }

// Capture modes a recording session can start in. 'mic' = audio only;
// 'screen' = mic + screen capture + system audio (both audio streams
// transcribed independently).
export type CaptureChoice = 'mic' | 'screen'

export type LocalConversation = {
  id: string
  startedAt: number
  endedAt: number
  transcript: string
  createdAt: number
  // 'recording' (default) for captured audio/screen sessions, 'chat' for
  // persisted Omi chat threads. `messages` holds the structured thread for
  // chat conversations (null for recordings).
  kind?: 'recording' | 'chat'
  messages?: ChatMessage[]
  // User-given name. When null/absent a default ("Recording"/"Chat with Omi")
  // is shown instead.
  title?: string | null
}

export type ListenSource = 'mic' | 'system'

/**
 * Which backend transcription pipeline a session uses:
 *  - 'conversation' → `/v4/listen`: the full pipeline (speech profiles, speaker
 *    assignment, memory events) that keeps a per-uid server-side conversation.
 *    Used by continuous mic/screen recording.
 *  - 'ptt' → `/v2/voice-message/transcribe-stream`: transcription-only, NO
 *    conversation lifecycle. Used by the overlay's hold-Space Ask box so separate
 *    holds never share a server-side conversation (which caused an earlier hold's
 *    speech to bleed into the next). Mirrors the macOS app's split. */
export type ListenMode = 'conversation' | 'ptt'

export type ListenStartArgs = {
  sessionId: string
  source: ListenSource
  /** Firebase ID token; main process attaches it as Authorization: Bearer <token>. */
  token: string
  /** BCP-47-ish language code for transcription (e.g. 'en', 'es'). */
  language: string
  /** Backend pipeline to use. Defaults to 'conversation' when omitted. */
  mode?: ListenMode
}

export type ListenMessage =
  | { sessionId: string; kind: 'connected' }
  | { sessionId: string; kind: 'segments'; segments: BackendSegment[] }
  | { sessionId: string; kind: 'event'; event: ListenEvent }
  | { sessionId: string; kind: 'error'; message: string; fatal: boolean }
  | { sessionId: string; kind: 'closed'; code: number; reason: string }

// ───────────────────────── Capture window IPC ─────────────────────────
// The hidden always-alive capture window (renderer #/capture) owns ALL audio +
// Rewind capture; UI windows are pure UI. Commands flow UI window → main →
// capture window; events flow capture window → main → the owning UI window (or a
// broadcast). The main process still owns every WebSocket (omi-listen:*), so
// audio origin (capture window) and transcript destination (any UI window)
// decouple — the listenFeed channel is already sender-agnostic, keyed by
// sessionId. Channels: 'omi-capture:cmd' / 'omi-capture:event'.

/** A command sent from a UI window (or main) to the capture window. */
export type CaptureCommand =
  // Continuous-conversation audio lane (mic or system). Always VAD-gated. sessionId
  // is the same id the UI window opened its listen session under, so the capture
  // window's feed and the UI window's transcript stream share it.
  | { type: 'audio-start'; sessionId: string; source: ListenSource }
  | { type: 'audio-stop'; sessionId: string }
  // Finalize the current always-on live-mic conversation now ("Save now").
  | { type: 'live-finalize' }
  // A UI LiveConversation view mounted/unmounted: when continuousRecording is OFF
  // this triggers a one-off live-mic session so "New" still captures.
  | { type: 'live-view'; active: boolean }
  // Push-to-talk lifecycle (warm mic, release, per-hold capture).
  | { type: 'ptt-warm' }
  | { type: 'ptt-release' }
  | { type: 'ptt-start'; captureId: string; backfillMs: number }
  | { type: 'ptt-drain'; captureId: string }
  | { type: 'ptt-dispose'; captureId: string }
  // A decorative desktop-video session (the screen-record mode's preview stream).
  // `sourceId` is the user-picked capture source; the capture window falls back to
  // the primary screen when it's absent.
  | { type: 'screen-view'; active: boolean; sourceId?: string }
  // The main window's auth transitioned (sign-in/out/account switch). `uid` is the
  // main window's current user id (null when signed out); the capture window
  // reloads itself if its own auth.currentUser disagrees, so its WS auth is always
  // fresh even across an account switch.
  | { type: 'auth-changed'; uid: string | null }

/** A mutation to the shared live-conversation store, emitted by the capture
 *  window as it owns the always-on mic session. UI windows apply these via
 *  liveConversation.applyRemoteOp so the LiveConversation view mirrors the store. */
export type LiveStoreOp =
  | { op: 'reset' }
  | { op: 'status'; status: 'idle' | 'connecting' | 'live' | 'error'; error?: string }
  | { op: 'append'; line: TranscriptLine }
  // The current conversation was finalized/saved; the UI window turns these
  // segments into a pending (optimistically-titled) conversation row.
  | { op: 'saved'; segments: TranscriptLine[] }

/** An event sent from the capture window to a UI window (routed to the owning
 *  window when it carries an owner, else broadcast to all non-capture windows). */
export type CaptureEvent =
  // Live-conversation store mirror (broadcast).
  | { type: 'live'; op: LiveStoreOp }
  // An audio lane's source (mic/system stream) failed (routed to the owner).
  | { type: 'audio-source-error'; sessionId: string; name: string; message: string }
  // Push-to-talk streamed data / lifecycle (routed to the owner).
  | { type: 'ptt-chunk'; captureId: string; pcm: ArrayBuffer }
  | { type: 'ptt-drained'; captureId: string; pcm: ArrayBuffer }
  | { type: 'ptt-capped'; captureId: string }
  | { type: 'ptt-error'; captureId: string; message: string }
  // ~30fps 32-bin waveform snapshots for the PTT visualizer (routed to the owner).
  | { type: 'ptt-levels'; captureId: string; bins: number[] }
  // The capture window was recreated/reloaded — UI windows re-issue their
  // standing commands (live-view, screen-view, an active PTT is abandoned).
  | { type: 'capture-window-restarted' }

/** The minimal surface the waveform visualizer needs from an amplitude source.
 *  A live `AnalyserNode` satisfies it directly (in-window PTT), and the IPC-fed
 *  PTT client provides an adapter that fills `dest` from the latest ptt-levels
 *  frame — so the same Waveform component works whether the mic graph is local or
 *  in the capture window. */
export type WaveformSource = {
  getByteFrequencyData: (dest: Uint8Array) => void
}

export type OmiOverlayApi = {
  /** Subscribe to summon events; callback fires each time the overlay is shown. Returns an unsubscribe fn. */
  onShown: (cb: () => void) => () => void
  /** Ask main to hide the overlay (after the renderer plays its fade-out). */
  hide: () => void
  /** Enable/disable the summon shortcut. Off until onboarding completes; disabling
   *  also hides the overlay if it's open. */
  setEnabled: (enabled: boolean) => void
  /** Report the panel's current content height so main can ease the window height. */
  setHeight: (px: number) => void
  /** Hide the overlay and surface the main window (used by the signed-out prompt). */
  focusMain: () => void
  /** Subscribe to window focus/blur (active=true on focus). Returns an unsubscribe fn. */
  onActiveChange: (cb: (active: boolean) => void) => () => void
  /** Fires just before main hides the overlay, so the renderer can pre-stage its
   *  panel hidden (opacity 0) for a clean fade-in on the next summon. Returns an
   *  unsubscribe fn. */
  onWillHide: (cb: () => void) => () => void
  /** Fires each time the summon shortcut is pressed (broadcast to every window),
   *  so the onboarding shortcut-setup step can light up its keycaps. Returns an
   *  unsubscribe fn. */
  onSummoned: (cb: () => void) => () => void
  /** Rebind the global summon accelerator (Electron accelerator string). Resolves
   *  true if claimed, false if it's taken (main keeps the previous binding). */
  setAccelerator: (accelerator: string) => Promise<boolean>
  /** Temporarily release the global shortcut so the renderer can record raw keys
   *  for a custom shortcut. */
  suspendShortcut: () => void
  /** Re-claim the current accelerator after recording (or cancelling). */
  resumeShortcut: () => Promise<boolean>
  /** Subscribe to the overlay's open/focused state (broadcast to every window),
   *  so the onboarding voice step can switch between "press the hotkey" and "hold
   *  Space". Returns an unsubscribe fn. */
  onVisibilityChange: (cb: (state: OverlayVisibility) => void) => () => void
  /** Tell main a push-to-talk transcript was just captured (called from the
   *  overlay), so it can broadcast it to the onboarding window. */
  notifyVoiceCaptured: () => void
  /** Subscribe to push-to-talk capture events (broadcast to every window).
   *  Returns an unsubscribe fn. */
  onVoiceCaptured: (cb: () => void) => () => void
  /** Tell main the user sent a message from the overlay (typed or spoken), so it
   *  can broadcast it to onboarding. Fired from the overlay's send choke-point. */
  notifyAsked: () => void
  /** Subscribe to overlay "asked" events — any message sent from the bar
   *  (broadcast to every window). Returns an unsubscribe fn. */
  onAsked: (cb: () => void) => () => void
}

/** Overlay window state broadcast to all renderers. `active` = visible & focused. */
export type OverlayVisibility = { open: boolean; active: boolean }

/** Listening state the renderer reports to the tray (drives icon/tooltip/menu).
 *  Mirrors the main-process TrayState in main/trayState.ts. */
export type TrayListeningState = 'idle' | 'listening' | 'paused'

/** The mic record chord and whether the OS accepted its registration. */
export type RecordHotkeyState = { accelerator: string; registered: boolean }

export type OmiBridgeApi = {
  getCaptureSources: () => Promise<CaptureSource[]>
  remapConversationId: (fromId: string, toId: string) => Promise<number>
  insertLocalConversation: (c: LocalConversation) => Promise<void>
  getLocalConversation: (id: string) => Promise<LocalConversation | null>
  listLocalConversations: () => Promise<LocalConversation[]>
  deleteLocalConversation: (id: string) => Promise<void>
  updateLocalConversationTitle: (id: string, title: string) => Promise<void>
  // The mic record chord (default Ctrl+Space, rebindable via setRecordHotkey)
  // fires on channel 'recorder:hotkey' from main; the callback receives the
  // capture mode to toggle ('mic'). Returns an unsubscribe function.
  onRecordHotkey: (cb: (choice: CaptureChoice) => void) => () => void
  // Omi v4/listen WebSocket sessions (main-process owned).
  listenStart: (args: ListenStartArgs) => Promise<void>
  listenStop: (sessionId: string) => Promise<void>
  /** Push a PCM16 chunk for an active listen session. Fire-and-forget. */
  listenFeed: (sessionId: string, pcm: ArrayBuffer) => void
  /** Ask a PTT session to finalize: flush buffered audio and trigger the backend's
   *  endpointing so the trailing transcript segment is emitted promptly. No-op for
   *  'conversation' sessions (v4/listen manages its own endpointing). */
  listenFinalize: (sessionId: string) => void
  /** Subscribe to status/segment/event messages from every listen session. */
  onListenMessage: (cb: (msg: ListenMessage) => void) => () => void
  // --- Capture window bridge (Phase 2) ---
  /** Send a capture command. From a UI window it's forwarded to the hidden
   *  capture window; the capture window itself services them. Fire-and-forget. */
  captureCommand: (cmd: CaptureCommand) => void
  /** Capture window: receive commands forwarded by main. `ownerId` is the
   *  webContents id of the UI window that issued the command (so owned events —
   *  audio errors, PTT — can be routed back to it). Returns an unsubscribe fn. */
  onCaptureCommand: (cb: (cmd: CaptureCommand, ownerId: number) => void) => () => void
  /** Capture window → main: emit an event. Main accepts it ONLY from the capture
   *  window (spoof guard) and routes it to `ownerId` (owned events) or broadcasts
   *  it (live-store / restart). Exposed to all windows but a no-op
   *  from any window other than the capture one. */
  captureEmit: (event: CaptureEvent, ownerId?: number) => void
  /** Subscribe to events from the capture window (audio errors, live-store ops,
   *  PTT chunks/levels). Returns an unsubscribe fn. */
  onCaptureEvent: (cb: (e: CaptureEvent) => void) => () => void
  /** True when OMI_ALLOW_VIRTUAL_MIC=1 — lets test harnesses feed a VB-Cable as
   *  the mic. When false, capture steers away from virtual/loopback default
   *  inputs (see lib/audio acquireMicStream). */
  allowVirtualMic: boolean
  indexFilesScan: () => Promise<FileIndexStatus>
  indexFilesStatus: () => Promise<FileIndexStatus>
  /** Indexed installed apps (Start-Menu shortcuts), newest-modified first. */
  indexFilesApps: (limit?: number) => Promise<IndexedAppRecord[]>
  /** Load the local onboarding knowledge graph. */
  localGraphLoad: () => Promise<KnowledgeGraph>
  /** Upsert nodes/edges (idempotent by id); returns the full graph after write. */
  localGraphUpsert: (
    nodes: OnboardingGraphNode[],
    edges: OnboardingGraphEdge[]
  ) => Promise<KnowledgeGraph>
  /** Clear the local onboarding graph (called once at first onboarding start). */
  localGraphClear: () => Promise<void>
  /** Aggregated local app-usage rows (foreground seconds per app). */
  getAppUsage: () => Promise<AppUsageRecord[]>
  /** Force-persist the in-memory tally now and return the fresh rows. */
  usageFlush: () => Promise<AppUsageRecord[]>
  /** Read/write the foreground-monitor opt-out flag. */
  usageGetSettings: () => Promise<UsageSettings>
  usageSetSettings: (next: UsageSettings) => Promise<UsageSettings>
  // Bulk-delete memories from the main process (survives renderer navigation /
  // reload; paced + backed-off). Renderer supplies the API base, a fresh token,
  // and the ids; progress streams via onMemoriesDeleteProgress.
  memoriesBulkDelete: (args: {
    baseURL: string
    token: string
    ids: string[]
  }) => Promise<{ deleted: number; failed: number; firstError?: string }>
  onMemoriesDeleteProgress: (
    cb: (p: { deleted: number; failed: number; total: number; done: boolean }) => void
  ) => () => void
  // Memory import (3b): parse a pasted ChatGPT/Claude dump into memory strings.
  // The renderer POSTs them to /v3/memories itself (it holds the auth token).
  memoryImportParse: (dump: string) => Promise<string[]>
  // Memory export (3c): write the given memories to a target. Obsidian/file open
  // a native picker in main; Notion uses the user's integration token.
  memoryExportObsidian: (memories: ExportMemory[]) => Promise<MemoryExportResult>
  memoryExportFile: (memories: ExportMemory[]) => Promise<MemoryExportResult>
  memoryExportNotion: (args: {
    token: string
    parentPageId: string
    memories: ExportMemory[]
  }) => Promise<MemoryExportResult>
  // --- Local knowledge graph (M2) ---
  /** Aggregate indexed_files into a digest for synthesis. */
  kgFileIndexDigest: () => Promise<FileIndexDigest>
  /** Full-replace the local graph (clears + inserts). */
  kgSaveGraph: (graph: LocalKnowledgeGraph) => Promise<void>
  kgStatus: () => Promise<LocalKGStatus>
  /** Nodes matching q (label/summary LIKE) plus their incident edges. */
  kgQueryNodes: (q: string, limit?: number) => Promise<LocalKnowledgeGraph>
  /** indexed_files matching q (filename/folder LIKE), optional file_type. */
  kgSearchFiles: (q: string, fileType?: string, limit?: number) => Promise<IndexedFileRecord[]>
  /** Run a single read-only SELECT against the local DB (sqlGuard-validated). */
  kgExecuteSql: (sql: string) => Promise<KgSqlResult>
  // Integrations (3e): read local Windows Sticky Notes for import. The renderer
  // synthesizes the returned note text and writes /v3/memories itself (it holds
  // the auth token).
  readStickyNotes: () => Promise<StickyNotesReadResult>
  // Auth: run the backend-mediated Google OAuth flow in the SYSTEM browser
  // (main owns the loopback callback + token exchange; Google blocks embedded
  // webview OAuth, so there is no in-app popup path). The renderer finishes
  // with signInWithCustomToken on the returned custom token.
  signInWithGoogle: () => Promise<GoogleSignInResult>
  // Integrations (3d): Google OAuth + Gmail/Calendar. Main owns the OAuth grant
  // and REST reads; the renderer synthesizes the returned items and writes
  // /v3/memories + /v1/action-items itself (it holds the Firebase token).
  googleConnect: () => Promise<GoogleStatus>
  googleDisconnect: () => Promise<GoogleStatus>
  googleStatus: () => Promise<GoogleStatus>
  googleGmailFetchNew: () => Promise<FetchNewResult<GmailItem>>
  googleCalendarFetchNew: () => Promise<FetchNewResult<CalendarItem>>
  googleMarkProcessed: (source: GoogleSource, ids: string[]) => Promise<void>
  rewindFrames: (from: number, to: number) => Promise<RewindFrame[]>
  rewindDayBounds: () => Promise<{ min: number; max: number } | null>
  rewindSearch: (query: string) => Promise<RewindSearchGroup[]>
  rewindFrameImage: (imagePath: string) => Promise<string>
  rewindGetSettings: () => Promise<RewindSettings>
  rewindSetSettings: (next: RewindSettings) => Promise<RewindSettings>
  rewindPruneNow: () => Promise<number>
  rewindPrimarySourceId: () => Promise<string | null>
  rewindSaveFrame: (data: Uint8Array) => Promise<{ captured: boolean; reason?: string }>
  onRewindSettings: (cb: (s: RewindSettings) => void) => () => void
  /** Capture the primary screen once and OCR it, returning the recognized text
   *  (or '' on failure/timeout). Used by the chat to read the screen at send time. */
  screenReadText: () => Promise<string>
  insightGetSettings: () => Promise<InsightSettings>
  insightSetSettings: (patch: Partial<InsightSettings>) => Promise<InsightSettings>
  insightAdd: (p: InsightPayload) => Promise<void>
  insightRecent: (limit: number) => Promise<InsightRecord[]>
  /** Engine → main: deliver this insight in the user's chosen style. */
  insightShow: (p: InsightPayload) => void
  /** Toast renderer → main: dismiss now. */
  insightDismiss: () => void
  /** Toast renderer → main: pause/resume the auto-dismiss while hovered. */
  insightHoverStart: () => void
  insightHoverEnd: () => void
  /** Settings → main: deliver an example insight (a test). */
  insightTest: () => void
  /** Toast renderer subscribes to receive the payload to render. */
  onInsightShow: (cb: (p: InsightPayload) => void) => () => void
  perfFirstPaint: () => void
  perfMark: (name: string) => void
  // Animation bench (OMI_ANIM_BENCH): the renderer probe reports a jank summary
  // for the startup entrance animations back to main.
  perfAnimResult: (stats: Record<string, number>) => void
  isAnimBench: boolean
  benchEcho: (x: number) => Promise<number>
  // True only under the perf bench (OMI_BENCH=1). Lets the renderer skip the
  // one-time onboarding gate so the bench mounts the authed shell (a returning
  // user is always onboarded), instead of stalling on the wizard.
  isBench: boolean
  // Whether the desktop-automation bridge is enabled (ON unless OMI_AUTOMATION=0).
  // When false the renderer skips its action-planner pre-step so chat behaves
  // like a normal assistant.
  automationEnabled: boolean
  automationSnapshot: (windowHandle?: string) => Promise<UiSnapshot>
  automationTargetWindow: () => Promise<string | null>
  // Native-dialog consent gate: shows the plan in a Windows dialog and runs it
  // only on approval. `canceled` = user declined; otherwise ok/message. This is
  // the ONLY automation-run path exposed to the renderer (the consent-free
  // `automation:run` handler was removed — it had no legitimate caller).
  automationConfirmRun: (
    plan: AutomationPlan
  ) => Promise<{ ok: boolean; canceled?: boolean; message?: string }>
  onAutomationStep: (cb: (r: StepResult) => void) => () => void
  // Cross-window conversations refresh: a renderer that writes a local
  // conversation calls notifyConversationsChanged(); main broadcasts
  // 'conversations:changed' to ALL windows so each invalidates its own
  // (per-process) conversations cache. Needed because the overlay and main
  // window are separate renderers with independent caches.
  notifyConversationsChanged: () => void
  onConversationsChanged: (cb: () => void) => () => void
  // --- Tray + lifecycle (Phase 1) ---
  /** Report the current listening state so main drives the tray icon/menu/tooltip. */
  trayReportState: (state: TrayListeningState) => void
  /** Tray Pause/Resume clicked — flip the continuousRecording pref, then report
   *  the new state via trayReportState. Returns an unsubscribe fn. */
  onTrayToggleListening: (cb: () => void) => () => void
  /** Tray Settings clicked (the window is already surfaced) — route to Settings.
   *  Returns an unsubscribe fn. */
  onTrayOpenSettings: (cb: () => void) => () => void
  /** Whether the app is set to launch at login, and whether the OS setting is
   *  even writable in this build (`supported` is false in unpackaged dev, where
   *  execPath is the bare electron.exe and a Run entry would be bogus). */
  getLoginItemSettings: () => Promise<{ openAtLogin: boolean; supported: boolean }>
  /** Enable/disable launch-at-login (writes the HKCU Run key via Electron). */
  setLaunchAtLogin: (enabled: boolean) => Promise<void>
  /** Quit for real (sets the quitting flag so windows don't just hide, then quits). */
  quitApp: () => void
  /** An auto-update finished downloading and is staged to install on next quit.
   *  Returns an unsubscribe fn. */
  onUpdateReady: (cb: (info: { version: string }) => void) => () => void
  /** The current mic record chord and whether the OS accepted the registration. */
  getRecordHotkey: () => Promise<RecordHotkeyState>
  /** Rebind the record chord (persisted). Never throws on a conflict — returns
   *  registered=false when the chord is owned by another app. */
  setRecordHotkey: (accelerator: string) => Promise<{ ok: boolean; registered: boolean }>
  /** The update staged for install-on-quit, if any (query on Settings mount —
   *  the one-shot update:ready event usually fires while Settings is unmounted). */
  getPendingUpdate: () => Promise<{ version: string } | null>
  /** Release all global chords while a rebind UI captures raw keys (pressing the
   *  current chord must be captured, not fire the shortcut). Always pair with resume. */
  suspendShortcutCapture: () => void
  resumeShortcutCapture: () => void
  screenSynthFramesSince: () => Promise<ScreenFrameLite[]>
  screenSynthGetState: () => Promise<ScreenSynthState>
  screenSynthSetState: (patch: Partial<ScreenSynthState>) => Promise<ScreenSynthState>
  screenSynthAdvanceWatermark: (ts: number) => Promise<void>
  screenSynthRecordRun: (run: ScreenSynthRun) => Promise<void>
}

// --- Screen activity → memories (Rewind OCR synthesis) ---
// A trimmed Rewind frame sent to the renderer for synthesis (no image bytes).
export type ScreenFrameLite = {
  ts: number
  app: string
  windowTitle: string
  processName: string
  ocrText: string
}

// Persisted synthesis state (main owns it; default OFF / opt-in).
export type ScreenSynthState = {
  enabled: boolean
  watermarkTs: number // last synthesized frame ts; 0 = never run
  lastRunAt: number | null
  lastCount: number // memories created on the last run
  denylist: string[] // app/site keywords to skip when synthesizing screen content
}

export type ScreenSynthRun = { lastRunAt: number; lastCount: number }

// Minimal memory shape the export targets need (the renderer maps its richer
// Memory objects down to this before sending them across the IPC bridge).
export type ExportMemory = {
  content: string
  category?: string | null
  createdAt?: string | null
}

export type MemoryExportResult = {
  // True when the user dismissed the native file/folder picker.
  canceled?: boolean
  count: number
  // File path (Obsidian/file) or page URL (Notion) the export landed at.
  location?: string
}

export type IndexedFileType =
  | 'document'
  | 'code'
  | 'image'
  | 'media'
  | 'archive'
  | 'application'
  | 'other'

export type IndexedFileRecord = {
  path: string
  filename: string
  extension: string
  fileType: IndexedFileType
  sizeBytes: number
  folder: string
  depth: number
  createdAt: number // ms epoch
  modifiedAt: number // ms epoch
  // Resolved .lnk target executable (absolute path), when this row is a shortcut
  // whose target could be read. Join key to AppUsageRecord.exePath.
  targetPath?: string
}

export type FileIndexStatus = {
  filesIndexed: number
  byType: Record<string, number>
  lastRunAt: number | null
  lastDurationMs: number | null
  running: boolean
}

// One indexed installed app, derived from an `indexed_files` row whose
// file_type is 'application'. `modifiedAt` is the shortcut's mtime (ms epoch),
// used as a rough recency/usage proxy by the app ranker.
export type IndexedAppRecord = {
  name: string
  path: string
  modifiedAt: number
  // Resolved .lnk target executable (absolute path). Undefined when the
  // shortcut could not be resolved. Join key to AppUsageRecord.exePath.
  targetPath?: string
}

// --- App usage (foreground-time tracking) ---

export type UsageCategory = 'browser' | 'editor' | 'comms' | 'media' | 'other'

// One aggregated app-usage row from the local app_usage table. Keyed by exe
// path; consumed by appSelection.rankApps to rank apps by real foreground time.
export type AppUsageRecord = {
  exePath: string
  exeName: string
  category: UsageCategory
  totalSeconds: number
  lastUsed: number
  distinctDays: number
}

// Persisted settings for the foreground monitor. `enabled` is the opt-out flag
// (default on); `retentionDays` is how long an app's usage row survives without
// being foregrounded before it's pruned (the feature's only recency control).
export type UsageSettings = {
  enabled: boolean
  retentionDays: number
}

// --- Knowledge graph (Omi backend /v1/knowledge-graph) ---
// camelCase renderer-facing shapes; wire format is snake_case (see knowledgeGraphMap).
export type KGNode = {
  id: string
  label: string
  nodeType: string
  aliases: string[]
  memoryIds: string[]
}

export type KGEdge = {
  id: string
  sourceId: string
  targetId: string
  label: string
  memoryIds: string[]
}

export type KnowledgeGraph = {
  nodes: KGNode[]
  edges: KGEdge[]
}

export type RebuildResult = {
  status: string
  nodesCount: number
  edgesCount: number
}

// --- Local knowledge graph (agent-built, local SQLite local_kg_*) ---
// DISTINCT from the server KGNode/KGEdge above (which carry memoryIds). This is
// the macOS-parity local graph synthesized from indexed_files + memories and
// consumed by the chat pre-step. Never conflate the two mechanisms.
export type LocalKGNodeType =
  | 'project'
  | 'app'
  | 'technology'
  | 'person'
  | 'org'
  | 'interest'
  | 'file_group'
  | 'card' // background-synthesized natural-language overview served to the chat floor

export type LocalKGNode = {
  id: string // `${slug(label)}:${nodeType}` — stable across re-synthesis
  label: string
  nodeType: LocalKGNodeType
  summary: string // one-sentence description; this is what chat reads
  source: 'files' | 'apps' | 'memories' | 'derived'
  createdAt: number
  aliases?: string[] // alternate names the LLM emitted for this entity
  sourceRefs?: string[] // folder paths / memory texts that justify this node
}

export type LocalKGEdge = {
  id: string
  sourceId: string
  targetId: string
  label: string // relationship phrase, e.g. "uses", "written in"
  createdAt: number
}

export type LocalKnowledgeGraph = { nodes: LocalKGNode[]; edges: LocalKGEdge[] }

// --- Onboarding brain-map graph (sandbox/ui; main-process SQLite onboarding_kg_*) ---
// The progressive-reveal onboarding graph builds a small user/language/apps graph
// and persists it. DISTINCT from the chat-KG LocalKGNode above and the server
// KnowledgeGraph — it just happens to share the camelCase node/edge shape.
export type OnboardingGraphNode = {
  id: string
  label: string
  nodeType: string
  aliases?: string[]
}

export type OnboardingGraphEdge = {
  id: string
  sourceId: string
  targetId: string
  label: string
}

// Result of a read-only SELECT run through the chat agent's execute_sql tool.
export type KgSqlResult = { columns: string[]; rows: Record<string, unknown>[] }

export type LocalKGStatus = {
  nodeCount: number
  edgeCount: number
  lastBuiltAt: number | null // max(created_at) over nodes, ms epoch
}

// Aggregated snapshot of indexed_files used to seed synthesis. Apps are listed
// separately from files; byExtension drives deterministic technology nodes.
export type FileIndexDigest = {
  totalFiles: number // non-application files
  byType: Record<string, number> // file_type -> count (excl. application)
  byExtension: Record<string, number> // extension -> count (excl. application)
  topFolders: { folder: string; count: number }[]
  // Recently-active WORKING folders: folders with code/document files modified
  // in the recent window (future-dated files excluded), newest activity first.
  // This is the macOS-style recency signal — what the user is working on NOW —
  // as opposed to topFolders (raw count, which surfaces stale game/media dirs).
  activeFolders: { folder: string; recentCount: number; lastModified: number }[]
  apps: string[] // installed app names
  sampleFiles: string[] // a few notable filenames
}

// --- Integrations: Windows Sticky Notes import (parity 3e) ---

/** One readable Sticky Note (cleaned). `text` is never empty for returned notes. */
export type StickyNote = {
  id: string
  text: string
  updatedAt: number // ms epoch, 0 if unknown
}

export type StickyNotesReadResult = {
  /** false when Sticky Notes / plum.sqlite isn't present on this PC. */
  available: boolean
  notes: StickyNote[]
  /** set on read failure (locked + copy failed, corrupt db, etc.) */
  error?: string
}

// --- Auth: backend-mediated Google sign-in (system browser + loopback) ---

/** Result of the main-process sign-in flow. On ok the renderer completes the
 *  session with firebase signInWithCustomToken(customToken); email/name are
 *  display-only claims decoded (unverified) from the Google id_token. */
export type GoogleSignInResult =
  | { ok: true; customToken: string; email?: string; givenName?: string; familyName?: string }
  | { ok: false; error: string }

// --- Integrations: Google (Gmail + Calendar) OAuth (parity 3d) ---

export type GoogleSource = 'gmail' | 'calendar'

/** Connection status surfaced to Settings. */
export type GoogleStatus = {
  connected: boolean
  email?: string
  /** ms epoch of the most recent successful sync (either source); undefined if never. */
  lastSyncAt?: number
}

/** One Gmail message, metadata only — never the full body. */
export type GmailItem = {
  id: string
  subject: string
  from: string
  snippet: string
  internalDateMs: number
}

/** One upcoming Calendar event. */
export type CalendarItem = {
  id: string
  title: string
  startMs: number
  endMs: number
  location?: string
  description?: string
  updatedMs: number
}

/** Result of a fetch-new call. `ok:false` + error:'not_connected' when no grant. */
export type FetchNewResult<T> = {
  ok: boolean
  items: T[]
  error?: string
}

// --- Windows OCR helper (win-ocr-helper) ---

export type OcrLine = {
  text: string
  x: number
  y: number
  w: number
  h: number
  confidence: number
}
export type OcrResult =
  | { ok: true; fullText: string; lines: OcrLine[] }
  | { ok: false; code: 'NO_LANGUAGE' | 'DECODE_FAILED' | 'HELPER_ERROR'; message?: string }

/** Foreground window info from the Win32 side of the helper. */
export type WindowInfo = { app: string; title: string; pid: number; processName: string }

// --- Rewind: screen-history timeline ---

export type RewindFrame = {
  id?: number
  ts: number // epoch ms
  app: string
  windowTitle: string
  processName: string
  ocrText: string
  imagePath: string
  width: number
  height: number
  indexed: number // 0 = not yet OCR'd, 1 = OCR done
}

export type RewindSearchGroup = {
  id: string
  app: string
  windowTitle: string
  startTs: number
  endTs: number
  frames: RewindFrame[]
  representative: RewindFrame
  matchSnippet: string
}

export type RewindSettings = {
  captureEnabled: boolean
  intervalMs: number
  retentionDays: number
  /** App names to never screenshot (case-insensitive substring match against the
   *  foreground app/process name). Empty = capture everything. */
  excludedApps: string[]
}

// --- Proactive Insights (Rewind OCR → Gemini → acrylic toast) ---
export type InsightCategory = 'productivity' | 'communication' | 'learning' | 'health' | 'other'

// One insight as shown in the toast (mirrors macOS ExtractedInsight).
export type InsightPayload = {
  headline: string // <= 5 words
  advice: string // 1-2 sentences, <= ~100 chars
  reasoning: string
  category: InsightCategory
  sourceApp: string
  confidence: number // 0..1
}

// Stored row (for dedupe; not rendered as a page in v1).
export type InsightRecord = InsightPayload & { id: number; ts: number; dismissed: number }

export type InsightNotificationStyle = 'omi' | 'native'

export type InsightSettings = {
  enabled: boolean // default ON
  intervalMin: number // default 15 (picker offers 15/20/30/60)
  // 'omi' = the in-app acrylic toast (richer, branded); 'native' = a Windows
  // notification (kept in the Action Center). Default 'omi'.
  notificationStyle: InsightNotificationStyle
  denylist: string[]
  lastRunAt: number | null
}

// ───────────────────────── Desktop Automation Bridge ─────────────────────────
// A pruned UI Automation node. `ref` is a stable address resolvable at execute
// time (see protocol.ts encodeRef/decodeRef): "a:<automationId>" or
// "n:<controlType>:<name>".
export interface UiaNode {
  ref: string
  controlType: string
  name: string
  automationId: string
  rect: { x: number; y: number; w: number; h: number }
  patterns: string[] // subset of: invoke, value, selectionItem, toggle
  enabled: boolean
  children?: UiaNode[]
}

export interface UiSnapshotWindow {
  handle: string
  title: string
  processName: string
  rect: { x: number; y: number; w: number; h: number }
}

export type UiSnapshot =
  | { ok: true; window: UiSnapshotWindow; elements: UiaNode[] }
  | { ok: false; code: string; message: string }

// One step in an approved plan. Closed union — the helper rejects unknown types.
export type AutomationStep =
  | { type: 'focus_window'; windowRef: string }
  | { type: 'invoke_element'; elementRef: string }
  | { type: 'set_value'; elementRef: string; value: string }
  | { type: 'select_item'; elementRef: string }
  | { type: 'toggle'; elementRef: string; state: boolean }
  | { type: 'send_keys'; keys: string }
  | { type: 'click'; elementRef?: string; point?: { x: number; y: number } }
  | { type: 'wait_for'; elementRef: string; timeoutMs: number }

export interface AutomationPlan {
  id: string
  summary: string
  targetWindow: string // window title or handle the plan acts on
  steps: AutomationStep[]
}

export type StepStatus = 'running' | 'ok' | 'failed'
export interface StepResult {
  planId: string
  stepIndex: number
  status: StepStatus
  detail?: string
}

export interface PlanRunResult {
  planId: string
  ok: boolean
  failedStepIndex?: number
  message?: string
}
