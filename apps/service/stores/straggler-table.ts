/**
 * THE STRAGGLER TABLE — the refused envelopes ruling B3 says must survive.
 *
 * When the account epoch fence answers `evidence: "preserve_envelope"`, the
 * user's edit was refused by a door that will never accept it, and the ONLY
 * copy of what they wrote is the envelope in front of us. `COORD-cross-generation-writes.md`
 * is explicit that a summary does not satisfy this: "A human handed that record
 * knows an edit was lost and roughly what it was, but cannot reproduce it." So
 * the row holds the FULL envelope, patch included, as the exact bytes received.
 *
 * Exactly one refusal in the whole fence preserves — `request_epoch_behind`, the
 * straggler — and a unit test in the fence pins that "exactly one" property. This
 * table is downstream of that decision and never second-guesses it: it stores what
 * it is told to store, and the fence decides.
 *
 * ── B3's "JOINED TO THE LIFECYCLE BY CONSTRUCTION" — WHAT THAT MEANS HERE ────
 *
 * These rows hold user content retained server-side after a refusal. B3 signs
 * their STRUCTURE on the condition that they are new-generation data under the
 * ADR-014 lifecycle projection, "so deletion dominates them with no separate
 * mechanism, and export covers them. Build them that way from the first row."
 *
 * Mechanically, here, that is: **the account id is the only key into this
 * table.** There is no row id, no global iterator, and no lookup that does not
 * start from an account. An account-scoped deletion therefore cannot miss a row
 * by forgetting about this module, because there is no reachable row that is not
 * under the account being deleted — and `deleteAccount`/`exportAccount` are the
 * two account-scoped operations the lifecycle needs, present from the first row
 * rather than added later. `straggler-table.test.ts` asserts the reachability
 * property directly, so a future `listAll()` added for convenience goes red.
 *
 * ── THE 90-DAY CAP IS A DECISION, NOT YET A BEHAVIOUR ────────────────────────
 *
 * David signed a hard 90-day cap, then export-and-delete
 * (`DAVID-retention-and-refusal-copy.md`). `RETENTION_CAP_SECONDS` is that
 * decision. `sweepExpired` is the mechanism that would enforce it — and NOTHING
 * IN THIS REPO CALLS IT ON A SCHEDULE. There is no scheduler, no job runner and
 * no production deployment here to host one. Until something does, the cap is a
 * decision with a callable implementation and no operational effect, and no
 * report may claim otherwise.
 */

/** David-signed, `DAVID-retention-and-refusal-copy.md`: 90 days, hard cap. */
export const RETENTION_CAP_DAYS = 90;
export const RETENTION_CAP_SECONDS = RETENTION_CAP_DAYS * 24 * 60 * 60;

export interface PreservedEnvelope {
  /** The exact request bytes. Not a summary, not a re-serialization. */
  readonly envelope_json: string;
  /** Ruling B1's key, lifted out so a row can be joined to the client journal. */
  readonly write_id: string;
  /** The epoch the op was created under — the reason it was refused. */
  readonly account_epoch: number;
  /** When this row was retained. Supplied by the caller's clock port. */
  readonly retained_at_epoch_seconds: number;
}

export interface StragglerTable {
  /** Retains one refused envelope under an account. */
  preserve(accountId: string, row: PreservedEnvelope): void;
  /**
   * Every retained envelope for one account, oldest first. This is the export
   * side of B3's lifecycle join, and it is the ONLY read path.
   */
  exportAccount(accountId: string): readonly PreservedEnvelope[];
  /** The deletion side. Total: an account with no rows is not an error. */
  deleteAccount(accountId: string): number;
  /**
   * The David-signed cap, as a mechanism. Removes every row older than the cap
   * relative to the supplied instant, across all accounts, and returns the
   * count. Nothing schedules this; see the module header.
   */
  sweepExpired(nowEpochSeconds: number): number;
  reset(): void;
}

export const createInMemoryStragglerTable = (): StragglerTable => {
  // The account id is the only key. See the header: this shape is what makes
  // B3's "deletion dominates them with no separate mechanism" true rather than
  // promised.
  const byAccount = new Map<string, PreservedEnvelope[]>();

  return Object.freeze({
    preserve(accountId: string, row: PreservedEnvelope): void {
      const rows = byAccount.get(accountId) ?? [];
      rows.push(row);
      byAccount.set(accountId, rows);
    },

    exportAccount(accountId: string): readonly PreservedEnvelope[] {
      return Object.freeze([...(byAccount.get(accountId) ?? [])]);
    },

    deleteAccount(accountId: string): number {
      const removed = byAccount.get(accountId)?.length ?? 0;
      byAccount.delete(accountId);
      return removed;
    },

    sweepExpired(nowEpochSeconds: number): number {
      // A row is expired when its AGE EXCEEDS the cap: `now - retained_at > cap`,
      // equivalently `retained_at < now - cap`. So a row exactly at the cap is
      // KEPT. The other spelling deletes user content one second early, which is
      // a data-destructive off-by-one on a David-signed retention window — the
      // kind of error that is invisible in review and permanent in effect.
      const horizon = nowEpochSeconds - RETENTION_CAP_SECONDS;
      let removed = 0;
      for (const [accountId, rows] of [...byAccount.entries()]) {
        const kept = rows.filter((row) => row.retained_at_epoch_seconds >= horizon);
        removed += rows.length - kept.length;
        if (kept.length === 0) byAccount.delete(accountId);
        else byAccount.set(accountId, kept);
      }
      return removed;
    },

    reset(): void {
      byAccount.clear();
    },
  });
};
