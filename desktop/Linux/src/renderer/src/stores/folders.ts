import { create } from 'zustand'
import { api } from '../api/client'
import type { Folder } from '../api/types'

interface FoldersStore {
  folders: Folder[]
  activeFolderId: string | null
  load: () => Promise<void>
  create: (name: string) => Promise<void>
  remove: (id: string) => Promise<void>
  setActive: (id: string | null) => void
  move: (convId: string, folderId: string | null) => Promise<void>
}

export const useFolders = create<FoldersStore>((set, get) => ({
  folders: [],
  activeFolderId: null,
  load: async () => {
    try {
      set({ folders: await api.listFolders() })
    } catch {
      set({ folders: [] })
    }
  },
  create: async (name) => {
    const trimmed = name.trim()
    if (!trimmed) return
    try {
      const f = await api.createFolder(trimmed)
      set({ folders: [...get().folders, f] })
    } catch {
      // ignore
    }
  },
  remove: async (id) => {
    set({
      folders: get().folders.filter((f) => f.id !== id),
      activeFolderId: get().activeFolderId === id ? null : get().activeFolderId
    })
    try {
      await api.deleteFolder(id)
    } catch {
      await get().load()
    }
  },
  setActive: (id) => set({ activeFolderId: id }),
  move: async (convId, folderId) => {
    try {
      await api.moveConversationToFolder(convId, folderId)
    } catch {
      // ignore
    }
  }
}))
