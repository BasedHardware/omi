import { useEffect, useState } from 'react'
import { toast } from '../../../../lib/toast'
import { ConnectorRow, PillButton } from './ConnectorRow'
import { ConnectorBrandMark } from './ConnectorBrandMark'
import { ChatReplyDemo } from '../../../chatReply/ChatReplyDemo'
import { BeeperConnectForm } from '../../../chatReply/BeeperConnectForm'
import type { BeeperDraft, BeeperStatus } from '../../../../../../shared/types'

const EMPTY: BeeperStatus = {
  running: false,
  connected: false,
  enabled: false,
  sendMode: 'draft',
  networks: ['whatsapp', 'telegram'],
  accounts: [],
  draftCount: 0,
  imessageSupported: false
}

/** Connect-hub detail: Omi drafts WhatsApp/Telegram replies as you. */
export function ChatReplyConnector(): React.JSX.Element {
  const [status, setStatus] = useState<BeeperStatus>(EMPTY)
  const [drafts, setDrafts] = useState<BeeperDraft[]>([])
  const [token, setToken] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

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
    setError(null)
    try {
      const connected = await window.omi.beeperConnect(token.trim())
      setToken('')
      try {
        setStatus(
          await window.omi.beeperSetSettings({
            enabled: true,
            sendMode: 'draft',
            networks: ['whatsapp', 'telegram']
          })
        )
      } catch {
        setStatus(connected)
      }
      toast('Chat replies connected', { tone: 'success' })
    } catch (e) {
      setError((e as Error).message || 'Could not connect')
    } finally {
      setBusy(false)
    }
  }

  const description = status.connected
    ? status.enabled
      ? 'Drafting replies in unread DMs from your memories.'
      : 'Connected. Turn on to draft replies.'
    : 'Omi drafts WhatsApp and Telegram replies as you.'

  return (
    <ConnectorRow
      iconNode={<ConnectorBrandMark brand="omi" />}
      title="WhatsApp & Telegram"
      description={description}
      action={
        status.connected ? (
          <PillButton
            tone={status.enabled ? 'neutral' : 'primary'}
            onClick={() =>
              void window.omi.beeperSetSettings({ enabled: !status.enabled }).then(setStatus)
            }
          >
            {status.enabled ? 'On' : 'Enable'}
          </PillButton>
        ) : undefined
      }
    >
      <div className="flex flex-col gap-4">
        <ChatReplyDemo />
        <BeeperConnectForm
          status={status}
          token={token}
          busy={busy}
          error={error}
          onToken={setToken}
          onConnect={() => void connect()}
          onInstall={() => void window.omi.beeperOpenDownload()}
        />
        {drafts.length > 0 && (
          <ul className="divide-y divide-white/5 rounded-lg border border-white/5">
            {drafts.map((d) => (
              <li key={d.id} className="flex flex-col gap-2 px-3 py-3 text-[13px]">
                <p className="text-home-ink">
                  {d.chatTitle}
                  <span className="ml-2 text-home-faint">{d.network}</span>
                </p>
                <p className="text-home-muted">In: {d.inboundText}</p>
                <p className="text-home-ink">Out: {d.replyText}</p>
                <div className="flex gap-2">
                  <PillButton
                    tone="primary"
                    onClick={() =>
                      void window.omi
                        .beeperSendDraft(d.id)
                        .then(() => window.omi.beeperListDrafts().then(setDrafts))
                        .catch((e: Error) =>
                          toast('Could not send', { tone: 'error', body: e.message })
                        )
                    }
                  >
                    Send
                  </PillButton>
                  <PillButton
                    tone="ghost"
                    onClick={() =>
                      void window.omi
                        .beeperDismissDraft(d.id)
                        .then(() => window.omi.beeperListDrafts().then(setDrafts))
                    }
                  >
                    Skip
                  </PillButton>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </ConnectorRow>
  )
}
