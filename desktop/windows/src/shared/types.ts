// BYOK provider key types used by the OmiBridgeApi surface below.
import type { ByokEnrollResult, ByokKeys, ByokProvider } from './byok'
import type {
  McpConnectorId,
  McpExportsSnapshot,
  McpConnectResult,
  McpCloudConnectorInfo
} from './mcpExports'

/** Cap for PCM chunks queued while an audio lane is becoming ready (~5s of
 *  16kHz mono int16). Shared by BOTH pre-ready buffers — the renderer's
 *  pre-session queue (usePushToTalk) and the main process's pre-OPEN WebSocket
 *  buffer (omiListen) — so the two windows can't silently diverge. */
export const PCM_PENDING_MAX_BYTES = 16000 * 2 * 5

/** IPC channel main broadcasts on a GPU-process crash (app.on('child-process-gone')
 *  in main/index.ts) so every window's WebGL surfaces can remount. Shared so the
 *  main-side send and the preload-side listener can't silently drift apart. */
export const GPU_CONTEXT_LOST_CHANNEL = 'gpu:context-lost'

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

/** A conversation the assistant's answer cited. Comes from the backend `done:`
 *  payload's `memories` array (typed `MessageConversation` server-side); the
 *  backend has already stripped the matching `[n]` markers from the reply text. */
export type ChatCitation = { id: string; title: string; emoji?: string }

/** A file attached to a sent chat message, as rendered in the thread. `id` is the
 *  server file id (FileChat.id) that was passed in the message's `file_ids`. */
export type ChatAttachment = { id: string; name: string; mimeType: string }

export type ChatMessage = {
  id?: string
  role: 'user' | 'assistant'
  content: string
  /** Files attached to this (user) message. Round-trips through the persisted
   *  messages JSON blob so a reloaded thread can still render them. */
  attachments?: ChatAttachment[]
  // --- Finalized from the terminal `done:` SSE payload (assistant messages only;
  // absent on user messages and on a still-streaming reply). Additive: older
  // persisted rows simply lack them. ---
  /** The server (Firestore) message id — distinct from the local client `id`.
   *  Required to wire rating / report / share, which key off the server id. */
  serverId?: string
  /** Conversations the answer cited (see ChatCitation). */
  citations?: ChatCitation[]
  /** Inline chart payload when the answer produced one. Opaque here — Windows has
   *  no chart UI yet; retained so the data isn't silently dropped. */
  chartData?: unknown
  /** Whether the backend flagged this turn to prompt the user for an NPS rating. */
  askForNps?: boolean
}

/**
 * Cloud-sync outbox state for a local conversation row. The client OWNS retry
 * idempotency (prod ignores client_session_id — a blind re-POST duplicates):
 *
 *   local_only ─▶ pending ─▶ posting ─▶ done
 *                    ▲          │  ╲
 *                    │          ▼   ▼
 *                    └────── failed  unconfirmed ─▶ (dedupe check) ─▶ done │ posting
 *
 *  - 'local_only'  never queued for sync (legacy rows, chats).
 *  - 'pending'     queued; persisted BEFORE the first POST attempt.
 *  - 'posting'     a POST is in flight.
 *  - 'done'        the cloud conversation exists (`cloudId` set).
 *  - 'failed'      the POST definitively failed (an HTTP error response was
 *                  received, so no conversation was created) — safe to re-post.
 *  - 'unconfirmed' AMBIGUOUS failure (timeout / network drop after send): the
 *                  backend may or may not have created the conversation. A retry
 *                  MUST first dedupe against recent cloud conversations
 *                  (started_at/finished_at match) before re-posting.
 * See lib/sync/outbox.ts for the transition rules and dedupe strategy.
 */
export type ConversationSyncState =
  | 'local_only'
  | 'pending'
  | 'posting'
  | 'done'
  | 'failed'
  | 'unconfirmed'

/** One transcript segment in the `/v1/conversations/from-segments` request shape
 * (snake_case matches the wire verbatim). `start`/`end` are WALL-CLOCK
 * session-relative seconds (stream timestamps compress silence out, so they are
 * re-derived at arrival — see lib/sync/segmentRetention.ts). */
export type SyncSegment = {
  text: string
  speaker?: string | null
  speaker_id?: number | null
  is_user: boolean
  person_id?: string | null
  start: number
  end: number
}

/** Outbox transition persisted via updateLocalConversationSync. */
export type ConversationSyncPatch = {
  syncState: ConversationSyncState
  /** Set (or clear with null) the cloud conversation id. Omit to leave as-is. */
  cloudId?: string | null
  /** Set (or clear with null) the last sync error. Omit to leave as-is. */
  syncError?: string | null
  /** Bump sync_attempts by one (set when a POST attempt starts). */
  incrementAttempts?: boolean
}

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
  // --- Cloud-sync outbox (screen recordings only; see ConversationSyncState) ---
  /** Outbox state; absent/'local_only' = never queued (legacy rows, chats). */
  syncState?: ConversationSyncState
  /** Raw merged segments (from-segments wire shape) retained so a retry or
   * backfill can re-POST without the original stream. Null for chats/legacy. */
  segments?: SyncSegment[] | null
  /** Cloud conversation id once synced. */
  cloudId?: string | null
  syncAttempts?: number
  syncError?: string | null
  // --- Track 4: local mirror of the cloud starred/folder fields (additive) ---
  starred?: boolean
  folderId?: string | null
}

export type ListenSource = 'mic' | 'system'

/**
 * Which backend transcription pipeline a session uses:
 *  - 'conversation' → `/v4/listen`: the full pipeline (speech profiles, speaker
 *    assignment, memory events) that keeps a per-uid server-side conversation.
 *    Used by continuous MIC-ONLY recording (a single socket, so the backend's
 *    racy per-uid conversation pointer is safe).
 *  - 'ptt' → `/v2/voice-message/transcribe-stream`: transcription-only, NO
 *    conversation lifecycle. Used by the overlay's hold-Space Ask box so separate
 *    holds never share a server-side conversation (which caused an earlier hold's
 *    speech to bleed into the next). Mirrors the macOS app's split.
 *  - 'transcribe' → same transcribe-stream endpoint as 'ptt', but for the
 *    long-lived SCREEN-session lanes (mic + system). A distinct mode value so the
 *    PTT single-at-a-time supersede logic never kills a screen session. Zero
 *    server-side conversations are created during the session; the client merges
 *    both lanes' segments on stop and POSTs /v1/conversations/from-segments
 *    (see lib/sync/), which makes the two-socket per-uid coalescing race
 *    structurally impossible. */
export type ListenMode = 'conversation' | 'ptt' | 'transcribe'

export type ListenStartArgs = {
  sessionId: string
  source: ListenSource
  /** Firebase ID token; main process attaches it as Authorization: Bearer <token>. */
  token: string
  /** BCP-47-ish language code for transcription (e.g. 'en', 'es'). */
  language: string
  /** Backend pipeline to use. Defaults to 'conversation' when omitted. */
  mode?: ListenMode
  /** Conversation mode only: a client-generated UUID passed to /v4/listen as
   *  `client_conversation_id`. The backend keys the server-side conversation on it,
   *  so a reconnect that re-sends the SAME id RESUMES the same conversation instead
   *  of stranding a half-recorded one. Regenerated per conversation (after each
   *  finalize/silence boundary); re-used across reconnects within one conversation. */
  clientConversationId?: string
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
  // Rebuild the warm mic graph (silent-mic recovery escalation, A7b) — the capture
  // window tears down + reopens getUserMedia with a retry ladder. Fire-and-forget.
  | { type: 'ptt-rebuild' }
  // A decorative desktop-video session (the screen-record mode's preview stream).
  // `sourceId` is the user-picked capture source; the capture window falls back to
  // the primary screen when it's absent.
  | { type: 'screen-view'; active: boolean; sourceId?: string }
  // Echo gate (Phase 6, layer 2): while Omi's voice is audibly playing (realtime
  // session or TTS), the voice surface holds this ACTIVE and every continuous
  // transcription lane in the capture window pauses its feed, so Omi never
  // transcribes itself. The sender owns the timing (including the ~300ms
  // release after the playback buffer drains); the capture window just obeys
  // the final boolean. PTT and the realtime session's own mic are NEVER gated.
  | { type: 'assistant-speaking'; active: boolean }
  // Omi's spoken words, injected into the live record from SOURCE text (the
  // provider's output transcript / the TTS input) instead of re-transcription.
  // `utteranceId` is stable per utterance so re-delivery upserts, not duplicates.
  | { type: 'assistant-utterance'; utteranceId: string; text: string }
  // The main window's auth transitioned (sign-in/out/account switch). `uid` is the
  // main window's current user id (null when signed out); the capture window
  // reloads itself if its own auth.currentUser disagrees, so its WS auth is always
  // fresh even across an account switch.
  | { type: 'auth-changed'; uid: string | null }
  // Meeting detection (Phase 5, sent by MAIN): start/stop the auto-capture
  // session (mic + system lanes) for a detected meeting. Serviced by
  // MeetingSessionHost in the capture window.
  | { type: 'meeting-capture-start'; meetingId: string; appName: string }
  | { type: 'meeting-capture-stop'; meetingId: string }

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
  // `orbLevel` (0..1) is a SEPARATE fast-response loudness for the orb: the bars'
  // `bins` come from a heavily smoothed analyser (springy bars), which lags too
  // much to wave the orb per syllable, so the capture window taps a second
  // low-smoothing analyser just for the orb lane.
  | { type: 'ptt-levels'; captureId: string; bins: number[]; orbLevel?: number }
  // The capture window was recreated/reloaded — UI windows re-issue their
  // standing commands (live-view, screen-view, an active PTT is abandoned).
  | { type: 'capture-window-restarted' }
  // Meeting auto-capture lifecycle, emitted by MeetingSessionHost. Broadcast
  // (and tapped by main's meeting monitor to keep the toast honest).
  | {
      type: 'meeting-capture-status'
      meetingId: string
      status: 'started' | 'error' | 'saved'
      message?: string
    }

/** The minimal surface the waveform visualizer needs from an amplitude source.
 *  A live `AnalyserNode` satisfies it directly (in-window PTT), and the IPC-fed
 *  PTT client provides an adapter that fills `dest` from the latest ptt-levels
 *  frame — so the same Waveform component works whether the mic graph is local or
 *  in the capture window. */
export type WaveformSource = {
  getByteFrequencyData: (dest: Uint8Array) => void
  /** Fast-response loudness 0..1 for the orb, when the source provides one (the
   *  IPC PTT adapter fills it from `ptt-levels.orbLevel`). Absent on a plain
   *  `AnalyserNode`; the orb then falls back to RMS of the frequency bins. */
  getOrbLevel?: () => number
}

export type OmiOverlayApi = {
  /** Subscribe to summon events; callback fires each time the overlay is shown. Returns an unsubscribe fn. */
  onShown: (cb: () => void) => () => void
  /** Ask main to hide the overlay (after the renderer plays its fade-out). */
  hide: () => void
  /** Enable/disable the summon shortcut. Off until onboarding completes; disabling
   *  also hides the overlay if it's open. */
  setEnabled: (enabled: boolean) => void
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
  /** Subscribe to the overlay's open/focused state (broadcast to every window).
   *  NOTE `active` (focused) is only ever true for the EXPANDED bar — a peek/PTT
   *  pill is deliberately non-focusable — so no step may gate its instructions on
   *  it. Returns an unsubscribe fn. */
  onVisibilityChange: (cb: (state: OverlayVisibility) => void) => () => void
  /** Tell main a push-to-talk transcript was just captured (called from the
   *  overlay), so it can broadcast it to the onboarding window. */
  notifyVoiceCaptured: () => void
  /** Subscribe to push-to-talk capture events (broadcast to every window).
   *  Returns an unsubscribe fn. */
  onVoiceCaptured: (cb: () => void) => () => void
  /** Tell main a push-to-talk capture FAILED (mic unavailable, transcription
   *  error): the user performed the gesture but it produced nothing. Broadcast so
   *  onboarding can say what went wrong instead of leaving the step silent. */
  notifyVoiceFailed: (message: string) => void
  /** Subscribe to push-to-talk failures (broadcast to every window). Returns an
   *  unsubscribe fn. */
  onVoiceFailed: (cb: (message: string) => void) => () => void
  /** Tell main the user sent a message from the overlay (typed or spoken), so it
   *  can broadcast it to onboarding. Fired from the overlay's send choke-point. */
  notifyAsked: () => void
  /** Subscribe to overlay "asked" events — any message sent from the bar
   *  (broadcast to every window). Returns an unsubscribe fn. */
  onAsked: (cb: () => void) => () => void
}

/** Overlay window state broadcast to all renderers. `active` = visible & focused. */
export type OverlayVisibility = { open: boolean; active: boolean }

/** Bar presentation modes: peek (edge-hover pill, unfocused, click-through with
 *  interactive islands), expanded (chat, the only focused mode), ptt (expanded
 *  listening for a hotkey hold, unfocused). */
export type BarMode = 'peek' | 'expanded' | 'ptt'
/** What triggered a reveal (hotkey tap/hold — top-edge hover reveal was
 *  removed). Both drive the same entrance motion (slide-in + orb genesis). */
export type BarReveal = 'summon' | 'ptt'

/** A single chat message projected across the bar↔main bridge. Structurally the
 *  renderer's `ChatMsg` (hooks/useChat) — kept here so the shared preload types
 *  don't import renderer code. */
export type BarChatMessage = { id?: string; role: 'user' | 'assistant'; content: string }
/** The bar orb's coarse activity, derived in the main window's ChatBridgeHost:
 *  'sending' while a reply streams, 'speaking' while a spoken (TTS) reply plays. */
export type BarChatStatus = 'idle' | 'sending' | 'speaking'
/** Projected chat state the main window broadcasts to the bar (viewport over the
 *  ONE chat engine — INV-CHAT-1). The bar renders this; it never owns a thread. */
export type BarChatState = {
  messages: BarChatMessage[]
  sending: boolean
  status: BarChatStatus
  /** A delegated coding-agent (ACP) task is running in the shared engine — the
   *  bar orb shows its distinctive 'agents' pose. Absent = false. */
  agentsActive?: boolean
}
/** `token` is a per-reveal monotonic id: the renderer echoes it back via
 *  `showAck` once it has painted the revealed frame, so main can reject a stale
 *  ack from a reveal that was cancelled/superseded (see the paint-ack handshake
 *  in main/bar/window.ts). */
export type BarShowPayload = { mode: BarMode; reveal: BarReveal; token: number }

/** A bar send blocked by the chat usage limit, relayed to the main window (which
 *  owns the shared usage-limit modal and the TTS voice). `spoken` = the blocked
 *  turn came from PTT, so the limit line is answered aloud (Mac speaks it).
 *  `popup` (default true) = raise the shared modal. The blocked-voice send path
 *  sets it false because the pre-capture PTT veto already owns the modal for
 *  voice — mirrors macOS, whose post-transcription voice path speaks without
 *  re-showing the popup. */
export type BarUsageLimitPayload = { message: string; spoken: boolean; popup?: boolean }

/** Low-rate orb-driving projection pushed MAIN → bar during a warm-hub PTT turn
 *  (A5 PR-6b). The main window owns the turn (capture, hub, playback); the bar is
 *  a pure viewport whose orb needs the phase + loudness to animate. NO per-frame
 *  audio is carried — only this coarse state on each reducer transition + a
 *  throttled `orbLevel`. `active:false` tells the bar to fall back to its own local
 *  orb state (today's behavior), so the flag-off path never sees this at all. */
export type VoiceHubBarState = {
  /** A main-owned warm-hub turn currently owns the bar orb. */
  active: boolean
  /** The mic is capturing (the orb's listening/speaking pose). */
  isListening: boolean
  /** Awaiting the hub's response (the orb's thinking pose). */
  isThinking: boolean
  /** The hub is speaking its reply (the orb's response-active pose). */
  isResponseActive: boolean
  /** Latest orb loudness in [0,1] sampled from the main-owned capture. */
  orbLevel: number
  /** Transient status/error hint for the bar (e.g. "Voice response failed — try
   *  again" when a committed hub turn's provider dies mid-reply). Empty when there is
   *  nothing to show. Sourced from the reducer projection; the reducer's `hintVisibility`
   *  deadline clears it (so it auto-dismisses). */
  hint: string
}

/** Renderer bridge for the top-edge bar window (see main/bar/window.ts). */
export type OmiBarApi = {
  /** The bar renderer has mounted + measured — flush any deferred first show. */
  ready: () => void
  /** Per-reveal paint acknowledgement: the renderer has committed a frame with
   *  the revealed state (double-rAF), so main may now show the HWND without
   *  flashing the previous off-screen frame. Echoes the reveal `token`. */
  showAck: (token: number) => void
  /** Slide-out finished; main may hide the window now. */
  requestHide: () => void
  /** Ask main to switch modes (focusability + hit-testing follow). */
  expand: () => void
  collapse: () => void
  /** Interactive-island hit-testing toggle (peek/ptt modes). */
  setInteractive: (interactive: boolean) => void
  /** Keep the summoned pill open (suppress the cursor retract watchdog) while a
   *  PTT hold / streaming reply / spoken answer is in flight; dropped after a
   *  short grace so the pill retracts once the exchange ends. */
  keepAlive: (active: boolean) => void
  /** Send a chat message through the bar→main bridge (the main window's single
   *  chat engine owns the thread). `fromVoice` requests a spoken reply. */
  sendChat: (text: string, fromVoice: boolean) => void
  /** Barge-in: a new PTT hold started — stop Omi's still-playing spoken reply.
   *  The reply plays in the MAIN window (useChat → voiceController), so this hops
   *  over the bar→main bridge; ChatBridgeHost calls interruptCurrentResponse. */
  interruptTts: () => void
  /** A bar send was refused by the chat usage limit. The shared UsageLimitPopup
   *  and TTS playback both live in the MAIN window, so the bar hops over the
   *  bridge; ChatBridgeHost raises the popup (and speaks `message` for a voice
   *  turn). Mac parity: the modal always shows on the main window, even when the
   *  block came from the floating bar. */
  notifyUsageLimit: (payload: BarUsageLimitPayload) => void
  /** Ask the main window to (re)broadcast the current chat state — called on
   *  mount / each reveal so the bar shows the ongoing thread. */
  requestChatState: () => void
  /** Projected chat state pushed from the main window (history + streaming +
   *  status). Returns an unsubscribe fn. */
  onChatState: (cb: (state: BarChatState) => void) => () => void
  onShow: (cb: (p: BarShowPayload) => void) => () => void
  onMode: (cb: (mode: BarMode) => void) => () => void
  onWillHide: (cb: () => void) => () => void
  /** Summon-hotkey physical hold state, driven by main's gesture machine.
   *  'down' arms the existing PTT machine; 'up' releases it. */
  onPtt: (cb: (phase: 'down' | 'up') => void) => () => void
  /** Warm-hub PTT (A5 PR-6b, gated on `pttHubEnabled`): a bar hold delegates the
   *  turn to the MAIN window's warm-hub driver instead of running the local
   *  cascade. `backfillMs` is the pre-roll the main-owned capture should include
   *  (time since the physical key-down). Sent ONLY when the flag is on — flag off,
   *  the bar never calls these and its local cascade path is byte-for-byte today's. */
  voiceHubBegin: (payload: { backfillMs: number }) => void
  /** Hub hold released — the main driver finalizes + commits the turn. */
  voiceHubEnd: () => void
  /** Hub hold aborted (Esc / focus loss) — the main driver cancels the turn. */
  voiceHubCancel: () => void
  /** Projected warm-hub turn state pushed from the MAIN window, so the bar orb
   *  animates during a main-owned turn (no per-frame audio crosses — just the low-
   *  rate orb level + phase). `active:false` ⇒ the bar uses its local orb state. */
  onVoiceHubState: (cb: (state: VoiceHubBarState) => void) => () => void
  /** Screen-share privacy toggle (persisted in main's app settings). */
  getContentProtection: () => Promise<boolean>
  setContentProtection: (enabled: boolean) => Promise<boolean>
}

// --- Halo overlay (main/glow/*) -----------------------------------------------
//
// The halo is a GENERIC capability: "draw a soft glowing ring around the user's
// active window". The window, geometry, gates, park pattern and follow-tick know
// nothing about WHY it is being drawn — the caller picks an appearance. Focus is
// simply the first caller; a recording indicator or a listening cue would be a new
// preset (a data change), not a change to any of the machinery.

/** How a halo LOOKS — colour-agnostic. `hues` are three neighbouring tones as
 *  space-separated RGB channels ("239 68 68"); the ring cross-fades between them
 *  so it breathes. `intensity` is the envelope's peak opacity. */
export type GlowPaint = {
  hues: [string, string, string]
  intensity: number
}

/** Named appearances. Adding one is a data change in main/glow/glowPresets.ts —
 *  no window, geometry or renderer code moves. */
export type GlowPresetName = 'distracted' | 'focused'

/** One halo run. `pad` (the ring's inset inside the overlay window), `overlap`
 *  (how far the ring is pulled INSIDE the target's edge) and `radius` (0 when the
 *  target's own corners are square — Win11 doesn't round maximized or snapped
 *  windows) are computed in main from the target's real geometry, so the renderer
 *  never guesses. `maximized` tells the ring that its outward glow is
 *  off-screen/under the taskbar and only its inset layers will be visible.
 *  `token` is echoed back via `showAck` once the ring has painted. */
export type GlowShowPayload = {
  paint: GlowPaint
  runId: number
  token: number
  pad: number
  overlap: number
  radius: number
  maximized: boolean
}

/** Renderer bridge for the halo window (see main/glow/glowWindow.ts). */
export type OmiGlowApi = {
  /** The halo renderer has mounted — flush any deferred show. */
  ready: () => void
  /** Paint acknowledgement: the ring's first frame is composited, so main may
   *  unpark the window without flashing the previous (stale) frame. */
  showAck: (token: number) => void
  /** Draw a halo around the active window in the named appearance. This is the
   *  Focus assistant's entry point (and today, the dev/QA trigger). */
  trigger: (preset: GlowPresetName) => void
  dismiss: () => void
  getCurrent: () => Promise<{ preset: GlowPresetName; runId: number } | null>
  onShow: (cb: (p: GlowShowPayload) => void) => () => void
  onHide: (cb: () => void) => () => void
}

/** Listening state the renderer reports to the tray (drives icon/tooltip/menu).
 *  Mirrors the main-process TrayState in main/trayState.ts. */
export type TrayListeningState = 'idle' | 'listening' | 'paused'

/** The mic record chord and whether the OS accepted its registration. `enabled`
 *  is whether the chord is registered at all: the Record card (only) lets the user
 *  turn it fully off (default Ctrl+Space collides with the Windows IME switch), and
 *  main leaves it unregistered while off. The summon path reuses this shape and
 *  does not populate `enabled` (its card has no Off affordance) — hence optional;
 *  consumers must treat `undefined` as enabled (`enabled !== false`). */
export type RecordHotkeyState = { accelerator: string; registered: boolean; enabled?: boolean }

/** Outcome of a manual "check for updates" from Settings → About.
 *  - `unsupported`: the updater is inert (unpackaged dev build) — updates install
 *    automatically only in packaged builds, so there is nothing to check.
 *  - `checking`: a check was kicked off (electron-updater downloads in the
 *    background and stages install-on-quit; progress arrives via update:ready).
 *  - `up-to-date`: the feed reported no newer version than the running build.
 *  - `update-available`: a newer version exists and is downloading/queued.
 *  - `error`: the check failed (offline, feed 404, bad signature…) — non-fatal. */
export type UpdateCheckResult = {
  status: 'unsupported' | 'checking' | 'up-to-date' | 'update-available' | 'error'
  /** Newer version string when `update-available`; the running version otherwise. */
  version?: string
  /** Human-readable failure reason when `error`. */
  message?: string
}

/** Result of an in-app Stripe Checkout flow (main/billing/checkoutWindow). */
export type CheckoutOutcome = 'success' | 'cancel' | 'closed'

/** A file chosen for chat attachment. Produced in the main process by the native
 *  file picker (`chat:openFiles`, which reads the bytes) or built in the renderer
 *  from a drag-drop `File`. `path` is only set for the picker path. `bytes` is
 *  null when the main process skipped reading an over-cap file, so the pending
 *  state layer can reject it with a reason instead of main ever loading it. */
export type PickedChatFile = {
  path?: string
  name: string
  mimeType: string
  size: number
  bytes: Uint8Array | null
}

export type OmiBridgeApi = {
  getCaptureSources: () => Promise<CaptureSource[]>
  remapConversationId: (fromId: string, toId: string) => Promise<number>
  insertLocalConversation: (c: LocalConversation) => Promise<void>
  getLocalConversation: (id: string) => Promise<LocalConversation | null>
  listLocalConversations: () => Promise<LocalConversation[]>
  deleteLocalConversation: (id: string) => Promise<void>
  updateLocalConversationTitle: (id: string, title: string) => Promise<void>
  /** Persist an outbox transition for a local conversation (cloud sync). */
  updateLocalConversationSync: (id: string, patch: ConversationSyncPatch) => Promise<void>
  /** Atomically claim a row for POSTing (pending/failed/unconfirmed → posting).
   *  Returns true iff this call won the claim; the compare-and-swap that keeps a
   *  stale-snapshot second driver from re-POSTing. `resetAttempts` restarts the
   *  attempt counter (manual re-sync of a wedged row). */
  claimConversationForPosting: (id: string, resetAttempts?: boolean) => Promise<boolean>
  // --- Track 4: conversation folders / starred (local cache + mirror) ---
  /** Cached folders for instant paint (ordered), reconciled from /v1/folders. */
  listConversationFolders: () => Promise<ConversationFolder[]>
  /** Replace the whole folder cache from a backend fetch. */
  replaceConversationFolders: (folders: ConversationFolder[]) => Promise<void>
  /** Optimistic single-folder upsert (create/edit) before the reconcile lands. */
  upsertConversationFolder: (folder: ConversationFolder) => Promise<void>
  /** Drop a folder from the cache (optimistic delete). */
  deleteConversationFolder: (id: string) => Promise<void>
  // --- PR8: LiveNotes (AI + manual notes during a live recording; local-only) ---
  /** Persist the session anchor when a recording starts (idempotent on id). */
  createTranscriptionSession: (session: {
    id: string
    startedAt: number
    createdAt: number
  }) => Promise<void>
  /** Insert one note (AI or manual). Always an INSERT — never overwrites a row. */
  createLiveNote: (note: LiveNote) => Promise<void>
  /** Update a note's text (explicit user edit). */
  updateLiveNote: (id: string, text: string, updatedAt: number) => Promise<void>
  /** Delete a note (explicit user delete). */
  deleteLiveNote: (id: string) => Promise<void>
  /** All notes for a session, oldest-first (crash-recovery reload). */
  listLiveNotes: (sessionId: string) => Promise<LiveNote[]>
  // --- Track 2: Voice & PTT depth (voice turn outbox) ---
  /** Enqueue (idempotent UPSERT on idempotencyKey) a voice turn for durable
   *  delivery. A re-enqueue for the same key updates the assistant text /
   *  interrupted flag (a barge-in follow-up) rather than inserting a duplicate. */
  insertVoiceTurn: (entry: VoiceTurnOutboxInput) => Promise<void>
  /** Pending turns oldest-first (created_at ascending), to preserve the
   *  single-writer drain ordering. Optional cap on rows returned. */
  listPendingVoiceTurns: (limit?: number) => Promise<VoiceTurnOutboxEntry[]>
  /** Delete the row on a positive kernel ack (Mac deletes on ack). */
  markVoiceTurnAcked: (idempotencyKey: string) => Promise<void>
  /** Record a failed delivery attempt: bumps attempts, stores the last error. */
  recordVoiceTurnFailure: (idempotencyKey: string, error: string) => Promise<void>
  /** Sign-out teardown: delete every user-scoped local table (conversations,
   *  captions, local KG, rewind frames, app usage, insights, indexed files) so a
   *  different account on this machine starts clean. */
  wipeUserData: () => Promise<void>
  // The mic record chord (default Ctrl+Space, rebindable via setRecordHotkey)
  // fires on channel 'recorder:hotkey' from main; the callback receives the
  // capture mode to toggle ('mic'). Returns an unsubscribe function.
  onRecordHotkey: (cb: (choice: CaptureChoice) => void) => () => void
  // Fires when the GPU process crashes/resets (main broadcasts on
  // child-process-gone type=GPU). Every live WebGL context is lost but the
  // renderer survives, so WebGL surfaces (the brain map) and already-decoded
  // brand images can be left broken; listeners remount/re-decode to recover.
  // Returns an unsubscribe function.
  onGpuContextLost: (cb: () => void) => () => void
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
  /** True when OMI_E2E=1 — renderer-side test hooks (e.g. window.__omiVoice)
   *  attach only in harness runs, never in production. */
  e2e: boolean
  /** True when OMI_E2E_FAKE_AUTH=1 — the shell E2E injects an offline fake user
   *  so the authed `/*` shell mounts on the real production build. A dedicated
   *  flag (never set by the app), so it can never activate in normal use. */
  e2eFakeAuth: boolean
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
  /** Read/write "Screen Sharing in Chat" (default ON) — the consent gate for the
   *  model-invoked capture_screen tool. Returns the stored value. */
  getChatScreenshotSharing: () => Promise<boolean>
  setChatScreenshotSharing: (enabled: boolean) => Promise<boolean>
  /** Open a Stripe Checkout URL in a modal in-app window; resolves when the flow
   *  completes ('success'/'cancel' at the backend redirect) or the user closes it
   *  ('closed'). Only displays Stripe's hosted page — completes no payment. */
  openCheckout: (url: string) => Promise<CheckoutOutcome>
  /** Open a web URL (e.g. the Stripe customer portal) in the system browser. */
  openExternalUrl: (url: string) => Promise<boolean>
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
  // --- Track 3 (AI user profile) ---
  // Once-daily synthesized "about the user" doc, generated + stored + synced in
  // the main process. The renderer pushes a session (Firebase token + base URLs)
  // since the token lives renderer-side, and drives generation.
  aiProfileSetSession: (
    session: { apiBase: string; desktopApiBase: string; token: string } | null
  ) => Promise<void>
  aiProfileGenerateNow: (session?: {
    apiBase: string
    desktopApiBase: string
    token: string
  }) => Promise<AiUserProfileRecord>
  aiProfileGetLatest: () => Promise<string | null>
  aiProfileEdit: (id: number, text: string) => Promise<void>
  aiProfileDelete: (id: number) => Promise<void>
  aiProfileDeleteAll: () => Promise<void>
  // --- Track 3 (task sync engine) ---
  // Local-first tasks: every read/write goes through main (which owns local SQLite
  // + backend REST). Reads return the LOCAL rows instantly and kick a background
  // sync; subscribe to `onTasksChanged` to re-fetch when the store updates.
  tasksListIncomplete: (opts?: { limit?: number; offset?: number }) => Promise<ActionItemRecord[]>
  tasksListCompleted: (opts?: { limit?: number; offset?: number }) => Promise<ActionItemRecord[]>
  tasksListDeleted: (opts?: { limit?: number; offset?: number }) => Promise<ActionItemRecord[]>
  tasksDashboardSlices: () => Promise<TaskDashboardSlices>
  tasksCreate: (fields: TaskCreateFields) => Promise<ActionItemRecord>
  tasksToggle: (args: { backendId: string; completed: boolean }) => Promise<void>
  tasksUpdate: (args: { backendId: string; fields: TaskUpdateFields }) => Promise<void>
  tasksDelete: (args: { backendId: string }) => Promise<void>
  tasksReconcile: () => Promise<void>
  /** main → renderer: the local task store changed (optimistic write or a
   *  background sync landed). Returns an unsubscribe fn. */
  onTasksChanged: (cb: () => void) => () => void
  /** Manual goal generation phase 1 (the Goals "Suggest" button). Client-side:
   *  assembles the on-device context bundle and generates ONE candidate goal via
   *  the Gemini proxy — WITHOUT creating it. The renderer previews the candidate;
   *  on accept it calls goalsCreateCandidate. Returns the candidate or a skip. */
  goalsGenerateCandidate: () => Promise<GoalCandidateResult>
  /** Manual phase 2: create the goal the user accepted from the preview. */
  goalsCreateCandidate: (candidate: GoalCandidate) => Promise<GoalGenerateResult>
  /** The "Automatically suggest goals" setting (Settings → Proactive insights). */
  goalsGetAutoGeneration: () => Promise<boolean>
  goalsSetAutoGeneration: (enabled: boolean) => Promise<boolean>
  /** main → renderer: a goal was created/removed (auto-gen or manual). Re-fetch. */
  onGoalsChanged: (cb: () => void) => () => void
  /** Dev/QA only: force one Focus analysis of the latest frame. Resolves
   *  `{ ok:false, reason:'no-frame' }` when nothing has been captured yet, and
   *  the handler is absent entirely on production builds. */
  focusAnalyzeNow: () => Promise<{ ok: boolean; reason?: string }>
  /** Dev/QA only: run the REAL Insight Phase-1 activity aggregate over the last 24h
   *  with `denylist` and return ONLY the distinct app names (never OCR/titles).
   *  Proves a denylisted app is excluded at the SQL layer. Absent in production. */
  insightDebugActivity: (denylist: string[]) => Promise<{ apps: string[]; rowCount: number }>
  /** Dev/QA only: run the REAL execute_sql closure with `denylist` and return ONLY
   *  the row count (or a content-free error). Proves the denylist CTE-shadow filters
   *  a denylisted app to zero rows. Absent in production. */
  insightDebugSql: (
    query: string,
    denylist: string[]
  ) => Promise<{ rowCount: number; error?: string }>
  /** Dev/QA only: optionally apply a notifications patch, then return the REAL
   *  insightAssistant.isEnabled() and the inputs deciding it. Absent in production. */
  insightDebugIsEnabled: (patch?: {
    notificationsEnabled?: boolean
    notificationFrequency?: number
  }) => Promise<{
    isEnabled: boolean
    insightEnabled: boolean
    notificationsEnabled: boolean
    notificationFrequency: number
  }>
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
  // Chat attachments: open a native multi-select file picker and read the chosen
  // files' bytes in main. The renderer uploads them to /v2/files itself (it holds
  // the auth token). Over-cap files come back with `bytes: null` so the renderer
  // can reject them without main ever loading a huge file.
  openChatFiles: () => Promise<PickedChatFile[]>
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
  // X (Twitter) connector — main runs the poll; the renderer relays the session.
  xStatus: (session: XConnectorSession) => Promise<XStatus>
  xConnect: (session: XConnectorSession) => Promise<XRunState>
  xRunState: () => Promise<XRunState>
  xSync: (session: XConnectorSession) => Promise<XSyncResult>
  xDisconnect: (session: XConnectorSession) => Promise<{ success: boolean }>
  onXProgress: (cb: (state: XRunState) => void) => () => void
  rewindFrames: (from: number, to: number) => Promise<RewindFrame[]>
  /** A day's frames, evenly down-sampled to ~500 (macOS parity). The day-scoped
   *  timeline loads through this; `rewindFrames` stays the unsampled primitive for
   *  the small incremental live-append on today. */
  rewindFramesSampled: (from: number, to: number) => Promise<RewindFrame[]>
  rewindDayBounds: () => Promise<{ min: number; max: number } | null>
  /** Total captured frames, all time — a COUNT(*), not a row fetch. */
  rewindFrameCount: () => Promise<number>
  /** Phase 1 of a Rewind search: KEYWORD (FTS5/BM25) results, immediately. Never
   *  waits on the network — semantic hits follow on `onRewindSearchResults`. */
  rewindSearch: (query: string) => Promise<RewindSearchGroup[]>
  /** Phase 2: the same result list with semantic hits merged in, delivered if and
   *  when the embedding round-trip lands. Never fires when semantic search is
   *  unavailable (signed out, backend down, nothing indexed) — the keyword results
   *  from `rewindSearch` simply stand. Callers must ignore a payload whose `query`
   *  is not the one they are currently showing. */
  onRewindSearchResults: (
    cb: (r: { query: string; groups: RewindSearchGroup[] }) => void
  ) => () => void
  /** Relay the Firebase session to the main-process Rewind embedding indexer
   *  (Track 4); null on sign-out. Without it, semantic search stays inert and
   *  `rewindSearch` returns keyword-only results. */
  rewindSetEmbedSession: (
    session: { desktopApiBase: string; token: string } | null
  ) => Promise<void>
  rewindFrameImage: (imagePath: string) => Promise<string>
  // --- Track 4 --- per-line OCR bounding boxes (normalized 0..1) for the
  // on-image search highlight overlay in the Rewind frame viewer.
  rewindFrameOcrLines: (frameId: number) => Promise<OcrLine[]>
  rewindGetSettings: () => Promise<RewindSettings>
  rewindSetSettings: (next: RewindSettings) => Promise<RewindSettings>
  rewindPruneNow: () => Promise<number>
  /** Recovery affordance: re-create rewind_frames rows for the JPEGs still on disk
   *  after a whole-DB reset/recovery wiped them. Only INSERTs missing rows (never
   *  deletes, idempotent). Resolves to the number of rows rebuilt. */
  rewindRebuildIndex: () => Promise<number>
  rewindPrimarySourceId: () => Promise<string | null>
  rewindSaveFrame: (data: Uint8Array) => Promise<{ captured: boolean; reason?: string }>
  onRewindSettings: (cb: (s: RewindSettings) => void) => () => void
  /** Runtime capture directive (pause + effective cadence) the main process derives
   *  from OS power/lock state; the capture host prefers it over the base interval. */
  rewindGetCaptureDirective: () => Promise<RewindCaptureDirective>
  onRewindCaptureDirective: (cb: (d: RewindCaptureDirective) => void) => () => void
  /** Capture the primary screen once and OCR it, returning the recognized text
   *  (or '' on failure/timeout). Used by the chat to read the screen at send time. */
  screenReadText: () => Promise<string>
  /** What happened to omi.db at startup — whether it was found corrupt and had to
   *  be repaired or reset. Read once on mount to tell the user. */
  dbRecoveryStatus: () => Promise<DbRecoveryStatus>
  /** Main → renderer: a live query just raised a database-corruption error. The
   *  repair can only run at startup, so the UI asks the user to restart. */
  onDbCorruptionDetected: (cb: () => void) => () => void
  /** Restart the app (used by the corruption prompt). */
  relaunchApp: () => void
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
  // --- Meeting detection (Phase 5) ---
  meetingGetSettings: () => Promise<MeetingSettings>
  /** Toast renderer → main: fetch the pending meeting toast payload on mount
   *  (a push can arrive before the React subscription exists). */
  meetingGetToast: () => Promise<MeetingToastPayload | null>
  meetingSetSettings: (patch: Partial<MeetingSettings>) => Promise<MeetingSettings>
  /** Toast renderer → main: a meeting-toast button was clicked. */
  meetingAction: (meetingId: string, action: MeetingToastAction) => void
  /** Toast renderer subscribes to meeting toast payloads. */
  onMeetingToast: (cb: (p: MeetingToastPayload) => void) => () => void
  // --- What's new (Phase 8) ---
  /** Toast renderer subscribes to post-update what's-new payloads. */
  onWhatsNewToast: (cb: (p: WhatsNewPayload) => void) => () => void
  /** Toast renderer → main: fetch the pending what's-new payload on mount. */
  whatsNewGetPending: () => Promise<WhatsNewPayload | null>
  /** Toast renderer → main: open the GitHub release notes in the browser. */
  whatsNewOpenNotes: () => void
  /** Open Windows Settings → Privacy & security → Microphone (denied-mic recovery
   *  in onboarding). Fixed `ms-settings:` target, no caller-supplied URL. */
  openMicPrivacySettings: () => void
  /** The REAL Windows microphone permission, read from the Capability Access Manager
   *  registry in main. `navigator.permissions.query` is NOT usable for this — Electron
   *  answers 'granted' unconditionally, so onboarding used to false-grant the mic step.
   *  'unknown' = never set / unreadable, and must be treated as NOT granted. */
  getMicPermissionState: () => Promise<MicPermissionState>
  perfFirstPaint: () => void
  perfMark: (name: string) => void
  /** True when the main window was created with the Win11 Mica background
   *  material (22H2+). The renderer sets data-mica on the root so the canvas
   *  goes translucent; flat solid fallback everywhere else. */
  micaEnabled: boolean
  // Animation bench (OMI_ANIM_BENCH): the renderer probe reports a jank summary
  // for the startup entrance animations back to main.
  perfAnimResult: (stats: Record<string, number>) => void
  isAnimBench: boolean
  benchEcho: (x: number) => Promise<number>
  // True only under the perf bench (OMI_BENCH=1). Lets the renderer skip the
  // one-time onboarding gate so the bench mounts the authed shell (a returning
  // user is always onboarded), instead of stalling on the wizard.
  isBench: boolean
  // True only in the E2E harness (OMI_E2E=1) — gates renderer-side test hooks.
  isE2E: boolean
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
  // --- Track 2 A4: system-audio mute during PTT capture ---
  // Fire-and-forget (never awaited): the PTT hold path must never wait on the
  // native helper. Mute is gated renderer-side on the pttMuteSystemAudio pref;
  // restore is unconditional so a mute is ALWAYS undone, even on error paths.
  muteSystemAudio: () => void
  restoreSystemAudio: () => void
  // Cross-window conversations refresh: a renderer that writes a local
  // conversation calls notifyConversationsChanged(); main broadcasts
  // 'conversations:changed' to ALL windows so each invalidates its own
  // (per-process) conversations cache. Needed because the overlay and main
  // window are separate renderers with independent caches.
  notifyConversationsChanged: () => void
  onConversationsChanged: (cb: () => void) => () => void
  // --- Bar chat bridge (main-window side; the bar is a viewport, INV-CHAT-1) ---
  /** The bar sent a message — the main window's ChatBridgeHost drives the ONE
   *  chat.send() (with fromVoice). Main-window renderer only. */
  onBarChatSend: (cb: (payload: { text: string; fromVoice: boolean }) => void) => () => void
  /** A bar PTT hold started — the main window barge-in: ChatBridgeHost calls
   *  voiceController.interruptCurrentResponse(). Main-window renderer only. */
  onBarChatInterrupt: (cb: () => void) => () => void
  /** A bar send was refused by the chat usage limit — ChatBridgeHost raises the
   *  shared UsageLimitPopup here (and speaks the line for a voice turn).
   *  Main-window renderer only. */
  onBarUsageLimit: (cb: (payload: BarUsageLimitPayload) => void) => () => void
  /** The bar (re)requested current chat state — ChatBridgeHost publishes now. */
  onBarRequestChatState: (cb: () => void) => () => void
  /** Broadcast the projected chat state to the bar (history + streaming + status). */
  publishChatState: (state: BarChatState) => void
  // --- Warm-hub PTT driver (main-window side; A5 PR-6b, gated on pttHubEnabled) ---
  /** A bar hold delegated its turn to the main-window warm-hub driver. Payload is
   *  the pre-roll backfill ms. Main-window renderer only. */
  onVoiceHubBegin: (cb: (payload: { backfillMs: number }) => void) => () => void
  /** The delegated hold was released — finalize + commit the main-owned turn. */
  onVoiceHubEnd: (cb: () => void) => () => void
  /** The delegated hold was aborted — cancel the main-owned turn. */
  onVoiceHubCancel: (cb: () => void) => () => void
  /** The machine resumed from sleep / unlocked — refresh the (likely-zombie) warm hub
   *  socket so the next PTT press isn't the one that discovers the dead session (A7c
   *  item E). Main-window renderer only. */
  onVoiceHubWake: (cb: () => void) => () => void
  /** Push the projected warm-hub turn state to the bar orb (main → bar). */
  publishVoiceHubState: (state: VoiceHubBarState) => void
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
  /** Turn the record chord fully on/off (Record card's "Off" chip). Off leaves it
   *  unregistered so the OS releases Ctrl+Space; on re-registers the stored chord
   *  (returns registered=false if now held by another app). Returns the fresh state. */
  setRecordHotkeyEnabled: (enabled: boolean) => Promise<RecordHotkeyState>
  /** The current floating-bar summon chord and whether the OS accepted it. Same
   *  shape as the record chord; the summon accelerator is persisted in renderer
   *  preferences (overlayShortcut) and re-applied to main on startup. */
  getSummonHotkey: () => Promise<RecordHotkeyState>
  /** Rebind the summon chord (re-registers globally + rebuilds the bar gesture).
   *  Never throws on a conflict — returns registered=false when the chord is owned
   *  by another app (main rolls back to the previous binding). Persist the new
   *  accelerator in preferences (overlayShortcut) on ok so it survives restarts. */
  setSummonHotkey: (accelerator: string) => Promise<{ ok: boolean; registered: boolean }>
  /** The update staged for install-on-quit, if any (query on Settings mount —
   *  the one-shot update:ready event usually fires while Settings is unmounted). */
  getPendingUpdate: () => Promise<{ version: string } | null>
  /** App display name + version (from Electron's app metadata). Shown in About. */
  getAppVersion: () => Promise<{ name: string; version: string }>
  /** Manually trigger an update check (Settings → About "Check for updates").
   *  Inert in unpackaged dev (returns `unsupported`). */
  checkForUpdates: () => Promise<UpdateCheckResult>
  /** Release all global chords while a rebind UI captures raw keys (pressing the
   *  current chord must be captured, not fire the shortcut). Always pair with resume. */
  suspendShortcutCapture: () => void
  resumeShortcutCapture: () => void
  screenSynthFramesSince: () => Promise<ScreenFrameLite[]>
  screenSynthGetState: () => Promise<ScreenSynthState>
  screenSynthSetState: (patch: Partial<ScreenSynthState>) => Promise<ScreenSynthState>
  screenSynthAdvanceWatermark: (ts: number) => Promise<void>
  screenSynthRecordRun: (run: ScreenSynthRun) => Promise<void>
  // --- Coding agents (Claude Code / OpenClaw / Hermes / Codex) ---
  /** Connection status for every known agent (commandOverrides come from prefs). */
  codingAgentList: (commandOverrides?: CodingAgentCommandOverrides) => Promise<CodingAgentInfo[]>
  /** Run one delegated task; resolves with the final outcome. Streaming
   *  progress arrives via onCodingAgentEvent, keyed by taskId. */
  codingAgentRun: (args: CodingAgentRunArgs) => Promise<CodingAgentResult>
  codingAgentCancel: (taskId: string) => Promise<boolean>
  /** Spawn the agent and complete the ACP handshake, then tear it down —
   *  proves the configured command works (Settings → Agents "Test"). For Claude
   *  Code, a missing/expired sign-in is reported as `needsAuth` (not a generic
   *  failure) so the UI can offer "Sign in" instead of a confusing error. */
  codingAgentTest: (
    agentId: CodingAgentId,
    commandOverrides?: CodingAgentCommandOverrides
  ) => Promise<CodingAgentTestResult>
  /** Whether the built-in Claude Code agent has usable credentials. */
  codingAgentAuthStatus: () => Promise<CodingAgentAuthStatus>
  /** Run the Claude Code sign-in: loopback PKCE flow + open the browser, then
   *  write credentials. Resolves with the post-sign-in status. */
  codingAgentStartAuth: () => Promise<CodingAgentStartAuthResult>
  /** Sign out of Claude Code (drop only its stored credentials). */
  codingAgentSignOut: () => Promise<CodingAgentAuthStatus>
  onCodingAgentEvent: (cb: (event: CodingAgentEvent) => void) => () => void
  // --- Main chat (kernel-routed pi-mono) ---
  /** Which engine the main typed-chat should use: 'legacy_sse' (the existing
   *  /v2/messages path) or 'pi_mono' (the kernel-routed managed-cloud door).
   *  PR-E2 reads this to branch; DARK until then. */
  chatGetEngine: () => Promise<'legacy_sse' | 'pi_mono'>
  /** Run one main-chat turn through the kernel + pi-mono adapter; resolves with the
   *  final outcome. Streaming progress arrives via onMainChatEvent, keyed by runId
   *  (and tagged with the caller's requestId). DARK: no renderer consumer yet. */
  mainChatSend: (args: MainChatSendArgs) => Promise<MainChatResult>
  /** Request cancellation of an in-flight main-chat run. Resolves true when the
   *  kernel accepted the cancellation. */
  mainChatCancel: (runId: string) => Promise<boolean>
  /** Subscribe to streaming main-chat events. Returns an unsubscribe function. */
  onMainChatEvent: (cb: (event: MainChatEvent) => void) => () => void
  // --- pi-mono managed-cloud chat session relay ---
  /** Push the renderer's Firebase session (token + desktop API base) to the
   *  main-side pi-mono session store on sign-in and on every id-token refresh;
   *  null on sign-out. The token lives only in the renderer on Windows, so the
   *  store — and the pi-mono adapter it feeds — is inert until this is called. */
  pimonoSetSession: (session: { desktopApiBase: string; token: string } | null) => Promise<void>
  // --- BYOK (bring-your-own-key) provider keys (encrypted at rest in main) ---
  /** Every stored provider key, decrypted. Returns key material to the renderer
   *  Settings UI (same trust model as the app). Empty map when none stored. */
  byokGetAll: () => Promise<ByokKeys>
  /** Encrypt + persist one provider's key. A blank key clears that provider. */
  byokSet: (provider: ByokProvider, key: string) => Promise<void>
  /** Remove one provider's stored key. */
  byokClear: (provider: ByokProvider) => Promise<void>
  /** Remove all stored provider keys. */
  byokClearAll: () => Promise<void>
  /** True only when all four providers have a key (backend all-or-nothing). */
  byokIsActive: () => Promise<boolean>
  /** Live-validate the stored keys and reconcile backend BYOK activation. The
   *  Firebase bearer token is relayed from the renderer's session. */
  byokEnroll: (token: string) => Promise<ByokEnrollResult>
  /** Sign-out: drop the backend BYOK enrollment (local keys are cleared via
   *  byokClearAll in the teardown path). Best-effort. */
  byokDeactivate: (token: string) => Promise<void>
  /** Fires when the BYOK key set or activation changed (any window). Returns an
   *  unsubscribe fn. Carries no key material — reload via byokGetAll. */
  onByokChanged: (cb: () => void) => () => void
  // --- "Use omi memory anywhere" MCP export connectors ---
  /** Current status of every export connector (detected / connected / requires),
   *  plus whether this account has a hosted MCP key. `ownerUserId` is the caller's
   *  Firebase uid (owner-uid guard on the key). */
  mcpStatus: (ownerUserId: string) => Promise<McpExportsSnapshot>
  /** Mint-or-reuse the hosted key and write the connector's MCP config. The
   *  Firebase token + uid are relayed from the renderer; the key stays in main.
   *  Returns the fresh snapshot plus a manual setup card when CLI automation
   *  failed and the user should run the copy-command instead. */
  mcpConnect: (
    connectorId: McpConnectorId,
    token: string,
    ownerUserId: string
  ) => Promise<McpConnectResult>
  /** Remove the connector's MCP config entry. */
  mcpDisconnect: (connectorId: McpConnectorId, ownerUserId: string) => Promise<McpExportsSnapshot>
  /** Rotate the hosted key and rewrite any already-connected configs. */
  mcpRotateKey: (token: string, ownerUserId: string) => Promise<McpExportsSnapshot>
  /** Fires when any connector's status changed. Returns an unsubscribe fn. */
  onMcpChanged: (cb: () => void) => () => void
  /** Sign-out / account-switch: wipe the hosted MCP key (belt-and-suspenders with
   *  the clear inside wipeUserData). Best-effort. */
  mcpClearKey: () => Promise<void>
  /** ChatGPT/Claude assisted-connector cards (static field values, no secret). */
  mcpCloudInfo: () => Promise<McpCloudConnectorInfo[]>
  /** Open a cloud connector's provider connector page (assisted "open & guide"). */
  mcpOpenCloudConnector: (url: string) => Promise<void>
  /** Memory-PACK variant: format the pack, copy to clipboard, open the provider
   *  chat. Returns the opened URL. */
  mcpMemoryPack: (
    provider: 'gemini' | 'chatgpt' | 'claude',
    memories: ExportMemory[]
  ) => Promise<string>
  // --- Encrypted-at-rest Firebase auth persistence ---
  /** Main-process encrypted store (safeStorage/DPAPI) backing a custom Firebase
   *  Persistence, so ID/refresh tokens never sit in plaintext localStorage. Keyed
   *  by Firebase's namespaced persistence key; values are opaque JSON strings. */
  authStore: {
    /** True when OS-backed encryption (DPAPI) is available on this machine. */
    isAvailable: () => Promise<boolean>
    /** Decrypt + return one entry's value, or null if unset/undecryptable. */
    get: (key: string) => Promise<string | null>
    /** Encrypt + persist one entry's value. */
    set: (key: string, value: string) => Promise<void>
    /** Remove one entry. */
    remove: (key: string) => Promise<void>
    /** Subscribe to cross-window change events (key only, never the value).
     *  Returns an unsubscribe function. */
    onChanged: (cb: (key: string) => void) => () => void
  }
  // --- Track 6 (UI surfaces) additions ---
  /** Settings → General → Font Size "Reset Window Size": restore the main window
   *  to its default content size (1280×820) and re-center it. */
  resetWindowSize: () => Promise<void>
  // --- Track 1 (agent control plane) ---
  /**
   * Call one agent-control tool as TRUSTED DIRECT CONTROL. The renderer is the
   * user's own UI, so a call from here carries the user's authority — which is
   * what lets it resolve a dispatch. Returns the raw JSON envelope:
   * `{"ok":true,...}` or `{"ok":false,"error":{"code","message"}}`.
   *
   * Tool names: see `AGENT_CONTROL_TOOL_NAMES` in shared/agentControlTools.ts.
   */
  agentControlCall: (name: string, input?: Record<string, unknown>) => Promise<string>
  // There is deliberately no `agentControlSetOwner`. The active owner — the
  // identity every control call's data is scoped to — is main-side host state and
  // is not settable from the renderer. See src/main/ipc/agentControl.ts.
  /** The control tools this caller may see. */
  agentControlTools: () => Promise<
    Array<{ name: string; description: string; inputSchema: Record<string, unknown> }>
  >
}

// --- Coding agents ---

export type CodingAgentId = 'acp' | 'openclaw' | 'hermes' | 'codex'

export type CodingAgentCommandOverrides = Partial<Record<Exclude<CodingAgentId, 'acp'>, string>>

export type CodingAgentInfo = {
  id: CodingAgentId
  displayName: string
  connected: boolean
  /** How to get connected, when not (shown by the chat + settings). */
  installHint?: string
}

export type CodingAgentRunArgs = {
  taskId: string
  prompt: string
  /** Preferred working directory; main falls back to the user's home dir. */
  cwd?: string
  /** Explicitly named agent; omitted = pick the best connected one. */
  agentId?: CodingAgentId
  commandOverrides?: CodingAgentCommandOverrides
}

export type CodingAgentEvent =
  | {
      type: 'agent_selected'
      taskId: string
      adapterId: CodingAgentId
      displayName: string
      fallback: boolean
    }
  | { type: 'status'; taskId: string; message: string }
  | { type: 'text_delta'; taskId: string; text: string }
  | { type: 'thinking_delta'; taskId: string; text: string }
  | {
      type: 'tool_activity'
      taskId: string
      name: string
      status: 'started' | 'completed' | 'failed'
      toolUseId?: string
      input?: Record<string, unknown>
    }
  | { type: 'tool_result_display'; taskId: string; toolUseId: string; name: string; output: string }
  // Claude Code hit an authentication failure mid-task — the UI surfaces a
  // "Sign in to Claude" prompt (the flow itself is triggered from the UI, never
  // auto-opened from inside the adapter).
  | { type: 'auth_required'; taskId: string; adapterId: CodingAgentId }

/** Result of Settings → Agents "Test". `needsAuth` marks the built-in Claude
 *  Code agent as not-signed-in (vs. a generic connection failure). */
export type CodingAgentTestResult = {
  ok: boolean
  error?: string
  needsAuth?: boolean
}

/** Whether the built-in Claude Code agent has usable credentials. */
export type CodingAgentAuthStatus = {
  connected: boolean
  /** Epoch ms of access-token expiry, when known. */
  expiresAt: number | null
}

/** Outcome of the Claude Code sign-in flow. */
export type CodingAgentStartAuthResult = {
  ok: boolean
  error?: string
  status: CodingAgentAuthStatus
}

export type CodingAgentResult = {
  taskId: string
  ok: boolean
  /** Agent that produced the outcome; null when none could run. */
  adapterId: CodingAgentId | null
  text: string
  costUsd?: number
  error?: string
}

// --- Main chat (kernel-routed, pi-mono managed-cloud) ---
// The DARK door PR-E2 will call to run a default-chat turn through the agent
// kernel and the managed-cloud pi-mono adapter, instead of the legacy /v2/messages
// SSE path. Wire shapes parallel CodingAgent* but key events by `runId` (the
// kernel's run identity) rather than `taskId`, because a chat turn IS a kernel run
// and cancellation targets the runId. Every event also carries the caller's
// `requestId` so the renderer can correlate a streaming turn to its send before
// the server-assigned `runId` is known (the `accepted` event delivers that runId).

export type MainChatSendArgs = {
  /** Caller-generated correlation id, echoed on every MainChatEvent and used as
   *  the kernel run's requestId. Lets the renderer match a streaming turn to its
   *  send before the run's server-assigned runId arrives. */
  requestId: string
  /** The already-context-prepended user prompt. PR-E2 assembles OCR/history
   *  context; the main-chat door forwards this string to the adapter verbatim. */
  prompt: string
  /** The raw user message, BEFORE any OCR/context prepend. The main-chat door
   *  records THIS (not `prompt`) as the user turn on the kernel transcript, so the
   *  stored transcript stays clean of the contexted prompt while the adapter still
   *  receives `prompt` verbatim. */
  cleanUserText: string
  /** Main-chat conversation id; maps to the main_chat/chat/<chatId> surface.
   *  Defaults to 'default' when omitted. */
  chatId?: string
}

export type MainChatEvent =
  /** The run has been accepted and assigned a runId — the first event of a turn.
   *  Carries the runId so the caller can later cancel it via mainChatCancel. */
  | { type: 'accepted'; requestId: string; runId: string }
  /** A run-lifecycle marker (queued/starting/running) for a spinner. */
  | { type: 'status'; requestId: string; runId: string; message: string }
  /** An assistant text chunk; accumulate in order to render the streaming reply. */
  | { type: 'text_delta'; requestId: string; runId: string; text: string }
  /** A reasoning/thinking chunk (shown separately from the reply). */
  | { type: 'thinking_delta'; requestId: string; runId: string; text: string }
  /** A tool invocation's lifecycle transition. */
  | {
      type: 'tool_activity'
      requestId: string
      runId: string
      name: string
      status: 'started' | 'completed' | 'failed'
      toolUseId?: string
      input?: Record<string, unknown>
    }
  /** A tool's rendered output. */
  | {
      type: 'tool_result_display'
      requestId: string
      runId: string
      toolUseId: string
      name: string
      output: string
    }
  /** The final assistant text (emitted on a successful turn before run_finished). */
  | { type: 'completed'; requestId: string; runId: string; text: string }
  /** Terminal event — the turn is done. The renderer stops the spinner here. */
  | {
      type: 'run_finished'
      requestId: string
      runId: string
      status: 'succeeded' | 'failed' | 'cancelled'
      error?: string
    }

export type MainChatResult = {
  runId: string
  requestId: string
  ok: boolean
  text: string
  terminalStatus: 'succeeded' | 'failed' | 'cancelled'
  costUsd?: number
  error?: string
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

// --- X (Twitter) connector (main runs the flow; renderer relays the session) ---

/** { apiBase, token } the renderer passes with each X IPC call (main has neither). */
export type XConnectorSession = { apiBase: string; token: string }

export type XStatus = {
  connected: boolean
  handle?: string
  postCount: number
  memoryCount: number
  syncing: boolean
  lastSyncedAt?: string
}

export type XSyncResult = {
  success: boolean
  newPosts: number
  memoriesCreated: number
  error?: string
}

export type XRunPhase = 'idle' | 'connecting' | 'syncing' | 'succeeded' | 'failed'

/** Live state of the (single) X import run, streamed over integrations:x:progress. */
export type XRunState = {
  phase: XRunPhase
  postCount: number
  memoryCount: number
  handle?: string
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
  /** True when this group surfaced ONLY via semantic (vector) recall — no frame in
   *  it was a keyword/FTS hit. Lets the UI distinguish a fuzzy "related" match from
   *  an exact keyword match. Set only on the phase-2 (merged) results. */
  matchedSemantically?: boolean
}

/** The real Windows microphone consent, read from the registry in main.
 *  'unknown' = the user has never been asked (or the key is unreadable). Callers MUST
 *  treat 'unknown' as not-granted — never as a grant. */
export type MicPermissionState = 'granted' | 'denied' | 'unknown'

export type RewindSettings = {
  captureEnabled: boolean
  intervalMs: number
  retentionDays: number
  /** App names to never screenshot (case-insensitive substring match against the
   *  foreground app/process name). Empty = capture everything. */
  excludedApps: string[]
}

/** Runtime capture directive pushed main→renderer, derived from OS power/lock state.
 *  `paused` tears down the capture stream (sleep/lock); `intervalMs` is the effective
 *  cadence (base × battery multiplier). Separate from the persisted RewindSettings. */
export type RewindCaptureDirective = {
  paused: boolean
  intervalMs: number
}

// --- Track 4: Rewind/Conversations/capture ---
// Row/DTO shapes for the additive PR0 tables. Handlers land with their features
// in later Track 4 PRs; these are the accurate column mirrors they build on.
// (OcrLine — per-line OCR box, persisted as rewind_frames.ocr_lines_json — is
// already defined above with the OCR helper types.)

/** Maps a rewind frame to the hash of its OCR content (rewind_embeddings row).
 *  Many frames share one hash — consecutive screenshots of a static screen have
 *  byte-identical text — and the vector is stored once per hash, not per frame. */
export type RewindEmbeddingRow = {
  frameId: number
  hash: string
}

/** The stored vector for one unique piece of content (rewind_embedding_vectors
 *  row). `vec` is the raw BLOB — a Uint8Array from better-sqlite3 (Buffer is a
 *  subclass) — holding L2-normalized Float32s. */
export type RewindEmbeddingVectorRow = {
  hash: string
  dim: number
  model: string
  vec: Uint8Array
  createdAt: number
}

/** A user/system conversation folder (conversation_folders row; mirrors the Mac
 *  Folder DTO). */
export type ConversationFolder = {
  id: string
  name: string
  color?: string | null
  icon?: string | null
  orderIdx: number
  isSystem: boolean
  conversationCount: number
  updatedAt?: number | null
}

/** Per-conversation speaker naming (conversation_speaker_names row). */
export type ConversationSpeakerName = {
  conversationId: string
  speakerId: number
  name?: string | null
  personId?: string | null
  isUser: boolean
}

/** A live meeting note (live_notes row) — AI-generated or manually authored. */
export type LiveNote = {
  id: string
  sessionId: string
  text: string
  isAi: boolean
  segStart?: number | null
  segEnd?: number | null
  createdAt: number
  updatedAt: number
}

/** A buffered live transcript segment persisted for crash recovery
 *  (rescue_segments row). `segmentJson` is a serialized wire-shape segment. */
export type RescueSegment = {
  sessionId: string
  seq: number
  segmentJson: string
  ts: number
}

// --- Proactive Insights (Rewind OCR → Gemini → acrylic toast) ---
export type InsightCategory = 'productivity' | 'communication' | 'learning' | 'health' | 'other'

// One insight as shown in the toast (mirrors macOS ExtractedInsight).
/** Outcome of the startup corruption check on omi.db (see main/ipc/dbRecovery.ts).
 *  Shared so the renderer's recovery notice and the main-process recovery agree on
 *  one shape. */
export type DbRecoveryStatus = {
  /** Corruption was detected and handled on this launch. */
  recovered: boolean
  /** Nothing was salvageable — the database was reset to an empty schema. */
  reset: boolean
  rowsRecovered: number
  /** Rows recovered per table (only tables that yielded at least one row). */
  tablesRecovered: Record<string, number>
  /** Where the corrupt original was archived, if the backup succeeded. */
  backupPath: string | null
  /** Corruption was CONFIRMED but deliberately not repaired — either the repair
   *  budget was exhausted (boot-loop guard) or a rebuild would have lost rows a
   *  working table still serves. The database is left exactly as it was. */
  unrepairable?: boolean
  /** Tables whose reads actually throw (populated on the confirmed-damage paths). */
  damagedTables?: string[]
}

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

// ---- Track 3 (proactive) ----
// Local persistence backing the proactive-intelligence + memory features. All
// three sets mirror the macOS reference implementation; see src/main/ipc/db.ts
// for the tables and readers/writers.

// Local history of the daily-synthesized AI User Profile. The backend is the
// source of truth; local rows exist so the stage-2 consolidation can read up to
// 5 past profiles.
export type AiUserProfileRecord = {
  id: number
  profileText: string
  dataSourcesUsed: string[] // parsed from the stored JSON array (never null)
  generatedAt: number // epoch ms
  backendSynced: boolean
}

// Insert input: id is assigned by SQLite; backendSynced defaults to false.
export type AiUserProfileInput = {
  profileText: string
  dataSourcesUsed?: string[]
  generatedAt: number
  backendSynced?: boolean
}

export type FocusSessionStatus = 'focused' | 'distracted'

// One Focus-assistant analysis. Mac has no backend focus API, so sessions live
// locally (and are dual-written as memories elsewhere).
export type FocusSessionRecord = {
  id: number
  screenshotId: string | null
  status: FocusSessionStatus
  appOrSite: string | null
  description: string | null
  message: string | null
  durationSeconds: number
  backendId: string | null
  backendSynced: boolean
  createdAt: number // epoch ms
  windowTitle: string | null
}

// Insert input: id is assigned by SQLite; optional fields default to null/0/false.
export type FocusSessionInput = {
  screenshotId?: string | null
  status: FocusSessionStatus
  appOrSite?: string | null
  description?: string | null
  message?: string | null
  durationSeconds?: number
  backendId?: string | null
  backendSynced?: boolean
  createdAt: number
  windowTitle?: string | null
}

// One extracted "memory" (a durable fact about the user, or external wisdom they
// can learn from). Mac's `MemoryRecord` has ~30 columns spanning tier lifecycle,
// tags, scoring and capture provenance — all backend-owned or unused by the
// desktop extraction path. Windows keeps only the local mirror + dedup source:
// the fields the extraction path writes plus backend-sync bookkeeping. `category`
// is narrowed to the two values the extractor ever produces (Mac's third value
// `manual` is for the manual-add path, which Windows does not have here).
export type MemoryCategory = 'system' | 'interesting'

export type MemoryRecord = {
  id: number
  content: string
  category: MemoryCategory
  sourceApp: string
  windowTitle: string
  contextSummary: string
  confidence: number | null
  /** rewind_frames.id the memory was extracted from (null if the frame is gone). */
  screenshotId: number | null
  backendId: string | null
  backendSynced: boolean
  createdAt: number // epoch ms
}

// Insert input: id is assigned by SQLite; optional fields default to ''/null/false.
export type MemoryInput = {
  content: string
  category: MemoryCategory
  sourceApp?: string
  windowTitle?: string
  contextSummary?: string
  confidence?: number | null
  screenshotId?: number | null
  backendId?: string | null
  backendSynced?: boolean
  createdAt: number
}

// Which local task table a stored embedding belongs to. The two tables both start
// rowids at 1, so this discriminator is what keeps `action_item:1` distinct from
// `staged_task:1` in the in-memory index (a deliberate fix ported from macOS).
export type TaskEmbeddingSource = 'action_item' | 'staged_task'

// --- Track 3: Local task storage (action_items + staged_tasks) ---
// Faithful port of macOS ActionItemStorage + StagedTaskStorage. The DDL and CRUD
// live in src/main/ipc/taskStore.ts (driver-agnostic) so production and the
// node:sqlite tests run byte-identical SQL. All timestamps are epoch-ms integers
// (Windows convention; Mac stores DATETIME). `relevanceScore` is lower = more
// important (1 = top). The 3072-dim Float32 embedding BLOB is NOT surfaced on the
// record — it is read only via the dedicated getAll*Embeddings accessors.

/** Who deleted a task. Mac stores free text; these are the values it emits. */
export type TaskDeletedBy = 'user' | 'ai_dedup' | 'staged'

/** One local action item (todo/task). Every column except `embedding` is mapped. */
export type ActionItemRecord = {
  id: number
  backendId: string | null
  backendSynced: boolean
  description: string
  completed: boolean
  deleted: boolean
  deletedBy: string | null
  source: string | null // screenshot | conversation | omi | manual | recurring
  conversationId: string | null
  priority: string | null // high | medium | low
  category: string | null
  tags: string[] // from tags_json
  dueAt: number | null // epoch ms
  screenshotId: number | null // rewind_frames.id (no FK; frames may be pruned)
  confidence: number | null
  sourceApp: string | null
  windowTitle: string | null
  contextSummary: string | null
  currentActivity: string | null
  metadataJson: string | null
  relevanceScore: number | null
  scoredAt: number | null // epoch ms
  fromStaged: boolean
  sortOrder: number | null
  indentLevel: number | null
  createdAt: number // epoch ms
  updatedAt: number // epoch ms
}

/** Insert input for a locally-extracted action item. `backendSynced` is forced to
 *  false by insertLocalActionItem; optional fields default to null/0/false. */
export type ActionItemInput = {
  backendId?: string | null
  backendSynced?: boolean
  description: string
  completed?: boolean
  deleted?: boolean
  deletedBy?: string | null
  source?: string | null
  conversationId?: string | null
  priority?: string | null
  category?: string | null
  tags?: string[]
  dueAt?: number | null
  screenshotId?: number | null
  confidence?: number | null
  sourceApp?: string | null
  windowTitle?: string | null
  contextSummary?: string | null
  currentActivity?: string | null
  metadataJson?: string | null
  embedding?: Float32Array | null
  relevanceScore?: number | null
  scoredAt?: number | null
  fromStaged?: boolean
  sortOrder?: number | null
  indentLevel?: number | null
  createdAt: number
  updatedAt: number
}

/** One staged task awaiting promotion to action_items. Same shape as
 *  ActionItemRecord minus the promotion/ordering fields (fromStaged, sortOrder,
 *  indentLevel), mirroring Mac's StagedTaskRecord. */
export type StagedTaskRecord = {
  id: number
  backendId: string | null
  backendSynced: boolean
  description: string
  completed: boolean
  deleted: boolean
  deletedBy: string | null
  source: string | null
  conversationId: string | null
  priority: string | null
  category: string | null
  tags: string[]
  dueAt: number | null
  screenshotId: number | null
  confidence: number | null
  sourceApp: string | null
  windowTitle: string | null
  contextSummary: string | null
  currentActivity: string | null
  metadataJson: string | null
  relevanceScore: number | null
  scoredAt: number | null
  createdAt: number
  updatedAt: number
}

/** Insert input for a staged task. `backendSynced` forced false by insertLocalStagedTask. */
export type StagedTaskInput = {
  backendId?: string | null
  backendSynced?: boolean
  description: string
  completed?: boolean
  deleted?: boolean
  deletedBy?: string | null
  source?: string | null
  conversationId?: string | null
  priority?: string | null
  category?: string | null
  tags?: string[]
  dueAt?: number | null
  screenshotId?: number | null
  confidence?: number | null
  sourceApp?: string | null
  windowTitle?: string | null
  contextSummary?: string | null
  currentActivity?: string | null
  metadataJson?: string | null
  embedding?: Float32Array | null
  relevanceScore?: number | null
  scoredAt?: number | null
  createdAt: number
  updatedAt: number
}

/** An incoming backend task row for syncTaskActionItems (the pull/upsert). Mirrors
 *  Mac's TaskActionItem sync payload: `backendId` is the server id (item.id). */
export type SyncActionItem = {
  backendId: string
  description: string
  completed: boolean
  deleted?: boolean | null
  deletedBy?: string | null
  source?: string | null
  conversationId?: string | null
  priority?: string | null
  category?: string | null
  tags?: string[]
  dueAt?: number | null
  sourceApp?: string | null
  windowTitle?: string | null
  metadataJson?: string | null
  relevanceScore?: number | null
  sortOrder?: number | null
  indentLevel?: number | null
  fromStaged?: boolean | null
  createdAt: number
  updatedAt?: number | null
}

/** Result of a defensive markSynced: `merged` = a duplicate backend_id already
 *  existed and the incoming row was folded into it; `keptId` = the surviving row. */
export type MarkSyncedResult = { merged: boolean; keptId: number }

/** {localId, embedding} pair for loading an in-memory embedding index. */
export type TaskEmbeddingRow = { id: number; embedding: Float32Array }

/** One (backendId, newPosition) re-rank instruction from the scoring service. */
export type TaskRerank = { backendId: string; newPosition: number }

// --- Task SYNC ENGINE IPC contract (main ↔ renderer) ---
// The main-process `taskSyncEngine` owns local SQLite + backend REST; the renderer
// is thin (IPC only). These are the payload shapes for the `tasks:*` channels
// (see src/main/ipc/tasks.ts for the channel list + semantics).

/** Fields the renderer supplies to create a task (`tasks:create`). Only
 *  description/completed/dueAt/conversationId reach the backend; priority/category/
 *  tags/source are Windows-local-only (the backend action-item model has no such
 *  fields). `dueAt` is epoch-ms. */
export type TaskCreateFields = {
  description: string
  completed?: boolean
  dueAt?: number | null
  conversationId?: string | null
  priority?: string | null
  category?: string | null
  tags?: string[]
  source?: string | null
}

/** Fields the renderer supplies to edit a task (`tasks:update`). `clearDueAt` wins
 *  over `dueAt`. Only description/completed/dueAt reach the backend. */
export type TaskUpdateFields = {
  description?: string
  priority?: string
  category?: string
  tags?: string[]
  dueAt?: number | null
  clearDueAt?: boolean
  completed?: boolean
}

/** Dashboard slices for the Tasks home (`tasks:dashboardSlices`). All are active
 *  (incomplete, non-deleted) tasks partitioned by due window. */
export type TaskDashboardSlices = {
  overdue: ActionItemRecord[]
  today: ActionItemRecord[]
  noDue: ActionItemRecord[]
}

// --- Meeting detection (Phase 5) ---
export type MeetingMode = 'off' | 'ask' | 'auto'

export type MeetingSettings = {
  /** Global behavior when a meeting is detected. Default 'ask' — never a silent
   *  auto-start on first run. */
  mode: MeetingMode
  /** Minutes of Tier-2 (mic) silence before the meeting is considered over. */
  endGraceMinutes: number
  /** Per-app overrides keyed by pattern id ('zoom', 'meet-web', …). */
  perApp: Record<string, MeetingMode>
  /** Whether the one-time "meeting detection is on" hint was shown. */
  firstRunToastShown: boolean
}

/** Payload for the meeting toast (rendered by the shared acrylic toast window). */
export type MeetingToastPayload = {
  meetingId: string
  appName: string
  /** 'ask' → "Meeting detected — start capturing?"; 'capturing' → live notice. */
  kind: 'ask' | 'capturing'
  /** Show the one-time first-run hint line. */
  firstRun?: boolean
}

export type MeetingToastAction = 'start' | 'stop' | 'dismiss'

// Post-update "what's new" toast (Phase 8). Shown once after the app updates to a
// version we have changelog notes for; rendered in the shared acrylic toast window.
export type WhatsNewPayload = {
  version: string
  changes: string[]
}

// A generated-but-not-yet-created goal, previewed before the user accepts it
// (D2 — Windows is ahead of Mac's blind-create). Mirrors the main-side
// GoalCandidate (assistants/goals/generate.ts) across the IPC boundary.
export type GoalSuggestionCandidate = {
  title: string
  description: string
  type: 'boolean' | 'scale' | 'numeric'
  target: number
  min: number
  max: number
  reasoning: string
  linkedTaskIds: string[]
}
export type GoalCandidate = {
  suggestion: GoalSuggestionCandidate
  /** linked_task_ids intersected with the fetched bundle (currently unused —
   *  task→goal linking has no backend field yet). */
  linkedTaskIds: string[]
}

// Outcome of manual phase 1 (goals:generateCandidate).
export type GoalCandidateResult =
  | { status: 'candidate'; candidate: GoalCandidate }
  | { status: 'skipped'; reason: 'no_session' | 'insufficient_context' | 'invalid_suggestion' }

// Outcome of a goal create (goals:createCandidate). Mirrors the main-side
// GenerateResult (assistants/goals/generate.ts) across the IPC boundary.
export type GoalGenerateResult =
  | { status: 'created'; goalId: string; title: string }
  | {
      status: 'skipped'
      reason: 'no_session' | 'insufficient_context' | 'invalid_suggestion' | 'stale' | 'error'
    }

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

// --- Track 2: Voice & PTT depth (voice turn outbox) ---
// Durable main-process outbox for a voice turn (PTT or realtime-session
// utterance) that must survive an app restart mid-flight. Mirrors the macOS
// RealtimeVoiceTurnOutboxEntry 1:1 (see the Track 2 Phase-B ground-truth doc);
// backed by the voice_turn_outbox SQLite table in main/ipc/db.ts. Unconsumed
// until Phase B / Track 1 publish the kernel-write path — the table + CRUD land
// early to claim the shared additive files.

/** A pending voice turn is either awaiting a positive kernel ack ('pending') or
 *  removed once acked (Mac deletes the row on ack — 'acked' is a terminal marker
 *  callers rarely observe, kept for parity/debuggability). */
export type VoiceTurnStatus = 'pending' | 'acked'

/** Fields the caller supplies when enqueuing a voice turn. Drain bookkeeping
 *  (status/attempts/lastError/updatedAtMs) is owned by the outbox itself. The
 *  same idempotencyKey is reused across a turn's completed/interrupted/optimistic
 *  variants so a re-enqueue is an idempotent UPSERT, not a duplicate. */
export interface VoiceTurnOutboxInput {
  /** UUID string, one per logical turn (natural dedup key). */
  idempotencyKey: string
  ownerId: string
  /** The surface triple (surface kind / app / session). Null until wired. */
  surface?: string | null
  appId?: string | null
  sessionId?: string | null
  userText?: string | null
  assistantText?: string | null
  /** True only for a barge-in-captured partial turn. */
  interrupted?: boolean
  createdAtMs: number
}

/** A durable voice_turn_outbox row (the shape listPendingVoiceTurns returns). */
export interface VoiceTurnOutboxEntry {
  idempotencyKey: string
  ownerId: string
  surface: string | null
  appId: string | null
  sessionId: string | null
  userText: string | null
  assistantText: string | null
  interrupted: boolean
  createdAtMs: number
  status: VoiceTurnStatus
  attempts: number
  lastError: string | null
  updatedAtMs: number
}
