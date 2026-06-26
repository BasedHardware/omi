import React, { useEffect, useRef, useState } from 'react'
import herologo from '../../assets/herologo.png'
import { IconCamera, IconPlus, IconSearch, IconSend, IconStar, IconTrash } from '../../components/Icons'
import { Markdown } from '../../components/ui'
import { clockTime } from '../../lib/format'
import { useAuth } from '../../stores/auth'
import { useChat, type UiChatMessage } from '../../stores/chat'
import { filterSessions, groupSessions, useChatSessions } from '../../stores/chatSessions'

const SUGGESTIONS = [
  'What should I do today?',
  'What did I just discuss?',
  'What do you see on my screen?',
  'Summarize my recent conversations'
]

// Small inline stroke icons (kept local so this file owns no shared-icon edits).
const IconThumbUp = ({ size = 13, filled }: { size?: number; filled?: boolean }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill={filled ? 'currentColor' : 'none'} stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round">
    <path d="M7 10v11" />
    <path d="M7 10l4-7a2 2 0 0 1 2.6 2.6L12.5 9H19a2 2 0 0 1 2 2.3l-1.2 7A2 2 0 0 1 17.8 20H7" />
  </svg>
)
const IconThumbDown = ({ size = 13, filled }: { size?: number; filled?: boolean }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill={filled ? 'currentColor' : 'none'} stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round">
    <path d="M17 14V3" />
    <path d="M17 14l-4 7a2 2 0 0 1-2.6-2.6L11.5 15H5a2 2 0 0 1-2-2.3l1.2-7A2 2 0 0 1 6.2 4H17" />
  </svg>
)
const IconCopy = ({ size = 13 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round">
    <rect x="9" y="9" width="11" height="11" rx="2.5" />
    <path d="M5 15V5a2 2 0 0 1 2-2h8" />
  </svg>
)
const IconCheck = ({ size = 13 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
    <path d="M5 12.5l4.5 4.5L19 7" />
  </svg>
)
const IconPencil = ({ size = 12 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round">
    <path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z" />
  </svg>
)

// Three bouncing dots (theme.css `typingBounce`), replaces the old spinner.
function TypingDots() {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 4, height: 18, padding: '2px 0' }}>
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          style={{
            width: 6,
            height: 6,
            borderRadius: '50%',
            background: 'var(--text-tertiary)',
            animation: 'typingBounce 1.3s ease-in-out infinite',
            animationDelay: `${i * 0.18}s`
          }}
        />
      ))}
    </div>
  )
}

// 32px avatar column. Assistant = omi mark, user = initial circle (ChatMessagesView.swift).
function Avatar({ role, userName }: { role: UiChatMessage['role']; userName?: string }) {
  if (role === 'assistant') {
    return <img src={herologo} width={32} height={32} style={{ borderRadius: 9, flexShrink: 0 }} alt="omi" />
  }
  const initial = (userName?.trim()?.[0] || 'Y').toUpperCase()
  return (
    <div
      style={{
        width: 32,
        height: 32,
        borderRadius: '50%',
        background: 'var(--user-bubble)',
        color: '#fff',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        fontSize: 13,
        fontWeight: 600,
        flexShrink: 0
      }}
    >
      {initial}
    </div>
  )
}

function AssistantActions({ message }: { message: UiChatMessage }) {
  const chat = useChat()
  const [copied, setCopied] = useState(false)
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(message.text)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      // clipboard may be unavailable
    }
  }
  const btn = (active: boolean): React.CSSProperties => ({
    display: 'flex',
    alignItems: 'center',
    color: active ? 'var(--text-secondary)' : 'var(--text-quaternary)',
    padding: 3,
    borderRadius: 6
  })
  return (
    <div style={{ display: 'flex', gap: 2, marginTop: 6 }}>
      <button
        onClick={() => void chat.rate(message.id, 1)}
        title="Helpful response"
        style={btn(message.rating === 1)}
        onMouseEnter={(e) => (e.currentTarget.style.color = message.rating === 1 ? 'var(--success)' : 'var(--text-tertiary)')}
        onMouseLeave={(e) => (e.currentTarget.style.color = message.rating === 1 ? 'var(--success)' : 'var(--text-quaternary)')}
      >
        <IconThumbUp filled={message.rating === 1} />
      </button>
      <button
        onClick={() => void chat.rate(message.id, -1)}
        title="Not helpful"
        style={btn(message.rating === -1)}
        onMouseEnter={(e) => (e.currentTarget.style.color = message.rating === -1 ? 'var(--error)' : 'var(--text-tertiary)')}
        onMouseLeave={(e) => (e.currentTarget.style.color = message.rating === -1 ? 'var(--error)' : 'var(--text-quaternary)')}
      >
        <IconThumbDown filled={message.rating === -1} />
      </button>
      <button
        onClick={() => void copy()}
        title="Copy response"
        style={btn(copied)}
        onMouseEnter={(e) => (e.currentTarget.style.color = copied ? 'var(--success)' : 'var(--text-tertiary)')}
        onMouseLeave={(e) => (e.currentTarget.style.color = copied ? 'var(--success)' : 'var(--text-quaternary)')}
      >
        {copied ? <span style={{ color: 'var(--success)', display: 'flex' }}><IconCheck /></span> : <IconCopy />}
      </button>
    </div>
  )
}

function MessageRow({ m, userName }: { m: UiChatMessage; userName?: string }) {
  const isUser = m.role === 'user'
  return (
    <div
      style={{
        display: 'flex',
        flexDirection: isUser ? 'row-reverse' : 'row',
        alignItems: 'flex-start',
        gap: 12
      }}
    >
      <Avatar role={m.role} userName={userName} />
      <div style={{ minWidth: 0, maxWidth: '82%', display: 'flex', flexDirection: 'column', alignItems: isUser ? 'flex-end' : 'flex-start' }}>
        {m.imageDataUrl && (
          <img
            src={m.imageDataUrl}
            style={{ maxWidth: 260, borderRadius: 12, marginBottom: 6, border: '1px solid var(--border)' }}
            alt="screenshot context"
          />
        )}
        <div
          className="text-selectable"
          style={{
            background: isUser ? 'var(--user-bubble)' : 'var(--bg-tertiary)',
            color: m.error ? 'var(--warning)' : 'var(--text-primary)',
            borderRadius: 'var(--radius-bubble)',
            padding: '10px 14px',
            fontSize: 14,
            lineHeight: 1.5
          }}
        >
          {isUser ? (
            m.text
          ) : m.text ? (
            <Markdown>{m.text}</Markdown>
          ) : m.streaming ? (
            <TypingDots />
          ) : null}
          {!isUser && m.streaming && m.text && (
            <span
              style={{
                display: 'inline-block',
                width: 7,
                height: 14,
                background: 'var(--purple-primary)',
                marginLeft: 3,
                verticalAlign: 'middle',
                animation: 'pulse 1s ease-in-out infinite'
              }}
            />
          )}
        </div>
        {!isUser && !m.streaming && m.text && !m.error && <AssistantActions message={m} />}
        {m.createdAt && (
          <div className="tnum" style={{ fontSize: 10, color: 'var(--text-quaternary)', marginTop: 4, padding: '0 2px' }}>
            {clockTime(m.createdAt)}
          </div>
        )}
      </div>
    </div>
  )
}

// One sidebar session row: selection, inline rename on double-click, star, delete-with-confirm.
function SessionRow({
  session,
  selected,
  onSelect,
  onRename,
  onToggleStar,
  onDelete
}: {
  session: { id: string; title?: string; starred?: boolean }
  selected: boolean
  onSelect: () => void
  onRename: (title: string) => void
  onToggleStar: () => void
  onDelete: () => void
}) {
  const [hovering, setHovering] = useState(false)
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(session.title || '')
  const [confirming, setConfirming] = useState(false)

  const startEditing = () => {
    setDraft(session.title || '')
    setEditing(true)
  }
  const commit = () => {
    const trimmed = draft.trim()
    if (trimmed && trimmed !== session.title) onRename(trimmed)
    setEditing(false)
  }

  return (
    <div
      onClick={() => !editing && onSelect()}
      onDoubleClick={startEditing}
      style={{
        padding: '8px 9px',
        borderRadius: 10,
        cursor: 'pointer',
        background: selected ? 'var(--bg-tertiary)' : 'transparent',
        display: 'flex',
        alignItems: 'center',
        gap: 6,
        marginBottom: 2
      }}
      onMouseEnter={(e) => {
        setHovering(true)
        if (!selected) e.currentTarget.style.background = 'rgba(37,37,37,0.6)'
      }}
      onMouseLeave={(e) => {
        setHovering(false)
        if (!selected) e.currentTarget.style.background = 'transparent'
      }}
    >
      {session.starred && !editing && (
        <span style={{ color: 'var(--warning)', display: 'flex', flexShrink: 0 }}>
          <IconStar size={11} filled />
        </span>
      )}
      {editing ? (
        <input
          autoFocus
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onClick={(e) => e.stopPropagation()}
          onBlur={commit}
          onKeyDown={(e) => {
            if (e.key === 'Enter') commit()
            if (e.key === 'Escape') setEditing(false)
          }}
          style={{
            flex: 1,
            minWidth: 0,
            fontSize: 12.5,
            padding: '2px 6px',
            borderRadius: 6,
            background: 'var(--bg-secondary)'
          }}
        />
      ) : (
        <span style={{ flex: 1, minWidth: 0, fontSize: 12.5, color: selected ? 'var(--text-primary)' : 'var(--text-secondary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {session.title || 'New Chat'}
        </span>
      )}
      {!editing && confirming ? (
        <div style={{ display: 'flex', alignItems: 'center', gap: 4 }} onClick={(e) => e.stopPropagation()}>
          <button
            onClick={() => {
              setConfirming(false)
              onDelete()
            }}
            style={{ color: 'var(--error)', fontSize: 11, padding: '1px 5px', borderRadius: 6, background: 'rgba(239,68,68,0.14)' }}
            title="Confirm delete"
          >
            Delete
          </button>
          <button
            onClick={() => setConfirming(false)}
            style={{ color: 'var(--text-quaternary)', fontSize: 11, padding: '1px 4px' }}
            title="Cancel"
          >
            Cancel
          </button>
        </div>
      ) : (
        !editing &&
        (hovering || session.starred) && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 2 }} onClick={(e) => e.stopPropagation()}>
            {hovering && (
              <button onClick={startEditing} style={{ color: 'var(--text-quaternary)', padding: 1 }} title="Rename">
                <IconPencil size={12} />
              </button>
            )}
            <button
              onClick={onToggleStar}
              style={{ color: session.starred ? 'var(--warning)' : 'var(--text-quaternary)', padding: 1 }}
              title="Star"
            >
              <IconStar size={12} filled={session.starred} />
            </button>
            {hovering && (
              <button onClick={() => setConfirming(true)} style={{ color: 'var(--text-quaternary)', padding: 1 }} title="Delete">
                <IconTrash size={12} />
              </button>
            )}
          </div>
        )
      )}
    </div>
  )
}

export function ChatPage() {
  const chat = useChat()
  const sessions = useChatSessions()
  const auth = useAuth((s) => s.state)
  const [input, setInput] = useState('')
  const [pendingShot, setPendingShot] = useState<string | null>(null)
  const endRef = useRef<HTMLDivElement | null>(null)
  const taRef = useRef<HTMLTextAreaElement | null>(null)

  useEffect(() => {
    chat.setUserName(auth?.name)
    void sessions.load()
    void chat.loadHistory()
  }, [auth?.name])

  // Switch the chat thread when the selected session changes.
  useEffect(() => {
    if (sessions.currentId && sessions.currentId !== chat.sessionId) {
      void chat.setSession(sessions.currentId)
    }
  }, [sessions.currentId])

  const visibleSessions = filterSessions(sessions.sessions, sessions.starredOnly, sessions.query)
  const grouped = groupSessions(visibleSessions)

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [chat.messages.length, chat.messages[chat.messages.length - 1]?.text?.length])

  const send = async (text?: string) => {
    const value = text ?? input
    if (!value.trim() && !pendingShot) return
    setInput('')
    const shot = pendingShot
    setPendingShot(null)
    const wantsScreen = /screen|see|looking at|tab|window/i.test(value)
    let imageDataUrl = shot ?? undefined
    let screenContext: string | undefined
    if (!imageDataUrl && wantsScreen) {
      const result = await window.omi.capture.screenshot()
      imageDataUrl = result?.dataUrl
    }
    if (imageDataUrl) {
      screenContext = (await window.omi.rewind.latestOcr(60_000)) ?? undefined
    }
    void chat.send(value, { imageDataUrl, screenContext })
  }

  const attachScreenshot = async () => {
    const result = await window.omi.capture.screenshot()
    if (result) setPendingShot(result.dataUrl)
  }

  const newChat = async () => {
    const id = await sessions.create()
    if (id) void chat.setSession(id)
    else chat.clear()
  }

  return (
    <div style={{ display: 'flex', height: '100%' }}>
      {/* Sessions sidebar (ChatSessionsSidebar.swift) */}
      <div style={{ width: 220, borderRight: '1px solid var(--border)', display: 'flex', flexDirection: 'column', flexShrink: 0 }}>
        <div style={{ padding: '44px 12px 8px' }}>
          <button className="btn-primary" style={{ width: '100%', fontSize: 12.5 }} onClick={() => void newChat()}>
            <IconPlus size={13} /> New chat
          </button>
          <button
            className={`chip ${sessions.starredOnly ? 'active' : ''}`}
            style={{ marginTop: 8, width: '100%', justifyContent: 'center' }}
            onClick={() => sessions.setStarredOnly(!sessions.starredOnly)}
          >
            <IconStar size={12} filled={sessions.starredOnly} /> Starred
          </button>
          {/* Search field (ChatSessionsSidebar.swift searchField) */}
          <div
            style={{
              marginTop: 8,
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              padding: '6px 10px',
              borderRadius: 8,
              background: 'rgba(37,37,37,0.6)',
              border: '1px solid var(--border)'
            }}
          >
            <span style={{ color: 'var(--text-quaternary)', display: 'flex', flexShrink: 0 }}>
              <IconSearch size={13} />
            </span>
            <input
              value={sessions.query}
              placeholder="Search chats…"
              onChange={(e) => sessions.setQuery(e.target.value)}
              style={{
                flex: 1,
                minWidth: 0,
                fontSize: 12.5,
                background: 'transparent',
                border: 'none',
                padding: 0
              }}
            />
            {sessions.query && (
              <button onClick={() => sessions.setQuery('')} style={{ color: 'var(--text-quaternary)', padding: 0, display: 'flex' }} title="Clear">
                ×
              </button>
            )}
          </div>
        </div>
        <div style={{ flex: 1, overflowY: 'auto', padding: '4px 8px 10px' }}>
          {grouped.map(([label, items]) => (
            <div key={label}>
              <div
                style={{
                  padding: '12px 9px 6px',
                  fontSize: 11,
                  fontWeight: 600,
                  color: 'var(--text-quaternary)',
                  textTransform: 'uppercase',
                  letterSpacing: 0.4
                }}
              >
                {label}
              </div>
              {items.map((s) => (
                <SessionRow
                  key={s.id}
                  session={s}
                  selected={sessions.currentId === s.id}
                  onSelect={() => sessions.select(s.id)}
                  onRename={(title) => void sessions.rename(s.id, title)}
                  onToggleStar={() => void sessions.toggleStar(s.id)}
                  onDelete={() => void sessions.remove(s.id)}
                />
              ))}
            </div>
          ))}
          {visibleSessions.length === 0 && (
            <div style={{ padding: 14, fontSize: 12, color: 'var(--text-quaternary)', textAlign: 'center' }}>
              {sessions.query ? 'No results' : sessions.starredOnly ? 'No starred chats' : 'No chats yet'}
            </div>
          )}
        </div>
      </div>

      {/* Chat thread */}
      <div style={{ display: 'flex', flexDirection: 'column', height: '100%', flex: 1, minWidth: 0 }}>
        <div
          style={{
            padding: '44px 24px 12px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            borderBottom: '1px solid var(--border)'
          }}
        >
          <span style={{ fontSize: 19, fontWeight: 700 }}>
            {sessions.sessions.find((s) => s.id === sessions.currentId)?.title || 'Chat'}
          </span>
          <button className="btn-secondary" style={{ padding: '5px 12px', fontSize: 12 }} onClick={() => void newChat()}>
            New chat
          </button>
        </div>

      <div style={{ flex: 1, overflowY: 'auto', padding: '22px 24px' }}>
        {chat.messages.length === 0 ? (
          <div style={{ height: '100%', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 16 }}>
            <div
              style={{
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                gap: 12,
                maxWidth: 420,
                padding: '32px 28px',
                borderRadius: 'var(--radius-card)',
                background: 'var(--bg-secondary)',
                border: '1px solid var(--border)',
                textAlign: 'center'
              }}
            >
              <img src={herologo} width={52} height={52} style={{ borderRadius: 14 }} alt="omi" />
              <div style={{ fontSize: 19, fontWeight: 700 }}>Chat with omi</div>
              <div style={{ fontSize: 13.5, color: 'var(--text-tertiary)', lineHeight: 1.5 }}>
                Ask anything, it knows your context, your conversations, memories and what is on your screen.
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, justifyContent: 'center', marginTop: 4 }}>
                {SUGGESTIONS.map((s) => (
                  <button key={s} className="chip" onClick={() => void send(s)}>
                    {s}
                  </button>
                ))}
              </div>
            </div>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 18, maxWidth: 760, margin: '0 auto' }}>
            {chat.messages.map((m) => (
              <MessageRow key={m.id} m={m} userName={chat.userName} />
            ))}
            <div ref={endRef} />
          </div>
        )}
      </div>

      <div style={{ padding: '12px 24px 20px' }}>
        {pendingShot && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
            <img src={pendingShot} style={{ height: 44, borderRadius: 8, border: '1px solid var(--border)' }} alt="" />
            <button style={{ fontSize: 11, color: 'var(--text-quaternary)' }} onClick={() => setPendingShot(null)}>
              Remove screenshot
            </button>
          </div>
        )}
        <div
          style={{
            display: 'flex',
            alignItems: 'flex-end',
            gap: 8,
            background: 'var(--bg-tertiary)',
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius-control)',
            padding: '8px 10px',
            maxWidth: 760,
            margin: '0 auto'
          }}
        >
          <button
            onClick={() => void attachScreenshot()}
            title="Attach screenshot"
            style={{ color: 'var(--text-quaternary)', padding: '6px 4px' }}
          >
            <IconCamera size={17} />
          </button>
          <textarea
            ref={taRef}
            value={input}
            placeholder="Message Omi…"
            rows={1}
            onChange={(e) => {
              setInput(e.target.value)
              e.currentTarget.style.height = 'auto'
              e.currentTarget.style.height = Math.min(140, e.currentTarget.scrollHeight) + 'px'
            }}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                void send()
              }
            }}
            style={{
              flex: 1,
              background: 'transparent',
              border: 'none',
              resize: 'none',
              fontSize: 14,
              lineHeight: 1.45,
              maxHeight: 140,
              padding: '6px 2px'
            }}
          />
          {chat.streaming ? (
            <button className="btn-secondary" style={{ padding: '7px 12px', fontSize: 12 }} onClick={chat.stop}>
              Stop
            </button>
          ) : (
            <button
              className="btn-primary"
              style={{ padding: '8px 12px', borderRadius: 12 }}
              onClick={() => void send()}
              disabled={!input.trim() && !pendingShot}
              title="Send"
            >
              <IconSend size={14} />
            </button>
          )}
        </div>
      </div>
      </div>
    </div>
  )
}
