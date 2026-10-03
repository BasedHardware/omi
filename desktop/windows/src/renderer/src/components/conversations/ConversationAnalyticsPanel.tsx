import { useEffect, useId, useState } from 'react'
import { ChevronDown, Loader2 } from 'lucide-react'
import { omiApi } from '../../lib/apiClient'
import type { ConversationAnalytics, TranscriptSegment } from '../../lib/omiApi.generated'
import { formatDuration } from '../../lib/conversations/detailFormat'

type AnalyticsResult = ({ status: 'error' } | { status: 'ready'; data: ConversationAnalytics }) & {
  conversationId: string
  transcriptSegments: TranscriptSegment[]
}

/** The server owns speaker grouping, ordering, and metric calculations. */
export function ConversationAnalyticsPanel({
  conversationId,
  transcriptSegments
}: {
  conversationId: string
  transcriptSegments: TranscriptSegment[]
}): React.JSX.Element {
  const panelId = useId()
  const [expanded, setExpanded] = useState(false)
  const [retry, setRetry] = useState(0)
  const [result, setResult] = useState<AnalyticsResult | null>(null)
  const state =
    result?.conversationId === conversationId && result.transcriptSegments === transcriptSegments
      ? result
      : null

  useEffect(() => {
    if (!expanded) return
    const controller = new AbortController()
    void omiApi
      .get<ConversationAnalytics>(`/v1/conversations/${conversationId}/analytics`, {
        signal: controller.signal
      })
      .then(({ data }) => {
        if (!controller.signal.aborted)
          setResult({ status: 'ready', data, conversationId, transcriptSegments })
      })
      .catch(() => {
        if (!controller.signal.aborted)
          setResult({ status: 'error', conversationId, transcriptSegments })
      })
    return () => controller.abort()
    // Speaker naming refreshes the transcript; reload its server-owned grouping too.
  }, [conversationId, expanded, retry, transcriptSegments])

  return (
    <section className="surface-card p-6">
      <h2>
        <button
          type="button"
          aria-expanded={expanded}
          aria-controls={panelId}
          onClick={() => {
            setResult(null)
            setExpanded((value) => !value)
          }}
          className="flex w-full items-center justify-between gap-3 text-left"
        >
          <span className="section-label">Speaker analytics</span>
          <ChevronDown
            aria-hidden
            className={`h-4 w-4 shrink-0 text-text-tertiary transition-transform ${expanded ? 'rotate-180' : ''}`}
          />
        </button>
      </h2>
      {!expanded && (
        <p className="mt-2 text-xs text-text-tertiary">Talk time and words per minute</p>
      )}
      <div id={panelId} hidden={!expanded}>
        {expanded && !state && (
          <p role="status" className="mt-4 flex items-center gap-2 text-sm text-text-tertiary">
            <Loader2 aria-hidden className="h-4 w-4 animate-spin" />
            Loading speaker analytics…
          </p>
        )}
        {expanded && state?.status === 'error' && (
          <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
            <p role="alert" className="text-sm text-text-tertiary">
              Couldn’t load speaker analytics.
            </p>
            <button
              type="button"
              onClick={() => {
                setResult(null)
                setRetry((value) => value + 1)
              }}
              className="btn-ghost px-3 py-1.5 text-xs"
            >
              Try again
            </button>
          </div>
        )}
        {expanded &&
          state?.status === 'ready' &&
          (state.data.speakers?.length ? (
            <>
              <dl className="mt-4 grid grid-cols-3 gap-3 text-xs">
                <div>
                  <dt className="text-text-tertiary">Total talk time</dt>
                  <dd className="mt-1 font-medium text-white">
                    {formatDuration(state.data.total_seconds)}
                  </dd>
                </div>
                <div>
                  <dt className="text-text-tertiary">Words</dt>
                  <dd className="mt-1 font-medium text-white">
                    {state.data.total_words.toLocaleString()}
                  </dd>
                </div>
                <div>
                  <dt className="text-text-tertiary">Speakers</dt>
                  <dd className="mt-1 font-medium text-white">{state.data.speaker_count}</dd>
                </div>
              </dl>
              <div className="mt-4 overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <caption className="sr-only">Talk time and speaking pace by speaker</caption>
                  <thead className="text-text-tertiary">
                    <tr className="border-b border-border">
                      <th scope="col" className="pb-2 pr-3 font-normal">
                        Speaker
                      </th>
                      <th
                        scope="col"
                        className="whitespace-nowrap pb-2 pr-3 text-right font-normal"
                      >
                        Talk time
                      </th>
                      <th scope="col" className="pb-2 pr-3 text-right font-normal">
                        Share
                      </th>
                      <th scope="col" className="whitespace-nowrap pb-2 text-right font-normal">
                        Words/min
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {state.data.speakers.map((speaker, index) => (
                      <tr key={index} className="border-b border-border last:border-0">
                        <th scope="row" className="min-w-24 py-3 pr-3 font-medium text-white">
                          <span className="break-words">{speaker.speaker}</span>
                          <div aria-hidden className="mt-1.5 h-1 rounded-full bg-white/10">
                            <div
                              className="h-full rounded-full bg-white/60"
                              style={{ width: `${speaker.talk_share * 100}%` }}
                            />
                          </div>
                        </th>
                        <td className="whitespace-nowrap py-3 pr-3 text-right tabular-nums text-text-secondary">
                          {formatDuration(speaker.talk_seconds)}
                        </td>
                        <td className="py-3 pr-3 text-right tabular-nums text-text-secondary">
                          {(speaker.talk_share * 100).toLocaleString(undefined, {
                            maximumFractionDigits: 1
                          })}
                          %
                        </td>
                        <td className="py-3 text-right tabular-nums text-text-secondary">
                          {speaker.words_per_minute.toLocaleString(undefined, {
                            maximumFractionDigits: 1
                          })}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="mt-3 text-xs leading-relaxed text-text-tertiary">
                Based on transcript timing. Words per minute measures speaking time, excluding
                pauses between segments.
              </p>
            </>
          ) : (
            <p className="mt-4 text-sm text-text-tertiary">
              No speaker analytics available for this conversation.
            </p>
          ))}
      </div>
    </section>
  )
}
