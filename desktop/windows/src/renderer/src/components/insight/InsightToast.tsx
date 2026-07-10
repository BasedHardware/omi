// src/renderer/src/components/insight/InsightToast.tsx
// Rendered inside the shared acrylic toast window (#/insight-toast). Shows
// whichever payload arrived last: a proactive insight ('insight:payload') or a
// meeting-detection notice ('meeting:toast' — Phase 5). Main owns visibility +
// auto-dismiss; hover pause reuses the same IPC for both kinds.
import { useEffect, useState } from 'react'
import type { InsightPayload, MeetingToastPayload } from '../../../../shared/types'
import './insight-toast.css'

type ToastContent =
  | { type: 'insight'; p: InsightPayload }
  | { type: 'meeting'; p: MeetingToastPayload }

function MeetingCard({ p }: { p: MeetingToastPayload }): React.JSX.Element {
  const capturing = p.kind === 'capturing'
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
        {capturing ? `Omi is capturing — ${p.appName}` : `${p.appName} looks like a meeting`}
      </div>
      <div className="insight-advice">
        {capturing
          ? 'Audio is being transcribed into a conversation.'
          : 'Capture and transcribe this meeting?'}
      </div>
      {p.firstRun ? (
        <div className="insight-foot">First run — change this in Settings → General.</div>
      ) : null}
      <div className="meeting-actions">
        {capturing ? (
          <button
            className="meeting-btn"
            onClick={() => window.omi.meetingAction(p.meetingId, 'stop')}
          >
            Stop
          </button>
        ) : (
          <>
            <button
              className="meeting-btn meeting-btn-primary"
              onClick={() => window.omi.meetingAction(p.meetingId, 'start')}
            >
              Start capturing
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

export function InsightToast(): React.JSX.Element {
  const [content, setContent] = useState<ToastContent | null>(null)

  useEffect(() => {
    document.body.classList.add('insight-toast-body')
    const offInsight = window.omi.onInsightShow((p) => setContent({ type: 'insight', p }))
    const offMeeting = window.omi.onMeetingToast((p) => setContent({ type: 'meeting', p }))
    // Pull the pending meeting payload: a push sent while this window was
    // loading (meeting detected right at startup) lands before this effect
    // subscribes and would otherwise be lost.
    void window.omi.meetingGetToast?.().then((p) => {
      if (p) setContent((cur) => cur ?? { type: 'meeting', p })
    })
    return () => {
      document.body.classList.remove('insight-toast-body')
      offInsight()
      offMeeting()
    }
  }, [])

  if (!content) return <div className="insight-toast-body" />
  if (content.type === 'meeting') return <MeetingCard p={content.p} />

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
