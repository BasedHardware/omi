/**
 * The "on-disk" `FallbackSink` adapter from COORD-degradation-is-
 * unobservable — dev/QA builds get this one, not the in-memory adapter,
 * because "the real app running locally is exactly where durability
 * matters most": an overnight degradation must still be there in the
 * morning.
 *
 * Append-only over the same `DurableLog` primitive the outbox journals
 * with, so it inherits the same durability protocol (append resolves only
 * once durable; scan order is append order) for free. Capped, because an
 * unbounded local ledger is its own failure mode — the cap is a coarse
 * "don't grow forever" bound, not a retention policy; there is no data yet
 * to design a real one against.
 *
 * PII policy lives at the adapter boundary (binding constraint #2 of the
 * ruling): this adapter keeps full `FallbackRecord` detail, same as the
 * in-memory one. A remote adapter, when it exists, applies an allowlist
 * here — call sites never change.
 */

import type { FallbackRecord, FallbackSink, StorageBridge } from "@omi-core/contracts";

const FALLBACK_LOG_NAME = "fallback-telemetry";

/** Oldest records are truncated once the log exceeds this many entries. */
export const DEFAULT_FALLBACK_SINK_CAP = 500;

export async function openOnDiskFallbackSink(
  bridge: StorageBridge,
  cap: number = DEFAULT_FALLBACK_SINK_CAP,
): Promise<FallbackSink> {
  const log = await bridge.openLog(FALLBACK_LOG_NAME);
  let size = (await log.scan(0)).length;

  return {
    record(event: FallbackRecord): void {
      // `record` is synchronous by contract (the port is `record(event):
      // void` — no promise). The append is fire-and-forget from the
      // caller's point of view; durability lands asynchronously, same as
      // every other DurableLog write on this side of the bridge.
      void log.append(JSON.stringify(event)).then(async (lsn) => {
        size += 1;
        if (size > cap) {
          // LSNs are monotonic and this log name is private to this
          // adapter, so "keep the newest `cap` entries" is exactly
          // "truncate everything at or below (latest lsn - cap)".
          await log.truncate(Math.max(0, lsn - cap));
          size = cap;
        }
      });
    },
  };
}

/**
 * Read back what's on disk — for a `/qa/*` route or dev-loop inspection.
 * Not part of the `FallbackSink` port; nothing in the write path needs it.
 */
export async function readOnDiskFallbackRecords(bridge: StorageBridge): Promise<FallbackRecord[]> {
  const log = await bridge.openLog(FALLBACK_LOG_NAME);
  const entries = await log.scan(0);
  return entries.map((entry) => JSON.parse(entry.payload) as FallbackRecord);
}
