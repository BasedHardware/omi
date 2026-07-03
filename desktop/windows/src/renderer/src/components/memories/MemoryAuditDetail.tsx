// Audit detail for a single memory: the full text with its provenance line,
// the provenance chain (capture, linked conversation, extraction,
// corroboration — only the steps whose backing fields exist), related memories
// from the same conversation, and the forget actions (this memory / all from
// this conversation / everything from this source).
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Brain,
  Check,
  ChevronRight,
  Loader2,
  MessageSquareText,
  Trash2
} from 'lucide-react'
import { omiApi } from '../../lib/apiClient'
import { toast } from '../../lib/toast'
import type { Memory } from '../../hooks/useMemories'
import {
  SOURCE_LABELS,
  memorySource,
  provenanceChain,
  relatedMemories,
  type ChainStep,
  type MemorySourceKind
} from '../../lib/memoryProvenance'
import { PageHeader } from '../layout/PageHeader'
import { ProvenanceLine, SourceTag } from './provenanceUi'
import { SOURCE_ICONS } from './sourceIcons'

function stepIcon(step: ChainStep, source: MemorySourceKind): React.JSX.Element {
  const cls = 'h-4 w-4'
  if (step.kind === 'capture') {
    const Icon = SOURCE_ICONS[source]
    return <Icon className={cls} />
  }
  if (step.kind === 'conversation') return <MessageSquareText className={cls} />
  if (step.kind === 'extraction') return <Brain className={cls} />
  return <Check className={cls} />
}

export function MemoryAuditDetail(props: {
  memory: Memory
  all: Memory[]
  onBack: () => void
  onOpenMemory: (memory: Memory) => void
  onForgotten: (id: string) => void
  onForgetConversation: (ids: string[]) => void
  onForgetSource: (kind: MemorySourceKind) => void
}): React.JSX.Element {
  const { memory, all, onBack, onOpenMemory, onForgotten, onForgetConversation, onForgetSource } =
    props
  const navigate = useNavigate()
  const source = memorySource(memory)
  const chain = provenanceChain(memory)
  const related = relatedMemories(all, memory)
  // The parent keys this component by memory id, so all local state (confirm
  // step, resolved conversation title) resets naturally when another memory
  // opens — no state juggling inside the effect.
  const [confirming, setConfirming] = useState(false)
  const [deleting, setDeleting] = useState(false)
  // Resolved lazily so the chain can show the conversation's real title; the
  // step renders without it (id-linked) until the fetch lands.
  const [conversationTitle, setConversationTitle] = useState<string | null>(null)

  useEffect(() => {
    const id = memory.conversation_id
    if (!id) return
    let cancelled = false
    ;(async () => {
      try {
        const r = await omiApi.get(`/v1/conversations/${id}`)
        const c = r.data as { title?: string | null; structured?: { title?: string | null } | null }
        const title = c.structured?.title || c.title
        if (!cancelled && title) setConversationTitle(title)
      } catch {
        /* keep the generic step title */
      }
    })()
    return () => {
      cancelled = true
    }
  }, [memory.id, memory.conversation_id])

  const forgetThis = async (): Promise<void> => {
    if (deleting) return
    setDeleting(true)
    try {
      await omiApi.delete(`/v3/memories/${memory.id}`)
      toast('Memory forgotten', { tone: 'info' })
      onForgotten(memory.id)
    } catch (e) {
      toast('Could not forget memory', { tone: 'error', body: (e as Error).message })
      setDeleting(false)
    }
  }

  return (
    <div className="flex h-full flex-col">
      <PageHeader
        title={memory.headline || memory.content.slice(0, 80)}
        subtitle={`${memory.category ?? 'memory'} · first learned ${new Date(
          memory.created_at
        ).toLocaleDateString()}`}
        onBack={onBack}
        actions={
          confirming ? (
            <div className="flex items-center gap-2">
              <button onClick={() => setConfirming(false)} className="btn-ghost px-3 py-2" disabled={deleting}>
                Cancel
              </button>
              <button onClick={forgetThis} className="btn-danger px-4 py-2" disabled={deleting}>
                {deleting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
                Forget permanently
              </button>
            </div>
          ) : (
            <button onClick={() => setConfirming(true)} className="btn-danger px-4 py-2">
              <Trash2 className="h-4 w-4" />
              Forget this memory
            </button>
          )
        }
      />

      <div className="flex-1 overflow-y-auto px-6 py-6 lg:px-10 lg:py-8">
        <div className="mx-auto max-w-3xl space-y-4">
          {confirming && (
            <div className="glass-subtle animate-fade-in px-4 py-3 text-sm text-white/70">
              This memory will be permanently removed from your account and from everything Omi
              says from now on. The recordings and conversations it came from are not touched.
              This cannot be undone.
            </div>
          )}

          <div className="surface-card p-6">
            <p className="text-sm leading-relaxed text-white/85">{memory.content}</p>
            <ProvenanceLine memory={memory} />
            {memory.user_review == null && !memory.manually_added && (
              <div className="mt-2 text-xs text-white/40">Not yet reviewed by you.</div>
            )}
          </div>

          <div className="surface-card p-6">
            <h2 className="section-label mb-4">Where this came from</h2>
            <ul className="space-y-4">
              {chain.map((step, i) => (
                <li key={i} className="flex items-start gap-3">
                  <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-xl border border-white/10 bg-black/20 text-white/65">
                    {stepIcon(step, source)}
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2 text-sm font-medium text-white/90">
                      {step.kind === 'conversation' && step.conversationId
                        ? `Linked conversation${conversationTitle ? `: ${conversationTitle}` : ''}`
                        : step.title}
                      {step.kind === 'conversation' && step.conversationId && (
                        <button
                          onClick={() => navigate(`/conversations/${step.conversationId}`)}
                          className="badge transition-colors hover:border-white/25 hover:text-white"
                          title="Open the source conversation"
                        >
                          Open
                          <ChevronRight className="h-3 w-3" />
                        </button>
                      )}
                    </div>
                    {step.sub && <p className="mt-0.5 text-xs text-white/45">{step.sub}</p>}
                  </div>
                  {step.at && (
                    <time className="shrink-0 text-xs text-white/35">
                      {new Date(step.at).toLocaleString()}
                    </time>
                  )}
                </li>
              ))}
            </ul>
          </div>

          {related.length > 0 && (
            <div className="surface-card p-6">
              <h2 className="section-label mb-3">From the same conversation ({related.length})</h2>
              <ul>
                {related.map((r) => (
                  <li key={r.id}>
                    <button
                      onClick={() => onOpenMemory(r)}
                      className="flex w-full items-center gap-3 border-b border-white/5 py-2.5 text-left last:border-b-0"
                    >
                      <span className="min-w-0 flex-1 truncate text-sm text-white/85">
                        {r.headline || r.content}
                      </span>
                      <span className="flex shrink-0 items-center gap-2 text-xs text-text-quaternary">
                        <SourceTag kind={memorySource(r)} />
                        <time>{new Date(r.created_at).toLocaleDateString()}</time>
                        <ChevronRight className="h-3.5 w-3.5 text-white/30" />
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}

          <div className="surface-card p-6">
            <p className="text-xs leading-relaxed text-white/45">
              Forgetting removes a memory from your account and from Omi&apos;s answers. It cannot
              be undone.
            </p>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              {related.length > 0 && (
                <button
                  onClick={() =>
                    onForgetConversation([memory.id, ...related.map((r) => r.id)])
                  }
                  className="btn-ghost px-3 py-2 text-sm"
                >
                  Forget all {related.length + 1} from this conversation
                </button>
              )}
              <button onClick={() => onForgetSource(source)} className="btn-ghost px-3 py-2 text-sm">
                Forget everything from {SOURCE_LABELS[source].toLowerCase()}…
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
