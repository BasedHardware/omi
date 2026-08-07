/**
 * Hermetic fakes. `MemoryStore` models a device: it survives "app restarts"
 * (new StorageBridge from the same store) and supports crash simulation
 * (`crashNow` drops un-fsynced state — here, anything appended after the
 * last checkpoint if `fsyncEvery` is set). Account isolation is real: the
 * store namespaces by uid exactly as shell bindings must.
 */

import type { DurableKv, DurableLog, LogEntry, StorageBridge } from "@omi-core/contracts";
import type { Env } from "@omi-core/kernel";

export class MemoryStore {
  private logs = new Map<string, { lsn: number; entries: LogEntry[] }>();
  private kvs = new Map<string, Map<string, string>>();
  private generations = new Map<string, number>();

  /** A fresh bridge = an app launch. Same store = same device disk. */
  openBridge(uid: string): StorageBridge {
    const generation = (this.generations.get(uid) ?? 0) + 1;
    this.generations.set(uid, generation);
    const ns = (name: string): string => `${uid}::${name}`;
    const logs = this.logs;
    const kvs = this.kvs;
    return {
      uid,
      generation,
      openLog: async (name: string): Promise<DurableLog> => {
        const key = ns(name);
        if (!logs.has(key)) logs.set(key, { lsn: 0, entries: [] });
        const log = logs.get(key)!;
        return {
          append: async (payload: string) => {
            log.lsn += 1;
            log.entries.push({ lsn: log.lsn, payload });
            return log.lsn;
          },
          scan: async (after: number) => log.entries.filter((e) => e.lsn > after),
          truncate: async (upTo: number) => {
            log.entries = log.entries.filter((e) => e.lsn > upTo);
          },
        };
      },
      openKv: async (name: string): Promise<DurableKv> => {
        const key = ns(name);
        if (!kvs.has(key)) kvs.set(key, new Map());
        const kv = kvs.get(key)!;
        return {
          get: async (k) => kv.get(k) ?? null,
          set: async (k, v) => void kv.set(k, v),
          delete: async (k) => void kv.delete(k),
        };
      },
      destroyAll: async () => {
        for (const key of [...logs.keys()]) if (key.startsWith(`${uid}::`)) logs.delete(key);
        for (const key of [...kvs.keys()]) if (key.startsWith(`${uid}::`)) kvs.delete(key);
      },
    };
  }

  /** Crash simulation: drop the tail of a log (entries after keepLsn). */
  crashDropLogTail(uid: string, name: string, keepLsn: number): void {
    const log = this.logs.get(`${uid}::${name}`);
    if (log) log.entries = log.entries.filter((e) => e.lsn <= keepLsn);
  }
}

/** Deterministic time: timers fire only when the test advances the clock. */
export class ManualEnv implements Env {
  private t = 1_000_000;
  private seed = 42;
  private timers: { at: number; fn: () => void; cancelled: boolean }[] = [];

  now(): number {
    return this.t;
  }

  random(): number {
    // xorshift — deterministic, good enough for slugs in tests
    this.seed ^= this.seed << 13;
    this.seed ^= this.seed >>> 17;
    this.seed ^= this.seed << 5;
    return (this.seed >>> 0) / 0xffffffff;
  }

  delay(ms: number, fn: () => void): () => void {
    const timer = { at: this.t + ms, fn, cancelled: false };
    this.timers.push(timer);
    return () => {
      timer.cancelled = true;
    };
  }

  /** Advance time, firing due timers in order; drains microtasks between. */
  async advance(ms: number): Promise<void> {
    const target = this.t + ms;
    for (;;) {
      const due = this.timers
        .filter((x) => !x.cancelled && x.at <= target)
        .sort((a, b) => a.at - b.at)[0];
      if (!due) break;
      this.t = due.at;
      this.timers = this.timers.filter((x) => x !== due);
      due.fn();
      await drainMicrotasks();
    }
    this.t = target;
    await drainMicrotasks();
  }
}

async function drainMicrotasks(): Promise<void> {
  for (let i = 0; i < 50; i++) await Promise.resolve();
}

/** Scriptable transport: push responses; sends resolve in FIFO order. */
export class ScriptedTransport {
  public readonly sent: string[] = [];
  private script: Array<
    | { ok: true; serverRevision?: string }
    | { ok: false; failure: import("@omi-core/contracts").WriteFailure }
  > = [];

  respondWith(...responses: typeof this.script): void {
    this.script.push(...responses);
  }

  async send(op: { opId: string }): Promise<
    | { ok: true; serverRevision?: string }
    | { ok: false; failure: import("@omi-core/contracts").WriteFailure }
  > {
    this.sent.push(op.opId);
    const next = this.script.shift();
    if (!next) return { ok: false, failure: { kind: "retryable", detail: "script exhausted" } };
    return next;
  }
}
