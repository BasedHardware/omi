import { useEffect, useState } from 'react'
import { StickyNote, Mail, Inbox, MessageSquare } from 'lucide-react'
import { toast } from '../../../lib/toast'
import { readAndExtractStickyNotes, importStickyMemories } from '../../../lib/stickyNotesImport'
import { toastImportTally } from '../../../lib/importToast'
import { useMemories } from '../../../hooks/useMemories'
import { useGoogleConnection } from '../../../hooks/useGoogleConnection'
import { GMAIL_SESSION_ENABLED } from '../../../lib/gmailSessionFeatureFlag'
import { auth } from '../../../lib/firebase'
import { SettingRow } from '../SettingRow'
import { Toggle } from '../Toggle'
import type {
  BeeperDraft,
  BeeperNetwork,
  BeeperSendMode,
  BeeperStatus,
  GmailSessionStatus
} from '../../../../../shared/types'

export function IntegrationsTab(): React.JSX.Element {
  const { memories, refresh } = useMemories()

  // --- Sticky Notes ---
  const [stickyReading, setStickyReading] = useState(false)
  const [stickyImporting, setStickyImporting] = useState(false)
  const [stickyMemories, setStickyMemories] = useState<string[] | null>(null)
  const [stickyProfile, setStickyProfile] = useState('')

  const readSticky = async (): Promise<void> => {
    if (stickyReading || stickyImporting) return
    setStickyReading(true)
    setStickyMemories(null)
    setStickyProfile('')
    try {
      const outcome = await readAndExtractStickyNotes(memories.map((m) => m.content))
      if (outcome.status === 'unavailable')
        toast('No Sticky Notes found on this PC', { tone: 'warn' })
      else if (outcome.status === 'error')
        toast('Could not read Sticky Notes', { tone: 'error', body: outcome.error })
      else if (outcome.status === 'empty')
        toast(
          outcome.reason === 'no-notes'
            ? 'No note text to import'
            : 'No new memories found in your notes',
          { tone: 'warn' }
        )
      else {
        setStickyMemories(outcome.memories)
        setStickyProfile(outcome.profile)
      }
    } catch (e) {
      toast('Could not read Sticky Notes', { tone: 'error', body: (e as Error).message })
    } finally {
      setStickyReading(false)
    }
  }

  const importSticky = async (): Promise<void> => {
    if (!stickyMemories || stickyMemories.length === 0 || stickyImporting) return
    setStickyImporting(true)
    const tally = await importStickyMemories(stickyMemories, stickyProfile)
    setStickyImporting(false)
    toastImportTally(tally)
    if (tally.ok > 0) await refresh()
    if (!tally.failed) {
      setStickyMemories(null)
      setStickyProfile('')
    }
  }

  // --- Google --- (client-side Gmail lane; shared with the Hub Email card, incl.
  // the sync-on-connect + 15-min background resync, via the singleton hook.)
  const {
    googleEnabled,
    status: googleStatus,
    connect: connectGoogle,
    disconnect: disconnectGoogle,
    syncNow: runSync,
    busy: googleBusy,
    syncing: googleSyncing
  } = useGoogleConnection()

  // --- Gmail (session): Option B. Sign into Google once inside an Omi-owned window;
  // we replay Gmail's web endpoints against that persisted session (no OAuth scopes). ---
  const [gmailStatus, setGmailStatus] = useState<GmailSessionStatus>({ connected: false })
  const [gmailBusy, setGmailBusy] = useState(false)
  const [gmailFetching, setGmailFetching] = useState(false)

  useEffect(() => {
    if (!GMAIL_SESSION_ENABLED) return
    window.omi
      .gmailSessionStatus()
      .then(setGmailStatus)
      .catch(() => {})
  }, [])

  const connectGmail = async (): Promise<void> => {
    if (gmailBusy) return
    setGmailBusy(true)
    try {
      // Pre-select the account: pass the signed-in Omi user's Google email so Google
      // lands on "Continue as <account>" instead of an empty identifier field.
      const next = await window.omi.gmailSessionConnect(auth.currentUser?.email ?? undefined)
      setGmailStatus(next)
      if (next.connected) toast('Gmail connected', { tone: 'success' })
      else if (next.message) toast('Gmail not connected', { tone: 'warn', body: next.message })
    } catch (e) {
      toast('Could not connect Gmail', { tone: 'error', body: (e as Error).message })
    } finally {
      setGmailBusy(false)
    }
  }

  const fetchGmail = async (): Promise<void> => {
    if (gmailFetching) return
    setGmailFetching(true)
    try {
      const res = await window.omi.gmailSessionFetch('newer_than:7d', 25)
      if (res.ok) {
        toast(`Read ${res.emails.length} recent email${res.emails.length === 1 ? '' : 's'}`, {
          tone: 'success'
        })
      } else {
        toast('Could not read Gmail', { tone: 'warn', body: res.error })
        // Network-probe the session (not the cheap cookie check): a stale-but-present
        // session verifies as disconnected, flipping the row back to a Connect prompt.
        setGmailStatus(await window.omi.gmailSessionVerify())
      }
    } catch (e) {
      toast('Could not read Gmail', { tone: 'error', body: (e as Error).message })
    } finally {
      setGmailFetching(false)
    }
  }

  const disconnectGmail = async (): Promise<void> => {
    if (gmailBusy) return
    setGmailBusy(true)
    try {
      setGmailStatus(await window.omi.gmailSessionDisconnect())
      toast('Gmail disconnected', { tone: 'success' })
    } catch (e) {
      toast('Could not disconnect', { tone: 'error', body: (e as Error).message })
    } finally {
      setGmailBusy(false)
    }
  }

  return (
    <>
      <ChatReplySettings />
      <SettingRow
        icon={StickyNote}
        title="Windows Sticky Notes"
        subtitle="Reads your Sticky Notes locally and saves durable facts as memories. Your notes are never uploaded — only the synthesized facts."
        keywords="sticky notes import integration"
        control={
          <div className="flex items-center gap-2">
            <button
              onClick={readSticky}
              disabled={stickyReading || stickyImporting}
              className="btn-ghost disabled:opacity-40"
            >
              {stickyReading ? 'Reading…' : 'Read notes'}
            </button>
            {stickyMemories && stickyMemories.length > 0 && (
              <button
                onClick={importSticky}
                disabled={stickyImporting}
                className="btn-primary px-4 py-2 disabled:opacity-40"
              >
                {stickyImporting
                  ? 'Importing…'
                  : `Import ${stickyMemories.length} memor${stickyMemories.length === 1 ? 'y' : 'ies'}`}
              </button>
            )}
          </div>
        }
      >
        {stickyProfile && (
          <p className="glass-subtle mb-2 rounded-lg px-4 py-3 text-sm italic text-text-tertiary">
            {stickyProfile}
          </p>
        )}
        {stickyMemories && stickyMemories.length > 0 && (
          <ul className="glass-subtle max-h-40 overflow-y-auto rounded-lg px-4 py-3 text-sm text-text-tertiary">
            {stickyMemories.map((m, i) => (
              <li key={i} className="py-0.5">
                • {m}
              </li>
            ))}
          </ul>
        )}
      </SettingRow>

      {googleEnabled && (
        <SettingRow
          icon={Mail}
          dot={googleStatus.connected ? 'on' : 'off'}
          title="Google (Gmail + Calendar)"
          subtitle={
            googleStatus.connected
              ? `Connected${googleStatus.email ? ` as ${googleStatus.email}` : ''}${
                  googleStatus.lastSyncAt
                    ? ` · last sync ${new Date(googleStatus.lastSyncAt).toLocaleString()}`
                    : ''
                }`
              : 'Turn recent email (subject/sender only) into memories and upcoming events into tasks.'
          }
          keywords="google gmail calendar sync integration"
          control={
            googleStatus.connected ? (
              <div className="flex items-center gap-2">
                <button
                  onClick={runSync}
                  disabled={googleSyncing}
                  className="btn-primary px-4 py-2 disabled:opacity-40"
                >
                  {googleSyncing ? 'Syncing…' : 'Sync now'}
                </button>
                <button
                  onClick={disconnectGoogle}
                  disabled={googleBusy}
                  className="btn-ghost disabled:opacity-40"
                >
                  Disconnect
                </button>
              </div>
            ) : (
              <button
                onClick={connectGoogle}
                disabled={googleBusy}
                className="btn-ghost disabled:opacity-40"
              >
                {googleBusy ? 'Connecting…' : 'Connect'}
              </button>
            )
          }
        />
      )}

      {GMAIL_SESSION_ENABLED && (
        <SettingRow
          icon={Inbox}
          dot={gmailStatus.connected ? 'on' : 'off'}
          title="Gmail (session)"
          subtitle={
            gmailStatus.connected
              ? 'Connected — reads recent mail through your signed-in Google session. No OAuth scopes; sign-in stays inside Omi.'
              : gmailStatus.message ||
                'Sign into Google once inside Omi, then read recent mail without restricted-scope OAuth.'
          }
          keywords="gmail session email inbox connect integration"
          control={
            gmailStatus.connected ? (
              <div className="flex items-center gap-2">
                <button
                  onClick={fetchGmail}
                  disabled={gmailFetching}
                  className="btn-primary px-4 py-2 disabled:opacity-40"
                >
                  {gmailFetching ? 'Reading…' : 'Fetch recent'}
                </button>
                <button
                  onClick={disconnectGmail}
                  disabled={gmailBusy}
                  className="btn-ghost disabled:opacity-40"
                >
                  Disconnect
                </button>
              </div>
            ) : (
              <button
                onClick={connectGmail}
                disabled={gmailBusy}
                className="btn-ghost disabled:opacity-40"
              >
                {gmailBusy ? 'Connecting…' : 'Connect'}
              </button>
            )
          }
        />
      )}
    </>
  )
}

const EMPTY_BEEPER: BeeperStatus = {
  running: false,
  connected: false,
  enabled: false,
  sendMode: 'draft',
  networks: ['whatsapp', 'telegram'],
  accounts: [],
  draftCount: 0,
  imessageSupported: false
}

function ChatReplySettings(): React.JSX.Element {
  const [status, setStatus] = useState<BeeperStatus>(EMPTY_BEEPER)
  const [drafts, setDrafts] = useState<BeeperDraft[]>([])
  const [token, setToken] = useState('')
  const [busy, setBusy] = useState(false)

  const refresh = async (): Promise<void> => {
    try {
      const [next, list] = await Promise.all([
        window.omi.beeperStatus(),
        window.omi.beeperListDrafts()
      ])
      setStatus(next)
      setDrafts(list)
    } catch {
      setStatus(EMPTY_BEEPER)
    }
  }

  useEffect(() => {
    window.omi
      .beeperStatus()
      .then(setStatus)
      .catch(() => {})
    window.omi
      .beeperListDrafts()
      .then(setDrafts)
      .catch(() => {})
    const unsub = window.omi.onBeeperChanged((next) => {
      setStatus(next)
      void window.omi
        .beeperListDrafts()
        .then(setDrafts)
        .catch(() => {})
    })
    return () => unsub()
  }, [])

  const connect = async (): Promise<void> => {
    if (busy || !token.trim()) return
    setBusy(true)
    try {
      setStatus(await window.omi.beeperConnect(token.trim()))
      setToken('')
      toast('Beeper connected', { tone: 'success' })
    } catch (e) {
      toast('Could not connect Beeper', { tone: 'error', body: (e as Error).message })
    } finally {
      setBusy(false)
    }
  }

  const patch = async (next: {
    enabled?: boolean
    sendMode?: BeeperSendMode
    networks?: BeeperNetwork[]
  }): Promise<void> => {
    try {
      setStatus(await window.omi.beeperSetSettings(next))
    } catch (e) {
      toast('Could not update chat reply', { tone: 'error', body: (e as Error).message })
    }
  }

  const subtitle = !status.connected
    ? status.running
      ? 'Beeper is running. Settings → Integrations: turn on Allow connections, scroll to Approved connections, click +.'
      : 'Install Beeper Desktop, connect WhatsApp or Telegram, then paste an access token.'
    : status.enabled
      ? status.sendMode === 'auto'
        ? 'Omi is sending drafts automatically in unread DMs.'
        : `${status.draftCount} draft${status.draftCount === 1 ? '' : 's'} waiting. Replies use your memories.`
      : 'Connected. Turn on to draft replies in unread DMs.'

  return (
    <>
      <SettingRow
        icon={MessageSquare}
        dot={status.connected && status.enabled ? 'on' : status.connected ? 'warn' : 'off'}
        title="Reply in your chats"
        subtitle={subtitle}
        keywords="beeper whatsapp telegram imessage chat reply draft"
        control={
          status.connected ? (
            <Toggle
              on={status.enabled}
              label="Enable chat replies"
              onChange={(on) => void patch({ enabled: on })}
            />
          ) : !status.running ? (
            <button
              type="button"
              onClick={() => void window.omi.beeperOpenDownload()}
              className="btn-ghost"
            >
              Install Beeper
            </button>
          ) : undefined
        }
      >
        {!status.connected && (
          <div className="mt-3 flex gap-2">
            <input
              type="password"
              autoComplete="off"
              placeholder="Paste Beeper access token"
              value={token}
              onChange={(e) => setToken(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') void connect()
              }}
              className="min-w-0 flex-1 rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-[13px] text-white placeholder:text-white/30 outline-none"
            />
            <button
              type="button"
              onClick={() => void connect()}
              disabled={busy || !token.trim()}
              className="btn-primary px-3 py-2 disabled:opacity-40"
            >
              {busy ? 'Connecting…' : 'Connect'}
            </button>
          </div>
        )}
        {status.connected && (
          <div className="mt-3 flex flex-col gap-3 text-[13px] text-white/70">
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={status.networks.includes('whatsapp')}
                onChange={(e) =>
                  void patch({
                    networks: toggleNetwork(status.networks, 'whatsapp', e.target.checked)
                  })
                }
              />
              WhatsApp
            </label>
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={status.networks.includes('telegram')}
                onChange={(e) =>
                  void patch({
                    networks: toggleNetwork(status.networks, 'telegram', e.target.checked)
                  })
                }
              />
              Telegram
            </label>
            <label className="flex items-center gap-2 opacity-50">
              <input type="checkbox" disabled checked={false} />
              iMessage — Mac only
            </label>
            <label className="flex items-center gap-2">
              <input
                type="radio"
                name="beeper-mode"
                checked={status.sendMode === 'draft'}
                onChange={() => void patch({ sendMode: 'draft' })}
              />
              Draft only (recommended)
            </label>
            <label className="flex items-center gap-2">
              <input
                type="radio"
                name="beeper-mode"
                checked={status.sendMode === 'auto'}
                onChange={() => void patch({ sendMode: 'auto' })}
              />
              Send automatically
            </label>
            <div className="flex gap-2">
              <button
                type="button"
                className="btn-ghost"
                onClick={() => void window.omi.beeperPollNow()}
              >
                Check now
              </button>
              <button
                type="button"
                className="btn-ghost"
                onClick={() =>
                  void window.omi
                    .beeperDisconnect()
                    .then(setStatus)
                    .catch((e: Error) => {
                      toast('Could not disconnect', { tone: 'error', body: e.message })
                    })
                }
              >
                Disconnect
              </button>
            </div>
            {drafts.length > 0 && (
              <ul className="divide-y divide-white/5 rounded-lg border border-white/5">
                {drafts.map((d) => (
                  <li key={d.id} className="flex flex-col gap-2 px-3 py-3">
                    <p className="text-white/85">
                      {d.chatTitle}
                      <span className="ml-2 text-white/35">{d.network}</span>
                    </p>
                    <p className="text-white/45">In: {d.inboundText}</p>
                    <p className="text-white/80">Out: {d.replyText}</p>
                    <div className="flex gap-2">
                      <button
                        type="button"
                        className="btn-primary px-3 py-1.5"
                        onClick={() =>
                          void window.omi
                            .beeperSendDraft(d.id)
                            .then(refresh)
                            .catch((e: Error) => {
                              toast('Could not send', { tone: 'error', body: e.message })
                            })
                        }
                      >
                        Send
                      </button>
                      <button
                        type="button"
                        className="btn-ghost"
                        onClick={() => void window.omi.beeperDismissDraft(d.id).then(refresh)}
                      >
                        Skip
                      </button>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </SettingRow>
    </>
  )
}

function toggleNetwork(current: BeeperNetwork[], n: BeeperNetwork, on: boolean): BeeperNetwork[] {
  if (on) return Array.from(new Set([...current, n]))
  return current.filter((x) => x !== n)
}
