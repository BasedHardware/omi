// Tiny generic pub/sub primitive shared by lib/usageLimit.ts and
// lib/settingsNav.ts: holds a current value, broadcasts it to every subscriber
// on set(), and replays the current value to a NEW subscriber immediately (so
// a set-before-subscribe race — e.g. navigate-then-mount — still delivers).
// No external deps, no React coupling — same shape as the existing lib/toast.ts
// pub/sub, just generalized over the value type. lib/toast.ts and
// lib/preferences.ts are pre-existing, broadly-used modules and are
// intentionally left as-is here (not rebuilt onto this primitive).

export type Signal<T> = {
  get(): T
  set(value: T): void
  /** Subscribe and immediately receive the current value; returns an unsubscribe fn. */
  subscribe(cb: (value: T) => void): () => void
}

export function createSignal<T>(initial: T): Signal<T> {
  let current = initial
  const listeners = new Set<(value: T) => void>()

  return {
    get: () => current,
    set(value) {
      current = value
      listeners.forEach((cb) => cb(current))
    },
    subscribe(cb) {
      listeners.add(cb)
      cb(current)
      return () => listeners.delete(cb)
    }
  }
}
