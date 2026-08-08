// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMCORE-006)
// domain-pending(DIV-DOMCORE-008)
// domain-pending(DIV-DOMAPPS-001)
// domain-pending(DIV-DOMAPPS-006)
// domain-pending(DIV-DOMX-001)
// domain-pending(DIV-DOMX-006)
import { createHash, createHmac } from "node:crypto";

import {
  computeApplicationSynthesizedProjectionGenerationDigest,
  readApplicationSynthesizedPageWithAttestation,
  type ApplicationReadAttestation,
  type ApplicationReadCoherentCoordinates,
  type ApplicationReadPorts,
  type ApplicationReadSnapshotAttestation,
  type ApplicationRecallGenerationDigests,
  type ApplicationSynthesizedPageRequest,
} from "../../../core/retrieve/application-read";
import {
  inspectApplicationMemoryReadAuthorization,
  readAfterApplicationAuthorization,
  type ApplicationMemoryReadAuthorizationRequest,
} from "../../../core/retrieve/authorization-boundary";
import type {
  AcceptedCoverageState,
  ContentSafeRecallTrace,
  RecallCompletenessInput,
  StmCoverageState,
} from "../../../core/retrieve/recall-integrity";
import { renderStructuralTree, type RenderNode } from "../../../core/retrieve/render";
import { buildDeterministicAnchors } from "../../../core/retrieve/tree";
import type { GraphSnapshot } from "../../../core/retrieve";
import {
  asOpaqueVisibleKeyset,
  issueMcpCursor,
  verifyMcpCursor,
  type McpCursorBindings,
  type McpCursorSigningKeyset,
} from "../../mcp/cursor";
import { createReaderScopedOpaqueCodecs } from "../codecs/opaque-refs";
// The canonical, transport-neutral granularity module. BE-FLOW landed it in
// core/ while this lane had a local copy; there must be exactly one selector or
// the two doors drift, which is the entire point of the ruling. The local copy
// is deleted.
import {
  DEFAULT_READ_ITEM_GRANULARITY,
  selectNodesForGranularity,
  type ReadItemGranularity,
} from "../../../core/retrieve/granularity";
import { createQaDeterministicSynthesizer } from "./qa-synthesizer";

/**
 * The composition root for the application memory read path.
 *
 * Every layer of this flow already existed and was individually green, but
 * nothing joined them: `readApplicationSynthesizedPage`, the SQLite QA loader,
 * and the signed cursor were each referenced only by their own unit tests. This
 * module is the single place where the authorization boundary, the projection,
 * the deterministic render set, the opaque codecs, and the signed cursor are
 * wired into one real read. There must be exactly one of these.
 *
 * SQLite is QA-only here and is never production authority. No production
 * store, concurrency model, or deployment topology is selected by this file.
 */

/** Version tag for the cursor policy this composition binds into every cursor. */
const CURSOR_POLICY_VERSION = "application-read-cursor-policy-v1";
const RENDER_STRATEGY = "application-read-qa";
const RENDER_MODEL_VERSION = "qa-deterministic-synthesizer-v1";
const RENDER_PROMPT_VERSION = "qa-prompt-v1";
const RENDER_POLICY_VERSION = "qa-policy-v1";
const RENDER_SCHEMA_VERSION = "qa-schema-v1";


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

const sha256Hex = (value: string): string => createHash("sha256").update(value, "utf8").digest("hex");

const compareStrings = (left: string, right: string): number =>
  left < right ? -1 : left > right ? 1 : 0;

const canonicalJson = (value: unknown): string => {
  if (value === null || typeof value === "boolean" || typeof value === "number"
    || typeof value === "string") return JSON.stringify(value) ?? "null";
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  if (typeof value !== "object") return "null";
  const record = value as Record<string, unknown>;
  return `{${Object.keys(record).sort(compareStrings)
    .map((key) => `${JSON.stringify(key)}:${canonicalJson(record[key])}`).join(",")}}`;
};

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

export interface MemoryReadCompositionConfig {
  /** Zero-argument coherent loader; called fresh for every internal revalidation. */
  readonly loadCoherent: () => CoherentQaLoad;
  readonly authorizationRequest: ApplicationMemoryReadAuthorizationRequest;
  /** HMAC root for the reader-scoped opaque handles. QA-supplied; never a production secret. */
  readonly codecRootSecret: Uint8Array;
  readonly cursorSigningKeyset: McpCursorSigningKeyset;
  readonly cursorTtlSeconds: number;
  /**
   * The authoritative read timestamp for this snapshot. Passed in, never read
   * from a clock, so the two internal revalidation loads agree and the flow
   * stays hermetic.
   */
  readonly readTimestampEpochSeconds: number;
  readonly traceSink: (trace: ContentSafeRecallTrace) => void | Promise<void>;
  /**
   * Which synthesized nodes count as served memories. EXPLICIT, never implied
   * by the transport - see ./granularity.ts. Defaults to the app-facing
   * granularity when omitted.
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
   */
  // domain-pending(DIV-DOMCORE-006)
  readonly acceptedCoverageState?: AcceptedCoverageState;
  // domain-pending(DIV-DOMCORE-006)
  readonly stmCoverageState?: StmCoverageState;
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

const buildGenerations = (
  authorizedGraphGeneration: string,
  authorizedContentDigest: string,
  acceptedState: AcceptedCoverageState,
  stmState: StmCoverageState,
  authorizationDigest: string,
  synthesizedProjectionGenerationDigest: string,
): ApplicationRecallGenerationDigests => Object.freeze({
  authorization_generation_digest: authorizationDigest,
  synthesized_projection_generation_digest: synthesizedProjectionGenerationDigest,
  durable_generation_digest: sha256Hex(canonicalJson({
    kind: "durable-generation",
    authorized_graph_generation: authorizedGraphGeneration,
  })),
  // Only the overlay's reported STATE, never its row count or row ids. The
  // state is already published in the completeness envelope, so binding it
  // reveals nothing the client cannot already read.
  overlay_generation_digest: sha256Hex(canonicalJson({
    kind: "overlay-generation",
    state: stmState,
  })),
  declared_generation_digest: sha256Hex(canonicalJson({
    kind: "declared-generation",
    authorized_graph_generation: authorizedGraphGeneration,
  })),
  accepted_generation_digest: sha256Hex(canonicalJson({
    kind: "accepted-generation",
    state: acceptedState,
  })),
  stm_generation_digest: sha256Hex(canonicalJson({
    kind: "stm-generation",
    state: stmState,
  })),

});

const buildReadCoordinates = (
  authorizedGraphGeneration: string,
  authorizedContentDigest: string,
  authorization: ApplicationMemoryReadAuthorizationRequest,
  authorizationDigest: string,
  persistedGrantStateDigest: string,
  readTimestampEpochSeconds: number,
): ApplicationReadCoherentCoordinates => Object.freeze({
  owner_identity_digest: sha256Hex(`owner:${authorization.owner_account_id}`),
  application_identity_digest: sha256Hex(`app:${authorization.credential.app_id ?? ""}`),
  credential_identity_digest: sha256Hex(`credential:${authorization.credential.key_id ?? ""}`),
  // The core cross-checks this against the authorization generation digest.
  authorization_state_digest: authorizationDigest,
  grant_state_digest: persistedGrantStateDigest,
  // Authorization-scoped, NOT the ledger head. See buildGenerations.
  account_head_digest: sha256Hex(canonicalJson({
    kind: "account-head",
    authorized_graph_generation: authorizedGraphGeneration,
  })),
  authorized_graph_digest: sha256Hex(canonicalJson({
    kind: "authorized-graph",
    authorized_graph_generation: authorizedGraphGeneration,
  })),
  coherent_projection_commit_digest: sha256Hex(canonicalJson({
    kind: "coherent-projection-commit",
    authorized_content_digest: authorizedContentDigest,
  })),
  // This read applies the application-default visibility, no filter, and no
  // query. They are still distinct bound coordinates so that introducing any of
  // them later invalidates outstanding cursors rather than silently reusing them.
  visibility_digest: sha256Hex("visibility:application-default-synthesized-v1"),
  filter_digest: sha256Hex("filter:none-v1"),
  query_digest: sha256Hex("query:none-v1"),
  source_digest: sha256Hex("source:durable-only-v1"),
  read_mode_digest: sha256Hex("read-mode:synthesized-latest-projection-v1"),
  read_timestamp_epoch_seconds: readTimestampEpochSeconds,
});

/**
 * Projects a read attestation onto the fifteen signed cursor bindings.
 *
 * The binding set is fixed at fifteen fields, but the attestation carries more
 * state than that - the coverage envelope, the projected content digest, and
 * the durable/overlay/declared/accepted/STM generations. Those residual fields
 * are folded into `cursor_policy_digest`. Without that fold a cursor minted
 * against one coverage state would verify against a different one, which is a
 * replay across snapshots: a page-two request could silently be answered from a
 * snapshot whose completeness no longer matches the page-one the client saw.
 */
// domain-pending(DIV-DOMX-001)
const attestationToCursorBindings = (
  attestation: ApplicationReadSnapshotAttestation,
): McpCursorBindings => Object.freeze({
  owner_digest: attestation.owner_identity_digest,
  app_digest: attestation.application_identity_digest,
  credential_key_digest: attestation.credential_identity_digest,
  authorization_generation_digest: attestation.authorization_state_digest,
  grant_generation_digest: attestation.grant_state_digest,
  account_generation_digest: attestation.account_head_digest,
  graph_generation_digest: attestation.authorized_graph_digest,
  projection_generation_digest: attestation.synthesized_projection_generation_digest,
  projection_commit_digest: attestation.coherent_projection_commit_digest,
  visibility_digest: attestation.visibility_digest,
  filter_digest: attestation.filter_digest,
  query_digest: attestation.query_digest,
  cursor_policy_digest: sha256Hex(canonicalJson({
    policy: CURSOR_POLICY_VERSION,
    projected_content_digest: attestation.projected_content_digest,
    durable_generation_digest: attestation.durable_generation_digest,
    overlay_generation_digest: attestation.overlay_generation_digest,
    declared_generation_digest: attestation.declared_generation_digest,
    accepted_generation_digest: attestation.accepted_generation_digest,
    stm_generation_digest: attestation.stm_generation_digest,
    coverage: attestation.coverage,
  })),
  source_digest: attestation.source_digest,
  read_mode_digest: attestation.read_mode_digest,
});

/**
 * Only grounded, current renders may be served. An empty, failed or stale render
 * has no synthesized projection to publish - and presenting one as absence would
 * be a lie.
 */
const isServableRender = (render: RenderNode): boolean =>
  render.status === "ready"
  && render.render_hash !== null
  && render.summary_text !== null
  && render.summary_text.length > 0
  && !render.stale
  && render.citations.length > 0;

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
  const authorization = config.authorizationRequest;
  // Runs the same gate the read will run, so a denial surfaces before any
  // render work happens rather than after.
  const evidence = inspectApplicationMemoryReadAuthorization(authorization);

  const codecs = createReaderScopedOpaqueCodecs({
    root_secret: config.codecRootSecret,
    reader_projection_digest: evidence.principal_digest,
  });

  /**
   * Reader-scoped, domain-separated frontier handle. Same construction as the
   * opaque-ref codecs (per-reader subkey, distinct label) but with the
   * `frontier-v1:` grammar the ratified parser expects.
   */
  const frontierSubkey = createHmac("sha256", Buffer.from(config.codecRootSecret))
    .update("omi.service.opaque-frontier.v1", "ascii")
    .update("\0", "ascii")
    .update(evidence.principal_digest, "ascii")
    .digest();
  const encodeFrontier = (internalFrontier: string): string =>
    `frontier-v1:${createHmac("sha256", frontierSubkey).update(internalFrontier, "utf8").digest("hex")}`;

  const preRenderLoad = config.loadCoherent();
  const preRenderProjection = readAfterApplicationAuthorization(authorization, () => ({
    // storage-provenance-ok(handed straight to readAfterApplicationAuthorization as its input; the render set is built from the PROJECTION it returns, and no value from this snapshot reaches the wire un-projected)
    snapshot: toStandardPrototypeJson(preRenderLoad.durable_snapshot),
    options: { account_timezone: preRenderLoad.account_timezone },
  }));

  const granularity = config.granularity ?? DEFAULT_READ_ITEM_GRANULARITY;
  // Conservative defaults: "we did not search it" is always true and leaks nothing.
  const declaredAcceptedState: AcceptedCoverageState = config.acceptedCoverageState ?? "bypassed";
  const declaredStmState: StmCoverageState = config.stmCoverageState ?? "bypassed";
  const tree = buildDeterministicAnchors(preRenderProjection);
  const allRenders = await renderStructuralTree(
    tree,
    preRenderProjection,
    createQaDeterministicSynthesizer(),
    {
      strategy: RENDER_STRATEGY,
      model_version: RENDER_MODEL_VERSION,
      prompt_version: RENDER_PROMPT_VERSION,
      policy_version: RENDER_POLICY_VERSION,
      schema_version: RENDER_SCHEMA_VERSION,
    },
  );
  const selectedNodeIds = new Set(
    selectNodesForGranularity(tree.nodes, granularity).map((node) => node.node_id),
  );
  const servedRenders = Object.freeze(
    allRenders
      .filter((render) => selectedNodeIds.has(render.node_id) && isServableRender(render))
      .slice()
      .sort((left, right) => compareStrings(left.node_id, right.node_id)),
  );
  const synthesizedProjectionGenerationDigest =
    computeApplicationSynthesizedProjectionGenerationDigest(preRenderProjection, servedRenders);

  const ports: ApplicationReadPorts = {
    resolveAttempt: () => ({
      authorization_request: authorization,
      load_coherent: () => {
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
            authorizedContentDigest,
            coverage.accepted.state,
            coverage.stm.state,
            evidence.authorization_digest,
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
    }),
    // The read core rebinds every returned render against the freshly projected
    // input and recomputes the generation receipt, so returning the memoized
    // set cannot smuggle in renders from a different projection.
    loadDurableRenders: () => [...servedRenders],
    encodeVisibleKey: codecs.encodeVisibleKey,
    encodeItemRef: codecs.encodeItemRef,
    encodeCitationRef: codecs.encodeCitationRef,
    encodeTraceRef: codecs.encodeTraceRef,
    verifyCursor: (cursor, attestation) => verifyMcpCursor(
      cursor,
      {
        bindings: attestationToCursorBindings(attestation),
        // The signed page read timestamp, never an ambient decode time.
        now_epoch_seconds: attestation.read_timestamp_epoch_seconds,
      },
      config.cursorSigningKeyset,
    ).last_visible_key,
    issueCursor: (lastVisibleKey, attestation) => issueMcpCursor(
      {
        last_visible_key: asOpaqueVisibleKeyset(lastVisibleKey),
        bindings: attestationToCursorBindings(attestation),
        issued_at_epoch_seconds: attestation.read_timestamp_epoch_seconds,
        ttl_seconds: config.cursorTtlSeconds,
      },
      config.cursorSigningKeyset,
    ),
    traceSink: config.traceSink,
  };

  return Object.freeze({ ports, servableRenderCount: servedRenders.length });
};

/** Reads one page of canonical ratified JSON through the prepared ports. */
export const readMemoryPage = async (
  request: ApplicationSynthesizedPageRequest,
  prepared: PreparedMemoryRead,
): Promise<MemoryPageResult> =>
  readApplicationSynthesizedPageWithAttestation(request, prepared.ports);
