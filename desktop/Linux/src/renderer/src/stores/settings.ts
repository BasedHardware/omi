import { create } from 'zustand'
import type { AppSettings } from '../../../shared/types'

interface SettingsStore {
  settings: AppSettings | null
  load: () => Promise<void>
  update: (partial: Partial<AppSettings>) => Promise<void>
}

export const useSettings = create<SettingsStore>((set) => ({
  settings: null,
  load: async () => {
    set({ settings: await window.omi.settings.get() })
  },
  update: async (partial) => {
    set({ settings: await window.omi.settings.set(partial) })
  }
}))
