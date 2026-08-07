/**
 * Injected environment — the hermeticity seam. Core code NEVER reads the
 * wall clock, Math.random, or timers directly; it receives an Env. Shells
 * bind the real one; testkit binds a manual one. This is what makes every
 * test deterministic and every replay reproducible.
 */
export interface Env {
  now(): number;
  random(): number;
  /** Schedule a callback; returns a cancel function. */
  delay(ms: number, fn: () => void): () => void;
}

// The base tsconfig deliberately loads no DOM/Node libs — core code is
// host-neutral. Timers exist on every host we ship to; declare them narrowly
// here rather than widening the lib for the whole workspace.
declare function setTimeout(fn: () => void, ms: number): unknown;
declare function clearTimeout(handle: unknown): void;

export function realEnv(): Env {
  return {
    now: () => Date.now(),
    random: Math.random,
    delay: (ms, fn) => {
      const t = setTimeout(fn, ms);
      return () => clearTimeout(t);
    },
  };
}
