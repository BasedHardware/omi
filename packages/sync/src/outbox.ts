/**
 * The impure binding: journals ops in a DurableLog, drives the pure engine,
 * interprets its effects against a Transport, and maintains the dead-letter
 * list. This file is deliberately thin — logic belongs in `engine.ts` where
 * it is enumerable by tests.
 *
 * Durability protocol: an op is journaled BEFORE it is acknowledged to the
 * caller; the journal replays into engine state on open; terminal outcomes
 * append a tombstone entry, and truncation advances past ops whose tombstone
 * is present (crash between outcome and tombstone = the op retries or
 * re-deads idempotently — opId idempotency on the server absorbs the replay).
 */

import type { DeadLetter, DurableKv, DurableLog, StorageBridge } from "@omi-core/contracts";
import type { Env } from "@omi-core/kernel";
import { INITIAL_STATE, step, type Effect, type EngineState, type PendingOp } from "./engine.js";

export interface Transport {
  /** Resolve with a classification — never throw. Throwing is a transport
   * bug and is treated as `retryable { unclassified: true }`. */
  send(op: PendingOp): Promise<
    | { ok: true; serverRevision?: string }
    | { ok: false; failure: import("@omi-core/contracts").WriteFailure }
  >;
}

type JournalEntry =
  | { t: "op"; op: PendingOp }
  | { t: "tombstone"; opId: string; outcome: import("@omi-core/contracts").OperationOutcome };

const DEAD_LETTERS_KEY = "dead-letters";

export class Outbox {
  private state: EngineState = INITIAL_STATE;
  private log!: DurableLog;
  private kv!: DurableKv;
  private cancelTimer: (() => void) | null = null;

  private constructor(
    private readonly env: Env,
    private readonly transport: Transport,
  ) {}

  static async open(bridge: StorageBridge, env: Env, transport: Transport): Promise<Outbox> {
    const box = new Outbox(env, transport);
    box.log = await bridge.openLog("outbox");
    box.kv = await bridge.openKv("outbox-meta");
    const entries = await box.log.scan(0);
    const done = new Set<string>();
    const ops: PendingOp[] = [];
    for (const e of entries) {
      const entry = JSON.parse(e.payload) as JournalEntry;
      if (entry.t === "tombstone") done.add(entry.opId);
      else ops.push(entry.op);
    }
    for (const op of ops) {
      if (!done.has(op.opId)) {
        box.state = { ...box.state, pending: [...box.state.pending, op] };
      }
    }
    if (box.state.pending.length > 0) box.scheduleFlush(0);
    return box;
  }

  /** Journal first, then acknowledge. The caller's optimistic UI may render
   * immediately after this resolves — the write is durable. */
  async enqueue(op: PendingOp): Promise<void> {
    await this.log.append(JSON.stringify({ t: "op", op } satisfies JournalEntry));
    this.dispatch({ t: "enqueued", op });
  }

  async deadLetters(): Promise<DeadLetter[]> {
    const raw = await this.kv.get(DEAD_LETTERS_KEY);
    return raw ? (JSON.parse(raw) as DeadLetter[]) : [];
  }

  /** The user discarded a dead letter from the unsent-items surface. */
  async discardDeadLetter(opId: string): Promise<void> {
    const remaining = (await this.deadLetters()).filter((d) => d.opId !== opId);
    await this.kv.set(DEAD_LETTERS_KEY, JSON.stringify(remaining));
  }

  onAuthRestored(): void {
    this.dispatch({ t: "auth-restored" });
  }

  private dispatch(event: Parameters<typeof step>[1]): void {
    const { state, effects } = step(this.state, event, this.env.now());
    this.state = state;
    for (const eff of effects) void this.interpret(eff);
  }

  private async interpret(eff: Effect): Promise<void> {
    switch (eff.t) {
      case "send": {
        let result: Awaited<ReturnType<Transport["send"]>>;
        try {
          result = await this.transport.send(eff.op);
        } catch (e) {
          result = { ok: false, failure: { kind: "retryable", unclassified: true, detail: String(e) } };
        }
        if (result.ok) {
          this.dispatch(
            result.serverRevision !== undefined
              ? { t: "send-ok", opId: eff.op.opId, serverRevision: result.serverRevision }
              : { t: "send-ok", opId: eff.op.opId },
          );
        } else {
          this.dispatch({ t: "send-failed", opId: eff.op.opId, failure: result.failure });
        }
        return;
      }
      case "schedule-flush":
        this.scheduleFlush(eff.afterMs);
        return;
      case "outcome": {
        await this.log.append(
          JSON.stringify({ t: "tombstone", opId: eff.opId, outcome: eff.outcome } satisfies JournalEntry),
        );
        if (eff.outcome.state === "dead" && eff.summaryForDeadLetter) {
          const op = eff.summaryForDeadLetter;
          const letters = await this.deadLetters();
          letters.push({
            opId: op.opId,
            recordId: op.recordId,
            domain: op.domain,
            summary: op.summary,
            failure: eff.outcome.failure,
            deadAt: eff.outcome.deadAt,
          });
          await this.kv.set(DEAD_LETTERS_KEY, JSON.stringify(letters));
        }
        return;
      }
      case "telemetry":
        // Telemetry sink binding arrives with the shell integration; the
        // effect exists so tests can assert emission today.
        return;
    }
  }

  private scheduleFlush(afterMs: number): void {
    this.cancelTimer?.();
    this.cancelTimer = this.env.delay(afterMs, () => this.dispatch({ t: "flush" }));
  }
}
