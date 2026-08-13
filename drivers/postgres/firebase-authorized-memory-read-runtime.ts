import { isProxy } from "node:util/types";

import { isWellFormedAccountId } from "../../core/control/account-control";
import {
  ApplicationReadInvalidatedError,
  type ApplicationReadPorts,
  type ApplicationSynthesizedPageRequest,
} from "../../core/retrieve/application-read";
import type { AcceptedCoverageState, ContentSafeRecallTrace, StmCoverageState } from
  "../../core/retrieve/recall-integrity";
import type { RenderNode } from "../../core/retrieve/render";
import type { ApplicationGrantProjectedTreeInputSnapshot } from
  "../../core/retrieve/authorization-boundary";
import { isInvalidMcpCursorError } from "../../apps/mcp/cursor";
import { createFirebaseIdentityVerifier } from "../../apps/service/auth/firebase-identity";
import {
  readDirectAuthorizedMemoryPage,
} from "../../apps/service/composition/memory-read";
import {
  createPostgresFirebaseAuthorizedGraphSnapshotRuntime,
  projectFirebaseAuthorizedGraphSnapshotLoad,
  type PostgresFirebaseAuthorizedGraphSnapshotRuntimeOptions,
} from "./firebase-authorized-graph-snapshot-runtime";

const RUNTIME_PORT: unique symbol = Symbol("postgres-firebase-authorized-memory-read-runtime");
const ACCEPTED_COVERAGE_STATES = new Set<AcceptedCoverageState>([
  "searched", "no_eligible", "pending", "unavailable", "stale", "bypassed",
  "source_bound", "time_bound", "policy_bound",
]);
const STM_COVERAGE_STATES = new Set<StmCoverageState>([
  "searched", "no_eligible", "unavailable", "stale", "bypassed",
  "source_bound", "time_bound", "policy_bound",
]);

export interface FirebaseAuthorizedMemoryProductOptions {
  readonly account_timezone: string;
  readonly codec_root_secret: Uint8Array;
  readonly produce_renders: (
    projected: ApplicationGrantProjectedTreeInputSnapshot,
  ) => Promise<readonly RenderNode[]>;
  readonly verify_cursor: ApplicationReadPorts["verifyCursor"];
  readonly issue_cursor: ApplicationReadPorts["issueCursor"];
  readonly trace_sink: (trace: ContentSafeRecallTrace) => void | Promise<void>;
  readonly accepted_coverage_state: AcceptedCoverageState;
  readonly stm_coverage_state: StmCoverageState;
}

export interface PostgresFirebaseAuthorizedMemoryReadRuntimeOptions {
  readonly authorization: PostgresFirebaseAuthorizedGraphSnapshotRuntimeOptions;
  readonly product: FirebaseAuthorizedMemoryProductOptions;
}

export type FirebaseAuthorizedMemoryReadOutcome =
  | Readonly<{
      kind: "denied";
      outcome: "authentication" | "authorization" | "stale_epoch" | "unavailable";
    }>
  | Readonly<{ kind: "invalidated" }>
  | Readonly<{ kind: "invalid_cursor" }>
  | Readonly<{ kind: "unavailable" }>
  | Readonly<{ kind: "loaded"; canonical_json: string }>;

export interface PostgresFirebaseAuthorizedMemoryReadRuntime {
  readonly [RUNTIME_PORT]: true;
  authenticate(idToken: string, nowEpochSeconds: number): Promise<boolean>;
  read(
    idToken: string,
    nowEpochSeconds: number,
    request: ApplicationSynthesizedPageRequest,
  ): Promise<FirebaseAuthorizedMemoryReadOutcome>;
  /** Internal consumer read that additionally binds the credential to an admitted owner. */
  readForAccount(
    idToken: string,
    nowEpochSeconds: number,
    expectedAccountId: string,
    request: ApplicationSynthesizedPageRequest,
  ): Promise<FirebaseAuthorizedMemoryReadOutcome>;
}

class ClosedGraphLoad extends Error {
  constructor(readonly outcome: Extract<
    FirebaseAuthorizedMemoryReadOutcome,
    { readonly kind: "denied" | "unavailable" }
  >) {
    super("authorized graph load closed");
    this.name = "ClosedGraphLoad";
  }
}

const exactRecord = (value: unknown, expected: readonly string[]): Record<string, unknown> => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype) {
    throw new TypeError("invalid Firebase-authorized memory read runtime options");
  }
  const descriptors = Object.getOwnPropertyDescriptors(value);
  const actual = Reflect.ownKeys(descriptors);
  const wanted = [...expected].sort();
  if (actual.some((key) => typeof key !== "string") || actual.length !== wanted.length
    || (actual as string[]).sort().some((key, index) => key !== wanted[index])) {
    throw new TypeError("invalid Firebase-authorized memory read runtime options");
  }
  for (const key of wanted) {
    const descriptor = descriptors[key];
    if (!descriptor || !descriptor.enumerable || !("value" in descriptor)) {
      throw new TypeError("invalid Firebase-authorized memory read runtime options");
    }
  }
  return Object.fromEntries(wanted.map((key) => [key, descriptors[key]!.value]));
};

const callable = (value: unknown): ((...args: never[]) => unknown) => {
  if (typeof value !== "function" || isProxy(value)) {
    throw new TypeError("invalid Firebase-authorized memory read runtime options");
  }
  return value as (...args: never[]) => unknown;
};

/**
 * The route-free production composition for the first direct product read.
 * It deliberately owns no Hono route and does not change runtime activation.
 */
export const createPostgresFirebaseAuthorizedMemoryReadRuntime = (
  optionsValue: PostgresFirebaseAuthorizedMemoryReadRuntimeOptions,
): PostgresFirebaseAuthorizedMemoryReadRuntime => {
  const options = exactRecord(optionsValue, ["authorization", "product"]);
  const product = exactRecord(options.product, [
    "account_timezone", "codec_root_secret", "produce_renders", "verify_cursor",
    "issue_cursor", "trace_sink", "accepted_coverage_state", "stm_coverage_state",
  ]);
  const timezone = product.account_timezone;
  const secret = product.codec_root_secret;
  if (typeof timezone !== "string" || timezone.length < 1 || timezone.length > 256
    || timezone.includes("\0") || !(secret instanceof Uint8Array) || isProxy(secret)
    || secret.byteLength < 32 || secret.byteLength > 4_096
    || !ACCEPTED_COVERAGE_STATES.has(product.accepted_coverage_state as AcceptedCoverageState)
    || !STM_COVERAGE_STATES.has(product.stm_coverage_state as StmCoverageState)) {
    throw new TypeError("invalid Firebase-authorized memory read runtime options");
  }
  const produceRenders = callable(product.produce_renders) as FirebaseAuthorizedMemoryProductOptions["produce_renders"];
  const verifyCursor = callable(product.verify_cursor) as ApplicationReadPorts["verifyCursor"];
  const issueCursor = callable(product.issue_cursor) as ApplicationReadPorts["issueCursor"];
  const traceSink = callable(product.trace_sink) as FirebaseAuthorizedMemoryProductOptions["trace_sink"];
  const authorization = options.authorization as unknown as PostgresFirebaseAuthorizedGraphSnapshotRuntimeOptions;
  const identityVerifier = createFirebaseIdentityVerifier({
    project_id: authorization.project_id,
    runtime_mode: authorization.runtime_mode,
    adapter: authorization.id_token_adapter,
  });
  const graph = createPostgresFirebaseAuthorizedGraphSnapshotRuntime(
    authorization,
  );
  const stableSecret = new Uint8Array(secret);

  const readPage = async (
    idToken: string,
    nowEpochSeconds: number,
    expectedAccountId: string | null,
    request: ApplicationSynthesizedPageRequest,
  ): Promise<FirebaseAuthorizedMemoryReadOutcome> => {
    if (expectedAccountId !== null && !isWellFormedAccountId(expectedAccountId)) {
      return Object.freeze({ kind: "denied" as const, outcome: "authorization" as const });
    }
    const loadAuthorized = async () => {
      const loaded = await graph.load(idToken, nowEpochSeconds);
      if (loaded.kind === "denied") {
        throw new ClosedGraphLoad(Object.freeze({
          kind: "denied" as const,
          outcome: loaded.outcome,
        }));
      }
      if (loaded.kind === "unavailable") {
        throw new ClosedGraphLoad(Object.freeze({ kind: "unavailable" as const }));
      }
      if (expectedAccountId !== null
        && loaded.snapshot.owner_account_id !== expectedAccountId) {
        throw new ClosedGraphLoad(Object.freeze({
          kind: "denied" as const,
          outcome: "authorization" as const,
        }));
      }
      return projectFirebaseAuthorizedGraphSnapshotLoad(loaded, timezone as string);
    };
    try {
      const page = await readDirectAuthorizedMemoryPage(request, {
        loadAuthorized,
        produceRenders,
        codecRootSecret: stableSecret,
        verifyCursor,
        issueCursor,
        traceSink,
        acceptedCoverageState: product.accepted_coverage_state as AcceptedCoverageState,
        stmCoverageState: product.stm_coverage_state as StmCoverageState,
      });
      return Object.freeze({ kind: "loaded" as const, canonical_json: page.canonical_json });
    } catch (error) {
      if (error instanceof ClosedGraphLoad) return error.outcome;
      if (isInvalidMcpCursorError(error)) {
        return Object.freeze({ kind: "invalid_cursor" as const });
      }
      if (error instanceof ApplicationReadInvalidatedError) {
        return Object.freeze({ kind: "invalidated" as const });
      }
      return Object.freeze({ kind: "unavailable" as const });
    }
  };

  return Object.freeze({
    [RUNTIME_PORT]: true as const,
    async authenticate(idToken: string, nowEpochSeconds: number) {
      return await identityVerifier.resolve(idToken, nowEpochSeconds) !== null;
    },
    async read(
      idToken: string,
      nowEpochSeconds: number,
      request: ApplicationSynthesizedPageRequest,
    ) {
      return readPage(idToken, nowEpochSeconds, null, request);
    },
    async readForAccount(
      idToken: string,
      nowEpochSeconds: number,
      expectedAccountId: string,
      request: ApplicationSynthesizedPageRequest,
    ) {
      return readPage(idToken, nowEpochSeconds, expectedAccountId, request);
    },
  });
};
