import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Loader2, Check } from 'lucide-react'
import { PageHeader } from '../components/layout/PageHeader'
import { liveConversation, requestFinalize, type LiveStatus } from '../lib/liveConversation'
import { startLiveMicSession } from '../lib/liveMicSession'
import { getPreferences } from '../lib/preferences'
import type { TranscriptLine } from '../../../shared/types'

function statusLabel(status: LiveStatus): string {
  if (status === 'connecting') return 'Connecting…'
  if (status === 'live') return 'Listening'
  if (status === 'error') return 'Microphone unavailable'
  return 'Idle'
}

// Live in-progress transcript of the mic capture (the "New" view). It does not
// control segmentation — the backend decides when the conversation ends, at which
// point it appears (titled) in the Conversations list and this view clears.
//
// Session ownership: when continuousRecording is ON, the background
// ContinuousRecordingHost already owns the mic session and this view just reads
// the shared store. When OFF, this view starts/stops its OWN one-off session so
// "New" still captures.
export function LiveConversation(): React.JSX.Element {
  const navigate = useNavigate()
  const [segments, setSegments] = useState<TranscriptLine[]>(liveConversation.getSegments())
  const [status, setStatus] = useState<LiveStatus>(liveConversation.getStatus())
  const [errorMsg, setErrorMsg] = useState<string | null>(liveConversation.getError())
  const [saved, setSaved] = useState<boolean>(liveConversation.isSaved())
  const [topic, setTopic] = useState(liveConversation.getSavedTopic())

  useEffect(() => {
    return liveConversation.subscribe(() => {
      setSegments([...liveConversation.getSegments()])
      setStatus(liveConversation.getStatus())
      setErrorMsg(liveConversation.getError())
      setSaved(liveConversation.isSaved())
      setTopic(liveConversation.getSavedTopic())
    })
  }, [])

  // Own a one-off session only when continuous mode is OFF (otherwise the
  // always-on host owns the shared session and this view just reads the store).
  // The session lifecycle (connect/retry, silence + "Save now" finalize, polling)
  // lives in startLiveMicSession, shared with ContinuousRecordingHost.
  useEffect(() => {
    if (getPreferences().continuousRecording) return
    const session = startLiveMicSession()
    return () => session.stop()
  }, [])

  return (
    <div className="flex h-full flex-col">
      <PageHeader
        title={saved ? topic.title || 'Conversation' : 'Live conversation'}
        titleSlot={
          saved ? (
            <h1 className="truncate font-display text-2xl font-bold tracking-tight text-white">
              {topic.emoji && <span className="mr-1.5">{topic.emoji}</span>}
              {topic.title || <span className="italic text-white/45">loading…</span>}
            </h1>
          ) : undefined
        }
        subtitle={statusLabel(status)}
        onBack={() => navigate('/conversations')}
        actions={
          <div className="flex items-center gap-2">
            <button
              onClick={() => requestFinalize()}
              disabled={segments.length === 0 || saved}
              className="btn-record flex items-center gap-2 disabled:opacity-40"
              title="Finalize this conversation now instead of waiting for the silence boundary"
            >
              <Check className="h-4 w-4" />
              Save now
            </button>
            <span className="badge flex items-center gap-1.5">
              <Loader2 className={`h-3 w-3 ${status === 'live' ? 'animate-spin' : ''}`} />
              {statusLabel(status)}
            </span>
          </div>
        }
      />
      <div className="flex-1 overflow-y-auto px-6 py-6 lg:px-10 lg:py-8">
        <div className="mx-auto max-w-3xl">
          <div className="surface-card p-6">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="section-label">Transcript</h2>
            </div>
            {segments.length > 0 ? (
              <ul className="space-y-4">
                {segments.map((s, i) => (
                  <li key={s.id ?? i} className="flex gap-3 animate-fade-in">
                    <span className="shrink-0 self-start rounded-full border border-white/15 bg-white/5 px-2.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-white/75">
                      {s.speaker || 'speaker'}
                    </span>
                    <p className="min-w-0 flex-1 whitespace-pre-wrap text-sm leading-relaxed text-white/85">
                      {s.text}
                    </p>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-white/45">
                {status === 'error'
                  ? `Couldn't start listening: ${errorMsg || 'unknown error'}. If this is a permission issue, allow the mic in Windows Settings → Privacy → Microphone; otherwise it'll retry automatically.`
                  : 'Listening… start speaking and your words will appear here. The finished conversation will show up in your list automatically.'}
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
