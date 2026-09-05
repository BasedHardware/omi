// Search: one box over conversations, memories, tasks and captured screen text.
//
// Before this page the only search inputs in the app were Rewind's (frames only)
// and Settings' (settings only), so a conversation, a memory or a task could be
// found by scrolling and no other way.
//
// Results are grouped by corpus rather than interleaved. The scores behind them
// come from separate indexes and a remote endpoint, so a single ranked list
// would be ordering by numbers that are not comparable; grouping keeps the
// ordering honest and makes "where would this have been?" answerable.

import { useEffect, useMemo, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { MessagesSquare, Brain, ListChecks, Monitor, SearchIcon, X } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { HOME_PATH } from '../routes/manifest'
import { PageHeader } from '../components/layout/PageHeader'
import { EmptyState } from '../components/ui/EmptyState'
import { useSearch } from '../hooks/useSearch'
import {
  CORPUS_LABELS,
  CORPUS_ORDER,
  type SearchCorpus,
  type SearchSlice
} from '../lib/search/runSearch'
import { COPY, corpusCountLabel, failedCorpora, searchPhase } from '../lib/search/searchCopy'
import type { CorpusHit } from '../../../shared/types'

const CORPUS_ICONS: Record<SearchCorpus, LucideIcon> = {
  conversations: MessagesSquare,
  memories: Brain,
  tasks: ListChecks,
  screen: Monitor
}

/** Where a result takes you. Only conversations have a detail route to land on;
 *  the rest open their own page, which is where the item lives. Deep-linking to
 *  one memory, task or frame needs a target that does not exist yet. */
const CORPUS_DESTINATIONS: Record<SearchCorpus, (hit: CorpusHit) => string> = {
  conversations: (hit) => `/conversations/${hit.id}`,
  memories: () => '/memories',
  tasks: () => '/tasks',
  screen: () => '/rewind'
}

function formatWhen(ts: number): string {
  if (!ts) return ''
  const d = new Date(ts)
  const sameYear = d.getFullYear() === new Date().getFullYear()
  return d.toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    ...(sameYear ? {} : { year: 'numeric' })
  })
}

function ResultRow(props: { hit: CorpusHit; onOpen: () => void }): React.JSX.Element {
  const { hit, onOpen } = props
  return (
    <button
      type="button"
      onClick={onOpen}
      className="flex w-full items-start justify-between gap-4 rounded-lg px-3 py-2.5 text-left hover:bg-white/[0.06]"
    >
      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm text-white/90">{hit.title}</span>
        {hit.detail && (
          <span className="mt-0.5 block truncate text-xs text-white/40">{hit.detail}</span>
        )}
      </span>
      <span className="shrink-0 pt-0.5 text-xs tabular-nums text-white/35">
        {formatWhen(hit.timestamp)}
      </span>
    </button>
  )
}

function CorpusSection(props: {
  corpus: SearchCorpus
  slice: SearchSlice
  onOpen: (hit: CorpusHit) => void
}): React.JSX.Element | null {
  const { corpus, slice, onOpen } = props
  // A corpus with nothing to say is left out entirely; a failed one stays so its
  // absence is stated rather than silent.
  if (slice.hits.length === 0 && !slice.failed) return null
  const Icon = CORPUS_ICONS[corpus]
  return (
    <section className="mb-6">
      <header className="mb-1.5 flex items-center gap-2 px-3">
        <Icon className="h-3.5 w-3.5 text-white/40" strokeWidth={1.8} />
        <h2 className="text-xs font-medium uppercase tracking-wide text-white/55">
          {CORPUS_LABELS[corpus]}
        </h2>
        <span className="text-xs text-white/30">{corpusCountLabel(slice)}</span>
      </header>
      {slice.hits.map((hit) => (
        <ResultRow key={`${corpus}:${hit.id}`} hit={hit} onOpen={() => onOpen(hit)} />
      ))}
    </section>
  )
}

export function Search(): React.JSX.Element {
  const navigate = useNavigate()
  const { input, setInput, results, searching, clear } = useSearch()
  const inputRef = useRef<HTMLInputElement>(null)

  // The page exists to be typed into, so it takes focus on arrival.
  useEffect(() => {
    inputRef.current?.focus()
  }, [])

  const phase = useMemo(
    () => searchPhase({ input, searching, results }),
    [input, searching, results]
  )
  const partial = useMemo(
    () => (results && phase.kind === 'results' ? failedCorpora(results) : []),
    [results, phase.kind]
  )

  const open = (corpus: SearchCorpus, hit: CorpusHit): void => {
    navigate(CORPUS_DESTINATIONS[corpus](hit))
  }

  return (
    <div className="flex h-full flex-col">
      <PageHeader title="Search" subtitle="Everything Omi has kept for you" />

      <div className="px-6">
        <div className="glass flex items-center gap-2 rounded-xl px-3 py-2">
          <SearchIcon className="h-4 w-4 shrink-0 text-white/40" strokeWidth={1.8} />
          <input
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key !== 'Escape') return
              // The whole Escape ladder has to live here. useKeyboardNav ignores
              // any key pressed inside an INPUT, so its escape-to-home never
              // fires while this box has focus - without the second branch an
              // empty box would swallow Escape and strand the page.
              e.preventDefault()
              if (input.length > 0) clear()
              else navigate(HOME_PATH)
            }}
            placeholder={COPY.placeholder}
            aria-label="Search"
            spellCheck={false}
            className="w-full bg-transparent text-sm text-white/90 outline-none placeholder:text-white/30"
          />
          {input.length > 0 && (
            <button
              type="button"
              onClick={clear}
              aria-label="Clear search"
              className="shrink-0 rounded p-0.5 text-white/40 hover:text-white/80"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          )}
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-3 pt-5">
        {phase.kind === 'prompt' && (
          <EmptyState icon={SearchIcon} title="Search" description={COPY.prompt} />
        )}
        {phase.kind === 'tooShort' && <p className="px-3 text-sm text-white/40">{COPY.tooShort}</p>}
        {phase.kind === 'searching' && (
          <p className="px-3 text-sm text-white/40">{COPY.searching}</p>
        )}
        {phase.kind === 'unavailable' && (
          <EmptyState icon={SearchIcon} title="Search unavailable" description={COPY.unavailable} />
        )}
        {phase.kind === 'empty' && (
          <EmptyState icon={SearchIcon} title="No matches" description={COPY.empty(phase.query)} />
        )}
        {phase.kind === 'results' && results && (
          <>
            {partial.length > 0 && (
              <p className="mb-4 px-3 text-xs text-amber-300/80">
                {COPY.partial(partial, CORPUS_LABELS)}
              </p>
            )}
            {CORPUS_ORDER.map((corpus) => (
              <CorpusSection
                key={corpus}
                corpus={corpus}
                slice={results[corpus]}
                onOpen={(hit) => open(corpus, hit)}
              />
            ))}
          </>
        )}
      </div>
    </div>
  )
}
