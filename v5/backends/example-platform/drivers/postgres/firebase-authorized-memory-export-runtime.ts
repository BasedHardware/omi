import { isProxy } from "node:util/types";

import { ApplicationReadInvalidatedError } from "../../core/retrieve/application-read";
import {
  OWNER_MEMORY_EXPORT_MAX_CHUNK_BYTES,
  OWNER_MEMORY_EXPORT_MIN_CHUNK_BYTES,
} from "../../core/retrieve/owner-memory-export";
import type { ApplicationGrantProjectedTreeInputSnapshot } from
  "../../core/retrieve/authorization-boundary";
import type { RenderNode } from "../../core/retrieve/render";
import { exportDirectAuthorizedMemories } from
  "../../apps/service/composition/memory-read";
import {
  createPostgresFirebaseAuthorizedGraphSnapshotRuntimeForCapability,
  projectFirebaseAuthorizedGraphSnapshotLoad,
  type PostgresFirebaseAuthorizedGraphSnapshotRuntimeOptions,
} from "./firebase-authorized-graph-snapshot-runtime";

const RUNTIME_PORT: unique symbol = Symbol("postgres-firebase-authorized-memory-export-runtime");

export interface FirebaseAuthorizedMemoryExportProductOptions {
  readonly account_timezone: string;
  readonly codec_root_secret: Uint8Array;
  readonly produce_renders: (
    projected: ApplicationGrantProjectedTreeInputSnapshot,
  ) => Promise<readonly RenderNode[]>;
  readonly chunk_max_bytes: number;
}

export interface PostgresFirebaseAuthorizedMemoryExportRuntimeOptions {
  readonly authorization: PostgresFirebaseAuthorizedGraphSnapshotRuntimeOptions;
  readonly product: FirebaseAuthorizedMemoryExportProductOptions;
}

export type FirebaseAuthorizedMemoryExportOutcome =
  | Readonly<{
      kind: "denied";
      outcome: "authentication" | "authorization" | "stale_epoch" | "unavailable";
    }>
  | Readonly<{ kind: "invalidated" }>
  | Readonly<{ kind: "unavailable" }>
  | Readonly<{
      kind: "loaded";
      manifest_json: string;
      chunk_json: readonly string[];
    }>;

export interface PostgresFirebaseAuthorizedMemoryExportRuntime {
  readonly [RUNTIME_PORT]: true;
  export(
    idToken: string,
    nowEpochSeconds: number,
  ): Promise<FirebaseAuthorizedMemoryExportOutcome>;
}

class ClosedGraphLoad extends Error {
  constructor(readonly outcome: Extract<
    FirebaseAuthorizedMemoryExportOutcome,
    { readonly kind: "denied" | "unavailable" }
  >) {
    super("authorized export graph load closed");
    this.name = "ClosedGraphLoad";
  }
}

const exactRecord = (value: unknown, expected: readonly string[]): Record<string, unknown> => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype) {
    throw new TypeError("invalid Firebase-authorized memory export runtime options");
  }
  const descriptors = Object.getOwnPropertyDescriptors(value);
  const actual = Reflect.ownKeys(descriptors);
  const wanted = [...expected].sort();
  if (actual.some((key) => typeof key !== "string") || actual.length !== wanted.length
    || (actual as string[]).sort().some((key, index) => key !== wanted[index])) {
    throw new TypeError("invalid Firebase-authorized memory export runtime options");
  }
  const result: Record<string, unknown> = {};
  for (const key of wanted) {
    const descriptor = descriptors[key];
    if (!descriptor || !descriptor.enumerable || !("value" in descriptor)) {
      throw new TypeError("invalid Firebase-authorized memory export runtime options");
    }
    result[key] = descriptor.value;
  }
  return result;
};

/**
 * Route-free private export composition. The exact `memories.export`
 * capability is checked and revalidated independently of `memories.read`.
 * No sink, route, retention rule, approval workflow, or deployment is chosen.
 */
export const createPostgresFirebaseAuthorizedMemoryExportRuntime = (
  optionsValue: PostgresFirebaseAuthorizedMemoryExportRuntimeOptions,
): PostgresFirebaseAuthorizedMemoryExportRuntime => {
  const options = exactRecord(optionsValue, ["authorization", "product"]);
  const product = exactRecord(options["product"], [
    "account_timezone", "codec_root_secret", "produce_renders", "chunk_max_bytes",
  ]);
  const timezone = product["account_timezone"];
  const secret = product["codec_root_secret"];
  const produceRenders = product["produce_renders"];
  const chunkMaxBytes = product["chunk_max_bytes"];
  if (typeof timezone !== "string" || timezone.length < 1 || timezone.length > 256
    || timezone.includes("\0") || !(secret instanceof Uint8Array) || isProxy(secret)
    || secret.byteLength < 32 || secret.byteLength > 4_096
    || typeof produceRenders !== "function" || isProxy(produceRenders)
    || !Number.isSafeInteger(chunkMaxBytes)
    || (chunkMaxBytes as number) < OWNER_MEMORY_EXPORT_MIN_CHUNK_BYTES
    || (chunkMaxBytes as number) > OWNER_MEMORY_EXPORT_MAX_CHUNK_BYTES) {
    throw new TypeError("invalid Firebase-authorized memory export runtime options");
  }
  const graph = createPostgresFirebaseAuthorizedGraphSnapshotRuntimeForCapability(
    options["authorization"] as PostgresFirebaseAuthorizedGraphSnapshotRuntimeOptions,
    "memories.export",
  );
  const stableSecret = new Uint8Array(secret);

  return Object.freeze({
    [RUNTIME_PORT]: true as const,
    async export(idToken: string, nowEpochSeconds: number) {
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
        return projectFirebaseAuthorizedGraphSnapshotLoad(loaded, timezone as string);
      };
      try {
        const bundle = await exportDirectAuthorizedMemories({
          loadAuthorized,
          produceRenders: produceRenders as FirebaseAuthorizedMemoryExportProductOptions["produce_renders"],
          codecRootSecret: stableSecret,
          chunkMaxBytes: chunkMaxBytes as number,
        });
        return Object.freeze({
          kind: "loaded" as const,
          manifest_json: bundle.manifest_json,
          chunk_json: Object.freeze([...bundle.chunk_json]),
        });
      } catch (error) {
        if (error instanceof ClosedGraphLoad) return error.outcome;
        if (error instanceof ApplicationReadInvalidatedError) {
          return Object.freeze({ kind: "invalidated" as const });
        }
        return Object.freeze({ kind: "unavailable" as const });
      }
    },
  });
};
