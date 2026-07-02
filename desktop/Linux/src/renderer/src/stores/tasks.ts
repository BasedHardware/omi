import { create } from 'zustand'
import { api } from '../api/client'
import type { StagedTask, TaskActionItem } from '../api/types'

interface TasksStore {
  incomplete: TaskActionItem[]
  completed: TaskActionItem[]
  staged: StagedTask[]
  loading: boolean
  error: string | null
  load: () => Promise<void>
  add: (description: string, dueAt?: string, priority?: string) => Promise<void>
  toggle: (task: TaskActionItem) => Promise<void>
  remove: (id: string) => Promise<void>
  update: (id: string, patch: Record<string, unknown>) => Promise<void>
  setPriority: (id: string, priority: string) => Promise<void>
  setIndent: (id: string, indent: number) => Promise<void>
  reorder: (orderedIds: string[]) => Promise<void>
  acceptStaged: (id: string) => Promise<void>
  dismissStaged: (id: string) => Promise<void>
}

function asItems<T>(res: { items: T[] } | T[]): T[] {
  return Array.isArray(res) ? res : (res.items ?? [])
}

export const useTasks = create<TasksStore>((set, get) => ({
  incomplete: [],
  completed: [],
  staged: [],
  loading: false,
  error: null,
  load: async () => {
    set({ loading: true, error: null })
    try {
      const [inc, comp, staged] = await Promise.all([
        api.listActionItems(false, 200),
        api.listActionItems(true, 50),
        api.listStagedTasks(20).catch(() => [] as StagedTask[])
      ])
      const incItems = asItems<TaskActionItem>(inc)
      incItems.sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0))
      set({ incomplete: incItems, completed: asItems<TaskActionItem>(comp), staged: asItems<StagedTask>(staged), loading: false })
    } catch (e) {
      set({ loading: false, error: String(e) })
    }
  },
  setIndent: async (id, indent) => {
    const clamped = Math.max(0, Math.min(3, indent))
    set({ incomplete: get().incomplete.map((t) => (t.id === id ? { ...t, indent_level: clamped } : t)) })
    try {
      await api.batchUpdateTaskOrder([{ id, indent_level: clamped }])
    } catch {
      await get().load()
    }
  },
  reorder: async (orderedIds) => {
    const byId = new Map(get().incomplete.map((t) => [t.id, t]))
    const reordered = orderedIds.map((id, i) => ({ ...byId.get(id)!, sort_order: (i + 1) * 1000 })).filter(Boolean)
    set({ incomplete: reordered })
    try {
      await api.batchUpdateTaskOrder(orderedIds.map((id, i) => ({ id, sort_order: (i + 1) * 1000 })))
    } catch {
      await get().load()
    }
  },
  acceptStaged: async (id) => {
    set({ staged: get().staged.filter((s) => s.id !== id) })
    try {
      const res = await api.promoteStagedTask()
      if (res.promoted_task) set({ incomplete: [res.promoted_task, ...get().incomplete] })
      await get().load()
    } catch {
      await get().load()
    }
  },
  dismissStaged: async (id) => {
    set({ staged: get().staged.filter((s) => s.id !== id) })
    try {
      await api.deleteStagedTask(id)
    } catch {
      // ignore
    }
  },
  add: async (description, dueAt, priority) => {
    const trimmed = description.trim()
    if (!trimmed) return
    const created = await api.createActionItem(trimmed, dueAt)
    // createActionItem doesn't carry priority; apply it as an additive follow-up patch.
    if (priority) {
      created.priority = priority
      api.updateActionItem(created.id, { priority }).catch(() => {})
    }
    set({ incomplete: [created, ...get().incomplete] })
  },
  setPriority: async (id, priority) => {
    set({
      incomplete: get().incomplete.map((t) => (t.id === id ? { ...t, priority } : t)),
      completed: get().completed.map((t) => (t.id === id ? { ...t, priority } : t))
    })
    try {
      await api.updateActionItem(id, { priority })
    } catch {
      await get().load()
    }
  },
  toggle: async (task) => {
    const completed = !task.completed
    if (completed) {
      set({
        incomplete: get().incomplete.filter((t) => t.id !== task.id),
        completed: [{ ...task, completed: true }, ...get().completed]
      })
    } else {
      set({
        completed: get().completed.filter((t) => t.id !== task.id),
        incomplete: [{ ...task, completed: false }, ...get().incomplete]
      })
    }
    try {
      await api.updateActionItem(task.id, { completed })
    } catch {
      await get().load()
    }
  },
  remove: async (id) => {
    set({
      incomplete: get().incomplete.filter((t) => t.id !== id),
      completed: get().completed.filter((t) => t.id !== id)
    })
    try {
      await api.deleteActionItem(id)
    } catch {
      await get().load()
    }
  },
  update: async (id, patch) => {
    await api.updateActionItem(id, patch)
    await get().load()
  }
}))
