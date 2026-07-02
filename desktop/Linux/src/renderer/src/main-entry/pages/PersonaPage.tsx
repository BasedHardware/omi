import React, { useEffect, useState } from 'react'
import { EmptyState, Spinner } from '../../components/ui'
import { personaProfileUrl, sanitizeUsername, usePersona } from '../../stores/persona'

// Mirrors PersonaPage.swift: manage the user's AI persona/clone. Empty state offers a
// create form (name + optional username with live availability check); created state
// shows the profile card, editable description, public-memories / prompt-status stats,
// a regenerate-from-memories action, a collapsible persona prompt, and the public
// share / chat link. Tokens, .card and .btn-* classes only; icons are inline SVGs
// (components/Icons.tsx and theme.css are off-limits here).

const Svg = (p: React.SVGProps<SVGSVGElement> & { size?: number }) => (
  <svg
    width={p.size ?? 14}
    height={p.size ?? 14}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth={2}
    strokeLinecap="round"
    strokeLinejoin="round"
    {...p}
  />
)
const PersonIcon = ({ size = 14 }: { size?: number }) => (
  <Svg size={size}>
    <circle cx="12" cy="8" r="4" />
    <path d="M4 21a8 8 0 0 1 16 0" />
  </Svg>
)
const PlusIcon = ({ size = 14 }: { size?: number }) => (
  <Svg size={size}>
    <path d="M12 5v14M5 12h14" />
  </Svg>
)
const RefreshIcon = ({ size = 14 }: { size?: number }) => (
  <Svg size={size}>
    <path d="M21 12a9 9 0 1 1-3-6.7L21 8" />
    <path d="M21 3v5h-5" />
  </Svg>
)
const TrashIcon = ({ size = 14 }: { size?: number }) => (
  <Svg size={size}>
    <path d="M3 6h18M8 6V4h8v2M6 6l1 14h10l1-14" />
  </Svg>
)
const PencilIcon = ({ size = 14 }: { size?: number }) => (
  <Svg size={size}>
    <path d="M12 20h9" />
    <path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z" />
  </Svg>
)
const ChevronDown = ({ size = 13 }: { size?: number }) => (
  <Svg size={size}>
    <path d="m6 9 6 6 6-6" />
  </Svg>
)
const ChevronUp = ({ size = 13 }: { size?: number }) => (
  <Svg size={size}>
    <path d="m18 15-6-6-6 6" />
  </Svg>
)
const CheckCircle = ({ size = 15 }: { size?: number }) => (
  <Svg size={size} stroke="var(--success)">
    <circle cx="12" cy="12" r="9" />
    <path d="m8.5 12 2.5 2.5 4.5-5" />
  </Svg>
)
const XCircle = ({ size = 15 }: { size?: number }) => (
  <Svg size={size} stroke="var(--error)">
    <circle cx="12" cy="12" r="9" />
    <path d="m9 9 6 6M15 9l-6 6" />
  </Svg>
)
const LinkIcon = ({ size = 13 }: { size?: number }) => (
  <Svg size={size}>
    <path d="M10 13a5 5 0 0 0 7 0l2-2a5 5 0 0 0-7-7l-1 1" />
    <path d="M14 11a5 5 0 0 0-7 0l-2 2a5 5 0 0 0 7 7l1-1" />
  </Svg>
)
const ChatIcon = ({ size = 13 }: { size?: number }) => (
  <Svg size={size}>
    <path d="M21 11.5a8 8 0 0 1-11.5 7.2L3 21l2.3-6.5A8 8 0 1 1 21 11.5Z" />
  </Svg>
)
const InfoIcon = ({ size = 13 }: { size?: number }) => (
  <Svg size={size}>
    <circle cx="12" cy="12" r="9" />
    <path d="M12 11v5M12 8h.01" />
  </Svg>
)
const MemoriesIcon = ({ size = 14 }: { size?: number }) => (
  <Svg size={size}>
    <path d="M12 3a4 4 0 0 0-4 4 3 3 0 0 0-2 5 3 3 0 0 0 2 5 4 4 0 0 0 8 0 3 3 0 0 0 2-5 3 3 0 0 0-2-5 4 4 0 0 0-4-4Z" />
    <path d="M12 3v18" />
  </Svg>
)
const PromptIcon = ({ size = 14 }: { size?: number }) => (
  <Svg size={size}>
    <path d="M21 12a8 8 0 0 1-11.5 7.2L3 21l2.3-6.5A8 8 0 1 1 21 12Z" />
  </Svg>
)

const STATUS_COLORS: Record<string, string> = {
  approved: 'var(--success)',
  'under-review': 'var(--warning)',
  rejected: 'var(--error)'
}
const statusColor = (status: string): string => STATUS_COLORS[status] ?? 'var(--text-quaternary)'
const statusText = (status: string): string => {
  switch (status) {
    case 'approved':
      return 'Active'
    case 'under-review':
      return 'Pending Review'
    case 'rejected':
      return 'Rejected'
    default:
      return status ? status.charAt(0).toUpperCase() + status.slice(1) : ''
  }
}

export function PersonaPage() {
  const store = usePersona()

  useEffect(() => {
    void store.load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const { persona, loading, error } = store

  return (
    <div style={{ height: '100%', overflowY: 'auto', padding: '44px 26px 26px' }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 22 }}>
        <div>
          <div className="page-title" style={{ fontSize: 28 }}>
            AI Persona
          </div>
          <div style={{ fontSize: 12.5, color: 'var(--text-quaternary)', marginTop: 4 }}>
            Create an AI clone of yourself that others can chat with
          </div>
        </div>
        {persona && (
          <button
            className="btn-secondary"
            style={{ fontSize: 12.5, padding: '7px 12px' }}
            onClick={() => void store.load()}
            disabled={loading}
            title="Refresh"
          >
            <RefreshIcon size={13} />
          </button>
        )}
      </div>

      {error && (
        <div
          style={{
            fontSize: 12.5,
            color: 'var(--error)',
            background: 'rgba(239,68,68,0.1)',
            border: '1px solid rgba(239,68,68,0.3)',
            borderRadius: 12,
            padding: '10px 14px',
            marginBottom: 16,
            maxWidth: 640
          }}
        >
          {error}
        </div>
      )}

      {loading && !persona ? (
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 14, paddingTop: 80 }}>
          <Spinner size={22} />
          <div style={{ fontSize: 13, color: 'var(--text-tertiary)' }}>Loading persona…</div>
        </div>
      ) : persona ? (
        <PersonaDetail />
      ) : (
        <NoPersona />
      )}
    </div>
  )
}

/** Empty state + inline create form (mirrors noPersonaView + CreatePersonaSheetContent). */
function NoPersona() {
  const store = usePersona()
  const [showForm, setShowForm] = useState(false)
  const [name, setName] = useState('')
  const [username, setUsername] = useState('')

  const canCreate =
    name.trim().length > 0 &&
    (username.length === 0 || (username.length >= 3 && store.usernameAvailable === true)) &&
    !store.creating

  const onUsernameChange = (raw: string) => {
    const clean = sanitizeUsername(raw)
    setUsername(clean)
    if (clean.length === 0) store.resetUsernameCheck()
    else void store.checkUsername(clean)
  }

  const submit = async () => {
    if (!canCreate) return
    const ok = await store.create(name.trim(), username || undefined)
    if (ok) {
      setShowForm(false)
      setName('')
      setUsername('')
    }
  }

  if (!showForm) {
    return (
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          textAlign: 'center',
          gap: 18,
          paddingTop: 56,
          maxWidth: 460,
          margin: '0 auto'
        }}
      >
        <div
          style={{
            width: 96,
            height: 96,
            borderRadius: 48,
            background: 'rgba(139,92,246,0.15)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: 'var(--purple-primary)'
          }}
        >
          <PersonIcon size={44} />
        </div>
        <div>
          <div style={{ fontSize: 20, fontWeight: 600, marginBottom: 8 }}>No Persona Yet</div>
          <div style={{ fontSize: 13.5, color: 'var(--text-secondary)', lineHeight: 1.5 }}>
            Create an AI clone of yourself using your public memories. Others can then chat with your persona to learn
            about you.
          </div>
        </div>
        <button className="btn-primary" onClick={() => setShowForm(true)}>
          <PlusIcon size={14} /> Create Persona
        </button>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--text-quaternary)', fontSize: 12.5 }}>
          <InfoIcon size={13} />
          Make memories public in the Memories page to enhance your persona
        </div>
      </div>
    )
  }

  return (
    <div className="card" style={{ padding: 22, maxWidth: 460, margin: '0 auto' }}>
      <div style={{ fontSize: 17, fontWeight: 600, marginBottom: 18 }}>Create AI Persona</div>

      {/* Name */}
      <label style={{ display: 'block', fontSize: 13, fontWeight: 500, color: 'var(--text-secondary)', marginBottom: 6 }}>
        Name
      </label>
      <input
        autoFocus
        value={name}
        placeholder="Your display name"
        onChange={(e) => setName(e.target.value)}
        style={{ width: '100%', marginBottom: 18 }}
      />

      {/* Username */}
      <label style={{ display: 'block', fontSize: 13, fontWeight: 500, color: 'var(--text-secondary)', marginBottom: 6 }}>
        Username (optional)
      </label>
      <div style={{ position: 'relative', display: 'flex', alignItems: 'center' }}>
        <span style={{ position: 'absolute', left: 12, color: 'var(--text-quaternary)', fontSize: 14 }}>@</span>
        <input
          value={username}
          placeholder="username"
          onChange={(e) => onUsernameChange(e.target.value)}
          style={{ width: '100%', paddingLeft: 26, paddingRight: 34 }}
        />
        <span style={{ position: 'absolute', right: 10, display: 'inline-flex' }}>
          {store.checkingUsername ? (
            <Spinner size={14} />
          ) : store.usernameAvailable === true ? (
            <CheckCircle size={16} />
          ) : store.usernameAvailable === false ? (
            <XCircle size={16} />
          ) : null}
        </span>
      </div>
      <div style={{ fontSize: 11, color: 'var(--text-quaternary)', marginTop: 6 }}>
        3-30 characters, lowercase letters, numbers, and underscores only
      </div>

      {/* Info */}
      <div
        style={{
          display: 'flex',
          gap: 8,
          alignItems: 'center',
          background: 'rgba(59,130,246,0.1)',
          color: 'var(--text-tertiary)',
          borderRadius: 10,
          padding: '10px 12px',
          fontSize: 12,
          margin: '18px 0'
        }}
      >
        <InfoIcon size={13} />
        Your persona will be built from your public memories. Make more memories public to improve it.
      </div>

      <div style={{ display: 'flex', gap: 10 }}>
        <button
          className="btn-secondary"
          style={{ flex: 1 }}
          onClick={() => {
            setShowForm(false)
            setName('')
            setUsername('')
            store.resetUsernameCheck()
          }}
        >
          Cancel
        </button>
        <button className="btn-primary" style={{ flex: 1 }} onClick={() => void submit()} disabled={!canCreate}>
          {store.creating ? <Spinner size={14} /> : <PlusIcon size={14} />}
          {store.creating ? 'Creating…' : 'Create Persona'}
        </button>
      </div>
    </div>
  )
}

/** Created persona view (mirrors personaDetailView). */
function PersonaDetail() {
  const store = usePersona()
  const persona = store.persona
  const [editing, setEditing] = useState(false)
  const [editName, setEditName] = useState('')
  const [editDescription, setEditDescription] = useState('')
  const [promptExpanded, setPromptExpanded] = useState(false)
  const [copied, setCopied] = useState(false)

  if (!persona) return null

  const hasPrompt = !!persona.persona_prompt && persona.persona_prompt.length > 0
  const profileUrl = persona.username ? personaProfileUrl(persona.username) : null

  const startEdit = () => {
    setEditName(persona.name)
    setEditDescription(persona.description)
    setEditing(true)
  }
  const save = async () => {
    const ok = await store.saveEdits(editName, editDescription)
    if (ok) setEditing(false)
  }
  const copyLink = () => {
    if (!profileUrl) return
    void navigator.clipboard.writeText(profileUrl)
    setCopied(true)
    setTimeout(() => setCopied(false), 1800)
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 18, maxWidth: 720 }}>
      {/* Profile card */}
      <div className="card" style={{ padding: 20, display: 'flex', alignItems: 'center', gap: 18 }}>
        <div
          style={{
            width: 72,
            height: 72,
            borderRadius: 36,
            background: 'rgba(139,92,246,0.15)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: 'var(--purple-primary)',
            flexShrink: 0,
            overflow: 'hidden'
          }}
        >
          {persona.image ? (
            <img src={persona.image} alt={persona.name} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
          ) : (
            <PersonIcon size={30} />
          )}
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 19, fontWeight: 600 }}>{persona.name}</div>
          {persona.username && (
            <div style={{ fontSize: 13, color: 'var(--text-quaternary)', marginTop: 2 }}>@{persona.username}</div>
          )}
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 8 }}>
            <span
              style={{ width: 8, height: 8, borderRadius: 4, background: statusColor(persona.status), flexShrink: 0 }}
            />
            <span style={{ fontSize: 12, fontWeight: 500, color: 'var(--text-secondary)' }}>
              {statusText(persona.status)}
            </span>
          </div>
        </div>
        <div style={{ display: 'flex', gap: 10 }}>
          <button
            className="btn-secondary"
            style={{ padding: 9, width: 36, height: 36 }}
            onClick={startEdit}
            title="Edit name & description"
          >
            <PencilIcon size={14} />
          </button>
          <button
            style={{
              padding: 9,
              width: 36,
              height: 36,
              borderRadius: 'var(--radius-control)',
              border: '1px solid rgba(239,68,68,0.3)',
              background: 'rgba(239,68,68,0.12)',
              color: 'var(--error)',
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center'
            }}
            onClick={() => {
              if (window.confirm('Delete your AI persona? This cannot be undone.')) void store.remove()
            }}
            disabled={store.deleting}
            title="Delete persona"
          >
            <TrashIcon size={14} />
          </button>
        </div>
      </div>

      {/* Description */}
      <div className="card" style={{ padding: 16 }}>
        <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 10 }}>
          Description
        </div>
        {editing ? (
          <>
            <input
              value={editName}
              placeholder="Name"
              onChange={(e) => setEditName(e.target.value)}
              style={{ width: '100%', marginBottom: 10 }}
            />
            <textarea
              value={editDescription}
              rows={3}
              placeholder="Describe your persona"
              onChange={(e) => setEditDescription(e.target.value)}
              style={{ width: '100%', fontSize: 13, resize: 'vertical' }}
            />
            <div style={{ display: 'flex', gap: 10, marginTop: 12 }}>
              <button className="btn-secondary" style={{ flex: 1 }} onClick={() => setEditing(false)}>
                Cancel
              </button>
              <button className="btn-primary" style={{ flex: 1 }} onClick={() => void save()} disabled={store.saving}>
                {store.saving ? 'Saving…' : 'Save Changes'}
              </button>
            </div>
          </>
        ) : (
          <div
            className="text-selectable"
            style={{
              fontSize: 13,
              lineHeight: 1.55,
              color: persona.description ? 'var(--text-primary)' : 'var(--text-quaternary)'
            }}
          >
            {persona.description || 'No description yet'}
          </div>
        )}
      </div>

      {/* Stats */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
        <StatCard
          icon={<MemoriesIcon size={14} />}
          title="Public Memories"
          value={String(persona.public_memories_count ?? 0)}
        />
        <StatCard
          icon={<PromptIcon size={14} />}
          title="Persona Prompt"
          value={hasPrompt ? 'Generated' : 'Not Generated'}
          warning={!hasPrompt}
        />
      </div>

      {/* Public link + chat */}
      <div className="card" style={{ padding: 16 }}>
        <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 10 }}>
          Share & Chat
        </div>
        {profileUrl ? (
          <>
            <code
              className="text-selectable"
              style={{
                display: 'block',
                fontSize: 12,
                background: 'var(--bg-tertiary)',
                padding: '8px 10px',
                borderRadius: 8,
                wordBreak: 'break-all',
                marginBottom: 12,
                color: 'var(--text-secondary)'
              }}
            >
              {profileUrl}
            </code>
            <div style={{ display: 'flex', gap: 10 }}>
              <button className="btn-secondary" style={{ fontSize: 12.5 }} onClick={copyLink}>
                <LinkIcon size={13} /> {copied ? 'Copied' : 'Copy link'}
              </button>
              <button
                className="btn-primary"
                style={{ fontSize: 12.5 }}
                onClick={() => window.omi.system.openExternal(profileUrl)}
              >
                <ChatIcon size={13} /> Chat with your persona
              </button>
            </div>
          </>
        ) : (
          <div style={{ fontSize: 12.5, color: 'var(--text-quaternary)', lineHeight: 1.5 }}>
            Set a username (via Edit) to get a public link people can use to chat with your persona.
          </div>
        )}
      </div>

      {/* Actions: regenerate from memories */}
      <div className="card" style={{ padding: 16 }}>
        <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 10 }}>Actions</div>
        <button
          onClick={() => void store.regenerate()}
          disabled={store.regenerating}
          style={{
            width: '100%',
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 8,
            padding: '11px 0',
            borderRadius: 'var(--radius-control)',
            background: 'rgba(139,92,246,0.15)',
            color: 'var(--purple-primary)',
            fontSize: 13,
            fontWeight: 600,
            opacity: store.regenerating ? 0.6 : 1
          }}
        >
          {store.regenerating ? <Spinner size={14} /> : <RefreshIcon size={14} />}
          {store.regenerating ? 'Regenerating…' : 'Regenerate from Memories'}
        </button>
      </div>

      {/* Persona prompt (collapsible) */}
      {hasPrompt && (
        <div className="card" style={{ padding: 16 }}>
          <button
            onClick={() => setPromptExpanded((v) => !v)}
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              width: '100%',
              color: 'var(--text-secondary)'
            }}
          >
            <span style={{ fontSize: 13, fontWeight: 600 }}>Persona Prompt</span>
            {promptExpanded ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
          </button>
          {promptExpanded && (
            <div
              className="text-selectable"
              style={{
                fontSize: 12.5,
                lineHeight: 1.6,
                color: 'var(--text-tertiary)',
                background: 'var(--bg-tertiary)',
                borderRadius: 10,
                padding: 12,
                marginTop: 12,
                whiteSpace: 'pre-wrap'
              }}
            >
              {persona.persona_prompt}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function StatCard({
  icon,
  title,
  value,
  warning
}: {
  icon: React.ReactNode
  title: string
  value: string
  warning?: boolean
}) {
  const accent = warning ? 'var(--warning)' : 'var(--purple-primary)'
  return (
    <div className="card" style={{ padding: 16 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: accent, marginBottom: 8 }}>
        {icon}
        <span style={{ fontSize: 12, color: 'var(--text-quaternary)' }}>{title}</span>
      </div>
      <div style={{ fontSize: 18, fontWeight: 600, color: warning ? 'var(--warning)' : 'var(--text-primary)' }}>
        {value}
      </div>
    </div>
  )
}
