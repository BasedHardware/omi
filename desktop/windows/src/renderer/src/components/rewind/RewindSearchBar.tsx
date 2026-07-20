import { useState } from 'react'

export function RewindSearchBar({
  onSearch,
  searching
}: {
  onSearch: (q: string) => void
  searching: boolean
}): React.JSX.Element {
  const [q, setQ] = useState('')
  const query = q.trim()
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault()
        onSearch(q)
      }}
      className="flex gap-2"
    >
      <input
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder="Search what was on screen…"
        className="flex-1 rounded bg-white/10 px-3 py-2 text-sm text-white outline-none"
      />
      <button
        type="submit"
        disabled={!query || searching}
        className="rounded bg-[color:var(--accent)] px-3 py-2 text-sm text-white disabled:cursor-not-allowed disabled:opacity-40"
      >
        {searching ? 'Searching…' : 'Search'}
      </button>
    </form>
  )
}
