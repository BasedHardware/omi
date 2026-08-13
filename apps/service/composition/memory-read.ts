// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMCORE-006)
// domain-pending(DIV-DOMCORE-008)
// domain-pending(DIV-DOMAPPS-001)
// domain-pending(DIV-DOMAPPS-006)
// domain-pending(DIV-DOMX-001)
// domain-pending(DIV-DOMX-006)
import { createHmac } from "node:crypto";
import { isProxy } from "node:util/types";

import {
  ApplicationReadInvalidatedError,
  computeApplicationSynthesizedProjectionGenerationDigest,
  readApplicationSynthesizedPageWithAttestation,
  type ApplicationReadAttestation,
  type ApplicationReadCoherentCoordinates,
  type ApplicationReadPorts,
  type ApplicationRecallGenerationDigests,
  type ApplicationSynthesizedPageRequest,
} from "../../../core/retrieve/application-read";
import {
  inspectApplicationMemoryReadAuthorization,
  readAfterApplicationAuthorization,
  type ApplicationMemoryReadAuthorizationRequest,
} from "../../../core/retrieve/authorization-boundary";
import { sha256CanonicalContent } from "../../../core/retrieve/content-digest";
import {
  buildOwnerMemoryExport,
  type OwnerMemoryExportBundle,
} from "../../../core/retrieve/owner-memory-export";
import type {
  AcceptedCoverageState,
  ContentSafeRecallTrace,
  RecallCompletenessInput,
  StmCoverageState,
} from "../../../core/retrieve/recall-integrity";
import {
  isApplicationGrantProjectedTreeInput,
  type ApplicationGrantProjectedTreeInputSnapshot,
} from "../../../core/retrieve/authorization-boundary";
import type { RenderNode } from "../../../core/retrieve/render";
import { buildDeterministicAnchors } from "../../../core/retrieve/tree";
import type { GraphSnapshot } from "../../../core/retrieve";
import { InvalidMcpCursorError, type McpCursorSigningKeyset } from "../../mcp/cursor";
// The canonical, transport-neutral granularity module. BE-FLOW landed it in
// core/ while this lane had a local copy; there must be exactly one selector or
// the two doors drift, which is the entire point of the ruling. The local copy
// is deleted.
import {
  DEFAULT_READ_ITEM_GRANULARITY,
  selectNodesForGranularity,
  type ReadItemGranularity,
} from "../../../core/retrieve/granularity";
import {
  createQaCursorAdapter,
  isSyntacticallyRedeemableCursor,
  QA_CURSOR_POLICY,
} from "../../qa/cursor-bindings";
import { produceQaRenders } from "../../qa/renders";
import { createReaderScopedOpaqueCodecs } from "../codecs/opaque-refs";

/**
 * THE composition root for the application memory read path — for BOTH doors.
 *
 * `ApplicationReadPorts` used to be constructed twice, independently: here for
 * the REST door and again in `apps/qa/recall-service.ts` for the MCP door. Two
 * modules constructing one port type are two implementations, not two adapters,
 * and the cost was measured rather than theorised: over one shared SQLite
 * snapshot and one shared principal the two doors returned the SAME memory
 * (byte-identical `text`, identical `provenance.outputDigest`) under DIFFERENT
 * public item ids —
 *
 *   MCP  mem1_eca59618fff27e10…   REST mem1_dd73274cc9b1a9ac…
 *
 * — because they keyed the opaque-ref codecs differently. Every node-level
 * cross-door assertion passed throughout. The two doors also disagreed on the
 * digest scheme, the declared-frontier derivation and the coverage default.
 *
 * So there is exactly ONE construction site, and it is this one. The transports
 * stay separate — `apps/mcp/protocol.ts` and `apps/service/routes/memories.ts`
 * are correctly different — but everything below the transport is shared. Rule
 * 16 (`scripts/lint-import-graph.ts` PORT_REGISTRY) is what keeps it that way.
 *
 * It lives under `apps/service/composition/` because that is where it already
 * was; `apps/qa/` already depends on `apps/service/` (see `apps/qa/server.ts`),
 * so no new edge is introduced by the MCP door calling it.
 *
 * SQLite is QA-only here and is never production authority. No production
 * store, concurrency model, or deployment topology is selected by this file.
 */

/**
 * Re-roots a value onto standard object prototypes.
 *
 * The SQLite QA loader hardens its output with null-prototype records, but
 * `application-read.ts` rejects any object whose prototype is not
 * `Object.prototype`. Note that `authorization-boundary.ts` ACCEPTS null
 * prototypes, so those two core modules disagree with each other; the mismatch
 * was invisible while nothing connected the driver to the read path. The
 * composition adapts rather than weakening either boundary. Any future durable
 * driver must satisfy the stricter of the two.
 */
const toStandardPrototypeJson = <Value>(value: Value): Value => structuredClone(value);

const compareStrings = (left: string, right: string): number =>
  left < right ? -1 : left > right ? 1 : 0;

/**
 * The QA coherent load this composition consumes. It is structurally the
 * `SqliteQaRecallLoad` produced by `createSqliteQaRecallLoader`, restated here
 * so the composition depends on the shape rather than on the SQLite driver.
 */
// domain-pending(DIV-DOMCORE-006)
export interface CoherentQaLoad {
  readonly owner_account_id: string;
  readonly account_timezone: string;
  /**
   * The durable graph snapshot. This is the ONE storage-scoped value this
   * composition consumes, and it is consumed for exactly one purpose: it is the
   * input handed to `readAfterApplicationAuthorization`, which applies the
   * policy closure and returns the authorized projection. Nothing derived from
   * it reaches the wire un-projected.
   */
  // storage-provenance-ok(the durable snapshot is the input to the authorization boundary; every wire value is derived from the projection it returns, never from this)
  readonly durable_snapshot: GraphSnapshot;
}

/** Port-call instrumentation vocabulary. Counts only; carries no content. */
export type MemoryReadPortCall =
  | "resolve" | "coherent" | "durable"
  | "visible" | "item" | "citation" | "trace"
  | "verify" | "issue" | "sink";

export interface MemoryReadCompositionConfig {
  /** Zero-argument coherent loader; called fresh for every internal revalidation. */
  readonly loadCoherent: () => CoherentQaLoad;
  /**
   * LIVE authorization state, re-resolved on every attempt.
   *
   * This is the revocation fence, and it is why the config takes a thunk rather
   * than a value. The REST door used to capture one authorization request at
   * prepare time and hand the same frozen object to every internal
   * revalidation, so a grant revoked BETWEEN the page build and its
   * revalidation was not observed — the read core's second load crossed the
   * boundary with the first load's answer. Resolving here means the revocation
   * denies the read before any byte, cursor, or trace is produced.
   *
   * The resolved request is captured once PER ATTEMPT and reused for that
   * attempt's coherent load, so the digest a cursor binds is the digest of the
   * request the authorization boundary actually validated. The MCP door
   * previously resolved twice per attempt, which left room for the two to
   * disagree.
   */
  readonly resolveAuthorization: () => ApplicationMemoryReadAuthorizationRequest;
  /** HMAC root for the reader-scoped opaque handles. QA-supplied; never a production secret. */
  readonly codecRootSecret: Uint8Array;
  readonly cursorSigningKeyset: McpCursorSigningKeyset;
  /** Defaults to the shared QA cursor policy's TTL. Bound into every cursor. */
  readonly cursorTtlSeconds?: number;
  /**
   * The authoritative read timestamp for this snapshot. Passed in, never read
   * from a clock, so the two internal revalidation loads agree and the flow
   * stays hermetic.
   */
  readonly readTimestampEpochSeconds: number;
  readonly traceSink: (trace: ContentSafeRecallTrace) => void | Promise<void>;
  /**
   * Which synthesized nodes count as served memories. EXPLICIT, never implied
   * by the transport - see core/retrieve/granularity.ts. Defaults to the
   * app-facing granularity when omitted.
   */
  // domain-pending(DIV-DOMCORE-008)
  readonly granularity?: ReadItemGranularity;
  /**
   * DECLARED coverage states for the sources this read does not search.
   *
   * They are configuration, never a storage count. That is the whole point: a
   * coverage state computed from row counts varies with rows the reader is not
   * authorized to see, which republishes their existence in the completeness
   * envelope - the same oracle class as the frontier and cursor bindings, in a
   * field the item-level byte-identity test does not reach.
   *
   * Both default to the conservative `bypassed`: "we did not search it" is
   * always true here and reveals nothing. A caller may declare `no_eligible`
   * ONLY when it can establish emptiness from something other than counting
   * rows at request time - for instance because it seeded the corpus itself.
   * Both doors do exactly that, and each proves it at its own call site.
   */
  // domain-pending(DIV-DOMCORE-006)
  readonly acceptedCoverageState?: AcceptedCoverageState;
  // domain-pending(DIV-DOMCORE-006)
  readonly stmCoverageState?: StmCoverageState;
  /** Optional per-port-call counter hook. Instrumentation only. */
  readonly onPortCall?: (call: MemoryReadPortCall) => void;
}

/**
 * Maps QA coverage onto the recall completeness envelope HONESTLY.
 *
 * The two rules that matter, both of which a plausible implementation gets
 * wrong in the direction of over-claiming:
 *
 * 1. The short-term overlay is NOT searchable through this path. The recall
 *    core refuses a synthesized STM frontier because STM has no produced-render
 *    authority boundary yet. So when eligible STM rows exist, the envelope must
 *    say the overlay was bypassed - reporting `no_eligible` would present
 *    durable-only recall as complete recall, which is exactly the false
 *    `complete: true` that costs user data.
 * 2. Accepted-work coverage may only be reported as `no_eligible` when the load
 *    actually declares there is no eligible accepted work. Anything that would
 *    imply a searched accepted frontier is downgraded to `bypassed`, because
 *    this composition genuinely did not search it.
 */
// domain-pending(DIV-DOMCORE-006)
// domain-pending(DIV-DOMCORE-008)
const buildCoverage = (
  declaredAccepted: AcceptedCoverageState,
  declaredStm: StmCoverageState,
  authorizedGraphGeneration: string,
  encodeFrontier: (internalFrontier: string) => string,
): RecallCompletenessInput => {
  // The declared frontier reaches the wire UNFILTERED. Unlike item, citation and
  // trace references it does not pass through the read core's opaque-ref codecs
  // or its forbidden-ref leak check - `mapCompleteness` copies it straight into
  // the page. So keeping it content-free AND authorization-scoped is this
  // composition's job.
  //
  // It is derived from the AUTHORIZED projection generation, never from the
  // ledger head. The ledger head counts every durable row including rows this
  // reader may not see, so a frontier derived from it changes when a hidden
  // record is added - an authorization oracle that survives even though the
  // items themselves are correctly filtered. A test caught exactly that.
  //
  // It is also KEYED and READER-SCOPED. The MCP door used to publish
  // `frontier-v1:qa:<graph generation>` — the visible generation in cleartext,
  // identical for every credential on the account, which makes the frontier a
  // cross-reader correlation key over exactly the closure the opaque-ref codecs
  // are scoped to keep separate.
  const declaredFrontier = encodeFrontier(`durable:${authorizedGraphGeneration}`);

  // Coverage states are DECLARED by the caller, never computed here from
  // storage. This composition previously derived the STM state from the
  // loader's eligible-row count, which was an oracle: that count filters only
  // on owner and consumption, applies NO policy-label filter, and counts
  // PROVISIONAL claims - none of which can ever enter this projection's
  // authorized closure, since the closure requires canonical placement,
  // canonical lifecycle, durable locality and generic policy labels. So the
  // count was 100% storage-scoped and 0% authorization-scoped, and it moved a
  // wire-visible completeness field.
  return Object.freeze({
    declared_frontier: declaredFrontier,
    accepted: Object.freeze({ state: declaredAccepted, searched_frontier: null }),
    stm: Object.freeze({ state: declaredStm, searched_frontier: null }),
    projection_freshness: "fresh" as const,
    intentional_bounds: Object.freeze([]),
  });
};

/**
 * One digest scheme for the whole composition: the core's
 * `sha256CanonicalContent`.
 *
 * The two doors used to disagree here — a local `sha256Hex(canonicalJson(…))`
 * pair on the REST side against `sha256CanonicalContent` on the MCP side — and
 * a composition that re-implements canonical JSON is a composition that can
 * disagree with the core about what canonical means. The local copy is deleted.
 */
const digestOf = (label: string, value: unknown): string =>
  sha256CanonicalContent({ version: `application-read-${label}-v1`, value });

const buildGenerations = (
  authorizedGraphGeneration: string,
  acceptedState: AcceptedCoverageState,
  stmState: StmCoverageState,
  authorizationDigest: string,
  declaredFrontier: string,
  granularity: ReadItemGranularity,
  synthesizedProjectionGenerationDigest: string,
): ApplicationRecallGenerationDigests => Object.freeze({
  // Must equal read_coordinates.authorization_state_digest; the application
  // read cross-checks the two and fails closed when they disagree.
  authorization_generation_digest: authorizationDigest,
  synthesized_projection_generation_digest: synthesizedProjectionGenerationDigest,
  durable_generation_digest: digestOf("durable-generation", authorizedGraphGeneration),
  // Only the overlay's reported STATE, never its row count or row ids. The
  // state is already published in the completeness envelope, so binding it
  // reveals nothing the client cannot already read.
  overlay_generation_digest: digestOf("overlay-generation", { state: stmState }),
  // Granularity is inside the generation receipt, so a cursor issued at one
  // granularity cannot redeem at another. Without this, page two of a
  // leaves-only read could be continued as an all-nodes read and silently
  // return items page one could never have contained.
  declared_generation_digest: digestOf("declared-generation", {
    authorized_graph_generation: authorizedGraphGeneration,
    declared_frontier: declaredFrontier,
    granularity,
  }),
  // Accepted and STM are reported from their DECLARED state, never from raw
  // internal counts, which would carry hidden-row cardinality to the wire.
  accepted_generation_digest: digestOf("accepted-generation", { state: acceptedState }),
  stm_generation_digest: digestOf("stm-generation", { state: stmState }),
});

const buildReadCoordinates = (
  authorizedGraphGeneration: string,
  authorizedContentDigest: string,
  authorization: ApplicationMemoryReadAuthorizationRequest,
  authorizationDigest: string,
  persistedGrantStateDigest: string,
  readTimestampEpochSeconds: number,
): ApplicationReadCoherentCoordinates => Object.freeze({
  // Identity coordinates come from the authorization request the boundary
  // validated, never from a separately-carried principal record: a second
  // source of truth for reader identity is how the two doors diverged.
  owner_identity_digest: digestOf("owner", authorization.owner_account_id),
  application_identity_digest: digestOf("application", authorization.credential.app_id ?? ""),
  credential_identity_digest: digestOf("credential", authorization.credential.key_id ?? ""),
  // The core cross-checks this against the authorization generation digest.
  // Re-derived from LIVE authorization on every coherent load: this is the
  // coordinate that changes the moment a grant is revoked.
  authorization_state_digest: authorizationDigest,
  grant_state_digest: persistedGrantStateDigest,
  // Authorization-scoped, NOT the ledger head. See buildGenerations.
  account_head_digest: digestOf("account-head", authorizedGraphGeneration),
  authorized_graph_digest: digestOf("authorized-graph", authorizedGraphGeneration),
  coherent_projection_commit_digest: digestOf("coherent-projection-commit", authorizedContentDigest),
  // This read applies the application-default visibility, no filter, and no
  // query. They are still distinct bound coordinates so that introducing any of
  // them later invalidates outstanding cursors rather than silently reusing them.
  visibility_digest: digestOf("visibility", { default_synthesized: true, raw_read: false }),
  filter_digest: digestOf("filter", { filters: [] }),
  query_digest: digestOf("query", { query: null }),
  source_digest: digestOf("source", { sources: ["durable"] }),
  read_mode_digest: digestOf("read-mode", { mode: "default_synthesized" }),
  read_timestamp_epoch_seconds: readTimestampEpochSeconds,
});

const buildDirectReadCoordinates = (
  load: DirectAuthorizedMemoryProjectionLoad,
  readTimestampEpochSeconds: number,
): ApplicationReadCoherentCoordinates => Object.freeze({
  owner_identity_digest: load.owner_identity_digest,
  application_identity_digest: load.application_identity_digest,
  credential_identity_digest: load.credential_identity_digest,
  authorization_state_digest: load.authorization_generation_digest,
  grant_state_digest: load.grant_state_digest,
  account_head_digest: load.account_generation_digest,
  authorized_graph_digest: digestOf("authorized-graph", load.projected.graph_generation),
  coherent_projection_commit_digest: digestOf(
    "coherent-projection-commit",
    load.projected.projected_content_digest,
  ),
  visibility_digest: digestOf("visibility", { default_synthesized: true, raw_read: false }),
  filter_digest: digestOf("filter", { filters: [] }),
  query_digest: digestOf("query", { query: null }),
  source_digest: digestOf("source", { sources: ["durable"] }),
  read_mode_digest: digestOf("read-mode", { mode: "default_synthesized" }),
  read_timestamp_epoch_seconds: readTimestampEpochSeconds,
});

export interface PreparedMemoryRead {
  readonly ports: ApplicationReadPorts;
  /** How many produced renders this snapshot is willing to serve, before paging. */
  readonly servableRenderCount: number;
}

export interface MemoryPageResult {
  readonly canonical_json: string;
  readonly attestation: ApplicationReadAttestation;
}

/**
 * One transaction-revalidated, already projected production read.  It carries
 * only content-free authority coordinates and a module-branded projection;
 * there is intentionally no structural credential/grant DTO here.
 */
export interface DirectAuthorizedMemoryProjectionLoad {
  readonly projected: ApplicationGrantProjectedTreeInputSnapshot;
  readonly owner_identity_digest: string;
  readonly application_identity_digest: string;
  readonly credential_identity_digest: string;
  readonly authorization_generation_digest: string;
  readonly grant_state_digest: string;
  readonly account_generation_digest: string;
  readonly db_now_epoch_seconds: number;
}

export interface DirectAuthorizedMemoryReadConfig {
  /** Fresh Firebase/PostgreSQL authorization plus graph projection per call. */
  readonly loadAuthorized: () => Promise<DirectAuthorizedMemoryProjectionLoad>;
  /** The production renderer remains injected and versioned by its RenderNode contract. */
  readonly produceRenders: (
    projected: ApplicationGrantProjectedTreeInputSnapshot,
  ) => Promise<readonly RenderNode[]>;
  readonly codecRootSecret: Uint8Array;
  readonly verifyCursor: ApplicationReadPorts["verifyCursor"];
  readonly issueCursor: ApplicationReadPorts["issueCursor"];
  readonly traceSink: (trace: ContentSafeRecallTrace) => void | Promise<void>;
  readonly granularity?: ReadItemGranularity;
  readonly acceptedCoverageState?: AcceptedCoverageState;
  readonly stmCoverageState?: StmCoverageState;
}

export interface DirectAuthorizedMemoryExportConfig {
  /** Fresh application authorization plus an exact reader-relative graph projection per call. */
  readonly loadAuthorized: () => Promise<DirectAuthorizedMemoryProjectionLoad>;
  readonly produceRenders: (
    projected: ApplicationGrantProjectedTreeInputSnapshot,
  ) => Promise<readonly RenderNode[]>;
  readonly codecRootSecret: Uint8Array;
  /** Exact maximum encoded bytes per complete-memory chunk; no item is split. */
  readonly chunkMaxBytes: number;
}

/**
 * Builds the read ports for one snapshot.
 *
 * Renders must be produced BEFORE the read begins, because `loadDurableRenders`
 * is synchronous while rendering is asynchronous. The pre-rendered set is
 * therefore memoized and returned on every call. This is safe, and is checked:
 * the read core recomputes the produced-render-set generation receipt on each
 * internal load and refuses the page if it disagrees, so a snapshot that
 * changed underneath the pre-render fails closed rather than serving stale
 * content.
 */
export const prepareMemoryRead = async (
  config: MemoryReadCompositionConfig,
): Promise<PreparedMemoryRead> => {
  const onPortCall = config.onPortCall ?? ((): void => {});
  // Runs the same gate the read will run, so a denial surfaces before any
  // render work happens rather than after. `principal_digest` covers only
  // owner/app/key, so it is stable across a later grant change — which is what
  // makes it a safe codec scope: revoking and re-granting must not renumber a
  // reader's memories.
  const prepareEvidence = inspectApplicationMemoryReadAuthorization(config.resolveAuthorization());

  const codecs = createReaderScopedOpaqueCodecs({
    root_secret: config.codecRootSecret,
    reader_projection_digest: prepareEvidence.principal_digest,
  });

  const cursorAdapter = createQaCursorAdapter({
    signing_keyset: config.cursorSigningKeyset,
    policy: {
      ...QA_CURSOR_POLICY,
      ttl_seconds: config.cursorTtlSeconds ?? QA_CURSOR_POLICY.ttl_seconds,
    },
  });

  /**
   * Reader-scoped, domain-separated frontier handle. Same construction as the
   * opaque-ref codecs (per-reader subkey, distinct label) but with the
   * `frontier-v1:` grammar the ratified parser expects.
   */
  const frontierSubkey = createHmac("sha256", Buffer.from(config.codecRootSecret))
    .update("omi.service.opaque-frontier.v1", "ascii")
    .update("\0", "ascii")
    .update(prepareEvidence.principal_digest, "ascii")
    .digest();
  const encodeFrontier = (internalFrontier: string): string =>
    `frontier-v1:${createHmac("sha256", frontierSubkey).update(internalFrontier, "utf8").digest("hex")}`;

  const preRenderLoad = config.loadCoherent();
  const preRenderProjection = readAfterApplicationAuthorization(config.resolveAuthorization(), () => ({
    // storage-provenance-ok(handed straight to readAfterApplicationAuthorization as its input; the render set is built from the PROJECTION it returns, and no value from this snapshot reaches the wire un-projected)
    snapshot: toStandardPrototypeJson(preRenderLoad.durable_snapshot),
    options: { account_timezone: preRenderLoad.account_timezone },
  }));

  const granularity = config.granularity ?? DEFAULT_READ_ITEM_GRANULARITY;
  // Conservative defaults: "we did not search it" is always true and leaks nothing.
  const declaredAcceptedState: AcceptedCoverageState = config.acceptedCoverageState ?? "bypassed";
  const declaredStmState: StmCoverageState = config.stmCoverageState ?? "bypassed";

  // Production is granularity-agnostic: the whole tree is rendered and the
  // selection happens here, through the SHARED selector. Rendering a pruned
  // tree would change a surviving rollup's render hash, so the granularities
  // would disagree about the bytes of an item they both contain.
  const allRenders = await produceQaRenders(preRenderProjection);
  const selectedNodeIds = new Set(
    selectNodesForGranularity(buildDeterministicAnchors(preRenderProjection).nodes, granularity)
      .map((structuralNode) => structuralNode.node_id),
  );
  const servedRenders = Object.freeze(
    allRenders
      .filter((render) => selectedNodeIds.has(render.node_id))
      .slice()
      .sort((left, right) => compareStrings(left.node_id, right.node_id)),
  );
  const synthesizedProjectionGenerationDigest =
    computeApplicationSynthesizedProjectionGenerationDigest(preRenderProjection, servedRenders);

  // THE ONE CONSTRUCTION SITE for ApplicationReadPorts. See the module header,
  // and PORT_REGISTRY in scripts/lint-import-graph.ts.
  const ports: ApplicationReadPorts = {
    resolveAttempt: () => {
      onPortCall("resolve");
      // Live, per attempt. Captured once here and reused by this attempt's
      // coherent load so the digest the cursor binds is the digest of the
      // request the authorization boundary actually validated.
      const authorization = config.resolveAuthorization();
      return {
        authorization_request: authorization,
        load_coherent: () => {
          onPortCall("coherent");
          const evidence = inspectApplicationMemoryReadAuthorization(authorization);
          const load = config.loadCoherent();
          // storage-provenance-ok(handed straight to readAfterApplicationAuthorization; every wire coordinate below is derived from projected.graph_generation / projected.projected_content_digest, never from this snapshot)
          const snapshot = toStandardPrototypeJson(load.durable_snapshot);

          // Project HERE, before deriving any coordinate the wire will see.
          //
          // The coherent load describes the whole durable corpus, including rows
          // this reader is not authorized to see. Deriving a frontier, generation
          // receipt, or cursor binding from it publishes the existence of those
          // rows: add one hidden record and the frontier and cursor change, while
          // the item list stays correctly filtered. That is an authorization
          // oracle, and `hidden-vs-absent.test.ts` failed on exactly it before
          // this change. Everything below is therefore derived from the projected
          // (authorization-scoped) generation and content digests instead.
          //
          // The core re-projects this same snapshot immediately afterwards; if the
          // two ever disagreed, the produced-render binding fails closed.
          const projected = readAfterApplicationAuthorization(authorization, () => ({
            snapshot,
            options: { account_timezone: load.account_timezone },
          }));
          const authorizedGraphGeneration = String(projected.graph_generation);
          const authorizedContentDigest = String(projected.projected_content_digest);
          const coverage = buildCoverage(
            declaredAcceptedState,
            declaredStmState,
            authorizedGraphGeneration,
            encodeFrontier,
          );

          return {
            projection_load: {
              snapshot,
              options: { account_timezone: load.account_timezone },
            },
            coverage,
            generations: buildGenerations(
              authorizedGraphGeneration,
              coverage.accepted.state,
              coverage.stm.state,
              evidence.authorization_digest,
              coverage.declared_frontier,
              granularity,
              synthesizedProjectionGenerationDigest,
            ),
            read_coordinates: buildReadCoordinates(
              authorizedGraphGeneration,
              authorizedContentDigest,
              authorization,
              evidence.authorization_digest,
              evidence.persisted_grant_state_digest,
              config.readTimestampEpochSeconds,
            ),
          };
        },
      };
    },
    // The read core rebinds every returned render against the freshly projected
    // input and recomputes the generation receipt, so returning the memoized
    // set cannot smuggle in renders from a different projection.
    loadDurableRenders: () => { onPortCall("durable"); return [...servedRenders]; },
    encodeVisibleKey: (tuple) => { onPortCall("visible"); return codecs.encodeVisibleKey(tuple); },
    encodeItemRef: (ref) => { onPortCall("item"); return codecs.encodeItemRef(ref); },
    encodeCitationRef: (closure) => { onPortCall("citation"); return codecs.encodeCitationRef(closure); },
    encodeTraceRef: (ref) => { onPortCall("trace"); return codecs.encodeTraceRef(ref); },
    verifyCursor: (cursor, attestation) => {
      onPortCall("verify");
      return cursorAdapter.verifyCursor(cursor, attestation);
    },
    issueCursor: (lastVisibleKey, attestation) => {
      onPortCall("issue");
      return cursorAdapter.issueCursor(lastVisibleKey, attestation);
    },
    traceSink: async (trace) => { onPortCall("sink"); await config.traceSink(trace); },
  };

  return Object.freeze({ ports, servableRenderCount: servedRenders.length });
};

/**
 * Reads one page of canonical ratified JSON through the prepared ports.
 *
 * The ratified keyset grammar is checked HERE, in the invalid-cursor error
 * currency, before the core sees the bytes. The core raises a plain `TypeError`
 * for a cursor that is too long or carries a non-printable byte, and a
 * `TypeError` is reported as an internal error rather than an invalid cursor —
 * so two mutations of one token produced two different public outcomes, which
 * tells an attacker which half of their guess was wrong.
 *
 * Measured on the REST door before this collapse: a 4096-character cursor
 * answered `400 bad_request`, a 4097-character one answered
 * `500 internal_server_error`. The MCP door already closed this at its own
 * composition; the REST door did not, because it had a different one.
 */
export const readMemoryPage = async (
  request: ApplicationSynthesizedPageRequest,
  prepared: PreparedMemoryRead,
): Promise<MemoryPageResult> => {
  if (request.cursor !== null && !isSyntacticallyRedeemableCursor(request.cursor)) {
    throw new InvalidMcpCursorError();
  }
  return readApplicationSynthesizedPageWithAttestation(request, prepared.ports);
};

const DIRECT_DIGEST = /^[a-f0-9]{64}$/;
const DIRECT_LOAD_KEYS = Object.freeze([
  "projected", "owner_identity_digest", "application_identity_digest",
  "credential_identity_digest", "authorization_generation_digest",
  "grant_state_digest", "account_generation_digest", "db_now_epoch_seconds",
]);

const snapshotDirectAuthorizedLoad = (
  value: unknown,
): DirectAuthorizedMemoryProjectionLoad => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype) {
    throw new TypeError("invalid direct authorized memory load");
  }
  const descriptors = Object.getOwnPropertyDescriptors(value);
  const actual = Reflect.ownKeys(descriptors);
  const expected = [...DIRECT_LOAD_KEYS].sort();
  if (actual.some((key) => typeof key !== "string")
    || actual.length !== expected.length
    || (actual as string[]).sort().some((key, index) => key !== expected[index])) {
    throw new TypeError("invalid direct authorized memory load");
  }
  for (const key of expected) {
    const descriptor = descriptors[key];
    if (!descriptor || !descriptor.enumerable || !("value" in descriptor)) {
      throw new TypeError("invalid direct authorized memory load");
    }
  }
  const record = Object.fromEntries(expected.map((key) => [key, descriptors[key]!.value])) as
    unknown as DirectAuthorizedMemoryProjectionLoad;
  if (!isApplicationGrantProjectedTreeInput(record.projected)
    || ![
      record.owner_identity_digest, record.application_identity_digest,
      record.credential_identity_digest, record.authorization_generation_digest,
      record.grant_state_digest, record.account_generation_digest,
    ].every((digest) => typeof digest === "string" && DIRECT_DIGEST.test(digest))
    || !Number.isSafeInteger(record.db_now_epoch_seconds)
    || record.db_now_epoch_seconds < 0) {
    throw new TypeError("invalid direct authorized memory load");
  }
  return Object.freeze({ ...record });
};

const directLoadSignature = (load: DirectAuthorizedMemoryProjectionLoad): string =>
  sha256CanonicalContent({
    version: "direct-authorized-memory-load-v1",
    graph_generation: load.projected.graph_generation,
    projected_content_digest: load.projected.projected_content_digest,
    projection_authorization_digest: load.projected.projection_authorization_digest,
    reader_projection_digest: load.projected.reader_projection_digest,
    owner_identity_digest: load.owner_identity_digest,
    application_identity_digest: load.application_identity_digest,
    credential_identity_digest: load.credential_identity_digest,
    authorization_generation_digest: load.authorization_generation_digest,
    grant_state_digest: load.grant_state_digest,
    account_generation_digest: load.account_generation_digest,
  });

const directFrontierEncoder = (
  rootSecret: Uint8Array,
  readerProjectionDigest: string,
): ((internalFrontier: string) => string) => {
  const subkey = createHmac("sha256", Buffer.from(rootSecret))
    .update("omi.service.opaque-frontier.v1", "ascii")
    .update("\0", "ascii")
    .update(readerProjectionDigest, "ascii")
    .digest();
  return (internalFrontier: string): string =>
    `frontier-v1:${createHmac("sha256", subkey).update(internalFrontier, "utf8").digest("hex")}`;
};

/**
 * Route-free direct product read over freshly authorized graph projections.
 *
 * It performs an authorized load before rendering, another after the awaited
 * renderer, the application read core's own two-pass coherence check, and one
 * final authorized load before any page bytes or trace leave this function.
 * Persisted semantic projections are not required or consulted.
 */
export const readDirectAuthorizedMemoryPage = async (
  request: ApplicationSynthesizedPageRequest,
  config: DirectAuthorizedMemoryReadConfig,
): Promise<MemoryPageResult> => {
  for (let attempt = 0; attempt < 2; attempt += 1) {
    const beforeRender = snapshotDirectAuthorizedLoad(await config.loadAuthorized());
    const allRenders = await config.produceRenders(beforeRender.projected);
    const afterRender = snapshotDirectAuthorizedLoad(await config.loadAuthorized());
    if (directLoadSignature(beforeRender) !== directLoadSignature(afterRender)) continue;

    const granularity = config.granularity ?? DEFAULT_READ_ITEM_GRANULARITY;
    const selectedNodeIds = new Set(
      selectNodesForGranularity(
        buildDeterministicAnchors(beforeRender.projected).nodes,
        granularity,
      ).map((node) => node.node_id),
    );
    const servedRenders = Object.freeze(
      [...allRenders]
        .filter((render) => selectedNodeIds.has(render.node_id))
        .sort((left, right) => compareStrings(left.node_id, right.node_id)),
    );
    const renderGeneration = computeApplicationSynthesizedProjectionGenerationDigest(
      beforeRender.projected,
      servedRenders,
    );
    const acceptedState = config.acceptedCoverageState ?? "bypassed";
    const stmState = config.stmCoverageState ?? "bypassed";
    const encodeFrontier = directFrontierEncoder(
      config.codecRootSecret,
      beforeRender.projected.reader_projection_digest,
    );
    const codecs = createReaderScopedOpaqueCodecs({
      root_secret: config.codecRootSecret,
      reader_projection_digest: beforeRender.projected.reader_projection_digest,
    });
    const readTimestamp = afterRender.db_now_epoch_seconds;
    const coherent = (load: DirectAuthorizedMemoryProjectionLoad) => {
      const coverage = buildCoverage(
        acceptedState,
        stmState,
        load.projected.graph_generation,
        encodeFrontier,
      );
      return Object.freeze({
        coverage,
        generations: buildGenerations(
          load.projected.graph_generation,
          coverage.accepted.state,
          coverage.stm.state,
          load.authorization_generation_digest,
          coverage.declared_frontier,
          granularity,
          renderGeneration,
        ),
        read_coordinates: buildDirectReadCoordinates(load, readTimestamp),
      });
    };
    let resolveCount = 0;
    const bufferedTraces: ContentSafeRecallTrace[] = [];
    const ports: ApplicationReadPorts = {
      resolveAttempt: () => {
        const load = resolveCount++ === 0 ? beforeRender : afterRender;
        return Object.freeze({
          authorized_projection: load.projected,
          coherent: coherent(load),
        });
      },
      loadDurableRenders: () => [...servedRenders],
      encodeVisibleKey: (tuple) => codecs.encodeVisibleKey(tuple),
      encodeItemRef: (ref) => codecs.encodeItemRef(ref),
      encodeCitationRef: (closure) => codecs.encodeCitationRef(closure),
      encodeTraceRef: (ref) => codecs.encodeTraceRef(ref),
      verifyCursor: config.verifyCursor,
      issueCursor: config.issueCursor,
      // Buffer only. No trace leaves before the final live authority load.
      traceSink: (trace) => { bufferedTraces.push(trace); },
    };
    const result = await readMemoryPage(request, Object.freeze({
      ports: Object.freeze(ports),
      servableRenderCount: servedRenders.length,
    }));

    const finalLoad = snapshotDirectAuthorizedLoad(await config.loadAuthorized());
    if (directLoadSignature(afterRender) !== directLoadSignature(finalLoad)) continue;

    // Telemetry is observational and cannot delay or change the authorized
    // page. Async sink failures are contained after the final fence.
    for (const trace of bufferedTraces) {
      try {
        const pending = config.traceSink(trace);
        if (pending && typeof (pending as Promise<void>).catch === "function") {
          void (pending as Promise<void>).catch(() => undefined);
        }
      } catch {
        // Content-safe telemetry failure never alters the product read.
      }
    }
    return result;
  }
  throw new ApplicationReadInvalidatedError();
};

/**
 * Route-free private export over one fully revalidated authorized projection.
 *
 * The export is assembled only from temporal-leaf renders, includes exact
 * claim/evidence lineage with reader-scoped opaque references, and is returned
 * only after a final live authorization/graph check. It chooses no route,
 * storage sink, approval workflow, retention duration, or sharing policy.
 */
export const exportDirectAuthorizedMemories = async (
  config: DirectAuthorizedMemoryExportConfig,
): Promise<OwnerMemoryExportBundle> => {
  for (let attempt = 0; attempt < 2; attempt += 1) {
    const beforeRender = snapshotDirectAuthorizedLoad(await config.loadAuthorized());
    const allRenders = await config.produceRenders(beforeRender.projected);
    const afterRender = snapshotDirectAuthorizedLoad(await config.loadAuthorized());
    if (directLoadSignature(beforeRender) !== directLoadSignature(afterRender)) continue;

    const leafIds = new Set(selectNodesForGranularity(
      buildDeterministicAnchors(beforeRender.projected).nodes,
      "temporal_leaf",
    ).map((node) => node.node_id));
    const renders = [...allRenders]
      .filter((render) => leafIds.has(render.node_id))
      .sort((left, right) => compareStrings(left.node_id, right.node_id));
    const codecs = createReaderScopedOpaqueCodecs({
      root_secret: config.codecRootSecret,
      reader_projection_digest: beforeRender.projected.reader_projection_digest,
    });
    const bundle = buildOwnerMemoryExport({
      projected: beforeRender.projected,
      renders,
      exported_at_epoch_seconds: afterRender.db_now_epoch_seconds,
      chunk_max_bytes: config.chunkMaxBytes,
      encode_ref: codecs.encodeMemoryExportRef,
    });
    const finalLoad = snapshotDirectAuthorizedLoad(await config.loadAuthorized());
    if (directLoadSignature(beforeRender) === directLoadSignature(finalLoad)) return bundle;
  }
  throw new ApplicationReadInvalidatedError();
};
