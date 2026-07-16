import { useEffect, useRef, useState } from 'react'
import { auth } from '../lib/firebase'
import { invalidateConversationsCache } from '../lib/pageCache'
import { gatherLocalContext } from '../lib/localAgent'
import { readCurrentScreen } from '../lib/screenContext'
import { looksLikeAction, looksLikeRawPlan, planActions } from '../lib/actionPlanner'
import { callAgentLLM } from '../lib/agentLLM'
import { detectAgentTask, resolveTaskCwd } from '../lib/agentTask'
import { beginClaudeSignIn } from '../lib/claudeSignIn'
import type {
  AutomationPlan,
  CodingAgentEvent,
  MainChatEvent,
  MainChatResult,
  ChatCitation,
  ChatAttachment
} from '../../../shared/types'
import { saveDesktopMessage } from '../lib/desktopChatMessages'
import { getMessages as getSessionMessages } from '../lib/chatSessionsClient'
import {
  awaitUploadsSettled,
  clearAttachments,
  getPendingAttachments
} from '../lib/chatAttachments'
import { getPreferences } from '../lib/preferences'
import { CHAT_INFINITE_ID_KEY } from '../lib/chatStorageKeys'
import { resolveChatId, mergeChatMessages } from '../lib/chatConversation'
import { parseDoneMessage, type DoneMessage } from '../lib/messagesSse'
import { speakText } from '../lib/voice/voiceController'
import { withByokHeadersIfActive } from '../lib/byokKeys'
import { friendlyChatError } from '../lib/chat/chatErrorCopy'

export type ChatMsg = {
  id?: string
  role: 'user' | 'assistant'
  content: string
  // --- Finalized from the terminal `done:` SSE frame (assistant only). Mirrors
  // the persisted ChatMessage shape so the data survives a round-trip to SQLite. ---
  /** Server (Firestore) message id — the handle for rating/report/share. */
  serverId?: string
  /** Conversations the answer cited (backend already stripped `[n]` from content). */
  citations?: ChatCitation[]
  /** Inline chart payload, if the answer produced one (opaque — no chart UI yet). */
  chartData?: unknown
  /** Whether the backend flagged this turn for an NPS prompt. */
  askForNps?: boolean
  /** Files attached to this (user) message — rendered as chips in the thread and
   *  round-tripped through the persisted messages JSON. */
  attachments?: ChatAttachment[]
}

const OMI_BASE = import.meta.env.VITE_OMI_API_BASE as string

// Hard ceiling on a single streamed reply. Mirrors the macOS client's per-send
// watchdog (ChatProvider.swift): if the SAME generation is still in flight after
// this long, abort the fetch, unlatch the engine, and surface a timeout so a
// wedged stream can't strand the chat forever.
export const CHAT_STREAM_TIMEOUT_MS = 180_000

// User-facing copy shown when a turn exceeds CHAT_STREAM_TIMEOUT_MS. Shared by BOTH
// watchdogs — the legacy /v2/messages catch path and the pi_mono per-turn watchdog —
// so the two can never drift. Exported so tests key off the same string (no copy drift).
export const CHAT_STREAM_TIMEOUT_COPY = 'Response took too long. Try again.'

// First-chat readiness copy (#123). Right after sign-in the FIRST turn can race
// session readiness — on legacy_sse the persisted Firebase user may not be
// rehydrated yet (auth.currentUser null → `Bearer undefined` → a raw 401 bubble);
// on pi_mono the owner/adapter relay may not have reached main yet (the send fails
// with a not-ready marker). Instead of surfacing a raw `Error:` line, show the
// INTERIM copy while we wait/retry once, and the FINAL copy if readiness never
// arrives. Exported so tests key off the same strings (no copy drift).
export const CHAT_NOT_READY_INTERIM = 'One moment, finishing sign-in…'
export const CHAT_NOT_READY_FINAL = 'Still finishing sign-in. Try again in a moment.'

// pi_mono not-ready markers (`result.error`). These strings are produced ONLY when
// the kernel isn't wired for a turn yet — the cold-start owner gate hasn't seen the
// verified uid (mainChat.ts), the adapter was never registered (adapterRegistry.ts),
// or the session was cleared before the pool built the adapter (controlPlane.ts).
// A genuine model/tool error ("the model exploded") never matches, so keying the
// one-shot retry on this can't swallow a real failure. Anchored/substring-exact.
const PI_MONO_NOT_READY_RE =
  /^Adapter not registered: pi-mono$|pi-mono session was cleared|^Sign-in has not completed yet/

// One-shot not-ready recovery timing. pi_mono: wait this long before the single
// retry so the async relay can land. legacy_sse: poll auth.currentUser this many
// times at this interval (~1.5s total) before giving up to the FINAL copy.
const NOT_READY_RETRY_DELAY_MS = 600
const NOT_READY_POLL_TRIES = 5
const NOT_READY_POLL_INTERVAL_MS = 300

export type UseChat = {
  history: ChatMsg[]
  sending: boolean
  /** True while a spoken (TTS) reply for a `fromVoice` message is playing —
   *  distinct from `sending` (which is the streaming phase). The bar orb uses it
   *  to show the "speaking" state after a voice exchange. */
  speaking: boolean
  /** True while a delegated coding-agent (ACP) task is running — the bar orb
   *  shows its distinctive 'agents' pose. */
  agentActive: boolean
  // `send` takes the message text. The draft input is intentionally NOT stored
  // here: this hook lives in the app-wide AppStateProvider, so keeping the
  // per-keystroke input in it would re-render the entire app shell (and every
  // mounted page) on every character. The draft is local component state in the
  // chat bar; only the persisted history/sending live here.
  // `send` is the single consent entry point for BOTH typed chat and voice
  // transcripts. When it classifies a message as an action and builds a valid
  // plan, approval + execution happen via a NATIVE Windows dialog (main process),
  // so it works identically from the main window and the bar. `fromVoice`
  // requests that the assistant's reply be spoken (TTS) once it's assembled.
  send: (text: string, opts?: { fromVoice?: boolean }) => Promise<void>
  /** Clear the thread to a fresh conversation. */
  reset: () => void
  /** Record a COMPLETED native realtime-hub voice turn (user transcript + assistant
   *  reply) into the thread — APPENDS both messages WITHOUT calling the LLM or TTS
   *  (the hub already produced and spoke the reply). INV-CHAT-1: the spoken turn
   *  lands in the one shared timeline. Empty user/assistant is ignored. */
  recordVoiceTurn: (userText: string, assistantText: string) => void
  /** Re-thread the live engine onto a chat session (multi-chat, pi_mono only).
   *  `id` = a server chat-session id → routes the kernel turn to that session's
   *  per-chatId conversation AND scopes shared-thread persistence to it; `null`
   *  returns to the default shared thread (continuity: session_id omitted). Aborts
   *  any in-flight generation, then loads that thread's transcript into `history`.
   *  The UI pairs this with `useChatSessions.selectSession(id)` for the highlight. */
  switchThread: (id: string | null) => void
  /** The active server chat-session id, or `null` on the default shared thread. */
  currentThreadId: string | null
}

/**
 * Omi chat backed by streaming `/v2/messages`. The thread is persisted as a
 * local conversation (kind='chat') in real time — created the moment a message
 * is sent and upserted as the reply streams — so it shows up in the
 * Conversations list immediately. One conversation per hook lifetime (i.e. per
 * Home mount / app launch).
 */
export function useChat(): UseChat {
  const mode = getPreferences().chatHistoryMode

  const [history, setHistory] = useState<ChatMsg[]>([])
  const [sending, setSending] = useState(false)
  // Spoken-reply (TTS) playback state. A ref counter keeps `speaking` correct if
  // a later reply's TTS starts before an earlier one drains.
  const [speaking, setSpeaking] = useState(false)
  const ttsActiveRef = useRef(0)
  // True while a delegated coding-agent (ACP) task is running — drives the bar
  // orb's distinctive 'agents' pose (projected to the bar via ChatBridgeHost).
  const [agentActive, setAgentActive] = useState(false)
  // Speak an assembled reply through the gated voice path — fire-and-forget so
  // the send promise resolves as soon as the text is rendered (audio plays on
  // its own). Only for voice-originated turns; falls back to the system voice
  // internally if backend TTS is unavailable.
  const maybeSpeak = (text: string, fromVoice: boolean): void => {
    if (!fromVoice || !text.trim()) return
    ttsActiveRef.current++
    setSpeaking(true)
    void speakText(text)
      .catch(() => {
        /* fully handled inside speakText (system-voice fallback); never throws */
      })
      .finally(() => {
        ttsActiveRef.current = Math.max(0, ttsActiveRef.current - 1)
        if (ttsActiveRef.current === 0) setSpeaking(false)
      })
  }

  // Resolve the conversation id once for this hook's lifetime, based on the mode.
  // 'infinite' shares one stable id across launches AND across the main/overlay
  // windows (stored in localStorage); 'per-launch' is fresh per mount.
  const chatIdRef = useRef<string | null>(null)
  // Resolve the DEFAULT shared thread's chat id (infinite: the stored stable id;
  // per-launch: a fresh mint). Reused by switchThread(null) to return to it.
  const resolveDefaultChatId = (): string =>
    resolveChatId(
      mode,
      {
        get: () => localStorage.getItem(CHAT_INFINITE_ID_KEY),
        set: (id) => {
          try {
            localStorage.setItem(CHAT_INFINITE_ID_KEY, id)
          } catch {
            /* private mode / quota */
          }
        }
      },
      () => `chat-${crypto.randomUUID()}`
    )
  if (chatIdRef.current === null) {
    chatIdRef.current = resolveDefaultChatId()
  }
  // The selected server chat-session id, or `null` on the default shared thread.
  // Distinct from chatIdRef: for a session the two are unified (D5 — session id ==
  // kernel chatId == saveDesktopMessage session_id), but for the DEFAULT thread
  // chatIdRef is a local uuid that must NEVER be sent as a session_id (continuity).
  // So this ref, not chatIdRef, gates whether saves carry a session_id.
  const sessionIdRef = useRef<string | null>(null)
  // Reactive projection of sessionIdRef for the UI (the header reads it; the async
  // save path reads the ref so it stays correct inside closures). Moved together in
  // switchThread. null = default shared thread.
  const [currentThreadId, setCurrentThreadId] = useState<string | null>(null)
  const startedAtRef = useRef<number>(0)
  // Synchronous mirror of `sending` for the re-entrancy guard. The `sending` state
  // captured in a `send` closure can be stale (e.g. a queued/auto-sent voice
  // message firing right as a previous reply finishes), which would wrongly drop
  // the new send; the ref is always current.
  const sendingRef = useRef(false)
  // Coding-agent task currently streaming into this thread, so reset (the
  // overlay's Esc) can actually stop the agent subprocess, not just the UI.
  const activeAgentTaskRef = useRef<string | null>(null)
  // Which chat engine this hook drives: 'legacy_sse' (the /v2/messages streaming
  // path, default) or 'pi_mono' (kernel-routed managed-cloud). Read once from main
  // appSettings at mount (single source of truth); a mid-session flip won't apply
  // until remount, which is intentional — engines are not swapped under an active
  // thread. Defaults to the safe legacy path until (and if) the read resolves.
  const engineRef = useRef<'legacy_sse' | 'pi_mono'>('legacy_sse')
  // The in-flight kernel run id (pi_mono engine), captured from its `accepted`
  // event so reset()/dismiss can cancel the managed-cloud attempt on the server,
  // not just tear down the on-screen thread (parallels activeAgentTaskRef).
  const activeKernelRunRef = useRef<string | null>(null)
  // Generation counter + abort handle for the in-flight chat stream. Every send
  // opens a new generation; reset()/dismiss bumps the counter AND aborts the
  // fetch/reader, so a dismissed reply that is still draining can neither write
  // into history/SQLite nor unlatch the busy flag out from under a newer send
  // (the C5 zombie-reply + interleaving class). Only the `/v2/messages` stream
  // path uses these; the agent path has its own cancel via activeAgentTaskRef.
  const genRef = useRef(0)
  const abortRef = useRef<AbortController | null>(null)

  // The single engine-busy latch. `sendingRef` is the SYNCHRONOUS mirror the
  // re-entrancy guard + infinite-load effect read; `sending` is the REACTIVE
  // projection the UI and the bar↔main bridge (ChatBridgeHost) observe. Always
  // move them together through this helper so the bridge never sees the engine
  // idle while a send still holds the latch — a minutes-long coding-agent task
  // holds it the whole time, and a bar/PTT message that raced a false "idle" gap
  // would be silently dropped by the re-entrancy guard (the C3 loss class).
  const setBusy = (busy: boolean): void => {
    sendingRef.current = busy
    setSending(busy)
  }

  // In infinite mode the ongoing thread is loaded once on mount (and legacy
  // id-less messages get backfilled ids so the merge can match them). This hook
  // is the app's single chat engine now (the bar is a viewport over it via the
  // main-process bridge — INV-CHAT-1), so there is one loader/writer.
  useEffect(() => {
    if (mode !== 'infinite' || !chatIdRef.current) return
    let cancelled = false
    // Capture the generation so a switchThread()/reset() that lands before this
    // async default-thread read resolves cancels the write — otherwise a slow
    // default load could overwrite a thread the user has since switched to (C5
    // symmetry with the send/agent/kernel paths).
    const myGen = genRef.current
    void window.omi
      .getLocalConversation(chatIdRef.current)
      .then((c) => {
        // Skip if a send already started before this async load resolved —
        // otherwise we'd overwrite the in-flight bubble (sendingRef is set
        // synchronously at the top of send()).
        if (cancelled || sendingRef.current || genRef.current !== myGen || !c?.messages) return
        startedAtRef.current = c.startedAt || Date.now()
        setHistory(
          c.messages.map((m) => ({
            id: m.id ?? crypto.randomUUID(),
            role: m.role,
            content: m.content
          }))
        )
      })
      .catch(() => {
        /* no prior conversation — start empty */
      })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Read the chat engine once at mount into engineRef (main appSettings is the
  // single source of truth). Guarded on the getter existing so the hook stays inert
  // where the bridge isn't present (older preload / tests) — leaving the safe
  // 'legacy_sse' default, which is what keeps the flag-OFF path byte-identical.
  useEffect(() => {
    const getEngine = window.omi.chatGetEngine
    if (typeof getEngine !== 'function') return
    let cancelled = false
    void getEngine()
      .then((engine) => {
        if (!cancelled && engine) engineRef.current = engine
      })
      .catch(() => {
        /* keep the legacy_sse default */
      })
    return () => {
      cancelled = true
    }
  }, [])

  // `stillValid`, when provided, is re-checked AFTER the async merge-read and
  // right before the write, so a reset()/dismiss that lands mid-persist cancels
  // the write instead of committing a dismissed (zombie) reply into the thread.
  const persistChat = async (thread: ChatMsg[], stillValid?: () => boolean): Promise<void> => {
    if (stillValid && !stillValid()) return
    if (!chatIdRef.current) {
      chatIdRef.current = `chat-${crypto.randomUUID()}`
    }
    if (!startedAtRef.current) startedAtRef.current = Date.now()

    // In infinite mode, read the current stored thread and MERGE by message id
    // instead of overwriting — this updates (not duplicates) a streamed assistant
    // message and preserves anything already persisted for the shared id across
    // launches. Per-launch keeps the simple single-writer replace path.
    let toStore = thread
    if (mode === 'infinite') {
      try {
        const existing = await window.omi.getLocalConversation(chatIdRef.current)
        if (existing?.startedAt) startedAtRef.current = existing.startedAt
        toStore = mergeChatMessages(existing?.messages ?? [], thread)
      } catch {
        /* fall back to writing just this thread */
      }
    }

    const transcript = toStore
      .map((m) => `${m.role === 'user' ? 'You' : 'Omi'}: ${m.content}`)
      .join('\n\n')
    if (stillValid && !stillValid()) return
    try {
      await window.omi.insertLocalConversation({
        id: chatIdRef.current,
        startedAt: startedAtRef.current,
        endedAt: Date.now(),
        transcript,
        createdAt: startedAtRef.current,
        kind: 'chat',
        messages: toStore
      })
      invalidateConversationsCache() // this renderer's cache (immediate)
      // …and tell every OTHER window (main ↔ overlay) to refresh too, since each
      // renderer has its own per-process conversations cache.
      window.omi.notifyConversationsChanged()
    } catch (e) {
      console.error('Failed to persist chat conversation:', e)
    }
  }

  // Desktop-automation pre-step. Returns:
  //   'planned' — produced a valid plan (parked in pendingPlan for approval);
  //               the user message is added here and normal chat is skipped.
  //   'error'   — the message looked like an action but we couldn't reach/parse
  //               the planner (e.g. backend 429, snapshot failed); the caller
  //               surfaces that instead of silently answering it as chat.
  //   'chat'    — not an action (or no keyword hint) → fall through to chat.
  // Snapshots the last non-Omi foreground window so we plan against the app the
  // user was actually using, not Omi itself.
  type PlanVerdict =
    | { kind: 'planned'; plan: AutomationPlan }
    | { kind: 'error' }
    | { kind: 'chat' }
  const tryPlan = async (text: string): Promise<PlanVerdict> => {
    // Desktop automation requires BOTH the OMI_AUTOMATION env kill-switch (on
    // unless OMI_AUTOMATION=0) and the user's onboarding opt-in. Until the user
    // grants the Automation step, every message falls straight through to normal
    // chat.
    if (!window.omi.automationEnabled) return { kind: 'chat' }
    if (!getPreferences().automationConsentedAt) return { kind: 'chat' }
    if (!looksLikeAction(text)) return { kind: 'chat' }
    try {
      const handle = await window.omi.automationTargetWindow().catch(() => null)
      const result = await planActions(text, {
        getSnapshot: () => window.omi.automationSnapshot(handle ?? undefined),
        callLLM: callAgentLLM
      })
      if (result.ok) return { kind: 'planned', plan: result.plan }
      return { kind: result.kind }
    } catch {
      return { kind: 'error' }
    }
  }

  // Delegated coding-agent task (Claude Code / OpenClaw / Hermes / Codex).
  // Runs when the message explicitly names an agent (or asks for "an agent").
  // Streams the agent's progress into an assistant bubble; when the named
  // agent isn't connected, replies with install/connect guidance instead.
  // Returns false when the message is not an agent task (fall through).
  const tryAgentTask = async (
    text: string,
    baseHistory: ChatMsg[],
    userMsg: ChatMsg
  ): Promise<boolean> => {
    const detection = detectAgentTask(text)
    if (!detection) return false

    // Capture this send's generation (send() bumped genRef just before calling
    // us). reset()/dismiss bumps genRef and cancels the task, so `isCurrent()`
    // goes false and every state write below is dropped — a dismissed agent task
    // must not resurface its thread, steal the busy latch, or clear the orb pose
    // out from under a newer send (same class as the streaming-path C5 guard).
    const myGen = genRef.current
    const isCurrent = (): boolean => genRef.current === myGen

    const prefs = getPreferences()
    let agents: Awaited<ReturnType<typeof window.omi.codingAgentList>>
    try {
      agents = await window.omi.codingAgentList(prefs.agentCommands)
    } catch {
      return false // bridge unavailable — let normal chat answer
    }

    const finish = (content: string): void => {
      if (!isCurrent()) return
      const msg: ChatMsg = { id: crypto.randomUUID(), role: 'assistant', content }
      setHistory((h) => [...h, msg])
      void persistChat([...baseHistory, userMsg, msg], isCurrent)
      setBusy(false)
    }

    if (detection.agentId) {
      const named = agents.find((a) => a.id === detection.agentId)
      if (named && !named.connected) {
        finish(
          `**${named.displayName}** isn't connected yet. ${
            named.installHint ?? 'You can connect it in Settings → Agents.'
          }`
        )
        return true
      }
    }
    const agentId = detection.agentId ?? agents.find((a) => a.connected)?.id
    if (!agentId) {
      finish('No coding agents are connected yet. You can connect one in Settings → Agents.')
      return true
    }

    setAgentActive(true)
    const taskId = crypto.randomUUID()
    activeAgentTaskRef.current = taskId
    const assistantId = crypto.randomUUID()

    // Streamed bubble: a header naming the agent, the latest running tool as a
    // transient italic line, and the agent's text as it arrives.
    let header = ''
    let activity: string | null = null
    let text_ = ''
    let statusNotes = ''
    const compose = (final: boolean): string => {
      let s = header
      if (statusNotes) s += `\n\n${statusNotes.trimEnd()}`
      if (text_) s += `\n\n${text_}`
      if (!final && activity) s += `\n\n_${activity}…_`
      return s || '_Starting the agent…_'
    }
    const render = (final = false): void => {
      const content = compose(final)
      setHistory((h) => {
        const next = [...h]
        const idx = next.findIndex((m) => m.id === assistantId)
        if (idx >= 0) next[idx] = { id: assistantId, role: 'assistant', content }
        return next
      })
    }
    setHistory((h) => [...h, { id: assistantId, role: 'assistant', content: compose(false) }])

    let lastPersist = Date.now()
    const unsubscribe = window.omi.onCodingAgentEvent((event: CodingAgentEvent) => {
      if (event.taskId !== taskId) return
      // A dismissed task (reset bumped the generation) drops all further renders
      // and persists — its events keep arriving until codingAgentCancel lands.
      if (!isCurrent()) return
      if (event.type === 'agent_selected') {
        header = event.fallback
          ? `**${event.displayName}** took over the task.`
          : `**${event.displayName}** is on it.`
      } else if (event.type === 'status') {
        statusNotes += `_${event.message}_\n`
      } else if (event.type === 'text_delta') {
        text_ += event.text
      } else if (event.type === 'tool_activity') {
        activity = event.status === 'started' ? event.name : null
      } else if (event.type === 'auth_required') {
        // Claude Code isn't signed in — show the upsell sheet + launch the
        // parallel OAuth (macOS parity). The task's own error result already
        // explains the block in the thread.
        beginClaudeSignIn()
      }
      render()
      if (Date.now() - lastPersist > 1500) {
        lastPersist = Date.now()
        void persistChat(
          [
            ...baseHistory,
            userMsg,
            { id: assistantId, role: 'assistant', content: compose(false) }
          ],
          isCurrent
        )
      }
    })

    try {
      const cwd = await resolveTaskCwd(text, {
        searchFiles: (q) => window.omi.kgSearchFiles(q),
        executeSql: (sql) => window.omi.kgExecuteSql(sql)
      })
      const result = await window.omi.codingAgentRun({
        taskId,
        prompt: detection.prompt,
        cwd,
        agentId,
        commandOverrides: prefs.agentCommands
      })
      if (!result.ok) {
        statusNotes += `_${result.error ?? 'The agent could not finish the task.'}_\n`
      } else if (!text_ && result.text) {
        text_ = result.text
      } else if (!text_) {
        text_ = 'Done.'
      }
    } catch (e) {
      statusNotes += `_Error: ${(e as Error).message}_\n`
    } finally {
      // Cleanup that must ALWAYS run (even for a dismissed task): stop clearing a
      // ref a newer task now owns, and release the event listener to avoid a leak.
      if (activeAgentTaskRef.current === taskId) activeAgentTaskRef.current = null
      unsubscribe()
      activity = null
      // State writes only for the still-current generation. A dismissed task was
      // already torn down by reset() (busy unlatched, history cleared, orb pose
      // dropped, subprocess cancelled) — re-running these would resurface the
      // cancelled thread and steal the latch/pose from a newer send.
      if (isCurrent()) {
        setAgentActive(false)
        render(true)
        void persistChat(
          [...baseHistory, userMsg, { id: assistantId, role: 'assistant', content: compose(true) }],
          isCurrent
        )
        setBusy(false)
      }
    }
    return true
  }

  // Default chat routed through the agent kernel → managed-cloud pi-mono adapter
  // (the 'pi_mono' engine). A SIBLING of tryAgentTask with the SAME C5 generation
  // guards (myGen/isCurrent; every state write, persist, saveMessage, and
  // setBusy(false) gated on isCurrent()); it consumes the mainChat event stream for
  // live deltas and drives the terminal outcome off the awaited mainChatSend result
  // (as tryAgentTask does off codingAgentRun). Because the kernel path — unlike
  // /v2/messages — does NOT persist to the shared/mobile thread as a side-effect,
  // it makes the explicit v2/desktop/messages saveMessage calls here (INV-CHAT-1):
  // the RAW user text at turn start and the assistant text on completion.
  const tryKernelChat = async (
    baseHistory: ChatMsg[],
    userMsg: ChatMsg,
    fromVoice: boolean
  ): Promise<void> => {
    // send() bumped genRef just before calling us. reset()/dismiss bumps it again +
    // cancels the run, so isCurrent() goes false and every write below is dropped.
    const myGen = genRef.current
    const isCurrent = (): boolean => genRef.current === myGen

    const assistantId = crypto.randomUUID()
    let assistantText = ''

    // INV-CHAT-1 site 1: persist the RAW user message at turn start (never the
    // context-prepended prompt). Fire-and-forget. session_id is OMITTED on the
    // default shared thread (sessionIdRef null → mobile/web continuity) and PASSED
    // when a chat session is selected (multi-chat), targeting that desktop-local
    // thread. saveDesktopMessage drops the field when undefined. This fires EXACTLY
    // ONCE per send: the not-ready retry below re-issues mainChatSend but never
    // re-runs this write (this renderer-side save is not idempotent — main's own
    // recordSurfaceTurn is requestId-keyed, but a second call here would double-save
    // the human turn), so it stays OUTSIDE the per-attempt helper.
    void saveDesktopMessage({
      text: userMsg.content,
      sender: 'human',
      clientMessageId: userMsg.id,
      messageSource: 'desktop_chat',
      // Include session_id ONLY for a selected session; the default thread omits
      // the key entirely (mobile/web continuity guard).
      ...(sessionIdRef.current ? { sessionId: sessionIdRef.current } : {})
    })

    const writeAssistant = (content: string): void => {
      if (!isCurrent()) return
      setHistory((h) => {
        const next = [...h]
        const idx = next.findIndex((m) => m.id === assistantId)
        if (idx >= 0) next[idx] = { id: assistantId, role: 'assistant', content }
        return next
      })
    }
    setHistory((h) => [...h, { id: assistantId, role: 'assistant', content: '' }])
    void persistChat(
      [...baseHistory, userMsg, { id: assistantId, role: 'assistant', content: '' }],
      isCurrent
    )

    let lastPersist = Date.now()

    // One send attempt: subscribe to the mainChat event stream for THIS requestId,
    // capture the run handle (so reset()/mainChatCancel targets the in-flight
    // attempt — verify activeKernelRunRef tracks the CURRENT attempt's run), await
    // the authoritative mainChatSend result, and unsubscribe. Streamed deltas
    // accumulate into the shared `assistantText`, reset per attempt so a retried
    // attempt starts clean. Deliberately does NOT persist/save/unlatch — the
    // user-save (above), assistant bubble, and terminal handling (below) all live
    // OUTSIDE this helper so they run exactly once regardless of a retry.
    const attempt = async (reqId: string, textToSend: string): Promise<MainChatResult> => {
      let attemptRunId: string | null = null
      assistantText = ''
      const unsubscribe = window.omi.onMainChatEvent((event: MainChatEvent) => {
        if (event.requestId !== reqId) return
        // A dismissed turn (reset bumped the generation) drops all further renders
        // and persists — events keep arriving until mainChatCancel lands.
        if (!isCurrent()) return
        if (event.type === 'accepted') {
          attemptRunId = event.runId
          activeKernelRunRef.current = event.runId
        } else if (event.type === 'text_delta') {
          assistantText += event.text
          writeAssistant(assistantText)
        }
        // status / thinking_delta / tool_* / completed / run_finished are covered by
        // the authoritative awaited mainChatSend result below (terminal + final
        // text), exactly as tryAgentTask relies on codingAgentRun's return.
        if (Date.now() - lastPersist > 1500) {
          lastPersist = Date.now()
          void persistChat(
            [
              ...baseHistory,
              userMsg,
              { id: assistantId, role: 'assistant', content: assistantText }
            ],
            isCurrent
          )
        }
      })
      try {
        return await window.omi.mainChatSend({
          requestId: reqId,
          prompt: textToSend,
          cleanUserText: userMsg.content,
          chatId: chatIdRef.current ?? 'default'
        })
      } finally {
        // Cleanup that must ALWAYS run (even for a dismissed turn): release the run
        // handle if it's still this attempt's, and drop the listener.
        if (activeKernelRunRef.current === attemptRunId) activeKernelRunRef.current = null
        unsubscribe()
      }
    }

    // Per-turn watchdog (pi_mono parity with the legacy /v2/messages path). The
    // kernel IPC (mainChatSend) resolves only on the run's terminal event; a hung
    // run or a wedged bridge would otherwise leave `sending` latched forever — a
    // permanent spinner in the Home ask-bar and the bar. Unlike the legacy fetch,
    // this IPC has NO abort primitive, so we can't unwind the await. Instead, on the
    // deadline we RECOVER the UX in THIS turn's bubble and INVALIDATE the turn
    // (exactly as reset() does): the abandoned in-flight send — even if it never
    // resolves — can then neither overwrite the timeout copy nor re-unlatch, because
    // every write past the bump is isCurrent()-gated on the pre-bump generation. The
    // timer is set BEFORE the try so it covers context-gathering + BOTH attempts +
    // the 600ms retry delay, and is cleared at the top of the finally so a normal
    // completion cancels it (the success path is otherwise byte-identical).
    const watchdog = setTimeout(() => {
      if (!isCurrent()) return
      // Recover the bubble FIRST (writeAssistant guards on the still-current gen) and
      // unlatch the spinner + attempt a best-effort server cancel…
      writeAssistant(CHAT_STREAM_TIMEOUT_COPY)
      setBusy(false)
      void window.omi.mainChatCancel(activeKernelRunRef.current ?? '').catch(() => {})
      // …then invalidate: bump the gen so the abandoned send's late deltas AND its
      // terminal finally (all gated on the pre-bump `myGen`) are dropped — no double
      // terminal, no zombie overwrite, no second setBusy. Capture the POST-bump gen
      // for the local persist so this watchdog's own bump can't cancel its own write
      // (persistChat re-checks stillValid after an async read in 'infinite' — the
      // DEFAULT — mode), while an external reset()/switchThread (which bumps again)
      // still cancels it: the cross-thread guard. INV-CHAT-1: the timeout line is NOT
      // a real reply, so it is persisted LOCALLY only — never saveDesktopMessage'd.
      const invalidated = ++genRef.current
      void persistChat(
        [
          ...baseHistory,
          userMsg,
          { id: assistantId, role: 'assistant', content: CHAT_STREAM_TIMEOUT_COPY }
        ],
        () => genRef.current === invalidated
      )
    }, CHAT_STREAM_TIMEOUT_MS)

    let errored = false
    let errorLine = ''
    try {
      // Same hybrid context pre-step as the /v2/messages path (:578-591): prepend
      // screen OCR + local KG context to the text SENT to the model, but persist
      // only the raw user text. Plain string concat — never the context packet (§6).
      // Gathered ONCE and reused across a retry (the message hasn't changed).
      const [screenContext, localContext] = await Promise.all([
        readCurrentScreen(),
        gatherLocalContext(userMsg.content)
      ])
      const contextParts = [screenContext, localContext].filter(Boolean)
      const textToSend = contextParts.length
        ? `${contextParts.join('\n\n')}\n\n${userMsg.content}`
        : userMsg.content

      // One requestId for the WHOLE turn (both attempts). Main's recordSurfaceTurn
      // records the kernel human turn keyed by this requestId and dedups on it, so
      // the not-ready retry below MUST reuse the same id — a fresh id per attempt
      // would defeat that dedup and append the user turn a second time on the kernel
      // transcript (polluting the per-session context tail). Reuse is safe: run
      // correlation uses a separate per-send clientId, and attempt 1 fully awaits +
      // unsubscribes before the retry subscribes, so there is no stream cross-talk.
      const requestId = crypto.randomUUID()
      let result = await attempt(requestId, textToSend)
      // First-chat not-ready recovery (#123): right after sign-in the owner/adapter
      // relay may not have reached main yet, so the FIRST send fails not-ready. Show
      // the interim copy, wait briefly, and retry ONCE (same requestId — see above).
      // Only the precise not-ready markers qualify (never a generic model error), so a
      // real failure surfaces immediately with no spurious retry. Guarded by
      // isCurrent() so a reset() during attempt 1 skips the retry. The delay's
      // setTimeout is NOT cancelled on reset(); instead the post-await isCurrent()
      // check is what prevents attempt 2. A reset() during the wait already
      // unlatched busy and cleared history, so the lingering ~600ms promise is
      // harmless: when it resolves we bail here before sending attempt 2.
      if (!result.ok && result.error && PI_MONO_NOT_READY_RE.test(result.error) && isCurrent()) {
        writeAssistant(CHAT_NOT_READY_INTERIM)
        await new Promise<void>((resolve) => setTimeout(resolve, NOT_READY_RETRY_DELAY_MS))
        if (!isCurrent()) return
        result = await attempt(requestId, textToSend)
      }

      if (result.ok) {
        if (result.text) assistantText = result.text
      } else if (result.error && PI_MONO_NOT_READY_RE.test(result.error)) {
        // Still not ready after the one retry: a friendly line, never a raw `Error:`.
        // hasRealText is false here, so (like any error line) it is neither saved to
        // the shared thread nor spoken.
        errored = true
        errorLine = CHAT_NOT_READY_FINAL
      } else {
        // Any other kernel failure: friendly, plain-English copy — never a raw
        // `Error: <technical string>` bubble (chat error taxonomy, Mac parity). Log
        // the RAW error first: the friendly copy reads as transient ("try again"),
        // so a deterministic contract/logic failure (e.g. a 400) would otherwise be
        // invisible in logs/Sentry. The bubble stays friendly; the log stays raw.
        console.error('[chat] kernel turn failed:', result.error)
        errored = true
        errorLine = friendlyChatError(result.error ?? '')
      }
    } catch (e) {
      console.error('[chat] kernel turn threw:', e)
      errored = true
      errorLine = friendlyChatError((e as Error).message)
    } finally {
      // A normal completion (before the deadline) cancels the watchdog. If the
      // watchdog already fired it bumped the generation, so the isCurrent() block
      // below is skipped — the recovered timeout state stands and there is no double
      // terminal. clearTimeout on an already-fired timer is a harmless no-op.
      clearTimeout(watchdog)
      // Terminal handling runs exactly once, after the FINAL attempt (each attempt
      // already released its own run handle + listener in its own finally). State
      // writes only for the still-current generation (a dismissed turn was already
      // torn down by reset(): busy unlatched, history cleared, run cancelled).
      if (isCurrent()) {
        const hasRealText = assistantText.trim().length > 0
        // Keep any partial streamed text on error (Mac keeps the partial); only show
        // an error/no-reply line when nothing real arrived.
        const displayContent = hasRealText
          ? assistantText
          : errored
            ? errorLine
            : "Omi didn't send a reply. Try again."
        writeAssistant(displayContent)
        void persistChat(
          [
            ...baseHistory,
            userMsg,
            { id: assistantId, role: 'assistant', content: displayContent }
          ],
          isCurrent
        )
        // INV-CHAT-1 site 2: persist the assistant turn to the shared thread — the
        // full reply on success, the partial on a bridge error (Mac sites 4 + 5).
        // Skip when there is no real assistant text so an error line never lands in
        // the shared/mobile thread.
        if (hasRealText) {
          void saveDesktopMessage({
            text: assistantText,
            sender: 'ai',
            clientMessageId: assistantId,
            messageSource: 'desktop_chat',
            ...(sessionIdRef.current ? { sessionId: sessionIdRef.current } : {})
          })
        }
        if (!errored && hasRealText) maybeSpeak(assistantText, fromVoice)
        setBusy(false)
      }
    }
  }

  const send = async (text: string, opts?: { fromVoice?: boolean }): Promise<void> => {
    // Re-entrancy latch (sendingRef is the always-current mirror of `sending`).
    // A send is allowed with text OR with staged attachments (Mac parity —
    // attachment-only sends); only a truly empty send is dropped. The file_ids
    // are drained from the pending list below.
    if ((!text.trim() && getPendingAttachments().length === 0) || sendingRef.current) return
    const fromVoice = !!opts?.fromVoice
    setBusy(true)
    // Open a new generation. reset()/dismiss bumps genRef, so `isCurrent()` goes
    // false for this send and every write it attempts thereafter is dropped —
    // that is what stops a dismissed reply from resurfacing or unlatching a newer
    // send (C5). Only the `/v2/messages` streaming path below checks it; the
    // agent/plan branches finish synchronously enough to keep their own flow.
    const myGen = ++genRef.current
    const isCurrent = (): boolean => genRef.current === myGen
    // Chat attachments (Track 1 platform layer): if files are pending, wait for
    // their optimistic uploads to settle, then snapshot the uploaded server ids
    // (file_ids) and their render metadata onto this user message. Uploads kick
    // off on add, so by now they're almost always done — the await is usually
    // instant. With ZERO pending attachments there is no await and the request
    // body below is byte-identical to before (regression guard).
    let sendFileIds: string[] = []
    let sentAttachments: ChatAttachment[] | undefined
    if (getPendingAttachments().length > 0) {
      await awaitUploadsSettled()
      const uploaded = getPendingAttachments().filter((a) => a.status === 'uploaded' && a.serverId)
      sendFileIds = uploaded.map((a) => a.serverId as string)
      sentAttachments = uploaded.map((a) => ({
        id: a.serverId as string,
        name: a.name,
        mimeType: a.mimeType
      }))
      // Guard the attachment-only path: if EVERY upload failed there are no
      // file_ids, and with empty text this would POST an empty message + render a
      // blank user bubble. Abort instead, and leave the failed attachments in the
      // composer so the user can retry or remove them (don't clear).
      if (!text.trim() && sendFileIds.length === 0) {
        setBusy(false)
        return
      }
      // The message now owns these files; clear the composer's pending list.
      clearAttachments()
    }
    const userMsg: ChatMsg = {
      id: crypto.randomUUID(),
      role: 'user',
      content: text,
      ...(sentAttachments && sentAttachments.length ? { attachments: sentAttachments } : {})
    }
    const baseHistory = history
    // Show the user's message immediately, BEFORE the (potentially ~2s) action-
    // planner snapshot+LLM round-trip, so the chat never appears to hang. The
    // planner then decides: park a plan, surface an error, or fall through to chat.
    setHistory((h) => [...h, userMsg])

    // Delegated coding-agent tasks take precedence over the UI-automation
    // planner and normal chat; tryAgentTask owns the latch when it handles one.
    if (await tryAgentTask(text, baseHistory, userMsg)) return

    // Desktop automation planner runs BEFORE the pi_mono engine branch: with
    // pi_mono the default chat engine, a keyword-action message ("just do X in
    // the app") must still be caught by tryPlan and NOT silently routed to the
    // kernel. tryPlan no-ops (returns {kind:'chat'}) when automation isn't
    // enabled/consented or the text doesn't look like an action, so a plain
    // message falls straight through to the pi_mono branch below.
    const verdict = await tryPlan(text)
    if (verdict.kind === 'planned') {
      // Consent + execution happen in a NATIVE Windows dialog (main process), so
      // this works the same from the main window and the floating overlay. We
      // don't stream a reply — just post the outcome.
      const r = await window.omi.automationConfirmRun(verdict.plan)
      const outMsg: ChatMsg = {
        id: crypto.randomUUID(),
        role: 'assistant',
        content: r.canceled
          ? "Okay, I won't do that."
          : r.ok
            ? 'Done.'
            : `I couldn't finish that: ${r.message ?? 'a step failed'}`
      }
      setHistory((h) => [...h, outMsg])
      void persistChat([...baseHistory, userMsg, outMsg])
      maybeSpeak(outMsg.content, fromVoice)
      setBusy(false)
      return
    }
    if (verdict.kind === 'error') {
      const errMsg: ChatMsg = {
        id: crypto.randomUUID(),
        role: 'assistant',
        content:
          "I couldn't turn that into an action I could run safely, so I didn't do anything. Try rephrasing it, or try again in a moment."
      }
      setHistory((h) => [...h, errMsg])
      void persistChat([...baseHistory, userMsg, errMsg])
      maybeSpeak(errMsg.content, fromVoice)
      setBusy(false)
      return
    }

    // pi_mono engine (now the default): route plain chat through the kernel
    // instead of the legacy /v2/messages block below. A single early return —
    // reached only for a {kind:'chat'} verdict, so a planned/errored automation
    // message never lands here. With the engine set to 'legacy_sse' this branch
    // is skipped and the legacy path runs byte-identically. Attachment sends fall
    // through to legacy: the kernel prompt has no PromptBlock/file_ids equivalent
    // yet (§6 out of scope), so a message carrying attachments keeps using
    // /v2/messages.
    if (engineRef.current === 'pi_mono' && sendFileIds.length === 0) {
      return tryKernelChat(baseHistory, userMsg, fromVoice)
    }

    const assistantId = crypto.randomUUID()
    const assistantMsg = (content: string): ChatMsg => ({
      id: assistantId,
      role: 'assistant',
      content
    })
    const buildThread = (assistant: ChatMsg): ChatMsg[] => [...baseHistory, userMsg, assistant]
    // Replace the last (assistant) bubble in-place with `msg`, but only while this
    // generation is still current — a stale reader must never touch state.
    const renderAssistant = (msg: ChatMsg): void => {
      if (!isCurrent()) return
      setHistory((h) => {
        const next = [...h]
        next[next.length - 1] = msg
        return next
      })
    }
    setHistory((h) => [...h, assistantMsg('')])

    void persistChat(buildThread(assistantMsg('')), isCurrent)
    let lastPersist = Date.now()

    let assistantText = ''
    let finalMsg: ChatMsg = assistantMsg('')
    // AbortController so reset()/dismiss tears the fetch + reader down promptly
    // rather than leaving it draining in the background.
    const ac = new AbortController()
    abortRef.current = ac
    // Per-send watchdog (macOS parity): abort a wedged stream at the deadline, but
    // ONLY if this same generation is still current — a newer send/reset has its
    // own controller and generation, so an earlier send's watchdog can never abort
    // it. `timedOut` steers the catch below to the user-facing timeout message.
    let timedOut = false
    const watchdog = setTimeout(() => {
      if (!isCurrent()) return
      timedOut = true
      ac.abort()
    }, CHAT_STREAM_TIMEOUT_MS)
    try {
      // First-chat readiness gate (#123, legacy_sse): right after sign-in the
      // persisted Firebase user may not be rehydrated yet, so auth.currentUser is
      // null and getIdToken() below would yield `Bearer undefined` → a raw 401
      // bubble. Show the interim copy and briefly wait for the session to
      // rehydrate BEFORE the fetch (Mac-parity: wait for readiness, don't
      // send-fail-retry); if it never arrives, show a friendly line instead of the
      // raw error. Gated ONLY on `!auth.currentUser` pre-fetch — a genuinely
      // revoked session that 401s AFTER the fetch is a real failure, not not-ready,
      // and must NOT be silently retried. When currentUser is already set (the
      // normal case) this whole block is skipped and the path is byte-identical.
      if (!auth.currentUser) {
        renderAssistant(assistantMsg(CHAT_NOT_READY_INTERIM))
        for (let i = 0; i < NOT_READY_POLL_TRIES && !auth.currentUser; i++) {
          await new Promise<void>((resolve) => setTimeout(resolve, NOT_READY_POLL_INTERVAL_MS))
          if (!isCurrent()) return
        }
        if (!auth.currentUser) {
          finalMsg = assistantMsg(CHAT_NOT_READY_FINAL)
          renderAssistant(finalMsg)
          return
        }
      }
      const token = await auth.currentUser?.getIdToken()
      // Hybrid pre-step: gather context to PREPEND to the text we send (not what we
      // persist). Both are best-effort ('' on failure) and run concurrently so the
      // send isn't serialized behind them:
      //   • current screen — the current screen's OCR text, attached as ambient
      //     context to EVERY message. It's framed so the model ignores it unless the
      //     message is actually about the screen, so it doesn't bloat answers. This
      //     is an instant hot-cache read, so normal messages don't pay a capture cost;
      //   • local KG/file context — apps/projects/tech the chat is grounded in.
      const [screenContext, localContext] = await Promise.all([
        readCurrentScreen(),
        gatherLocalContext(userMsg.content)
      ])
      const contextParts = [screenContext, localContext].filter(Boolean)
      const textToSend = contextParts.length
        ? `${contextParts.join('\n\n')}\n\n${userMsg.content}`
        : userMsg.content
      const res = await fetch(`${OMI_BASE}/v2/messages`, {
        method: 'POST',
        // BYOK: attach X-BYOK-* (all-or-none) when active so managed chat runs on
        // the user's own keys. This lane is a raw fetch, so it can't ride the
        // axios interceptor — withByokHeadersIfActive covers it directly.
        headers: withByokHeadersIfActive({
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
          // Same convention as the macOS/Flutter clients — lets the backend give
          // Windows-appropriate answers instead of defaulting to macOS steps.
          'X-App-Platform': 'windows'
        }),
        // Only include file_ids when there are uploaded attachments; with none
        // the body stays exactly `{ text }` (no key) — the backend defaults
        // file_ids to [], so this preserves today's request byte-for-byte.
        body: JSON.stringify(
          sendFileIds.length ? { text: textToSend, file_ids: sendFileIds } : { text: textToSend }
        ),
        signal: ac.signal
      })
      if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`)

      // Each SSE line arrives as `data: <chunk>` (with `done:` marking the end).
      // Strip the field prefix before appending, otherwise the literal "data:"
      // leaks into the rendered reply. The backend also (a) emits ephemeral
      // "thinking" status events whose payload starts with `think:` ("Checking
      // action items", "Searching memories") — those aren't part of the reply,
      // so drop them; (b) emits a terminal `done:` frame (handled below) and an
      // occasional `message:` frame (base64 JSON for a file-chat side message) —
      // neither is reply text, so drop them so the raw base64 never leaks into the
      // bubble; and (c) encodes reply newlines as the literal token `__CRLF__` so
      // they survive single-line SSE framing; restore those.
      const parseChunk = (line: string): string | null => {
        if (!line || line.startsWith('done:') || line.startsWith('message:')) return null
        const content = line.startsWith('data:') ? line.slice(5).replace(/^ /, '') : line
        if (content.startsWith('think:')) return null
        return content.replace(/__CRLF__/g, '\n')
      }

      // The terminal `done:` frame carries the AUTHORITATIVE final message: a
      // base64 ResponseMessage whose text has the `[n]` citation markers stripped
      // and which carries the server id + cited conversations + chart/NPS data.
      // We capture it here and let it win over the streamed text (C4).
      let donePayload: DoneMessage | null = null
      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() ?? ''
        for (const line of lines) {
          if (line.startsWith('done:')) {
            donePayload = parseDoneMessage(line) ?? donePayload
            continue
          }
          const chunk = parseChunk(line)
          if (chunk === null) continue
          assistantText += chunk
          renderAssistant(assistantMsg(assistantText))
        }
        if (isCurrent() && Date.now() - lastPersist > 1500) {
          lastPersist = Date.now()
          void persistChat(buildThread(assistantMsg(assistantText)), isCurrent)
        }
      }
      if (buffer.startsWith('done:')) {
        donePayload = parseDoneMessage(buffer) ?? donePayload
      } else {
        const tail = parseChunk(buffer)
        if (tail !== null) {
          assistantText += tail
          renderAssistant(assistantMsg(assistantText))
        }
      }
      // Prefer the done payload's citation-stripped text and attach its metadata;
      // fall back to the streamed text if the stream ended without a done frame.
      if (donePayload) {
        assistantText = donePayload.text || assistantText
        finalMsg = {
          ...assistantMsg(assistantText),
          serverId: donePayload.id,
          citations: donePayload.citations.length ? donePayload.citations : undefined,
          chartData: donePayload.chartData,
          askForNps: donePayload.askForNps || undefined
        }
      } else {
        finalMsg = assistantMsg(assistantText)
      }
      // The conversational backend sometimes answers an action-intent message
      // with raw plan JSON (when it reached chat WITHOUT our planner — e.g. a
      // keyword-less follow-up like "again"). Don't render that raw in the thread.
      if (looksLikeRawPlan(assistantText)) {
        assistantText =
          'It looks like you want me to do something in an app. Phrase it as a direct command (e.g. "type report in the search box") with that app focused, and I\'ll show you a plan to approve.'
        finalMsg = assistantMsg(assistantText)
      }
      // INTERIM blank-reply guard (superseded by the structured error taxonomy
      // planned for the chat platform rework). The backend can end the
      // /v2/messages stream as 200 OK with zero bytes — a swallowed pipeline
      // exception yields no data chunks AND no done: frame — which would
      // otherwise render and persist a silent blank assistant bubble. Match the
      // catch path's contract instead: when nothing at all arrived, replace the
      // empty pending bubble with an error message (and, like the catch path,
      // don't speak it). A done: frame carrying structured content (chart /
      // citations) with intentionally empty text is a valid completion, so only
      // the truly-empty case trips this.
      const hasStructuredContent = !!(
        finalMsg.chartData ||
        (finalMsg.citations && finalMsg.citations.length)
      )
      const noReply = !assistantText.trim() && !hasStructuredContent
      if (noReply) {
        assistantText = "Omi didn't send a reply. Try again."
        finalMsg = assistantMsg(assistantText)
      }
      renderAssistant(finalMsg)
      // Voice turn: speak the assembled reply (only on the success path, and only
      // if this generation wasn't dismissed — never speak a zombie reply). Skip
      // the no-reply error so it matches the catch path, which never speaks.
      if (isCurrent() && !noReply) maybeSpeak(assistantText, fromVoice)
    } catch (e) {
      // A reset()/dismiss aborts the fetch, which rejects here — but the generation
      // is already stale, so we must NOT surface an error bubble for it. A watchdog
      // timeout aborts the SAME generation, so it stays current and surfaces the
      // macOS-parity timeout copy instead of the raw "aborted" error.
      if (isCurrent()) {
        // The thrown message is `HTTP <status>` (from the !res.ok throw) or a
        // transport error ("Failed to fetch") when offline — map it to friendly,
        // plain-English copy instead of surfacing the raw string in a bubble.
        assistantText = timedOut
          ? CHAT_STREAM_TIMEOUT_COPY
          : friendlyChatError((e as Error).message)
        finalMsg = assistantMsg(assistantText)
        renderAssistant(finalMsg)
      }
    } finally {
      clearTimeout(watchdog)
      if (abortRef.current === ac) abortRef.current = null
      // Only the current generation may unlatch the busy flag and persist. A stale
      // (dismissed) generation leaves both alone: reset() already unlatched, and a
      // newer send may now own the latch — clobbering either would reintroduce the
      // interleaving/zombie bug.
      if (isCurrent()) {
        setBusy(false)
        await persistChat(buildThread(finalMsg), isCurrent)
      }
    }
  }

  // Start a fresh thread: drop the history and forget the persisted-conversation
  // id so the next send creates a new local conversation.
  const reset = (): void => {
    // Invalidate any in-flight chat generation and abort its fetch/reader. Bumping
    // genRef makes the stale reader's `isCurrent()` false, so it can no longer
    // write to history or SQLite or unlatch the busy flag (C5); the abort stops
    // the reader promptly instead of leaving it draining.
    genRef.current++
    abortRef.current?.abort()
    abortRef.current = null
    // Esc while an agent task is running cancels the task (aborts the attempt
    // and tears the adapter subprocess down), not just the on-screen thread.
    if (activeAgentTaskRef.current) {
      void window.omi.codingAgentCancel(activeAgentTaskRef.current).catch(() => {})
      activeAgentTaskRef.current = null
    }
    // Esc while a pi_mono kernel run is streaming cancels the managed-cloud attempt
    // on the server (parallels the agent-task cancel above), not just the UI.
    if (activeKernelRunRef.current) {
      void window.omi.mainChatCancel(activeKernelRunRef.current).catch(() => {})
      activeKernelRunRef.current = null
    }
    setHistory([])
    setBusy(false)
    // Esc also drops the 'agents' orb pose immediately — the cancel above tears
    // the task down, so don't wait for the in-flight codingAgentRun to resolve.
    setAgentActive(false)
    // Per-launch: forget the id so the next send creates a NEW conversation.
    // Infinite: keep the shared id — reset is only a fresh on-screen view of the
    // same ongoing thread, not a new conversation.
    if (mode !== 'infinite') {
      chatIdRef.current = null
      startedAtRef.current = 0
    }
  }

  // Record a COMPLETED native realtime-hub voice turn (user transcript + assistant
  // reply) into the ONE thread (INV-CHAT-1). The hub already produced AND spoke the
  // reply on the bar, so this APPENDS both messages and persists them WITHOUT
  // calling the LLM or TTS — it must NOT re-answer (no send()). Windows-side mirror
  // of macOS RealtimeHubController's turn persistence (both texts, exactly-once on
  // the terminal; the driver owns the turnRecorded dedup + empty-final guard).
  const recordVoiceTurn = (userText: string, assistantText: string): void => {
    const user = userText.trim()
    const assistant = assistantText.trim()
    if (!user || !assistant) return
    // Same generation guard the send/agent paths use: if the thread is reset while
    // this record's persist is in flight, drop the write so the turn can't be
    // misattributed to the new conversation (per-launch mode replaces, not merges).
    const myGen = genRef.current
    const isCurrent = (): boolean => genRef.current === myGen
    const userMsg: ChatMsg = { id: crypto.randomUUID(), role: 'user', content: user }
    const assistantMsg: ChatMsg = { id: crypto.randomUUID(), role: 'assistant', content: assistant }
    const base = history
    setHistory((h) => [...h, userMsg, assistantMsg])
    void persistChat([...base, userMsg, assistantMsg], isCurrent)
  }

  // Re-thread the live engine onto a chat session (multi-chat, pi_mono). Aborts any
  // in-flight generation exactly like reset(), repoints chatIdRef + sessionIdRef at
  // the target, then loads that thread's transcript into `history`.
  const switchThread = (id: string | null): void => {
    // Same in-flight teardown as reset(): a dismissed reply from the previous thread
    // must not write into the new one or steal the busy latch.
    genRef.current++
    abortRef.current?.abort()
    abortRef.current = null
    if (activeAgentTaskRef.current) {
      void window.omi.codingAgentCancel(activeAgentTaskRef.current).catch(() => {})
      activeAgentTaskRef.current = null
    }
    if (activeKernelRunRef.current) {
      void window.omi.mainChatCancel(activeKernelRunRef.current).catch(() => {})
      activeKernelRunRef.current = null
    }
    setBusy(false)
    setAgentActive(false)

    // Point the engine at the target thread. For a session, unify the ids (D5:
    // session id == kernel chatId == saveDesktopMessage session_id). For null,
    // return to the default shared thread (session_id omitted on saves).
    sessionIdRef.current = id
    setCurrentThreadId(id)
    chatIdRef.current = id ?? resolveDefaultChatId()
    startedAtRef.current = 0

    // Load the target's transcript. Capture the generation so a slower load a newer
    // switch/reset supersedes never paints stale history over the current thread.
    const myGen = genRef.current
    const isCurrent = (): boolean => genRef.current === myGen
    setHistory([])
    if (id === null) {
      // Default thread: the local conversation (as the mount loader reads it).
      const localId = chatIdRef.current
      void window.omi
        .getLocalConversation(localId)
        .then((c) => {
          if (!isCurrent() || !c?.messages) return
          startedAtRef.current = c.startedAt || Date.now()
          setHistory(
            c.messages.map((m) => ({
              id: m.id ?? crypto.randomUUID(),
              role: m.role,
              content: m.content
            }))
          )
        })
        .catch(() => {
          /* no prior conversation — start empty */
        })
    } else {
      // A session: durable SERVER messages (cross-device, Mac parity) — NOT local
      // SQLite, which has no rows for a session created on mobile / another install.
      void getSessionMessages({ sessionId: id })
        .then((msgs) => {
          if (!isCurrent()) return
          setHistory(
            msgs.map((m) => ({
              id: m.id,
              role: m.sender === 'ai' ? 'assistant' : 'user',
              content: m.text
            }))
          )
        })
        .catch(() => {
          /* leave the thread empty on a load failure */
        })
    }
  }

  return {
    history,
    sending,
    speaking,
    agentActive,
    send,
    reset,
    recordVoiceTurn,
    switchThread,
    currentThreadId
  }
}
