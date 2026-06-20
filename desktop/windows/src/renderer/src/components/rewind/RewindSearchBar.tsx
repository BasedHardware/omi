import { useState } from 'react'

export function RewindSearchBar({
  onSearch,
  onClear,
  searching,
  activeQuery
}: {
  onSearch: (q: string) => void
  onClear: () => void
  searching: boolean
  activeQuery: string
}): React.JSX.Element {
  const [q, setQ] = useState('')
  const hasQuery = q.trim().length > 0
  const hasActiveSearch = activeQuery.length > 0

  const clear = (): void => {
    setQ('')
    onClear()
  }

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault()
        onSearch(q)
      }}
      className="flex min-h-10 gap-2"
    >
      <input
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder="Search what was on screen..."
        className="min-w-0 flex-1 rounded bg-white/10 px-3 py-2 text-sm text-white outline-none placeholder:text-white/35"
      />
      <button
        type="submit"
        disabled={!hasQuery || searching}
        className="w-24 rounded bg-[color:var(--accent)] px-3 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-45"
      >
        {searching ? 'Searching' : 'Search'}
      </button>
      {hasActiveSearch && (
        <button
          type="button"
          onClick={clear}
          className="w-20 rounded bg-white/10 px-3 py-2 text-sm text-white hover:bg-white/15"
        >
          Clear
        </button>
      )}
    </form>
  )
}
