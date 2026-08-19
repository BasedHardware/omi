// src/renderer/src/components/insight/InsightToast.tsx
// Rendered inside the shared acrylic toast window (#/insight-toast). Shows
// whichever payload arrived last: a proactive insight, a meeting-detection notice,
// a what's-new card, or a Beeper suggested-reply draft. Main owns visibility +
// auto-dismiss; hover pause reuses the same IPC for all kinds.
import { useEffect, useState } from 'react'
import type {
  BeeperDraft,
  InsightPayload,
  MeetingToastPayload,
  WhatsNewPayload
} from '../../../../shared/types'
import './insight-toast.css'

type ToastContent =
  | { type: 'insight'; p: InsightPayload }
  | { type: 'meeting'; p: MeetingToastPayload }
  | { type: 'whatsnew'; p: WhatsNewPayload }
  | { type: 'beeperDraft'; p: BeeperDraft }

// Post-update changelog card (Phase 8). Shares the acrylic card shell; a compact
// list of the version's changes with the full notes one click away.
function WhatsNewCard({ p }: { p: WhatsNewPayload }): React.JSX.Element {
  return (
    <div
      className="insight-card"
      onMouseEnter={() => window.omi.insightHoverStart()}
      onMouseLeave={() => window.omi.insightHoverEnd()}
    >
      <div className="insight-head">
        <span className="insight-cat">What&apos;s new</span>
        <button className="insight-x" onClick={() => window.omi.insightDismiss()} aria-label="Dismiss">
          ✕
        </button>
      </div>
      <div className="insight-headline">New in Omi {p.version}</div>
      <ul className="whatsnew-list">
        {p.changes.slice(0, 3).map((c, i) => (
          <li key={i}>{c}</li>
        ))}
      </ul>
      <div className="whatsnew-actions">
        <button
          className="meeting-btn meeting-btn-primary"
          onClick={() => window.omi.whatsNewOpenNotes()}
        >
          View release notes
        </button>
      </div>
    </div>
  )
}

function MeetingCard({ p }: { p: MeetingToastPayload }): React.JSX.Element {
  const capturing = p.kind === 'capturing'
  const starting = p.kind === 'starting'
  const failed = p.kind === 'error'
  const errorKind = p.errorKind ?? 'startup'
  return (
    <div
      className="insight-card"
      onMouseEnter={() => window.omi.insightHoverStart()}
      onMouseLeave={() => window.omi.insightHoverEnd()}
    >
      <div className="insight-head">
        <span className="insight-cat">Meeting detected</span>
        <button
          className="insight-x"
          onClick={() => window.omi.meetingAction(p.meetingId, 'dismiss')}
          aria-label="Dismiss"
        >
          ✕
        </button>
      </div>
      <div className="insight-headline">
        {capturing
          ? `Omi is capturing — ${p.appName}`
          : starting
            ? `Starting capture — ${p.appName}`
            : failed
              ? errorKind === 'runtime'
                ? `Capture stopped — ${p.appName}`
                : errorKind === 'save'
                  ? `Capture couldn't be saved — ${p.appName}`
                  : `Capture didn't start — ${p.appName}`
              : `${p.appName} looks like a meeting`}
      </div>
      <div className="insight-advice">
        {capturing
          ? 'Audio is being transcribed into a conversation.'
          : starting
            ? 'Connecting audio and transcription…'
            : failed
              ? errorKind === 'save'
                ? 'The recording ended, but Omi could not save the local meeting transcript.'
                : 'Check your sign-in, internet connection, and Windows microphone access, then retry.'
              : 'Capture and transcribe this meeting?'}
      </div>
      {p.firstRun ? (
        <div className="insight-foot">First run — change this in Settings → General.</div>
      ) : null}
      <div className="meeting-actions">
        {capturing || starting ? (
          <button
            className="meeting-btn"
            onClick={() => window.omi.meetingAction(p.meetingId, 'stop')}
          >
            {starting ? 'Cancel' : 'Stop'}
          </button>
        ) : failed && errorKind === 'save' ? (
          <button
            className="meeting-btn"
            onClick={() => window.omi.meetingAction(p.meetingId, 'dismiss')}
          >
            Dismiss
          </button>
        ) : (
          <>
            <button
              className="meeting-btn meeting-btn-primary"
              onClick={() => window.omi.meetingAction(p.meetingId, 'start')}
            >
              {failed ? 'Retry' : 'Start capturing'}
            </button>
            <button
              className="meeting-btn"
              onClick={() => window.omi.meetingAction(p.meetingId, 'dismiss')}
            >
              Not now
            </button>
          </>
        )}
      </div>
    </div>
  )
}

function BeeperDraftCard({ p }: { p: BeeperDraft }): React.JSX.Element {
  const send = async (): Promise<void> => {
    try {
      await window.omi.beeperSendDraft(p.id)
      window.omi.insightDismiss()
    } catch {
      /* keep the card so they can retry or skip */
    }
  }
  const skip = async (): Promise<void> => {
    try {
      await window.omi.beeperDismissDraft(p.id)
    } finally {
      window.omi.insightDismiss()
    }
  }
  const network = (p.network || 'chat').trim()
  return (
    <div
      className="insight-card"
      onMouseEnter={() => window.omi.insightHoverStart()}
      onMouseLeave={() => window.omi.insightHoverEnd()}
    >
      <div className="insight-head">
        <span className="insight-cat">Suggested reply</span>
        <button className="insight-x" onClick={() => void skip()} aria-label="Dismiss">
          ✕
        </button>
      </div>
      <p className="beeper-net">
        {network} · {p.chatTitle}
      </p>
      <div className="beeper-thread">
        <div className="beeper-row beeper-row-them">
          <p className="beeper-bubble beeper-bubble-them">{p.inboundText}</p>
        </div>
        <div className="beeper-row beeper-row-you">
          <p className="beeper-bubble beeper-bubble-you">{p.replyText}</p>
        </div>
      </div>
      <p className="beeper-caption">Drafted by Omi from your memories. You send it.</p>
      <div className="meeting-actions">
        <button className="meeting-btn meeting-btn-primary" onClick={() => void send()}>
          Send
        </button>
        <button className="meeting-btn" onClick={() => void skip()}>
          Skip
        </button>
      </div>
    </div>
  )
}

export function InsightToast(): React.JSX.Element {
  const [content, setContent] = useState<ToastContent | null>(null)

  useEffect(() => {
    document.body.classList.add('insight-toast-body')
    const offInsight = window.omi.onInsightShow((p) => setContent({ type: 'insight', p }))
    const offMeeting = window.omi.onMeetingToast((p) => setContent({ type: 'meeting', p }))
    const offWhatsNew = window.omi.onWhatsNewToast((p) => setContent({ type: 'whatsnew', p }))
    const offDraft = window.omi.onBeeperDraftToast((p) => setContent({ type: 'beeperDraft', p }))
    // Pull any pending payload: a push sent while this window was loading (meeting
    // detected — or the what's-new / draft toast firing — right at startup) lands
    // before this effect subscribes and would otherwise be lost.
    void window.omi.meetingGetToast?.().then((p) => {
      if (p) setContent((cur) => cur ?? { type: 'meeting', p })
    })
    void window.omi.whatsNewGetPending?.().then((p) => {
      if (p) setContent((cur) => cur ?? { type: 'whatsnew', p })
    })
    void window.omi.beeperGetDraftToast?.().then((p) => {
      if (p) setContent((cur) => cur ?? { type: 'beeperDraft', p })
    })
    return () => {
      document.body.classList.remove('insight-toast-body')
      offInsight()
      offMeeting()
      offWhatsNew()
      offDraft()
    }
  }, [])

  if (!content) return <div className="insight-toast-body" />
  if (content.type === 'meeting') return <MeetingCard p={content.p} />
  if (content.type === 'whatsnew') return <WhatsNewCard p={content.p} />
  if (content.type === 'beeperDraft') return <BeeperDraftCard p={content.p} />

  const insight = content.p
  return (
    <div
      className="insight-card"
      onMouseEnter={() => window.omi.insightHoverStart()}
      onMouseLeave={() => window.omi.insightHoverEnd()}
    >
      <div className="insight-head">
        <span className="insight-cat">{insight.category}</span>
        <button className="insight-x" onClick={() => window.omi.insightDismiss()} aria-label="Dismiss">
          ✕
        </button>
      </div>
      <div className="insight-headline">{insight.headline}</div>
      <div className="insight-advice">{insight.advice}</div>
      <div className="insight-foot">{insight.sourceApp}</div>
    </div>
  )
}
