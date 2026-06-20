import { useEffect, useState, useMemo } from 'react'
import { Lightbulb, ChevronDown, ChevronUp, RefreshCw, Search } from 'lucide-react'
import type { InsightRecord, InsightCategory } from '../../../shared/types'
import { PageHeader } from '../components/layout/PageHeader'
import { EmptyState } from '../components/ui/EmptyState'

const CATEGORIES: { id: InsightCategory | 'all'; label: string }[] = [
  { id: 'all', label: 'All' },
  { id: 'productivity', label: 'Productivity' },
  { id: 'communication', label: 'Communication' },
  { id: 'learning', label: 'Learning' },
  { id: 'health', label: 'Health' },
  { id: 'other', label: 'Other' }
]

const CAT_COLOR: Record<InsightCategory, string> = {
  productivity: 'text-blue-400 bg-blue-400/10',
  communication: 'text-purple-400 bg-purple-400/10',
  learning: 'text-green-400 bg-green-400/10',
  health: 'text-rose-400 bg-rose-400/10',
  other: 'text-amber-400 bg-amber-400/10'
}

function fmtTs(ts: number): string {
  const d = new Date(ts)
  const now = new Date()
  const diffMs = now.getTime() - d.getTime()
  const diffDays = Math.floor(diffMs / 86_400_000)
  if (diffDays === 0) return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  if (diffDays === 1) return `Yesterday, ${d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`
  if (diffDays < 7) return d.toLocaleDateString([], { weekday: 'short', hour: '2-digit', minute: '2-digit' })
  return d.toLocaleDateString([], { month: 'short', day: 'numeric' })
}

function InsightCard({ rec }: { rec: InsightRecord }): React.JSX.Element {
  const [expanded, setExpanded] = useState(false)
  const colorClass = CAT_COLOR[rec.category] ?? 'text-white/40 bg-white/5'

  return (
    <div className="surface-card p-5 transition-all">
      <div className="flex items-start gap-3">
        <div className="min-w-0 flex-1">
          <div className="mb-2 flex items-center gap-2">
            <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium capitalize ${colorClass}`}>
              {rec.category}
            </span>
            {rec.confidence < 0.8 && (
              <span className="text-xs text-text-quaternary">{Math.round(rec.confidence * 100)}% confidence</span>
            )}
          </div>
          <div className="font-display text-base font-semibold leading-snug text-text-primary">
            {rec.headline}
          </div>
          <p className="mt-2 text-sm leading-relaxed text-text-secondary">{rec.advice}</p>

          {rec.reasoning && (
            <div className="mt-3">
              <button
                onClick={() => setExpanded((e) => !e)}
                className="flex items-center gap-1 text-xs text-text-quaternary hover:text-text-tertiary"
              >
                {expanded ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
                {expanded ? 'Hide reasoning' : 'Show reasoning'}
              </button>
              {expanded && (
                <p className="mt-2 rounded-lg bg-white/5 px-3 py-2.5 text-xs leading-relaxed text-text-tertiary">
                  {rec.reasoning}
                </p>
              )}
            </div>
          )}

          <div className="mt-3 flex items-center gap-2 text-xs text-text-quaternary">
            {rec.sourceApp && <span className="truncate">{rec.sourceApp}</span>}
            {rec.sourceApp && <span>·</span>}
            <time>{fmtTs(rec.ts)}</time>
          </div>
        </div>
      </div>
    </div>
  )
}

export function Insights(): React.JSX.Element {
  const [records, setRecords] = useState<InsightRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [category, setCategory] = useState<InsightCategory | 'all'>('all')
  const [query, setQuery] = useState('')
  const [showDismissed, setShowDismissed] = useState(false)

  const load = async (): Promise<void> => {
    setLoading(true)
    try {
      const recs = await window.omi.insightRecent(500)
      setRecords(recs)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void load() }, [])

  const filtered = useMemo(() => {
    let list = records.filter((r) => showDismissed || r.dismissed === 0)
    if (category !== 'all') list = list.filter((r) => r.category === category)
    const q = query.trim().toLowerCase()
    if (q) {
      list = list.filter(
        (r) =>
          r.headline.toLowerCase().includes(q) ||
          r.advice.toLowerCase().includes(q) ||
          r.sourceApp?.toLowerCase().includes(q)
      )
    }
    return list
  }, [records, category, query, showDismissed])

  const subtitle = loading ? 'Loading…' : `${filtered.length} insight${filtered.length === 1 ? '' : 's'}`

  return (
    <div className="flex h-full flex-col">
      <PageHeader
        title="Insights"
        subtitle={subtitle}
        actions={
          <div className="flex items-center gap-2">
            <button
              onClick={() => setShowDismissed((v) => !v)}
              className={`btn-ghost px-3 py-2 text-xs ${showDismissed ? 'text-white/90' : 'text-white/50'}`}
              title={showDismissed ? 'Hide dismissed' : 'Show dismissed'}
            >
              {showDismissed ? 'Hide dismissed' : 'Show dismissed'}
            </button>
            <button onClick={() => void load()} className="btn-ghost px-3 py-2" disabled={loading} title="Refresh">
              <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
            </button>
          </div>
        }
      />

      {/* Category tabs + search */}
      <div className="flex flex-col gap-3 border-b border-white/5 px-6 pb-3 pt-3 lg:px-10">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-text-quaternary" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search insights…"
            className="input-field w-full py-2 pl-9 text-sm"
          />
        </div>
        <div className="flex gap-1 overflow-x-auto pb-1">
          {CATEGORIES.map(({ id, label }) => (
            <button
              key={id}
              onClick={() => setCategory(id)}
              className={`shrink-0 rounded-full px-3 py-1 text-sm transition-colors ${
                category === id
                  ? 'bg-white/15 text-text-primary'
                  : 'text-text-tertiary hover:bg-white/8 hover:text-text-secondary'
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-6 py-6 lg:px-10 lg:py-8">
        {!loading && records.length === 0 && (
          <EmptyState
            icon={Lightbulb}
            title="No insights yet"
            description="Insights are generated from your recent screen activity while you work. Enable Rewind capture and check back after a few minutes."
          />
        )}

        {!loading && records.length > 0 && filtered.length === 0 && (
          <div className="glass-subtle mx-auto max-w-4xl px-4 py-3 text-sm text-white/60">
            No insights match your filter.
          </div>
        )}

        <div className="mx-auto grid max-w-4xl grid-cols-1 gap-3 lg:grid-cols-2">
          {filtered.map((rec) => (
            <InsightCard key={rec.id} rec={rec} />
          ))}
        </div>
      </div>
    </div>
  )
}
