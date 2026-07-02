import { create } from 'zustand'
import type { AuthState } from '../../../shared/types'

interface AuthStore {
  state: AuthState | null
  init: () => void
  signIn: (provider: 'google' | 'apple') => void
  signOut: () => void
}

let unsubscribe: (() => void) | null = null

export const useAuth = create<AuthStore>((set) => ({
  state: null,
  init: () => {
    void window.omi.auth.getState().then((s) => set({ state: s }))
    unsubscribe?.()
    unsubscribe = window.omi.auth.onChanged((s) => set({ state: s }))
  },
  signIn: (provider) => window.omi.auth.signIn(provider),
  signOut: () => {
    window.omi.auth.signOut()
    set({ state: { signedIn: false } })
  }
}))
