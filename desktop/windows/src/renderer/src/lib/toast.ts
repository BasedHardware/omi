// Tiny pub/sub toast system. Components subscribe via onToast(); anywhere can
// dispatch via toast(). No external deps.

export type ToastTone = 'info' | 'success' | 'warn' | 'error'

export type Toast = {
  id: number
  tone: ToastTone
  title: string
  body?: string
  duration: number
}

const listeners = new Set<(toasts: Toast[]) => void>()
let queue: Toast[] = []
let nextId = 1

function emit(): void {
  listeners.forEach((cb) => cb(queue))
}

export function toast(
  title: string,
  opts: { body?: string; tone?: ToastTone; duration?: number } = {}
): number {
  const t: Toast = {
    id: nextId++,
    tone: opts.tone ?? 'info',
    title,
    body: opts.body,
    duration: opts.duration ?? (opts.tone === 'error' ? 6000 : 4000)
  }
  queue = [...queue, t]
  emit()
  if (t.duration > 0) {
    setTimeout(() => dismissToast(t.id), t.duration)
  }
  return t.id
}

export function dismissToast(id: number): void {
  const before = queue.length
  queue = queue.filter((t) => t.id !== id)
  if (queue.length !== before) emit()
}

export function onToast(cb: (toasts: Toast[]) => void): () => void {
  listeners.add(cb)
  cb(queue)
  return () => listeners.delete(cb)
}
