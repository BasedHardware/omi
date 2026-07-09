import { useCallback, useEffect, useState } from 'react'
import { Bot, ExternalLink, Loader2, RefreshCw, Send, Trash2, Users } from 'lucide-react'
import { PageHeader } from '../components/layout/PageHeader'
import { auth } from '../lib/firebase'
import { getPreferences } from '../lib/preferences'
import { toast } from '../lib/toast'
import { cn } from '../lib/utils'
import type { AiCloneChat, AiCloneChatMode, AiCloneDraft, AiCloneState } from '../../../shared/types'

const OMI_BASE = import.meta.env.VITE_OMI_API_BASE as string
const MODES: { value: AiCloneChatMode; label: string }[] = [
  { value: 'off', label: 'Off' },
  { value: 'draft', label: 'Draft' },
  { value: 'auto', label: 'Auto' }
]

/** Fresh Firebase auth bundle for main's /v2/messages calls. */
async function buildAuth(): Promise<{ token: string; apiBase: string; displayName?: string } | null> {
  const token = await auth.currentUser?.getIdToken()
  if (!token) return null
  const displayName =
    auth.currentUser?.displayName?.trim() || getPreferences().displayName?.trim() || undefined
  return { token, apiBase: OMI_BASE, displayName }
}

export function AiClone(): React.JSX.Element {
  const [state, setState] = useState<AiCloneState | null>(null)
  const [chats, setChats] = useState<AiCloneChat[] | null>(null)
  const [tokenInput, setTokenInput] = useState('')
  const [busy, setBusy] = useState(false)

  const refreshChats = useCallback(async (): Promise<void> => {
    try {
      setChats(await window.omi.aiCloneListChats())
    } catch {
      setChats([])
    }
  }, [])

  // Initial state + live events. Also answer token-expired requests with a
  // fresh Firebase ID token so the responder keeps working across the ~1h
  // token lifetime without user interaction.
  useEffect(() => {
    void window.omi.aiCloneGetState().then(setState)
    return window.omi.onAiCloneEvent((e) => {
      if (e.kind === 'state') setState(e.state)
      if (e.kind === 'token-expired') {
        void buildAuth().then((a) => a && window.omi.aiCloneProvideAuthToken(a))
      }
    })
  }, [])

  // While enabled, proactively re-supply the token every 30 minutes (getIdToken
  // transparently refreshes) so main never holds an expired one.
  useEffect(() => {
    if (!state?.enabled) return
    const id = setInterval(() => {
      void buildAuth().then((a) => a && window.omi.aiCloneProvideAuthToken(a))
    }, 30 * 60 * 1000)
    return () => clearInterval(id)
  }, [state?.enabled])

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- intentional load-once-when-reachable; setChats lands after an async IPC round-trip, not synchronously
    if (state?.beeperConnected && state.beeperReachable && chats === null) void refreshChats()
  }, [state?.beeperConnected, state?.beeperReachable, chats, refreshChats])

  const connect = async (): Promise<void> => {
    const token = tokenInput.trim()
    if (!token || busy) return
    setBusy(true)
    try {
      const next = await window.omi.aiCloneConnect(token)
      setState(next)
      if (next.beeperConnected) {
        setTokenInput('')
        toast('Beeper connected', { tone: 'success' })
        void refreshChats()
      } else if (next.error) {
        toast('Could not connect', { tone: 'error', body: next.error })
      }
    } finally {
      setBusy(false)
    }
  }

  const disconnect = async (): Promise<void> => {
    if (busy) return
    setBusy(true)
    try {
      setState(await window.omi.aiCloneDisconnect())
      setChats(null)
      toast('Beeper disconnected', { tone: 'success' })
    } finally {
      setBusy(false)
    }
  }

  const toggleEnabled = async (): Promise<void> => {
    if (!state || busy) return
    setBusy(true)
    try {
      const enabling = !state.enabled
      const authBundle = enabling ? await buildAuth() : undefined
      if (enabling && !authBundle) {
        toast('Sign in to Omi first', { tone: 'error' })
        return
      }
      setState(await window.omi.aiCloneSetEnabled(enabling, authBundle ?? undefined))
    } finally {
      setBusy(false)
    }
  }

  const setMode = async (chat: AiCloneChat, mode: AiCloneChatMode): Promise<void> => {
    if (
      mode === 'auto' &&
      chat.mode !== 'auto' &&
      !window.confirm(
        `Auto-send replies in "${chat.title}"? Omi will answer new messages there without asking you first.`
      )
    ) {
      return
    }
    setChats((cs) => (cs ?? []).map((c) => (c.id === chat.id ? { ...c, mode } : c)))
    await window.omi.aiCloneSetChatMode(chat.id, mode)
  }

  if (!state) {
    return (
      <div className="flex h-full items-center justify-center text-white/40">
        <Loader2 className="h-5 w-5 animate-spin" />
      </div>
    )
  }

  return (
    <>
      <PageHeader
        title="AI Clone"
        subtitle="Omi answers your WhatsApp, Telegram and other chats as you — drafts first, auto-send only where you allow it."
      />
      <div className="min-h-0 flex-1 overflow-y-auto px-6 pb-10 lg:px-10">
        <div className="mx-auto flex max-w-3xl flex-col gap-6">
          <ConnectCard
            state={state}
            tokenInput={tokenInput}
            setTokenInput={setTokenInput}
            busy={busy}
            onConnect={connect}
            onDisconnect={disconnect}
            onToggleEnabled={toggleEnabled}
          />
          {state.beeperConnected && (
            <ChatsCard chats={chats} onRefresh={refreshChats} onSetMode={setMode} />
          )}
          {state.beeperConnected && <InboxCard state={state} />}
        </div>
      </div>
    </>
  )
}

function StatusDot({ on }: { on: boolean }): React.JSX.Element {
  return (
    <span
      className={cn('inline-block h-2 w-2 shrink-0 rounded-full', on ? 'bg-emerald-400' : 'bg-white/25')}
    />
  )
}

function ConnectCard(props: {
  state: AiCloneState
  tokenInput: string
  setTokenInput: (v: string) => void
  busy: boolean
  onConnect: () => Promise<void>
  onDisconnect: () => Promise<void>
  onToggleEnabled: () => Promise<void>
}): React.JSX.Element {
  const { state, tokenInput, setTokenInput, busy } = props
  return (
    <section className="surface-card p-5">
      <div className="flex items-start justify-between gap-4">
        <div className="flex min-w-0 items-start gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl border border-white/10 bg-white/5">
            <Bot className="h-5 w-5 text-white/70" />
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2 font-display font-semibold text-white/95">
              <StatusDot on={state.beeperConnected && state.beeperReachable} />
              Beeper
            </div>
            <p className="mt-0.5 text-xs leading-relaxed text-white/55">
              {state.beeperConnected
                ? state.beeperReachable
                  ? 'Connected — listening for new messages.'
                  : 'Token saved, but Beeper Desktop isn’t reachable. Open Beeper Desktop.'
                : 'Beeper bundles WhatsApp, Telegram, Signal and more into one inbox on this PC. Omi connects to it locally — messages never leave your machine on the way in.'}
            </p>
            {state.error && <p className="mt-1 text-xs text-red-400/90">{state.error}</p>}
          </div>
        </div>
        {state.beeperConnected && (
          <button onClick={props.onDisconnect} disabled={busy} className="btn-ghost shrink-0 disabled:opacity-40">
            Disconnect
          </button>
        )}
      </div>

      {!state.beeperConnected ? (
        <div className="mt-4">
          <div className="flex gap-2">
            <input
              type="password"
              value={tokenInput}
              onChange={(e) => setTokenInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && void props.onConnect()}
              placeholder="Paste your Beeper access token"
              className="min-w-0 flex-1 rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white placeholder:text-white/30 focus:border-white/30 focus:outline-none"
            />
            <button
              onClick={props.onConnect}
              disabled={busy || !tokenInput.trim()}
              className="btn-primary px-4 py-2 disabled:opacity-40"
            >
              {busy ? 'Connecting…' : 'Connect'}
            </button>
          </div>
          <p className="mt-2 flex items-center gap-1 text-[11px] text-white/40">
            <ExternalLink className="h-3 w-3" />
            In Beeper Desktop: Settings → Integrations → Approved connections → “+” to create a token.
          </p>
        </div>
      ) : (
        <div className="mt-4 flex items-center justify-between rounded-xl border border-white/10 bg-white/5 px-4 py-3">
          <div>
            <div className="text-sm font-medium text-white/90">Respond on my behalf</div>
            <div className="text-xs text-white/50">
              {state.enabled
                ? `On — drafting replies${state.autoSentThisHour ? ` · ${state.autoSentThisHour} auto-sent this hour` : ''}`
                : 'Off — Omi is not reading or answering your chats.'}
            </div>
          </div>
          <button
            onClick={props.onToggleEnabled}
            disabled={busy}
            aria-pressed={state.enabled}
            className={cn(
              'relative h-5 w-9 shrink-0 rounded-full transition-colors duration-200 disabled:opacity-40',
              state.enabled ? 'bg-[color:var(--accent)]' : 'bg-white/15'
            )}
          >
            <span
              className={cn(
                'absolute top-0.5 h-4 w-4 rounded-full bg-white transition-all duration-200',
                state.enabled ? 'left-[18px]' : 'left-0.5'
              )}
            />
          </button>
        </div>
      )}
    </section>
  )
}

function ChatsCard(props: {
  chats: AiCloneChat[] | null
  onRefresh: () => Promise<void>
  onSetMode: (chat: AiCloneChat, mode: AiCloneChatMode) => Promise<void>
}): React.JSX.Element {
  const { chats } = props
  return (
    <section className="surface-card p-5">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="font-display font-semibold text-white/95">Chats</h2>
        <button onClick={() => void props.onRefresh()} className="btn-ghost p-2" title="Refresh chats">
          <RefreshCw className="h-4 w-4" />
        </button>
      </div>
      <p className="mb-3 text-xs text-white/50">
        Draft = Omi writes a reply and waits for your approval below. Auto = Omi sends it
        immediately (never for group chats).
      </p>
      {chats === null ? (
        <div className="flex justify-center py-6 text-white/40">
          <Loader2 className="h-5 w-5 animate-spin" />
        </div>
      ) : chats.length === 0 ? (
        <p className="py-4 text-center text-sm text-white/40">
          No chats yet — make sure your networks are connected in Beeper.
        </p>
      ) : (
        <ul className="flex flex-col divide-y divide-white/5">
          {chats.map((chat) => (
            <li key={chat.id} className="flex items-center gap-3 py-2.5">
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="truncate text-sm font-medium text-white/90">{chat.title}</span>
                  {chat.type === 'group' && <Users className="h-3 w-3 shrink-0 text-white/35" />}
                </div>
                <div className="text-[11px] text-white/40">{chat.network}</div>
              </div>
              <div className="flex shrink-0 overflow-hidden rounded-lg border border-white/10">
                {MODES.map(({ value, label }) => (
                  <button
                    key={value}
                    onClick={() => void props.onSetMode(chat, value)}
                    className={cn(
                      'px-2.5 py-1 text-[11px] font-medium transition-colors',
                      chat.mode === value
                        ? 'bg-white/15 text-white'
                        : 'text-white/45 hover:bg-white/5 hover:text-white/80'
                    )}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

function InboxCard({ state }: { state: AiCloneState }): React.JSX.Element {
  return (
    <section className="surface-card p-5">
      <h2 className="mb-3 font-display font-semibold text-white/95">
        Inbox{state.pendingDrafts.length > 0 && ` · ${state.pendingDrafts.length} waiting`}
      </h2>
      {state.pendingDrafts.length === 0 ? (
        <p className="py-4 text-center text-sm text-white/40">
          Nothing waiting — new drafts show up here the moment someone messages you.
        </p>
      ) : (
        <div className="flex flex-col gap-3">
          {state.pendingDrafts.map((d) => (
            <DraftRow key={d.id} draft={d} />
          ))}
        </div>
      )}
      {state.activity.length > 0 && (
        <div className="mt-5">
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-white/40">
            Recent activity
          </h3>
          <ul className="flex flex-col gap-1">
            {state.activity.slice(0, 8).map((a) => (
              <li key={a.id} className="flex items-baseline gap-2 text-xs">
                <span className="shrink-0 text-white/35">
                  {new Date(a.at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                </span>
                <span
                  className={cn(
                    'shrink-0 font-medium',
                    a.kind === 'error' ? 'text-red-400/80' : 'text-white/60'
                  )}
                >
                  {a.kind === 'auto_sent'
                    ? `Auto-sent to ${a.chatTitle}:`
                    : a.kind === 'draft_sent'
                      ? `Sent to ${a.chatTitle}:`
                      : a.kind === 'draft_dismissed'
                        ? `Dismissed (${a.chatTitle}):`
                        : `${a.chatTitle}:`}
                </span>
                <span className="truncate text-white/45">{a.text}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  )
}

function DraftRow({ draft }: { draft: AiCloneDraft }): React.JSX.Element {
  const [text, setText] = useState(draft.replyText)
  const [busy, setBusy] = useState(false)

  const approve = async (): Promise<void> => {
    if (busy || !text.trim()) return
    setBusy(true)
    try {
      const next = await window.omi.aiCloneApproveDraft(draft.id, text)
      if (next.error) toast('Could not send', { tone: 'error', body: next.error })
      else toast(`Sent to ${draft.chatTitle}`, { tone: 'success' })
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="rounded-xl border border-white/10 bg-white/5 p-3">
      <div className="mb-1 flex items-center gap-2 text-xs text-white/50">
        <span className="font-medium text-white/80">{draft.senderName}</span>
        <span className="badge">{draft.network}</span>
        <span className="ml-auto shrink-0">
          {new Date(draft.createdAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
        </span>
      </div>
      <p className="mb-2 text-sm text-white/70">“{draft.incomingText}”</p>
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={Math.min(4, Math.max(2, Math.ceil(text.length / 60)))}
        className="mb-2 w-full resize-none rounded-lg border border-white/10 bg-black/20 px-3 py-2 text-sm text-white/90 focus:border-white/30 focus:outline-none"
      />
      <div className="flex justify-end gap-2">
        <button
          onClick={() => void window.omi.aiCloneDiscardDraft(draft.id)}
          disabled={busy}
          className="btn-ghost flex items-center gap-1.5 disabled:opacity-40"
        >
          <Trash2 className="h-3.5 w-3.5" /> Dismiss
        </button>
        <button
          onClick={approve}
          disabled={busy || !text.trim()}
          className="btn-primary flex items-center gap-1.5 px-4 py-2 disabled:opacity-40"
        >
          {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Send className="h-3.5 w-3.5" />}
          Approve & Send
        </button>
      </div>
    </div>
  )
}
