/**
 * Shared, truthful lifecycle state for a domain store.
 *
 * Refresh state is deliberately independent from the transport's error
 * vocabulary. A list read either produced a usable result, or it did not; the
 * UI must not infer "offline" (or any other cause) from a status code it never
 * received. `hasSavedData` lets a surface distinguish an empty ready state
 * from a refresh failure while retaining previously synced rows.
 */

import type { QueueStatus } from "@omi-core/sync";

export type RefreshPhase =
  | "initial-loading"
  | "refreshing"
  | "ready"
  | "saved-but-refresh-failed"
  | "unavailable";

export interface RefreshStatus {
  readonly phase: RefreshPhase;
  readonly hasSavedData: boolean;
}

export interface StoreStatus {
  readonly refresh: RefreshStatus;
  readonly queue: QueueStatus;
}

export interface RefreshToken {
  readonly generation: number;
}

/**
 * Pure in-memory refresh lifecycle. The generation fence prevents an older
 * overlapping refresh from replacing the status produced by a newer one.
 * Callers apply fetched rows through `applyIfCurrent()`, which serializes the
 * projection mutation and re-checks the generation at the write gate.
 */
export class RefreshTracker {
  private generation = 0;
  private current: RefreshStatus;
  private applicationTail = Promise.resolve();

  /** A reopened store can have durable rows before its first refresh. */
  constructor(hasSavedData = false) {
    this.current = { phase: "initial-loading", hasSavedData };
  }

  begin(): RefreshToken {
    const token = { generation: ++this.generation };
    this.current = {
      phase: this.current.phase === "initial-loading" && !this.current.hasSavedData ? "initial-loading" : "refreshing",
      hasSavedData: this.current.hasSavedData,
    };
    return token;
  }

  isCurrent(token: RefreshToken): boolean {
    return token.generation === this.generation;
  }

  /**
   * Serialize projection mutations and re-check freshness at the mutation
   * gate. An older write that is already in flight finishes first; a newer
   * write then runs after it and is therefore the final durable application.
   * Work that reaches the gate after a newer refresh starts is skipped.
   */
  async applyIfCurrent(token: RefreshToken, operation: () => Promise<void>): Promise<boolean> {
    const predecessor = this.applicationTail;
    let release!: () => void;
    this.applicationTail = new Promise<void>((resolve) => {
      release = resolve;
    });
    await predecessor;
    try {
      if (!this.isCurrent(token)) return false;
      await operation();
      return true;
    } finally {
      release();
    }
  }

  /**
   * Finish only the newest refresh. `listSucceeded` comes from the list read,
   * not from an id-snapshot/reconcile response (snapshots may be incomplete).
   */
  complete(token: RefreshToken, listSucceeded: boolean, hasSavedData: boolean): boolean {
    if (!this.isCurrent(token)) return false;
    this.current = listSucceeded
      ? { phase: "ready", hasSavedData }
      : hasSavedData
        ? { phase: "saved-but-refresh-failed", hasSavedData: true }
        : { phase: "unavailable", hasSavedData: false };
    return true;
  }

  snapshot(): RefreshStatus {
    return this.current;
  }
}
