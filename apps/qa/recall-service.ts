// domain-pending(DIV-DOMAPPS-001)
// domain-pending(DIV-DOMAPPS-006)
// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMCORE-006)
// domain-pending(DIV-DOMCORE-008)
// domain-pending(DIV-DOMTASK-004)
// domain-pending(DIV-DOMX-001)
// domain-pending(DIV-DOMX-005)
// domain-pending(DIV-DOMX-006)
import type { Database } from "bun:sqlite";

import {
  computeApplicationSynthesizedProjectionGenerationDigest,
  readApplicationSynthesizedPageWithAttestation,
  type ApplicationReadPorts,
  type ApplicationRecallGenerationDigests,
  type ApplicationReadCoherentCoordinates,
  type ApplicationSynthesizedPageResult,
} from "../../core/retrieve/application-read";
import {
  readAfterApplicationAuthorization,
  type ApplicationGrantProjectedTreeInputSnapshot,
  type ApplicationMemoryReadAuthorizationRequest,
} from "../../core/retrieve/authorization-boundary";
import { sha256CanonicalContent } from "../../core/retrieve/content-digest";
import type { ContentSafeRecallTrace, RecallCompletenessInput } from "../../core/retrieve/recall-integrity";
import type { RenderNode } from "../../core/retrieve/render";
import {
  createSqliteQaRecallLoader,
  type SqliteQaRecallLimits,
} from "../../drivers/sqlite/application-recall-read";
import { InvalidMcpCursorError } from "../mcp/cursor";
import type { QaReferenceCodecs } from "./codecs";
import { isSyntacticallyRedeemableCursor, type QaCursorAdapter } from "./cursor-bindings";
import { produceQaRenders } from "./renders";

/**
 * The QA composition of the localhost recall flow:
 *
 *   SQLite QA snapshot -> authorized projection -> deterministic renders ->
 *   application pagination -> signed cursor -> ratified page bytes
 *
 * SQLite is QA storage only and is never a production authority. This module
 * selects no production store, concurrency model, or retrieval policy.
 */

/** The declared frontier for a QA read. Content-free and stable per snapshot. */
const QA_DECLARED_FRONTIER_PREFIX = "frontier-v1:qa:";

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
  readonly codecs: QaReferenceCodecs;
  readonly cursor: QaCursorAdapter;
  readonly authorization: QaAuthorizationSource;
  /**
   * The authoritative read timestamp for this snapshot. Supplied, never read
   * from a wall clock, so a QA read and a replayed read agree exactly.
   */
  readonly read_timestamp_epoch_seconds: number;
  readonly traceSink: (trace: ContentSafeRecallTrace) => void | Promise<void>;
}

export interface QaRecallPageRequest {
  readonly limit: number;
  readonly cursor: string | null;
}

interface QaCoherentMaterial {
  readonly projected: ApplicationGrantProjectedTreeInputSnapshot;
  readonly renders: readonly RenderNode[];
  readonly snapshot: unknown;
  readonly account_timezone: string;
  readonly coverage: RecallCompletenessInput;
  readonly generations: ApplicationRecallGenerationDigests;
  /** Visible-closure identity. Never a storage-level digest. */
  readonly visible_generation: string;
  readonly visible_content_digest: string;
}

export interface QaRecallReader {
  /** Recomputes the coherent snapshot and its produced renders. */
  readonly refresh: () => Promise<void>;
  readonly readPage: (request: QaRecallPageRequest) => Promise<ApplicationSynthesizedPageResult>;
  /** Instrumentation for the proofs; carries no content. */
  readonly counters: () => Readonly<Record<string, number>>;
}

const digestOf = (label: string, value: unknown): string =>
  sha256CanonicalContent({ version: `qa-recall-${label}-v1`, value });

/**
 * Coverage for a QA read.
 *
 * `accepted` and `stm` are reported as `no_eligible` rather than `searched`
 * because neither source has a produced-render authority boundary yet — the
 * application read core rejects a claimed searched frontier for them outright.
 * Claiming otherwise would be a false completeness assertion, which the repo
 * treats as user data loss, not a rounding error.
 */
const qaCoverage = (declaredFrontier: string): RecallCompletenessInput => Object.freeze({
  declared_frontier: declaredFrontier,
  accepted: Object.freeze({ state: "no_eligible", searched_frontier: null }),
  stm: Object.freeze({ state: "no_eligible", searched_frontier: null }),
  projection_freshness: "fresh",
  intentional_bounds: Object.freeze([]),
}) as RecallCompletenessInput;

export const createQaRecallReader = (options: QaRecallReaderOptions): QaRecallReader => {
  const {
    db, principal, account_timezone: accountTimezone, limits, codecs,
    cursor: cursorAdapter, authorization, read_timestamp_epoch_seconds: readTimestamp, traceSink,
  } = options;

  if (!Number.isSafeInteger(readTimestamp) || readTimestamp < 0) {
    throw new TypeError("QA recall reader requires an authoritative read timestamp");
  }

  const loadCoherent = createSqliteQaRecallLoader({
    db,
    owner_account_id: principal.owner_account_id,
    account_timezone: accountTimezone,
    limits,
  });

  const counters: Record<string, number> = {
    refresh: 0, resolve: 0, coherent: 0, durable: 0,
    verify: 0, issue: 0, visible: 0, item: 0, citation: 0, trace: 0, sink: 0,
  };

  let material: QaCoherentMaterial | null = null;

  /**
   * Builds the coherent material once per refresh. Renders must be produced
   * before the read begins because the application read's coherent-load and
   * durable-render ports are both synchronous, while render production is not.
   *
   * Authorization is deliberately NOT captured here. It is re-resolved on every
   * attempt so a revocation between the read and its revalidation is observed
   * rather than served from a stale snapshot.
   */
  const buildMaterial = async (): Promise<QaCoherentMaterial> => {
    const load = loadCoherent();
    const snapshot = load.durable_snapshot;

    // A throwaway projection used only to produce renders and derive the
    // generation receipt. The authoritative projection is rebuilt inside the
    // authorization boundary on every attempt.
    const projected = readAfterApplicationAuthorization(
      authorization.resolveAuthorizationRequest(principal),
      () => ({ snapshot: structuredClone(snapshot), options: { account_timezone: accountTimezone } }),
    );
    const renders = await produceQaRenders(projected);

    // ── The visible-derivation rule ────────────────────────────────────────
    // Everything that can reach the wire is derived from the AUTHORIZED
    // PROJECTION, never from the raw storage snapshot.
    //
    // This is not stylistic. `load.coherent_snapshot_digest` and
    // `internal_coverage.durable.ledger_head.sequence` both cover records the
    // reader cannot see. Measured on a 6-claim snapshot with one claim hidden by
    // policy versus a 5-claim snapshot where it never existed: the digests differ
    // (3ad6626b… vs 1441b306…) and the ledger sequence differs (6 vs 5). Routing
    // either to the declared frontier or into a cursor binding publishes the
    // existence of a record the reader is not allowed to know about — a textbook
    // authorization oracle, and one that looks entirely reasonable in review.
    //
    // `projected.graph_generation` and `projected.projected_content_digest` are
    // computed over the visible closure only, so they are safe and, as a bonus,
    // more correct: a cursor now survives writes that do not affect this reader
    // instead of being invalidated by unrelated activity.
    //
    // `load.coherent_snapshot_digest` is deliberately NOT used anywhere below.
    const visibleGeneration = projected.graph_generation;
    const visibleContent = projected.projected_content_digest;
    const declaredFrontier = `${QA_DECLARED_FRONTIER_PREFIX}${visibleGeneration}`;
    const coverage = qaCoverage(declaredFrontier);

    const generations: ApplicationRecallGenerationDigests = Object.freeze({
      // Must equal read_coordinates.authorization_state_digest; the application
      // read cross-checks the two and fails closed when they disagree.
      authorization_generation_digest: digestOf("authorization", authorizationState()),
      synthesized_projection_generation_digest:
        computeApplicationSynthesizedProjectionGenerationDigest(projected, renders),
      durable_generation_digest: digestOf("durable", visibleGeneration),
      overlay_generation_digest: digestOf("overlay", { overlays: [] }),
      declared_generation_digest: digestOf("declared", { declared_frontier: declaredFrontier }),
      // Accepted and STM are reported as no-eligible, so their generation
      // receipts are derived from that declared state rather than from raw
      // internal counts, which would carry hidden-row cardinality to the wire.
      accepted_generation_digest: digestOf("accepted", { state: "no_eligible" }),
      stm_generation_digest: digestOf("stm", { state: "no_eligible" }),
    });

    return Object.freeze({
      projected,
      renders,
      snapshot,
      account_timezone: accountTimezone,
      coverage,
      generations,
      visible_generation: visibleGeneration,
      visible_content_digest: visibleContent,
    });
  };

  /** Content-free description of the current live authorization state. */
  const authorizationState = (): unknown => {
    const request = authorization.resolveAuthorizationRequest(principal);
    return {
      owner_account_id: request.owner_account_id,
      credential: {
        owner_account_id: request.credential.owner_account_id,
        credential_kind: request.credential.credential_kind,
        app_id: request.credential.app_id,
        key_id: request.credential.key_id,
        scopes: [...request.credential.scopes].sort(),
        active: request.credential.active,
      },
      persisted_grant: request.persisted_grant === null ? null : {
        owner_account_id: request.persisted_grant.owner_account_id,
        consumer: request.persisted_grant.consumer,
        app_id: request.persisted_grant.app_id,
        key_id: request.persisted_grant.key_id,
        enabled: request.persisted_grant.enabled,
        default_read: request.persisted_grant.default_read,
        scopes: [...request.persisted_grant.scopes].sort(),
      },
    };
  };

  const readCoordinates = (current: QaCoherentMaterial): ApplicationReadCoherentCoordinates => Object.freeze({
    owner_identity_digest: digestOf("owner", principal.owner_account_id),
    application_identity_digest: digestOf("application", principal.app_id),
    credential_identity_digest: digestOf("credential", principal.key_id),
    // Re-derived from LIVE authorization on every coherent load. This is the
    // coordinate that changes the moment a grant is revoked.
    authorization_state_digest: current.generations.authorization_generation_digest,
    grant_state_digest: digestOf("grant", authorizationState()),
    // Visible-derived, per the rule in buildMaterial. A storage-level digest
    // here would republish hidden-record existence through the cursor.
    account_head_digest: digestOf("account", current.visible_generation),
    authorized_graph_digest: digestOf("graph", current.visible_generation),
    coherent_projection_commit_digest: digestOf("commit", current.visible_content_digest),
    visibility_digest: digestOf("visibility", { default_synthesized: true, raw_read: false }),
    filter_digest: digestOf("filter", { filters: [] }),
    query_digest: digestOf("query", { query: null }),
    source_digest: digestOf("source", { sources: ["durable"] }),
    read_mode_digest: digestOf("read-mode", { mode: "default_synthesized" }),
    read_timestamp_epoch_seconds: readTimestamp,
  });

  const buildPorts = (current: QaCoherentMaterial): ApplicationReadPorts => ({
    resolveAttempt: () => {
      counters.resolve += 1;
      return {
        // Live authorization: this is the fence. A revocation landing between the
        // page build and its revalidation is seen here and denies the read
        // before any byte, cursor, or trace is produced.
        authorization_request: authorization.resolveAuthorizationRequest(principal),
        load_coherent: () => {
          counters.coherent += 1;
          const liveAuthorizationDigest = digestOf("authorization", authorizationState());
          return {
            projection_load: {
              snapshot: structuredClone(current.snapshot) as never,
              options: { account_timezone: current.account_timezone },
            },
            coverage: current.coverage,
            generations: {
              ...current.generations,
              authorization_generation_digest: liveAuthorizationDigest,
            },
            read_coordinates: {
              ...readCoordinates(current),
              authorization_state_digest: liveAuthorizationDigest,
            },
          };
        },
      };
    },

    loadDurableRenders: () => {
      counters.durable += 1;
      // A fresh plain array of the same branded render identities. The core
      // rejects proxies, decorated arrays, and unbranded lookalikes.
      return [...current.renders];
    },

    encodeVisibleKey: (tuple) => { counters.visible += 1; return codecs.encodeVisibleKey(tuple); },
    encodeItemRef: (ref) => { counters.item += 1; return codecs.encodeItemRef(ref); },
    encodeCitationRef: (closure) => { counters.citation += 1; return codecs.encodeCitationRef(closure); },
    encodeTraceRef: (ref) => { counters.trace += 1; return codecs.encodeTraceRef(ref); },

    verifyCursor: (rawCursor, attestation) => {
      counters.verify += 1;
      return cursorAdapter.verifyCursor(rawCursor, attestation);
    },
    issueCursor: (lastVisibleKey, attestation) => {
      counters.issue += 1;
      return cursorAdapter.issueCursor(lastVisibleKey, attestation);
    },
    traceSink: async (trace) => { counters.sink += 1; await traceSink(trace); },
  });

  return Object.freeze({
    refresh: async (): Promise<void> => {
      counters.refresh += 1;
      material = await buildMaterial();
    },

    readPage: async (request: QaRecallPageRequest): Promise<ApplicationSynthesizedPageResult> => {
      const current = material;
      if (current === null) {
        throw new TypeError("QA recall reader was read before its first refresh");
      }
      // The ratified keyset grammar is checked here, in the invalid-cursor error
      // currency, BEFORE the core sees the bytes. The core raises a plain
      // TypeError for a syntactically bad cursor, which the transport reports as
      // an internal error rather than an invalid cursor — and two public outcomes
      // for two mutations of one token is an authorization oracle.
      if (request.cursor !== null && !isSyntacticallyRedeemableCursor(request.cursor)) {
        throw new InvalidMcpCursorError();
      }
      return readApplicationSynthesizedPageWithAttestation(
        { limit: request.limit, cursor: request.cursor },
        buildPorts(current),
      );
    },

    counters: () => Object.freeze({ ...counters }),
  });
};
