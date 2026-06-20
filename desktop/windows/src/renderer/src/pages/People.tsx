import { useCallback, useEffect, useRef, useState } from 'react'
import { Users, Plus, Trash2, X, Loader2, Search } from 'lucide-react'
import { omiApi } from '../lib/apiClient'
import { PageHeader } from '../components/layout/PageHeader'
import { EmptyState } from '../components/ui/EmptyState'
import { toast } from '../lib/toast'

type Person = { id: string; name: string; created_at?: string }

function getInitials(name: string): string {
  return name
    .split(' ')
    .map((n) => n[0])
    .join('')
    .slice(0, 2)
    .toUpperCase()
}

function avatarColor(name: string): string {
  const palette = [
    'bg-purple-500/30 text-purple-200',
    'bg-blue-500/30 text-blue-200',
    'bg-emerald-500/30 text-emerald-200',
    'bg-orange-500/30 text-orange-200',
    'bg-pink-500/30 text-pink-200',
    'bg-cyan-500/30 text-cyan-200',
  ]
  let h = 0
  for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) | 0
  return palette[Math.abs(h) % palette.length]
}

export function People(): React.JSX.Element {
  const [people, setPeople] = useState<Person[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [creating, setCreating] = useState(false)
  const [newName, setNewName] = useState('')
  const [saving, setSaving] = useState(false)
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const [convCounts, setConvCounts] = useState<Record<string, number>>({})
  const newNameRef = useRef<HTMLInputElement>(null)

  const load = useCallback(async (): Promise<void> => {
    setError(null)
    try {
      const r = await omiApi.get<Person[]>('/v1/users/people')
      const list = Array.isArray(r.data) ? r.data.filter((p) => p.id && p.name) : []
      setPeople(list)
      // Best-effort conversation counts per person
      const counts: Record<string, number> = {}
      await Promise.allSettled(
        list.map(async (p) => {
          try {
            const cr = await omiApi.get('/v1/conversations', {
              params: { person_id: p.id, limit: 1, offset: 0 }
            })
            const d = cr.data as { total?: number } | unknown[]
            counts[p.id] =
              typeof (d as { total?: number }).total === 'number'
                ? (d as { total: number }).total
                : Array.isArray(d)
                  ? d.length
                  : 0
          } catch {
            /* non-fatal */
          }
        })
      )
      setConvCounts(counts)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  useEffect(() => {
    if (creating) setTimeout(() => newNameRef.current?.focus(), 80)
  }, [creating])

  const createPerson = async (): Promise<void> => {
    const name = newName.trim()
    if (!name || saving) return
    if (people.some((p) => p.name.toLowerCase() === name.toLowerCase())) {
      toast('A person with that name already exists', { tone: 'error' })
      return
    }
    setSaving(true)
    try {
      const r = await omiApi.post<Person>('/v1/users/people', { name })
      setPeople((prev) => [...prev, r.data])
      setNewName('')
      setCreating(false)
      toast(`Added ${name}`, { tone: 'info' })
    } catch (e) {
      toast('Could not create person', { tone: 'error', body: (e as Error).message })
    } finally {
      setSaving(false)
    }
  }

  const deletePerson = async (id: string, name: string): Promise<void> => {
    if (!confirm(`Remove ${name}? This will not delete their conversations.`)) return
    setDeletingId(id)
    try {
      await omiApi.delete(`/v1/users/people/${id}`)
      setPeople((prev) => prev.filter((p) => p.id !== id))
      toast('Person removed', { tone: 'info' })
    } catch (e) {
      toast('Could not delete', { tone: 'error', body: (e as Error).message })
    } finally {
      setDeletingId(null)
    }
  }

  const filtered = people.filter((p) =>
    p.name.toLowerCase().includes(search.toLowerCase())
  )

  return (
    <div className="flex h-full flex-col">
      <PageHeader
        title="People"
        subtitle={loading ? 'Loading…' : `${people.length} ${people.length === 1 ? 'person' : 'people'}`}
        actions={
          <button onClick={() => setCreating((v) => !v)} className="btn-primary px-3 py-2">
            <Plus className="h-4 w-4" />
            Add Person
          </button>
        }
      />
      <div className="flex-1 overflow-y-auto px-6 py-6 lg:px-10 lg:py-8">
        <div className="mx-auto max-w-2xl space-y-4">
          {/* Search */}
          {people.length > 5 && (
            <div className="flex items-center gap-2 rounded-xl border border-white/[0.08] bg-white/[0.03] px-3 py-2">
              <Search className="h-4 w-4 shrink-0 text-white/35" />
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search people…"
                className="flex-1 border-0 bg-transparent text-sm text-white placeholder:text-white/30 focus:outline-none"
              />
              {search && (
                <button onClick={() => setSearch('')} className="text-white/30 hover:text-white/60">
                  <X className="h-3.5 w-3.5" />
                </button>
              )}
            </div>
          )}

          {/* Add person inline form */}
          {creating && (
            <div className="surface-card animate-fade-in p-4 space-y-3">
              <p className="text-xs font-semibold uppercase tracking-wider text-white/40">New Person</p>
              <input
                ref={newNameRef}
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') void createPerson()
                  else if (e.key === 'Escape') {
                    setCreating(false)
                    setNewName('')
                  }
                }}
                placeholder="Full name"
                className="input-field"
              />
              <div className="flex justify-end gap-2">
                <button
                  onClick={() => { setCreating(false); setNewName('') }}
                  className="btn-ghost px-3 py-2 text-sm"
                >
                  Cancel
                </button>
                <button
                  onClick={() => void createPerson()}
                  disabled={!newName.trim() || saving}
                  className="btn-primary px-4 py-2 text-sm disabled:opacity-40"
                >
                  {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Add'}
                </button>
              </div>
            </div>
          )}

          {/* Loading skeletons */}
          {loading && (
            <ul className="space-y-2">
              {Array.from({ length: 5 }).map((_, i) => (
                <li key={i} className="surface-card flex items-center gap-4 p-4">
                  <div className="skeleton h-10 w-10 shrink-0 rounded-full" />
                  <div className="flex-1 space-y-2">
                    <div className="skeleton h-4 w-36" />
                    <div className="skeleton h-3 w-20" />
                  </div>
                </li>
              ))}
            </ul>
          )}

          {error && (
            <div className="glass-subtle px-4 py-3 text-sm text-white/60">{error}</div>
          )}

          {!loading && people.length === 0 && !creating && (
            <EmptyState
              icon={Users}
              title="No people yet"
              description="When you assign names to speakers in conversation transcripts, they appear here. You can also add people manually."
            />
          )}

          {!loading && filtered.length > 0 && (
            <ul className="space-y-2">
              {filtered.map((person) => (
                <li
                  key={person.id}
                  className="surface-card group flex items-center gap-4 p-4 animate-fade-in"
                >
                  {/* Avatar */}
                  <div
                    className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-full text-sm font-semibold ${avatarColor(person.name)}`}
                  >
                    {getInitials(person.name)}
                  </div>

                  {/* Info */}
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium text-white/90">{person.name}</p>
                    <p className="text-[11px] text-white/40">
                      {convCounts[person.id] != null
                        ? `${convCounts[person.id]} conversation${convCounts[person.id] !== 1 ? 's' : ''}`
                        : 'Speaker identified'}
                    </p>
                  </div>

                  {/* Delete */}
                  <button
                    onClick={() => void deletePerson(person.id, person.name)}
                    disabled={deletingId === person.id}
                    className="shrink-0 rounded-md p-1.5 text-white/25 opacity-0 transition-all hover:bg-white/5 hover:text-rose-300/80 group-hover:opacity-100 disabled:opacity-50"
                    title="Remove person"
                  >
                    {deletingId === person.id ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <Trash2 className="h-4 w-4" />
                    )}
                  </button>
                </li>
              ))}
            </ul>
          )}

          {!loading && search && filtered.length === 0 && (
            <div className="pt-10 text-center text-sm text-white/40">
              No people match "{search}"
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
