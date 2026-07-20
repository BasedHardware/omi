import type { RewindSearchGroup } from '../../../../shared/types'

export function SearchResultsFilmstrip({
  groups,
  onJump,
  searched,
  error
}: {
  groups: RewindSearchGroup[]
  onJump: (ts: number) => void
  searched: boolean
  error: string | null
}): React.JSX.Element {
  if (error) return <div className="py-4 text-sm text-red-300">Search failed: {error}</div>
  if (!searched) {
    return <div className="py-4 text-sm text-white/40">Search your captured screen history.</div>
  }
  if (groups.length === 0) return <div className="py-4 text-sm text-white/40">No matches.</div>
  return (
    <div className="flex flex-col gap-2">
      {groups.map((g) => (
        <button
          key={g.id}
          onClick={() => onJump(g.representative.ts)}
          className="rounded bg-white/5 p-3 text-left hover:bg-white/10"
        >
          <div className="text-xs text-white/50">
            {new Date(g.startTs).toLocaleString()} · {g.app}
            {g.windowTitle ? ` — ${g.windowTitle}` : ''}
          </div>
          <div className="text-sm text-white/90">{g.matchSnippet}</div>
        </button>
      ))}
    </div>
  )
}
