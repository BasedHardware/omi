import { create } from 'zustand'
import { api } from '../api/client'
import type { ServerMemory } from '../api/types'

// Filter set mirrors the Mac memories page (v0.11.438): Manual, About You, Insights, Workflow.
// Filtering is driven purely by the backend `category` field (like mobile + the Mac app),
// so a memory with no category is NOT coerced into any bucket, it only shows under "All".
export type MemoryFilter = 'all' | 'manual' | 'system' | 'interesting' | 'workflow'

// Concrete categories that can be multi-selected (everything except the "all" sentinel).
export type MemoryCategory = Exclude<MemoryFilter, 'all'>
export const MEMORY_CATEGORIES: MemoryCategory[] = ['manual', 'system', 'interesting', 'workflow']
export const MEMORY_CATEGORY_LABELS: Record<MemoryCategory, string> = {
  manual: 'Manual',
  system: 'About You',
  interesting: 'Insights',
  workflow: 'Workflow'
}

const PAGE_SIZE = 100
const UNDO_SECONDS = 4

interface MemoriesStore {
  items: ServerMemory[]
  loading: boolean
  loadingMore: boolean
  hasMore: boolean
  // Legacy single-select filter (kept for compatibility); mirrors the first
  // selected category, or 'all' when none/multiple are selected.
  filter: MemoryFilter
  // Multi-select category filter (the Mac dropdown popover model).
  selectedTags: Set<MemoryCategory>
  search: string
  error: string | null
  // Undo-delete state
  pendingDelete: ServerMemory | null
  undoRemaining: number
  // Bulk operations
  bulkBusy: boolean

  load: () => Promise<void>
  loadMore: () => Promise<void>
  setFilter: (f: MemoryFilter) => void
  toggleTag: (c: MemoryCategory) => void
  setSelectedTags: (tags: Set<MemoryCategory>) => void
  clearTags: () => void
  setSearch: (q: string) => void
  add: (content: string) => Promise<void>
  edit: (id: string, content: string) => Promise<void>
  remove: (id: string) => Promise<void>
  undoDelete: () => void
  confirmDelete: () => void
  makeAllPublic: () => Promise<void>
  makeAllPrivate: () => Promise<void>
  deleteAll: () => Promise<void>
  filtered: () => ServerMemory[]
  tagCount: (c: MemoryCategory) => number
  totalCount: () => number
}

// Module-scoped timer so the countdown ticks without living in the store shape.
let undoTimer: ReturnType<typeof setInterval> | null = null

export const useMemories = create<MemoriesStore>((set, get) => {
  // Perform the real backend delete (after the undo window or on confirm).
  const performDelete = async (memory: ServerMemory) => {
    try {
      await api.deleteMemory(memory.id)
    } catch {
      // Restore on failure (matches the Mac app's optimistic-rollback behavior).
      set((s) => {
        if (s.items.some((m) => m.id === memory.id)) return s
        const items = [...s.items, memory].sort((a, b) => (b.created_at ?? '').localeCompare(a.created_at ?? ''))
        return { items }
      })
    }
  }

  const clearUndoTimer = () => {
    if (undoTimer) {
      clearInterval(undoTimer)
      undoTimer = null
    }
  }

  return {
    items: [],
    loading: false,
    loadingMore: false,
    hasMore: false,
    filter: 'all',
    selectedTags: new Set<MemoryCategory>(),
    search: '',
    error: null,
    pendingDelete: null,
    undoRemaining: 0,
    bulkBusy: false,

    load: async () => {
      set({ loading: true, error: null })
      try {
        const items = await api.listMemories(PAGE_SIZE, 0)
        set({ items, loading: false, hasMore: items.length >= PAGE_SIZE })
      } catch (e) {
        set({ loading: false, error: String(e) })
      }
    },

    loadMore: async () => {
      const { loading, loadingMore, hasMore, items } = get()
      if (loading || loadingMore || !hasMore) return
      set({ loadingMore: true })
      try {
        const next = await api.listMemories(PAGE_SIZE, items.length)
        // De-dupe by id in case the window shifted between requests.
        const seen = new Set(items.map((m) => m.id))
        const merged = [...items, ...next.filter((m) => !seen.has(m.id))]
        set({ items: merged, loadingMore: false, hasMore: next.length >= PAGE_SIZE })
      } catch {
        set({ loadingMore: false })
      }
    },

    setFilter: (f) =>
      set(
        f === 'all'
          ? { filter: 'all', selectedTags: new Set<MemoryCategory>() }
          : { filter: f, selectedTags: new Set<MemoryCategory>([f]) }
      ),

    toggleTag: (c) =>
      set((s) => {
        const next = new Set(s.selectedTags)
        if (next.has(c)) next.delete(c)
        else next.add(c)
        return { selectedTags: next, filter: next.size === 1 ? ([...next][0] as MemoryFilter) : 'all' }
      }),

    setSelectedTags: (tags) =>
      set({ selectedTags: new Set(tags), filter: tags.size === 1 ? ([...tags][0] as MemoryFilter) : 'all' }),

    clearTags: () => set({ selectedTags: new Set<MemoryCategory>(), filter: 'all' }),

    setSearch: (q) => set({ search: q }),

    add: async (content) => {
      const trimmed = content.trim()
      if (!trimmed) return
      await api.createMemory(trimmed)
      await get().load()
    },

    edit: async (id, content) => {
      const prev = get().items
      set({ items: prev.map((m) => (m.id === id ? { ...m, content } : m)) })
      try {
        await api.editMemory(id, content)
      } catch {
        set({ items: prev }) // roll back on failure, matching remove()
      }
    },

    // Optimistic delete with a 4s undo window. The memory leaves the list
    // immediately; the real backend delete only fires when the countdown
    // reaches 0 (confirmDelete) unless undoDelete() restores it first.
    remove: async (id) => {
      // If a different delete is already pending, commit it first.
      const existing = get().pendingDelete
      if (existing && existing.id !== id) {
        clearUndoTimer()
        void performDelete(existing)
      }
      const memory = get().items.find((m) => m.id === id)
      if (!memory) return

      set((s) => ({
        items: s.items.filter((m) => m.id !== id),
        pendingDelete: memory,
        undoRemaining: UNDO_SECONDS
      }))

      clearUndoTimer()
      undoTimer = setInterval(() => {
        const remaining = get().undoRemaining - 0.1
        if (remaining <= 0) {
          get().confirmDelete()
        } else {
          set({ undoRemaining: Math.max(0, remaining) })
        }
      }, 100)
    },

    undoDelete: () => {
      const memory = get().pendingDelete
      if (!memory) return
      clearUndoTimer()
      set((s) => ({
        items: [...s.items, memory].sort((a, b) => (b.created_at ?? '').localeCompare(a.created_at ?? '')),
        pendingDelete: null,
        undoRemaining: 0
      }))
    },

    confirmDelete: () => {
      const memory = get().pendingDelete
      clearUndoTimer()
      set({ pendingDelete: null, undoRemaining: 0 })
      if (memory) void performDelete(memory)
    },

    makeAllPublic: async () => {
      set({ bulkBusy: true })
      try {
        await api.updateAllMemoriesVisibility('public')
        set((s) => ({ items: s.items.map((m) => ({ ...m, visibility: 'public' })) }))
      } catch {
        await get().load()
      } finally {
        set({ bulkBusy: false })
      }
    },

    makeAllPrivate: async () => {
      set({ bulkBusy: true })
      try {
        await api.updateAllMemoriesVisibility('private')
        set((s) => ({ items: s.items.map((m) => ({ ...m, visibility: 'private' })) }))
      } catch {
        await get().load()
      } finally {
        set({ bulkBusy: false })
      }
    },

    deleteAll: async () => {
      set({ bulkBusy: true })
      // Cancel any pending single delete first.
      clearUndoTimer()
      set({ pendingDelete: null, undoRemaining: 0 })
      try {
        await api.deleteAllMemories()
        set({ items: [], hasMore: false })
      } catch {
        await get().load()
      } finally {
        set({ bulkBusy: false })
      }
    },

    filtered: () => {
      const { items, selectedTags, filter, search } = get()
      let result = items

      // Category filter: prefer the multi-select set; fall back to the legacy
      // single `filter`. A memory matches only by its exact backend category,
      // uncategorized memories never match a specific category (no 'system' coercion).
      if (selectedTags.size > 0) {
        result = result.filter((m) => !!m.category && selectedTags.has(m.category as MemoryCategory))
      } else if (filter !== 'all') {
        result = result.filter((m) => m.category === filter)
      }

      const q = search.trim().toLowerCase()
      if (q) {
        result = result.filter(
          (m) => m.content.toLowerCase().includes(q) || (m.headline ?? '').toLowerCase().includes(q)
        )
      }
      return result
    },

    tagCount: (c) => get().items.filter((m) => m.category === c).length,

    totalCount: () => get().items.length
  }
})
