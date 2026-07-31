import { useState } from 'react'

export function RewindSearchBar({ onSearch }: { onSearch: (q: string) => void }): React.JSX.Element {
  const [q, setQ] = useState('')
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
        autoFocus
        className="flex-1 rounded-control border border-line bg-white/[0.07] px-3.5 py-2 text-sm text-white outline-none transition-colors placeholder:text-white/35 focus:border-line-strong"
      />
      <button
        type="submit"
        className="rounded-control bg-[color:var(--accent)] px-4 py-2 text-sm font-medium text-[color:var(--accent-contrast)] transition-opacity hover:opacity-90"
      >
        Search
      </button>
    </form>
  )
}
