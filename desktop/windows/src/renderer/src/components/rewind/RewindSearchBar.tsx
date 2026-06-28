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
        className="flex-1 rounded bg-white/10 px-3 py-2 text-sm text-white outline-none"
      />
      <button
        type="submit"
        className="rounded bg-[color:var(--accent)] px-3 py-2 text-sm text-white"
      >
        Search
      </button>
    </form>
  )
}
