import type { RewindSearchGroup } from '../../../../shared/types'

export function SearchResultsFilmstrip({
  groups,
  onJump
}: {
  groups: RewindSearchGroup[]
  onJump: (ts: number) => void
}): React.JSX.Element {
  if (groups.length === 0) return <div className="py-4 text-sm text-white/40">No matches.</div>
  return (
    <div className="flex flex-col gap-2">
      {groups.map((g) => (
        <button
          key={g.id}
          onClick={() => onJump(g.representative.ts)}
          className="rounded-control border border-line bg-white/[0.04] p-3 text-left transition-colors hover:border-line-strong hover:bg-white/[0.08]"
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
