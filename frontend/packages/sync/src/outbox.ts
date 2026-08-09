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

/**
 * The values a write-path op must carry from the moment it is JOURNALED —
 * COORD-write-path-rulings B1 and the account-epoch fence's straggler stamp.
 *
 * WHY THIS IS A PORT AND WHY THE OUTBOX CONSULTS IT.
 *
 * B1 says the write id is *minted and journaled at enqueue*. Left as a
 * convention, that is one `{ ...op, writeId: mint() }` a future domain store
 * forgets, and the failure is silent: the op sends, the server registry sees a
 * new key on every replay, and a crash-replayed op applies twice. Making the
 * stamp the outbox's job at the one place that appends to the journal is what
 * makes forgetting unrepresentable rather than merely discouraged.
 *
 * It is OPTIONAL because the legacy wire has no registry and no epoch: a store
 * that passes no source journals exactly what it journaled before, byte for
 * byte. Nothing about legacy behaviour changes.
 *
 * Both members may return `null`, which means "I cannot stamp this op". That
 * is not a value the outbox may paper over — see `enqueue`.
 */
export interface WriteStampSource {
  /** B1: 64 lowercase hex from independent entropy. `null` = entropy unusable. */
  mintWriteId(): string | null;
  /** The account epoch the op is being created under. `null` = not known yet. */
  currentAccountEpoch(): number | null;
}

/**
 * Thrown by `enqueue` when a configured `WriteStampSource` cannot stamp the op.
 *
 * The op is NOT journaled: a write we could never send must not be
 * acknowledged to the caller, because the caller renders optimistically the
 * moment `enqueue` resolves and the user would see an edit that can only ever
 * become a dead letter. Failing the call surfaces through the same operation-
 * error path a failed journal append already takes, so no new thing is said to
 * a user.
 */
export class WriteStampUnavailableError extends Error {
  constructor(readonly missing: "write-id" | "account-epoch") {
    super(`outbox: cannot journal a write op without a ${missing}`);
    this.name = "WriteStampUnavailableError";
  }
}

/**
 * Thrown by `enqueue` when a caller hands it an op that is ALREADY stamped.
 *
 * B1's property is that a `write_id` is minted from independent entropy by the
 * outbox. Until this existed, that property was enforced by the ABSENCE OF A
 * CALLER rather than by the code: `stamp()` read `op.writeId ?? mint()`, so a
 * caller-supplied id was journaled verbatim and mint was never reached. The
 * comment defending it said "there is no such caller today" — a fact about the
 * tree, not a property of the module, and a fact about the tree stops being
 * true the moment somebody adds a caller.
 *
 * The reachable harm, measured rather than imagined: a malformed id is caught
 * downstream (`buildWriteOpEnvelope` refuses to build an envelope on one), but
 * a WELL-FORMED DUPLICATE passes every check and the server answers
 * `write_id_reuse` — a permanent dead letter, which is a lost edit the user is
 * told about. The same hole existed on the legacy path, where a planted stamp
 * is journaled by an outbox with no stamp source and would be honoured later by
 * a platform transport draining that same journal.
 *
 * So the stamps are the outbox's to mint, always, and an op that arrives
 * carrying them is refused rather than silently overwritten. Refused, because a
 * caller passing a `writeId` has a mistaken model of who owns idempotency, and
 * quietly discarding their value would hide that instead of correcting it.
 *
 * A REPLAY IS NOT A CALLER. Journaled ops replay through `Outbox.open`, which
 * pushes them into engine state directly and never calls `enqueue`, so a
 * replayed op keeps its journaled stamps and this never fires for it. That is
 * the case the `??` clause was written for, and it was never reaching `enqueue`
 * to begin with.
 */
export class CallerSuppliedWriteStampError extends Error {
  constructor(readonly field: "writeId" | "accountEpoch") {
    super(
      `outbox: ${field} is minted by the outbox at enqueue and may not be supplied by a caller ` +
        `(COORD-write-path-rulings B1)`,
    );
    this.name = "CallerSuppliedWriteStampError";
  }
}

type JournalEntry =
  | { t: "op"; op: PendingOp }
  | { t: "tombstone"; opId: string; outcome: import("@omi-core/contracts").OperationOutcome };

const DEAD_LETTERS_KEY = "dead-letters";

export type QueuePhase = "idle" | "queued" | "sending" | "retrying" | "needs-auth";

export interface QueueStatus {
  readonly phase: QueuePhase;
  readonly pendingCount: number;
}

export class Outbox {
  private state: EngineState = INITIAL_STATE;
  /** Fired after every state transition and terminal outcome — stores use it
   * to re-render. Not a public event bus; one owner (the store) subscribes. */
  public onChange: (() => void) | null = null;
  /** Fired once per terminal outcome, with the op that reached it. Stores use
   * confirmed creates/patches/deletes to fold optimistic state into the
   * durable projection without waiting for a refresh. */
  public onOutcome:
    | ((op: PendingOp, outcome: import("@omi-core/contracts").OperationOutcome) => void | Promise<void>)
    | null = null;
  private log!: DurableLog;
  private kv!: DurableKv;
  private cancelTimer: (() => void) | null = null;

  private constructor(
    private readonly env: Env,
    private readonly transport: Transport,
    private readonly stamps: WriteStampSource | null,
  ) {}

  /**
   * `domain` namespaces the journal and dead-letter store. It is REQUIRED, not
   * defaulted: a shell hosting two domains opens two Outboxes over one bridge,
   * and a shared namespace makes them read each other's journals and replay
   * each other's ops through the wrong transport — a memory write dispatched
   * at the tasks adapter, and vice versa. One durable log per domain is what
   * makes that unrepresentable; the required parameter is what stops the next
   * domain from forgetting.
   *
   * `stamps` is the write-path stamp source (B1). Omit it for the legacy wire,
   * which has neither a write registry nor an account epoch.
   */
  static async open(
    bridge: StorageBridge,
    env: Env,
    transport: Transport,
    domain: string,
    stamps: WriteStampSource | null = null,
  ): Promise<Outbox> {
    const box = new Outbox(env, transport, stamps);
    box.log = await bridge.openLog(`outbox-${domain}`);
    box.kv = await bridge.openKv(`outbox-meta-${domain}`);
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
   * immediately after this resolves — the write is durable.
   *
   * B1: when a `WriteStampSource` is configured, the write id and the account
   * epoch are stamped HERE — in the same statement that appends to the journal
   * — so a stamped op and a journaled op are the same object by construction.
   * An op that arrives already stamped is REFUSED, on every path, stamped or
   * legacy: see `CallerSuppliedWriteStampError` for why that is a property of
   * the code rather than of who happens to call it today.
   */
  async enqueue(op: PendingOp): Promise<void> {
    const stamped = this.stamp(op);
    await this.log.append(JSON.stringify({ t: "op", op: stamped } satisfies JournalEntry));
    this.dispatch({ t: "enqueued", op: stamped });
  }

  private stamp(op: PendingOp): PendingOp {
    // Checked BEFORE the stamp source, so the refusal is identical whether or
    // not this outbox mints. A legacy outbox journals whatever it is handed,
    // and a journal is not private to the transport that wrote it — the same
    // durable log is what a platform transport would drain after a generation
    // flip, at which point a planted id becomes a real `write_id` on a real
    // wire. "Legacy behaves byte-identically" is true of ops that arrive
    // unstamped, which after this is all of them.
    if (op.writeId !== undefined) throw new CallerSuppliedWriteStampError("writeId");
    if (op.accountEpoch !== undefined) throw new CallerSuppliedWriteStampError("accountEpoch");
    if (this.stamps === null) return op;
    const writeId = this.stamps.mintWriteId();
    if (writeId === null) throw new WriteStampUnavailableError("write-id");
    const accountEpoch = this.stamps.currentAccountEpoch();
    if (accountEpoch === null) throw new WriteStampUnavailableError("account-epoch");
    return { ...op, writeId, accountEpoch };
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

  /** Snapshot of ops not yet at a terminal outcome, in send order. */
  pendingOps(): readonly PendingOp[] {
    return this.state.pending;
  }

  /** Public queue state for surfaces; derived from the engine, never UI flags. */
  queueStatus(): QueueStatus {
    const pendingCount = this.state.pending.length;
    if (pendingCount === 0) return { phase: "idle", pendingCount };
    if (this.state.pausedForAuth) return { phase: "needs-auth", pendingCount };
    if (this.state.inFlight !== null) return { phase: "sending", pendingCount };
    if (this.state.backoffStep > 0) return { phase: "retrying", pendingCount };
    return { phase: "queued", pendingCount };
  }

  private dispatch(event: Parameters<typeof step>[1]): void {
    const { state, effects } = step(this.state, event, this.env.now());
    this.state = state;
    for (const eff of effects) void this.interpret(eff);
    this.onChange?.();
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
        await this.onOutcome?.(eff.op, eff.outcome);
        if (eff.outcome.state === "dead") {
          const op = eff.op;
          const letters = await this.deadLetters();
          letters.push({
            opId: op.opId,
            recordId: op.recordId,
            domain: op.domain,
            summary: op.summary,
            // The full serialized domain op, not just its summary — the
            // export-then-exclude disposition (COORD-cross-generation-writes)
            // requires reconstructing the user's edit by hand, and a summary
            // cannot do that.
            payload: op.payload,
            failure: eff.outcome.failure,
            deadAt: eff.outcome.deadAt,
          });
          await this.kv.set(DEAD_LETTERS_KEY, JSON.stringify(letters));
        }
        return;
      }
      case "telemetry": {
        // COORD-degradation-is-unobservable: this used to be `return;` —
        // sound telemetry emitted into a sink nothing bound. `Env.fallbackSink`
        // is that binding now. `from`/`to` are derived mechanically (not a
        // hand-maintained case per path) because the ruling is explicit:
        // do not design a failure taxonomy up front, just bind the channel.
        this.env.fallbackSink.record({
          path: eff.path,
          from: "outbox",
          to: eff.path.split(".").at(-1) ?? eff.path,
          detail: eff.detail,
          at: this.env.now(),
        });
        return;
      }
    }
  }

  private scheduleFlush(afterMs: number): void {
    this.cancelTimer?.();
    this.cancelTimer = this.env.delay(afterMs, () => this.dispatch({ t: "flush" }));
  }
}
