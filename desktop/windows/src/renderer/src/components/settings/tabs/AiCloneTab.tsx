// Settings → AI Clone (Track 2): connect a Beeper Desktop access token, pick
// which chats Omi may draft/auto-send replies for, and review/approve/dismiss
// queued drafts. Beeper is the aggregation layer across WhatsApp, Telegram,
// iMessage, etc., so this one connect flow covers all of them — there's no
// per-network UI to build here.
import { useEffect, useState } from 'react'
import { MessageCircle } from 'lucide-react'
import { SettingRow } from '../SettingRow'
import { useAiCloneStatus, useAiCloneChats, useAiCloneDrafts } from '../../../hooks/useAiClone'
import type { AiCloneChatMode } from '../../../../../shared/types'

const MODE_LABEL: Record<AiCloneChatMode, string> = {
  off: 'Off',
  draft: 'Draft for review',
  auto_send: 'Auto-send'
}

const MODES: AiCloneChatMode[] = ['off', 'draft', 'auto_send']

/** How often the drafts queue refreshes while this tab is open, so a draft
 *  produced by a background poll shows up without the user re-opening
 *  Settings. Status/chats don't need this — they only change on user action. */
const DRAFTS_POLL_MS = 15_000

export function AiCloneTab(): React.JSX.Element {
  const { status, refresh: refreshStatus } = useAiCloneStatus()
  const { chats, refresh: refreshChats } = useAiCloneChats()
  const { drafts, refresh: refreshDrafts } = useAiCloneDrafts()

  const [tokenInput, setTokenInput] = useState('')
  const [connecting, setConnecting] = useState(false)
  const [connectError, setConnectError] = useState<string | undefined>()
  const [editing, setEditing] = useState<Record<string, string>>({})

  useEffect(() => {
    const id = setInterval(refreshDrafts, DRAFTS_POLL_MS)
    return () => clearInterval(id)
  }, [refreshDrafts])

  const connect = (): void => {
    const token = tokenInput.trim()
    if (!token) return
    setConnecting(true)
    setConnectError(undefined)
    void window.omi
      .aiCloneConnect(token)
      .then((result) => {
        setConnecting(false)
        if (!result.connected) {
          setConnectError(result.error ?? 'Could not connect — check the token and try again.')
          return
        }
        setTokenInput('')
        refreshStatus()
        refreshChats()
      })
      .catch(() => {
        setConnecting(false)
        setConnectError('Could not connect — check the token and try again.')
      })
  }

  const disconnect = (): void => {
    void window.omi
      .aiCloneDisconnect()
      .then(() => {
        refreshStatus()
        refreshChats()
      })
      .catch(() => {})
  }

  const setMode = (chatID: string, displayName: string, mode: AiCloneChatMode): void => {
    void window.omi
      .aiCloneSetChatMode(chatID, displayName, mode)
      .then(refreshChats)
      .catch(() => {})
  }

  const approve = (id: string, editedText?: string): void => {
    void window.omi
      .aiCloneApproveDraft(id, editedText)
      .then(refreshDrafts)
      .catch(() => {})
    setEditing((e) => {
      const next = { ...e }
      delete next[id]
      return next
    })
  }

  const dismiss = (id: string): void => {
    void window.omi
      .aiCloneDismissDraft(id)
      .then(refreshDrafts)
      .catch(() => {})
  }

  return (
    <>
      <SettingRow
        icon={MessageCircle}
        title="Beeper"
        subtitle="Connects Omi to your messaging accounts (WhatsApp, Telegram, iMessage, and anything else Beeper bridges) so it can draft or send replies as you."
        keywords="ai clone beeper telegram whatsapp imessage messages reply auto-reply"
        dot={status.connected ? 'on' : 'off'}
        control={
          status.connected ? (
            <button onClick={disconnect} className="btn-ghost">
              Disconnect
            </button>
          ) : undefined
        }
      >
        {status.connected ? (
          <div className="text-sm text-text-tertiary">
            {status.accounts.length > 0
              ? `Connected — ${status.accounts.map((a) => a.network).join(', ')}.`
              : 'Connected, but no messaging accounts were found in Beeper Desktop.'}
          </div>
        ) : (
          <div className="space-y-2">
            <div className="text-sm text-text-tertiary">
              Open Beeper Desktop → Settings → Developer, generate an access token, and paste it
              here. Beeper Desktop must be running on this computer.
            </div>
            <div className="flex items-center gap-2">
              <input
                type="password"
                value={tokenInput}
                onChange={(e) => setTokenInput(e.target.value)}
                placeholder="Beeper access token"
                className="input-field flex-1"
              />
              <button
                onClick={connect}
                disabled={connecting || !tokenInput.trim()}
                className="btn-ghost disabled:opacity-40"
              >
                {connecting ? 'Connecting…' : 'Connect'}
              </button>
            </div>
            {connectError && <div className="text-sm text-amber-400">{connectError}</div>}
          </div>
        )}
      </SettingRow>

      {status.connected && (
        <SettingRow
          icon={MessageCircle}
          title="Chats"
          subtitle="Choose how Omi handles new messages in each chat. Off by default — nothing is drafted or sent until you opt a chat in."
          keywords="chats chat mode draft auto send review"
        >
          {chats.length === 0 ? (
            <div className="text-sm text-text-tertiary">No chats found yet.</div>
          ) : (
            <div className="divide-y divide-white/[0.06]">
              {chats.map((chat) => (
                <div key={chat.chatID} className="flex items-center justify-between gap-3 py-2.5">
                  <div className="min-w-0">
                    <div className="truncate text-sm text-text-primary">{chat.displayName}</div>
                    <div className="text-xs text-text-tertiary">{chat.network}</div>
                  </div>
                  <select
                    value={chat.mode}
                    onChange={(e) =>
                      setMode(chat.chatID, chat.displayName, e.target.value as AiCloneChatMode)
                    }
                    className="input-field w-44 shrink-0"
                  >
                    {MODES.map((mode) => (
                      <option key={mode} value={mode}>
                        {MODE_LABEL[mode]}
                      </option>
                    ))}
                  </select>
                </div>
              ))}
            </div>
          )}
        </SettingRow>
      )}

      {drafts.length > 0 && (
        <SettingRow
          icon={MessageCircle}
          title="Drafted replies"
          subtitle="Waiting for your review before anything gets sent."
          keywords="drafts review queue approve dismiss"
        >
          <div className="space-y-3">
            {drafts.map((draft) => (
              <div key={draft.id} className="rounded-lg bg-white/[0.04] p-3">
                <div className="mb-1 text-xs text-text-tertiary">{draft.chatDisplayName}</div>
                <div className="mb-2 text-sm text-text-tertiary">
                  Them: {draft.incomingMessageText}
                </div>
                <textarea
                  value={editing[draft.id] ?? draft.draftText}
                  onChange={(e) => setEditing((ed) => ({ ...ed, [draft.id]: e.target.value }))}
                  rows={2}
                  className="input-field mb-2 w-full resize-none"
                />
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => approve(draft.id, editing[draft.id])}
                    className="btn-ghost"
                  >
                    Send
                  </button>
                  <button onClick={() => dismiss(draft.id)} className="btn-ghost">
                    Dismiss
                  </button>
                </div>
              </div>
            ))}
          </div>
        </SettingRow>
      )}
    </>
  )
}
