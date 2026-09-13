import { useEffect, useRef, useState } from 'react'
import { Loader2, Plus, RefreshCw, X } from 'lucide-react'
import {
  VOCABULARY_LIMIT,
  VOCABULARY_TERM_MAX_CHARS,
  addVocabularyTerms,
  fetchTranscriptionVocabulary,
  removeVocabularyTerm,
  saveTranscriptionVocabulary
} from '../../../lib/transcriptionVocabulary'
import { toast } from '../../../lib/toast'

// Mac's "Custom Vocabulary" card body (SettingsContentView+Transcription.swift):
// removable term chips in a flow layout, a single-line "Add a word..." field that
// submits on Enter or the + button, and a "N terms" counter. Windows chrome (white
// /neutral chips, no purple). Every edit writes the whole list through
// saveTranscriptionVocabulary optimistically and reverts on rejection, the same
// way the Conversations list handles star/rename.

type Loaded =
  | { nonce: number; terms: string[]; error: null }
  | { nonce: number; terms: null; error: string }

export function VocabularyEditor(): React.JSX.Element {
  // The fetch result is stored with the reload nonce it answered, so "loading"
  // is simply "no answer for the current nonce yet" — a retry bumps the nonce
  // and the effect only ever STARTS the request (state lands in its callbacks).
  const [reloadNonce, setReloadNonce] = useState(0)
  const [loaded, setLoaded] = useState<Loaded | null>(null)
  const [draft, setDraft] = useState('')
  const [saving, setSaving] = useState(false)
  const inputRef = useRef<HTMLInputElement | null>(null)

  useEffect(() => {
    let cancelled = false
    fetchTranscriptionVocabulary()
      .then((list) => {
        if (!cancelled) setLoaded({ nonce: reloadNonce, terms: list, error: null })
      })
      .catch((e: unknown) => {
        if (!cancelled)
          setLoaded({
            nonce: reloadNonce,
            terms: null,
            error: (e as Error).message || 'Could not load vocabulary'
          })
      })
    return () => {
      cancelled = true
    }
  }, [reloadNonce])

  const current = loaded && loaded.nonce === reloadNonce ? loaded : null
  const terms = current?.terms ?? null
  const loadError = current?.error ?? null
  const setTerms = (next: string[]): void =>
    setLoaded({ nonce: reloadNonce, terms: next, error: null })

  const commit = async (next: string[], prev: string[]): Promise<void> => {
    setTerms(next) // optimistic
    setSaving(true)
    try {
      await saveTranscriptionVocabulary(next)
    } catch (e) {
      setTerms(prev)
      toast('Could not save vocabulary', { tone: 'error', body: (e as Error).message })
    } finally {
      setSaving(false)
    }
  }

  const onAdd = (): void => {
    if (!terms || saving) return
    const result = addVocabularyTerms(terms, draft)
    if (result.overflow.length > 0) {
      toast(`Vocabulary is limited to ${VOCABULARY_LIMIT} terms`, {
        tone: 'warn',
        body: 'Remove a term before adding another.'
      })
    }
    if (result.tooLong.length > 0) {
      toast(`Terms must be ${VOCABULARY_TERM_MAX_CHARS} characters or fewer`, {
        tone: 'warn',
        body: 'Shorten the term and try again.'
      })
    }
    if (result.added.length === 0) {
      if (result.tooLong.length === 0) setDraft('')
      inputRef.current?.focus()
      return
    }
    setDraft('')
    void commit(result.terms, terms)
    inputRef.current?.focus()
  }

  const onRemove = (term: string): void => {
    if (!terms) return
    void commit(removeVocabularyTerm(terms, term), terms)
  }

  if (loadError) {
    return (
      <div className="flex items-center justify-between gap-3 rounded-xl border border-white/10 bg-white/[0.02] px-4 py-3">
        <p className="text-xs text-text-tertiary">Couldn’t load your vocabulary.</p>
        <button
          type="button"
          onClick={() => setReloadNonce((n) => n + 1)}
          className="btn-ghost px-2.5 py-1 text-xs"
        >
          <RefreshCw className="h-3.5 w-3.5" />
          Try again
        </button>
      </div>
    )
  }

  if (terms === null) {
    return (
      <div className="flex items-center gap-2 text-xs text-text-tertiary" role="status">
        <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />
        Loading vocabulary…
      </div>
    )
  }

  const full = terms.length >= VOCABULARY_LIMIT
  const canAdd = draft.trim().length > 0 && !full && !saving

  return (
    <div className="space-y-3">
      {terms.length > 0 && (
        <ul className="flex flex-wrap gap-1.5" aria-label="Custom vocabulary terms">
          {terms.map((term) => (
            <li
              key={term}
              className="flex items-center gap-1 rounded-full border border-white/10 bg-white/[0.06] py-1 pl-3 pr-1.5 text-xs text-text-secondary"
            >
              {term}
              <button
                type="button"
                onClick={() => onRemove(term)}
                disabled={saving}
                aria-label={`Remove ${term}`}
                title={`Remove ${term}`}
                className="rounded-full p-0.5 text-text-quaternary transition-colors hover:bg-white/10 hover:text-white disabled:opacity-40"
              >
                <X className="h-3 w-3" />
              </button>
            </li>
          ))}
        </ul>
      )}

      <form
        className="flex items-center gap-2"
        onSubmit={(e) => {
          e.preventDefault()
          onAdd()
        }}
      >
        <input
          ref={inputRef}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          disabled={full}
          placeholder={
            full ? `Limit of ${VOCABULARY_LIMIT} terms reached` : 'Add a word or phrase…'
          }
          aria-label="Add a vocabulary term"
          className="flex-1 rounded-xl border border-white/15 bg-white/[0.04] px-3 py-2 text-sm text-white placeholder:text-white/40 focus:border-white/40 focus:outline-none disabled:opacity-50"
        />
        <button
          type="submit"
          disabled={!canAdd}
          aria-label="Add term"
          title="Add term"
          className="flex h-9 w-9 items-center justify-center rounded-xl border border-white/15 bg-white/[0.04] text-white transition-colors hover:bg-white/10 disabled:opacity-40"
        >
          {saving ? (
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
          ) : (
            <Plus className="h-4 w-4" />
          )}
        </button>
      </form>

      <p className="text-[11px] text-text-quaternary">
        Press Enter or click + to add · separate several with commas · click × to remove ·{' '}
        <span data-testid="vocabulary-count">
          {terms.length}/{VOCABULARY_LIMIT}
        </span>{' '}
        terms
      </p>
    </div>
  )
}
