import { useEffect, useState } from 'react'
import { StepScaffold } from './StepScaffold'
import { ChatReplyDemo } from '../chatReply/ChatReplyDemo'
import { BeeperConnectForm } from '../chatReply/BeeperConnectForm'
import type { BeeperStatus } from '../../../../shared/types'

type ChatReplyStepProps = {
  stepIndex: number
  totalSteps: number
  onContinue: () => void
  onSkip: () => void
}

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

export function ChatReplyStep({
  stepIndex,
  totalSteps,
  onContinue,
  onSkip
}: ChatReplyStepProps): React.JSX.Element {
  const [status, setStatus] = useState<BeeperStatus>(EMPTY)
  const [token, setToken] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [revealed, setRevealed] = useState(false)

  useEffect(() => {
    const id = requestAnimationFrame(() => setRevealed(true))
    return () => cancelAnimationFrame(id)
  }, [])

  useEffect(() => {
    let cancelled = false
    window.omi
      .beeperStatus()
      .then((next) => {
        if (!cancelled) setStatus(next)
      })
      .catch(() => {
        if (!cancelled) setStatus(EMPTY)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const connect = async (): Promise<void> => {
    if (busy || !token.trim()) return
    setBusy(true)
    setError(null)
    try {
      setStatus(await window.omi.beeperConnect(token.trim()))
      setToken('')
    } catch (e) {
      setError((e as Error).message || 'Could not connect')
    } finally {
      setBusy(false)
    }
  }

  const handleContinue = async (): Promise<void> => {
    if (status.connected) {
      try {
        await window.omi.beeperSetSettings({
          enabled: true,
          sendMode: 'draft',
          networks: ['whatsapp', 'telegram']
        })
      } catch {
        /* still advance — Settings can finish the setup */
      }
    }
    onContinue()
  }

  return (
    <StepScaffold
      stepIndex={stepIndex}
      totalSteps={totalSteps}
      align="left"
      widthClassName="w-full max-w-[440px]"
      eyebrow="YOUR CHATS"
      title="Omi can reply as you."
      subtitle="Drafts in WhatsApp and Telegram from your memories — you tap Send."
      onContinue={() => void handleContinue()}
      onSkip={onSkip}
      continueLabel={status.connected ? 'Enable drafts' : 'Continue'}
    >
      <div className="flex w-full flex-col gap-4">
        <ChatReplyDemo revealed={revealed} />
        <div className="w-full rounded-2xl border border-white/5 bg-white/[0.03] p-4">
          <p className="mb-2 text-[13px] font-medium text-white/85">Connect WhatsApp & Telegram</p>
          <BeeperConnectForm
            status={status}
            token={token}
            busy={busy}
            error={error}
            onToken={setToken}
            onConnect={() => void connect()}
            onInstall={() => void window.omi.beeperOpenDownload()}
          />
        </div>
      </div>
    </StepScaffold>
  )
}
