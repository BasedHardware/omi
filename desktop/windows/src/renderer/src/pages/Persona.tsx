import { useCallback, useEffect, useState } from 'react'
import { User, Plus, RefreshCw, Pencil, Trash2, CheckCircle, Clock, XCircle, X, Loader2 } from 'lucide-react'
import { omiApi } from '../lib/apiClient'
import { toast } from '../lib/toast'

type PersonaStatus = 'approved' | 'under-review' | 'rejected' | string

type Persona = {
  id: string
  name: string
  username?: string
  description?: string
  persona_prompt?: string
  status?: PersonaStatus
  image?: string
  approved?: boolean
  private?: boolean
}

const STATUS_CONFIG: Record<string, { label: string; icon: typeof CheckCircle; color: string }> = {
  approved: { label: 'Approved', icon: CheckCircle, color: 'text-green-400' },
  'under-review': { label: 'Under Review', icon: Clock, color: 'text-amber-400' },
  rejected: { label: 'Rejected', icon: XCircle, color: 'text-red-400' },
}

function StatusBadge({ status }: { status?: string }): React.JSX.Element {
  const cfg = status ? STATUS_CONFIG[status] : null
  if (!cfg) return <span className="text-xs text-text-quaternary">Unknown</span>
  const Icon = cfg.icon
  return (
    <span className={`flex items-center gap-1.5 text-sm font-medium ${cfg.color}`}>
      <Icon className="h-4 w-4" />
      {cfg.label}
    </span>
  )
}

function initials(name: string): string {
  return name.split(/\s+/).map((w) => w[0]).join('').toUpperCase().slice(0, 2)
}

export function Persona(): React.JSX.Element {
  const [persona, setPersona] = useState<Persona | null | undefined>(undefined) // undefined = loading
  const [creating, setCreating] = useState(false)
  const [regenerating, setRegenerating] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [showCreate, setShowCreate] = useState(false)
  const [editMode, setEditMode] = useState(false)
  const [showPrompt, setShowPrompt] = useState(false)
  const [nameInput, setNameInput] = useState('')
  const [descInput, setDescInput] = useState('')

  const load = useCallback(async () => {
    try {
      const r = await omiApi.get<Persona>('/v1/personas')
      setPersona(r.data)
    } catch (e: unknown) {
      const status = (e as { response?: { status?: number } }).response?.status
      if (status === 404) setPersona(null)
      else {
        console.warn('[persona] load failed', e)
        setPersona(null)
      }
    }
  }, [])

  useEffect(() => { void load() }, [load])

  const createPersona = async (): Promise<void> => {
    if (!nameInput.trim()) return
    setCreating(true)
    try {
      await omiApi.post('/v1/user/persona')
      await load()
      setShowCreate(false)
      toast('Persona created!', { tone: 'success' })
    } catch (e) {
      toast('Failed to create persona', { tone: 'error', body: (e as Error).message })
    } finally {
      setCreating(false)
    }
  }

  const regenerate = async (): Promise<void> => {
    if (!persona) return
    setRegenerating(true)
    try {
      await omiApi.post(`/v1/personas/${persona.id}/regenerate-prompt`)
      await load()
      toast('Persona regenerated from your memories!', { tone: 'success' })
    } catch (e) {
      toast('Regeneration failed', { tone: 'error', body: (e as Error).message })
    } finally {
      setRegenerating(false)
    }
  }

  const saveEdit = async (): Promise<void> => {
    if (!persona) return
    try {
      const form = new FormData()
      form.append('persona_data', JSON.stringify({ name: nameInput, description: descInput }))
      await omiApi.patch(`/v1/personas/${persona.id}`, form, {
        headers: { 'Content-Type': 'multipart/form-data' }
      })
      await load()
      setEditMode(false)
      toast('Persona updated', { tone: 'success' })
    } catch (e) {
      toast('Update failed', { tone: 'error', body: (e as Error).message })
    }
  }

  const deletePersona = async (): Promise<void> => {
    if (!persona) return
    if (!window.confirm('Delete your AI persona? This cannot be undone.')) return
    setDeleting(true)
    try {
      await omiApi.delete(`/v1/personas/${persona.id}`)
      setPersona(null)
      toast('Persona deleted', { tone: 'success' })
    } catch (e) {
      toast('Delete failed', { tone: 'error', body: (e as Error).message })
    } finally {
      setDeleting(false)
    }
  }

  const startEdit = (): void => {
    if (!persona) return
    setNameInput(persona.name)
    setDescInput(persona.description ?? '')
    setEditMode(true)
  }

  return (
    <div className="flex h-full flex-col overflow-y-auto p-6">
      {/* Header */}
      <div className="mb-8 flex items-center gap-4 px-1">
        <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-purple-500/20">
          <User className="h-5 w-5 text-purple-400" />
        </div>
        <div>
          <h1 className="font-display text-2xl font-bold tracking-tight text-white">AI Persona</h1>
          <p className="text-sm text-white/50">Create an AI clone of yourself that others can chat with</p>
        </div>
      </div>

      {/* Loading */}
      {persona === undefined && (
        <div className="flex flex-1 items-center justify-center">
          <Loader2 className="h-6 w-6 animate-spin text-white/30" />
        </div>
      )}

      {/* No Persona */}
      {persona === null && (
        <div className="flex flex-1 flex-col items-center justify-center text-center">
          <div className="mb-5 flex h-24 w-24 items-center justify-center rounded-full bg-purple-500/15">
            <User className="h-11 w-11 text-purple-400" strokeWidth={1.5} />
          </div>
          <h2 className="mb-2 text-xl font-semibold text-text-primary">No Persona Yet</h2>
          <p className="mb-6 max-w-sm text-sm text-text-tertiary">
            Create an AI clone of yourself built from your public memories. Others can discover
            and chat with your persona on the Omi platform.
          </p>
          <button
            onClick={() => { setNameInput(''); setShowCreate(true) }}
            className="flex items-center gap-2 rounded-xl bg-purple-500 px-5 py-2.5 text-sm font-semibold text-white hover:bg-purple-400"
          >
            <Plus className="h-4 w-4" />
            Create Persona
          </button>
          <div className="mt-6 flex max-w-sm items-start gap-2 rounded-xl bg-white/[0.04] px-4 py-3 text-left">
            <span className="mt-0.5 text-sm">💡</span>
            <p className="text-xs text-text-tertiary leading-relaxed">
              Make memories public in the Memories page to enhance your persona — more public
              memories means a richer, more accurate AI clone.
            </p>
          </div>
        </div>
      )}

      {/* Persona Exists */}
      {persona && (
        <div className="mx-auto w-full max-w-xl space-y-6">
          {/* Avatar + name card */}
          <div className="surface-card p-6">
            <div className="flex items-start gap-4">
              {persona.image ? (
                <img src={persona.image} alt={persona.name} className="h-20 w-20 rounded-2xl object-cover" />
              ) : (
                <div className="flex h-20 w-20 shrink-0 items-center justify-center rounded-2xl bg-purple-500/20 text-2xl font-bold text-purple-300">
                  {initials(persona.name)}
                </div>
              )}
              <div className="min-w-0 flex-1">
                {editMode ? (
                  <input
                    value={nameInput}
                    onChange={(e) => setNameInput(e.target.value)}
                    className="mb-2 w-full rounded-lg bg-white/10 px-3 py-2 text-lg font-semibold text-white focus:outline-none"
                    placeholder="Your display name"
                  />
                ) : (
                  <h2 className="text-xl font-semibold text-text-primary">{persona.name}</h2>
                )}
                {persona.username && (
                  <p className="mt-0.5 text-sm text-text-tertiary">@{persona.username}</p>
                )}
                <div className="mt-2">
                  <StatusBadge status={persona.status} />
                </div>
              </div>
              {!editMode ? (
                <div className="flex gap-2">
                  <button
                    onClick={startEdit}
                    title="Edit persona"
                    className="rounded-xl p-2.5 text-text-quaternary hover:bg-white/[0.06] hover:text-text-secondary"
                  >
                    <Pencil className="h-4 w-4" />
                  </button>
                  <button
                    onClick={() => void deletePersona()}
                    disabled={deleting}
                    title="Delete persona"
                    className="rounded-xl p-2.5 text-text-quaternary hover:bg-red-500/15 hover:text-red-400 disabled:opacity-40"
                  >
                    {deleting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
                  </button>
                </div>
              ) : (
                <button
                  onClick={() => setEditMode(false)}
                  className="rounded-xl p-2.5 text-text-quaternary hover:bg-white/[0.06]"
                >
                  <X className="h-4 w-4" />
                </button>
              )}
            </div>

            {/* Description */}
            <div className="mt-4">
              <p className="mb-1.5 text-sm font-semibold text-text-secondary">Description</p>
              {editMode ? (
                <textarea
                  value={descInput}
                  onChange={(e) => setDescInput(e.target.value)}
                  rows={3}
                  className="w-full rounded-lg bg-white/10 px-3 py-2 text-sm text-text-secondary focus:outline-none"
                  placeholder="Describe your persona…"
                />
              ) : (
                <p className="text-sm text-text-tertiary">{persona.description || 'No description yet'}</p>
              )}
            </div>

            {editMode && (
              <div className="mt-4 flex gap-2">
                <button onClick={() => setEditMode(false)} className="btn-ghost">Cancel</button>
                <button onClick={() => void saveEdit()} className="btn-primary">Save Changes</button>
              </div>
            )}
          </div>

          {/* Actions */}
          <button
            onClick={() => void regenerate()}
            disabled={regenerating}
            className="flex w-full items-center justify-center gap-2 rounded-xl bg-purple-500/15 py-3 text-sm font-semibold text-purple-300 hover:bg-purple-500/25 disabled:opacity-50"
          >
            {regenerating
              ? <><Loader2 className="h-4 w-4 animate-spin" /> Regenerating…</>
              : <><RefreshCw className="h-4 w-4" /> Regenerate from Memories</>
            }
          </button>

          {/* Persona prompt (collapsible) */}
          {persona.persona_prompt && (
            <div className="surface-card overflow-hidden">
              <button
                onClick={() => setShowPrompt((v) => !v)}
                className="flex w-full items-center justify-between px-5 py-4 text-sm font-semibold text-text-secondary"
              >
                Persona Prompt
                <span className="text-text-quaternary">{showPrompt ? '▲' : '▼'}</span>
              </button>
              {showPrompt && (
                <div className="border-t border-white/[0.06] px-5 py-4">
                  <pre className="whitespace-pre-wrap font-mono text-xs leading-relaxed text-text-tertiary">
                    {persona.persona_prompt}
                  </pre>
                </div>
              )}
            </div>
          )}

          <div className="flex items-start gap-2 rounded-xl bg-white/[0.04] px-4 py-3">
            <span className="text-sm">💡</span>
            <p className="text-xs text-text-tertiary leading-relaxed">
              Make memories public in the Memories page to enhance your persona — more public
              memories means a richer, more accurate AI clone.
            </p>
          </div>
        </div>
      )}

      {/* Create sheet */}
      {showCreate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="w-full max-w-md rounded-2xl border border-white/[0.08] bg-[#111] p-6 shadow-2xl">
            <div className="mb-5 flex items-center justify-between">
              <h3 className="text-lg font-semibold text-text-primary">Create AI Persona</h3>
              <button onClick={() => setShowCreate(false)} className="text-text-quaternary hover:text-text-tertiary">
                <X className="h-5 w-5" />
              </button>
            </div>
            <div className="space-y-4">
              <div>
                <label className="mb-1.5 block text-sm font-medium text-text-secondary">
                  Name <span className="text-red-400">*</span>
                </label>
                <input
                  value={nameInput}
                  onChange={(e) => setNameInput(e.target.value)}
                  placeholder="Your display name"
                  className="w-full rounded-xl bg-white/10 px-4 py-3 text-sm text-text-primary placeholder:text-text-quaternary focus:outline-none"
                  autoFocus
                />
              </div>
              <div className="rounded-xl bg-white/[0.04] px-4 py-3 text-xs text-text-tertiary leading-relaxed">
                Your persona will be built from your public memories. Enable more memories to
                make it more accurate and personal.
              </div>
            </div>
            <div className="mt-5 flex justify-end gap-2">
              <button onClick={() => setShowCreate(false)} className="btn-ghost">Cancel</button>
              <button
                onClick={() => void createPersona()}
                disabled={!nameInput.trim() || creating}
                className="btn-primary disabled:opacity-50"
              >
                {creating ? 'Creating…' : 'Create Persona'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
