import React, { useEffect, useMemo, useRef, useState } from 'react'
import type { Person, ServerTranscriptSegment } from '../api/types'
import { Spinner } from './ui'
import { isDuplicatePerson } from '../lib/speakers'

// Inline SVG so this file owns its iconography (Icons.tsx is owned elsewhere).
const XMark = ({ size = 14 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
    <path d="M6 6l12 12M18 6L6 18" />
  </svg>
)

export interface SpeakerModalResult {
  isUser: boolean
  personId: string | null
  /** All segments to tag (either every same-speaker segment, or just the tapped one). */
  segments: ServerTranscriptSegment[]
}

interface SpeakerModalProps {
  /** The tapped segment whose speaker we are naming. */
  segment: ServerTranscriptSegment
  /** All segments of the conversation (used to find same-speaker segments). */
  allSegments: ServerTranscriptSegment[]
  /** Known people (backend identities). */
  people: Person[]
  /** Create a new person, returning it (and ideally adding to `people` upstream). */
  onCreatePerson: (name: string) => Promise<Person | null>
  /** Save the selection. */
  onSave: (result: SpeakerModalResult) => void
  onDismiss: () => void
}

/**
 * Modal for naming a transcript speaker, the React port of NameSpeakerSheet.swift:
 * pick You / an existing person / add a new one (with a duplicate-name guard), and
 * optionally tag every segment from this speaker.
 */
export function SpeakerModal({
  segment,
  allSegments,
  people,
  onCreatePerson,
  onSave,
  onDismiss
}: SpeakerModalProps) {
  const [selectedPersonId, setSelectedPersonId] = useState<string | null>(null)
  const [isUserSelected, setIsUserSelected] = useState(false)
  const [isAdding, setIsAdding] = useState(false)
  const [newName, setNewName] = useState('')
  const [creating, setCreating] = useState(false)
  const [saving, setSaving] = useState(false)
  const addRef = useRef<HTMLInputElement | null>(null)

  // Same-speaker segments (non-user) in this conversation.
  const sameSpeakerSegments = useMemo(
    () =>
      allSegments.filter(
        (s) => !s.is_user && (s.speaker_id ?? null) === (segment.speaker_id ?? null) && (segment.speaker_id ?? null) !== null
      ),
    [allSegments, segment.speaker_id]
  )
  const otherCount = Math.max(0, sameSpeakerSegments.length - 1)
  const [tagAll, setTagAll] = useState(true)

  const speakerNumber = (segment.speaker_id ?? 0) + 1
  const previewText = segment.text.length > 120 ? `${segment.text.slice(0, 120)}…` : segment.text

  const duplicate = isAdding && isDuplicatePerson(newName, people)
  const canCreate = newName.trim().length > 0 && !duplicate
  const canSave = isUserSelected || selectedPersonId !== null

  useEffect(() => {
    if (isAdding) addRef.current?.focus()
  }, [isAdding])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onDismiss()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onDismiss])

  const pickYou = () => {
    setIsUserSelected(true)
    setSelectedPersonId(null)
    setIsAdding(false)
    setNewName('')
  }
  const pickPerson = (id: string) => {
    setSelectedPersonId(id)
    setIsUserSelected(false)
    setIsAdding(false)
    setNewName('')
  }
  const pickAdd = () => {
    setIsAdding(true)
    setIsUserSelected(false)
    setSelectedPersonId(null)
  }

  const createAndSelect = async () => {
    const trimmed = newName.trim()
    if (!trimmed || duplicate) return
    setCreating(true)
    const person = await onCreatePerson(trimmed)
    setCreating(false)
    if (person) {
      setSelectedPersonId(person.id)
      setIsAdding(false)
      setNewName('')
    }
  }

  const doSave = () => {
    if (!canSave || saving) return
    setSaving(true)
    const targetSegments =
      tagAll && sameSpeakerSegments.length > 0 ? sameSpeakerSegments : [segment]
    onSave({
      isUser: isUserSelected,
      personId: isUserSelected ? null : selectedPersonId,
      segments: targetSegments
    })
  }

  return (
    <div
      onMouseDown={onDismiss}
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(0,0,0,0.55)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 1000
      }}
    >
      <div
        onMouseDown={(e) => e.stopPropagation()}
        className="card"
        style={{
          width: 400,
          maxHeight: '82vh',
          display: 'flex',
          flexDirection: 'column',
          background: 'var(--bg-primary)',
          overflow: 'hidden'
        }}
      >
        {/* Header */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '18px 20px 12px'
          }}
        >
          <span style={{ fontSize: 16, fontWeight: 600 }}>Name Speaker</span>
          <button
            onClick={onDismiss}
            style={{ color: 'var(--text-tertiary)', padding: 4, display: 'flex' }}
            title="Close"
          >
            <XMark size={15} />
          </button>
        </div>
        <div style={{ height: 1, background: 'var(--border)' }} />

        {/* Body */}
        <div style={{ padding: 20, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 20 }}>
          {/* Speaker info */}
          <div
            style={{
              padding: 12,
              borderRadius: 10,
              background: 'var(--bg-secondary)'
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
              <span
                style={{
                  width: 28,
                  height: 28,
                  borderRadius: '50%',
                  background: 'var(--bg-quaternary)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: 12,
                  fontWeight: 600
                }}
              >
                {speakerNumber}
              </span>
              <span style={{ fontSize: 14, fontWeight: 500 }}>Speaker {speakerNumber}</span>
            </div>
            <div style={{ fontSize: 13, color: 'var(--text-secondary)', fontStyle: 'italic', lineHeight: 1.45 }}>
              “{previewText}”
            </div>
          </div>

          {/* People selection */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            <span style={{ fontSize: 13, fontWeight: 500, color: 'var(--text-secondary)' }}>Who is this?</span>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
              <Chip label="You" selected={isUserSelected} onClick={pickYou} />
              {people.map((p) => (
                <Chip key={p.id} label={p.name} selected={selectedPersonId === p.id} onClick={() => pickPerson(p.id)} />
              ))}
              <Chip label="+ Add Person" selected={isAdding} action onClick={pickAdd} />
            </div>

            {isAdding && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                  <input
                    ref={addRef}
                    placeholder="Person name"
                    value={newName}
                    onChange={(e) => setNewName(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && canCreate) void createAndSelect()
                    }}
                    style={{
                      flex: 1,
                      background: 'var(--bg-secondary)',
                      borderColor: duplicate ? 'var(--error)' : 'var(--border)'
                    }}
                  />
                  <button
                    className="btn-primary"
                    style={{ padding: '7px 14px', fontSize: 12.5, opacity: canCreate ? 1 : 0.45 }}
                    disabled={!canCreate || creating}
                    onClick={() => void createAndSelect()}
                  >
                    {creating ? <Spinner size={13} /> : 'Add'}
                  </button>
                </div>
                {duplicate && (
                  <span style={{ fontSize: 11.5, color: 'var(--error)' }}>A person with this name already exists</span>
                )}
              </div>
            )}
          </div>

          {/* Tag-all toggle */}
          {otherCount > 0 && (
            <button
              onClick={() => setTagAll((v) => !v)}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 10,
                textAlign: 'left',
                padding: '4px 0'
              }}
            >
              <span
                style={{
                  width: 18,
                  height: 18,
                  borderRadius: 5,
                  flexShrink: 0,
                  border: tagAll ? 'none' : '1.5px solid var(--text-quaternary)',
                  background: tagAll ? 'var(--purple-primary)' : 'transparent',
                  color: '#fff',
                  fontSize: 12,
                  lineHeight: '18px',
                  textAlign: 'center'
                }}
              >
                {tagAll ? '✓' : ''}
              </span>
              <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
                Also tag {otherCount} other segment{otherCount === 1 ? '' : 's'} from this speaker
              </span>
            </button>
          )}
        </div>

        <div style={{ height: 1, background: 'var(--border)' }} />
        {/* Footer */}
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, padding: '14px 20px' }}>
          <button className="btn-secondary" onClick={onDismiss}>
            Cancel
          </button>
          <button
            className="btn-primary"
            style={{ opacity: canSave ? 1 : 0.45 }}
            disabled={!canSave || saving}
            onClick={doSave}
          >
            {saving ? <Spinner size={13} /> : 'Save'}
          </button>
        </div>
      </div>
    </div>
  )
}

function Chip({
  label,
  selected,
  action,
  onClick
}: {
  label: string
  selected: boolean
  action?: boolean
  onClick: () => void
}) {
  return (
    <button
      onClick={onClick}
      style={{
        padding: '8px 14px',
        borderRadius: 'var(--radius-chip)',
        fontSize: 13,
        fontWeight: selected ? 600 : 400,
        background: selected ? '#fff' : 'var(--bg-tertiary)',
        color: selected ? '#000' : action ? 'var(--purple-secondary)' : 'var(--text-primary)',
        border: selected
          ? '1px solid var(--border)'
          : action
            ? '1px solid rgba(139,92,246,0.3)'
            : '1px solid transparent',
        whiteSpace: 'nowrap'
      }}
    >
      {label}
    </button>
  )
}
