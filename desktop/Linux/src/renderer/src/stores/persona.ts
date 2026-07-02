import { create } from 'zustand'
import { api } from '../api/client'
import type { Persona } from '../api/types'

// Mirrors PersonaPage.swift's state machine: load the user's persona (or null when
// none exists yet), create/enable it, edit name+description, regenerate the prompt
// from public memories, delete it, and a debounced username-availability check used
// by the create form. Everything wraps the persona REST methods on api/client.ts.

// Public profile URL on the personas web host (web/personas-open-source/src/app/u/[username]).
// Visiting it redirects to a chat with the persona, so it doubles as the
// "chat with your persona" link.
export const PERSONA_PROFILE_BASE = 'https://personas.omi.me/u/'
export const personaProfileUrl = (username: string): string => `${PERSONA_PROFILE_BASE}${username}`

// Username rules match the Mac create sheet: 3-30 chars, lowercase letters,
// numbers and underscores only.
export const sanitizeUsername = (raw: string): string =>
  raw
    .toLowerCase()
    .replace(/[^a-z0-9_]/g, '')
    .slice(0, 30)

interface PersonaStore {
  persona: Persona | null
  loading: boolean
  error: string | null

  // Create form
  creating: boolean
  // Username availability for the create form (null = unknown/not checked).
  checkingUsername: boolean
  usernameAvailable: boolean | null

  // Mutations in flight
  saving: boolean
  regenerating: boolean
  deleting: boolean

  load: () => Promise<void>
  create: (name: string, username?: string) => Promise<boolean>
  saveEdits: (name?: string, description?: string) => Promise<boolean>
  regenerate: () => Promise<void>
  remove: () => Promise<void>
  checkUsername: (username: string) => Promise<void>
  resetUsernameCheck: () => void
}

// Module-scoped token so a stale username check can't clobber a newer one's result.
let usernameCheckSeq = 0

export const usePersona = create<PersonaStore>((set, get) => ({
  persona: null,
  loading: false,
  error: null,
  creating: false,
  checkingUsername: false,
  usernameAvailable: null,
  saving: false,
  regenerating: false,
  deleting: false,

  load: async () => {
    set({ loading: true, error: null })
    try {
      const persona = await api.getPersona()
      set({ persona: persona ?? null, loading: false })
    } catch (e) {
      const msg = String(e)
      // Treat missing auth (preview / expired token) as "no persona yet" with a clean
      // empty state, the same way the other pages fall back rather than showing an error.
      if (/\b(401|403)\b/.test(msg)) {
        set({ persona: null, loading: false, error: null })
      } else {
        set({ loading: false, error: `Failed to load persona: ${msg}` })
      }
    }
  },

  create: async (name, username) => {
    const trimmed = name.trim()
    if (!trimmed) return false
    set({ creating: true, error: null })
    try {
      const persona = await api.createPersona(trimmed, username && username.length > 0 ? username : undefined)
      set({ persona, creating: false, usernameAvailable: null })
      return true
    } catch (e) {
      set({ creating: false, error: String(e) })
      return false
    }
  },

  // Only send changed fields, matching saveEdits() in PersonaPage.swift.
  saveEdits: async (name, description) => {
    const current = get().persona
    if (!current) return false
    const patch: { name?: string; description?: string } = {}
    if (name !== undefined && name !== current.name) patch.name = name
    if (description !== undefined && description !== current.description) patch.description = description
    if (Object.keys(patch).length === 0) return true
    set({ saving: true, error: null })
    try {
      const persona = await api.updatePersona(patch)
      set({ persona, saving: false })
      return true
    } catch (e) {
      set({ saving: false, error: `Failed to save: ${String(e)}` })
      return false
    }
  },

  regenerate: async () => {
    if (!get().persona) return
    set({ regenerating: true, error: null })
    try {
      await api.regeneratePersonaPrompt()
      // Reload to pick up the regenerated prompt + updated counts, like the Mac page.
      await get().load()
    } catch (e) {
      set({ error: `Failed to regenerate: ${String(e)}` })
    } finally {
      set({ regenerating: false })
    }
  },

  remove: async () => {
    set({ deleting: true, error: null })
    try {
      await api.deletePersona()
      set({ persona: null, deleting: false })
    } catch (e) {
      set({ deleting: false, error: `Failed to delete persona: ${String(e)}` })
    }
  },

  // Debounce-safe availability check: <3 chars clears the result (matches the
  // Mac sheet's guard), and only the latest in-flight request may set state.
  checkUsername: async (username) => {
    if (username.length < 3) {
      set({ usernameAvailable: null, checkingUsername: false })
      return
    }
    const seq = ++usernameCheckSeq
    set({ checkingUsername: true })
    try {
      const res = await api.checkPersonaUsername(username)
      if (seq !== usernameCheckSeq) return
      set({ usernameAvailable: res.available, checkingUsername: false })
    } catch {
      if (seq !== usernameCheckSeq) return
      set({ usernameAvailable: null, checkingUsername: false })
    }
  },

  resetUsernameCheck: () => {
    usernameCheckSeq++
    set({ usernameAvailable: null, checkingUsername: false })
  }
}))
