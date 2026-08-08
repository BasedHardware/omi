import type { FallbackSink } from "@omi-core/contracts";

/**
 * Injected environment — the hermeticity seam. Core code NEVER reads the
 * wall clock, Math.random, or timers directly; it receives an Env. Shells
 * bind the real one; testkit binds a manual one. This is what makes every
 * test deterministic and every replay reproducible.
 *
 * `fallbackSink` is here for the same reason: COORD-degradation-is-
 * unobservable found that `FallbackSink` existed only as a parameter type —
 * nothing bound it, so `degrade()`'s telemetry went into `case "telemetry":
 * return;`. Requiring it on `Env` means the sink travels wherever the clock
 * does, a test's sink is torn down structurally with its `ManualEnv` (no
 * cleanup hook to forget), and `realEnv()` cannot be called without a caller
 * consciously choosing an adapter — there is no implicit unbound default.
 */
export interface Env {
  now(): number;
  random(): number;
  /** Schedule a callback; returns a cancel function. */
  delay(ms: number, fn: () => void): () => void;
  readonly fallbackSink: FallbackSink;
}

// The base tsconfig deliberately loads no DOM/Node libs — core code is
// host-neutral. Timers exist on every host we ship to; declare them narrowly
// here rather than widening the lib for the whole workspace.
declare function setTimeout(fn: () => void, ms: number): unknown;
declare function clearTimeout(handle: unknown): void;

/**
 * `fallbackSink` is required, not defaulted. Kernel has no I/O of its own
 * (it doesn't know if it's hosting a dev/QA build that wants the on-disk
 * adapter from `@omi-core/sync`, or a one-off script that wants an
 * in-memory one) — so the caller composing a real shell picks the adapter
 * per COORD-degradation-is-unobservable's table and passes it in.
 */
export function realEnv(fallbackSink: FallbackSink): Env {
  return {
    now: () => Date.now(),
    random: Math.random,
    delay: (ms, fn) => {
      const t = setTimeout(fn, ms);
      return () => clearTimeout(t);
    },
    fallbackSink,
  };
}
