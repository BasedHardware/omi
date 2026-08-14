// domain-pending(DIV-DOMAPPS-001)
// domain-pending(DIV-DOMAPPS-006)
// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMCORE-006)
// domain-pending(DIV-DOMCORE-008)
// domain-pending(DIV-DOMTASK-004)
// domain-pending(DIV-DOMX-001)
// domain-pending(DIV-DOMX-006)
import type { Database } from "bun:sqlite";

import type { ApplicationSynthesizedPageResult } from "../../core/retrieve/application-read";
import type { ApplicationMemoryReadAuthorizationRequest } from "../../core/retrieve/authorization-boundary";
import type { ContentSafeRecallTrace } from "../../core/retrieve/recall-integrity";
import {
  createSqliteQaRecallLoader,
  type SqliteQaRecallLimits,
} from "../../drivers/sqlite/application-recall-read";
import {
  DEFAULT_READ_ITEM_GRANULARITY,
  isReadItemGranularity,
  type ReadItemGranularity,
} from "../../core/retrieve/granularity";
import type { McpCursorSigningKeyset } from "../mcp/cursor";
import {
  QA_MEMORY_READ_CURSOR_BINDINGS,
  qaMemoryReadProduceRenders,
} from "./memory-read-bindings";
import {
  prepareMemoryRead,
  readMemoryPage,
  type CoherentQaLoad,
  type MemoryReadPortCall,
  type PreparedMemoryRead,
} from "../service/composition/memory-read";

/**
 * The MCP door's READER over the shared read composition.
 *
 *   SQLite QA snapshot -> authorized projection -> deterministic renders ->
 *   application pagination -> signed cursor -> ratified page bytes
 *
 * This module used to construct `ApplicationReadPorts` itself, independently of
 * the REST door's composition, and the two disagreed on the digest scheme, the
 * declared-frontier derivation, the coverage default and the opaque codecs —
 * which made them mint different public item ids for the same memory. That
 * construction is DELETED. Everything below the transport now comes from
 * `apps/service/composition/memory-read.ts`; what remains here is the part that
 * is genuinely this door's: the SQLite loader, the per-granularity material
 * cache, the coverage declaration this surface is entitled to make, and the
 * port-call counters the proofs read.
 *
 * SQLite is QA storage only and is never a production authority. This module
 * selects no production store, concurrency model, or retrieval policy.
 */

export interface QaRecallPrincipal {
  readonly owner_account_id: string;
  readonly app_id: string;
  readonly key_id: string;
}

/** Live authorization state, re-read on every attempt so revocation is observed. */
export interface QaAuthorizationSource {
  readonly resolveAuthorizationRequest: (
    principal: QaRecallPrincipal,
  ) => ApplicationMemoryReadAuthorizationRequest;
}

export interface QaRecallReaderOptions {
  readonly db: Database;
  readonly principal: QaRecallPrincipal;
  readonly account_timezone: string;
  readonly limits: SqliteQaRecallLimits;
  /** HMAC root for the shared reader-scoped opaque handles. Never a production secret. */
  readonly codec_root_secret: Uint8Array;
  readonly cursor_signing_keyset: McpCursorSigningKeyset;
  readonly authorization: QaAuthorizationSource;
  /**
   * The authoritative read timestamp for this snapshot. Supplied, never read
   * from a wall clock, so a QA read and a replayed read agree exactly.
   */
  readonly read_timestamp_epoch_seconds: number;
  readonly traceSink: (trace: ContentSafeRecallTrace) => void | Promise<void>;
  /**
   * Item granularity, stated explicitly per the coordinator's provisional
   * ruling. Never inferred from the transport.
   */
  // domain-pending(DIV-DOMCORE-008)
  readonly granularity?: ReadItemGranularity;
}

export interface QaRecallPageRequest {
  readonly limit: number;
  readonly cursor: string | null;
  /**
   * Stated granularity, or `null` for "caller did not ask" — which resolves to
   * the reader's configured default, never to a transport-specific value.
   */
  // domain-pending(DIV-DOMCORE-008)
  readonly granularity?: string | null;
}

export interface QaRecallReader {
  /** Recomputes the coherent snapshot and its produced renders. */
  readonly refresh: () => Promise<void>;
  readonly readPage: (request: QaRecallPageRequest) => Promise<ApplicationSynthesizedPageResult>;
  /** Instrumentation for the proofs; carries no content. */
  readonly counters: () => Readonly<Record<string, number>>;
}

const fail = (message: string): never => { throw new TypeError(`QA recall service: ${message}`); };

export const createQaRecallReader = (options: QaRecallReaderOptions): QaRecallReader => {
  const {
    db, principal, account_timezone: accountTimezone, limits,
    codec_root_secret: codecRootSecret, cursor_signing_keyset: cursorSigningKeyset,
    authorization, read_timestamp_epoch_seconds: readTimestamp, traceSink,
  } = options;
  const granularity = options.granularity ?? DEFAULT_READ_ITEM_GRANULARITY;

  if (!Number.isSafeInteger(readTimestamp) || readTimestamp < 0) {
    throw new TypeError("QA recall reader requires an authoritative read timestamp");
  }

  const loadSqlite = createSqliteQaRecallLoader({
    db,
    owner_account_id: principal.owner_account_id,
    account_timezone: accountTimezone,
    limits,
  });

  /**
   * FAIL CLOSED ON THE COVERAGE ASSUMPTION.
   *
   * This surface declares `no_eligible` for accepted work and STM below. That
   * declaration is leak-free — it is a constant, so no storage cardinality
   * reaches the wire — and it is only *honest* while the fixtures genuinely
   * have no STM rows. If any appeared, this path (which never searches STM)
   * would claim completeness it has not earned, and a wrong `complete: true` is
   * user data loss under rule 12.
   *
   * So assert the assumption instead of trusting it. Reading the count here is
   * a guard that fails the read; it derives no wire value, which is exactly
   * what the storage-provenance fence's escape hatch is for. The guard lives
   * with the DECLARATION, not in the shared composition — the composition
   * defaults to the conservative `bypassed` and cannot know what any given
   * caller is entitled to claim.
   */
  const loadCoherent = (): CoherentQaLoad => {
    const load = loadSqlite();
    // storage-provenance-ok(fail-closed guard on a completeness assumption; no wire value derives from this)
    if (load.internal_coverage.stm.eligible_items !== 0) {
      return fail("QA coverage claims no eligible STM work, but STM rows exist");
    }
    return load as unknown as CoherentQaLoad;
  };

  const counters: Record<string, number> = {
    refresh: 0, resolve: 0, coherent: 0, durable: 0,
    verify: 0, issue: 0, visible: 0, item: 0, citation: 0, trace: 0, sink: 0,
  };
  const onPortCall = (call: MemoryReadPortCall): void => { counters[call] = (counters[call] ?? 0) + 1; };

  /**
   * One prepared read per granularity. Renders differ between granularities
   * (different node sets produce different generation receipts), so they cannot
   * share a cache entry. Keyed rather than rebuilt per request so repeated reads
   * at one granularity stay deterministic and cheap.
   *
   * Caching is safe across a revocation because the prepared read holds a LIVE
   * authorization resolver, not a captured request: the grant is re-read inside
   * every attempt.
   */
  const preparedByGranularity = new Map<ReadItemGranularity, PreparedMemoryRead>();

  const prepare = async (forGranularity: ReadItemGranularity): Promise<PreparedMemoryRead> =>
    prepareMemoryRead({
      cursorBindings: QA_MEMORY_READ_CURSOR_BINDINGS,
      produceRenders: qaMemoryReadProduceRenders,
      loadCoherent,
      // Live authorization: this is the fence. A revocation landing between the
      // page build and its revalidation is seen here and denies the read before
      // any byte, cursor, or trace is produced.
      resolveAuthorization: () => authorization.resolveAuthorizationRequest(principal),
      codecRootSecret,
      cursorSigningKeyset,
      readTimestampEpochSeconds: readTimestamp,
      granularity: forGranularity,
      // DECLARED, not counted at request time. This surface owns its whole
      // fixture — the seeder writes no accepted work and no STM rows, and
      // `loadCoherent` above fails the read if that ever stops being true.
      // domain-pending(DIV-DOMCORE-006)
      acceptedCoverageState: "no_eligible",
      // domain-pending(DIV-DOMCORE-006)
      stmCoverageState: "no_eligible",
      traceSink,
      onPortCall,
    });

  return Object.freeze({
    refresh: async (): Promise<void> => {
      counters.refresh += 1;
      preparedByGranularity.clear();
      preparedByGranularity.set(granularity, await prepare(granularity));
    },

    readPage: async (request: QaRecallPageRequest): Promise<ApplicationSynthesizedPageResult> => {
      if (preparedByGranularity.size === 0) {
        throw new TypeError("QA recall reader was read before its first refresh");
      }
      // `null`/omitted means the caller did not ask, which resolves to the
      // reader's configured default -- NOT to a transport-specific value. An
      // unrecognised value is a client error, not a silent fallback.
      const requested = request.granularity ?? null;
      if (requested !== null && !isReadItemGranularity(requested)) {
        throw new TypeError("QA recall reader received an unknown item granularity");
      }
      const effective: ReadItemGranularity = requested ?? granularity;
      let prepared = preparedByGranularity.get(effective);
      if (prepared === undefined) {
        prepared = await prepare(effective);
        preparedByGranularity.set(effective, prepared);
      }
      // The syntactic cursor pre-check lives in `readMemoryPage`, so both doors
      // reject a malformed cursor in the same error currency.
      return readMemoryPage({ limit: request.limit, cursor: request.cursor }, prepared);
    },

    counters: () => Object.freeze({ ...counters }),
  });
};
