import { Database } from "bun:sqlite";
import { mkdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

import type {
  CachedModelResultValidation,
  ModelInitialPromptIdentity,
  ModelInvocationSuccess,
  ModelInvokeRequest,
  ModelPort,
} from "../drivers/model/port";

const DIGEST = /^[a-f0-9]{64}$/;
const PROCESS_LOCKS = new Map<string, () => void>();
let exitHookInstalled = false;

export type OfflineModelPipelineLockAttempt =
  | Readonly<{ kind: "acquired"; release: () => void }>
  | Readonly<{ kind: "busy" }>
  | Readonly<{ kind: "unavailable" }>;

const digest = (kind: "credential" | "explicit", value: string): string =>
  new Bun.CryptoHasher("sha256")
    .update(`offline-model-pipeline-v1\u0000${kind}\u0000${value}`)
    .digest("hex");

/** The returned coordinate is safe to persist locally; the input never is. */
export const offlineModelPipelineResourceDigest = (input: Readonly<{
  credential?: string;
  explicit_resource_id?: string;
}>): string => {
  const explicit = input.explicit_resource_id?.trim();
  if (explicit) return digest("explicit", explicit);
  if (!input.credential) throw new TypeError("offline model pipeline resource unavailable");
  return digest("credential", input.credential);
};

export const offlineModelPipelineLockRoot = (): string => {
  const configured = process.env["OMI_MODEL_PIPELINE_LOCK_DIR"]?.trim();
  return configured ? resolve(configured) : join(tmpdir(), "omi-model-pipeline-locks");
};

/**
 * SQLite owns the crash semantics: an EXCLUSIVE transaction is released by the
 * operating system even after SIGKILL. The database contains no rows or secret
 * material; its digest-only filename is the complete durable surface.
 */
export const tryAcquireOfflineModelPipelineLock = (
  resourceDigest: string,
  root = offlineModelPipelineLockRoot(),
): OfflineModelPipelineLockAttempt => {
  if (!DIGEST.test(resourceDigest)) return Object.freeze({ kind: "unavailable" });
  const absoluteRoot = resolve(root);
  let db: Database | undefined;
  try {
    mkdirSync(absoluteRoot, { recursive: true, mode: 0o700 });
    db = new Database(join(absoluteRoot, `pipeline-${resourceDigest}.sqlite`), { create: true });
    db.exec("PRAGMA busy_timeout = 0; BEGIN EXCLUSIVE");
    let released = false;
    const release = () => {
      if (released) return;
      released = true;
      try { db?.exec("ROLLBACK"); } catch { /* close still releases the OS lock */ }
      try { db?.close(); } catch { /* idempotent content-safe cleanup */ }
      db = undefined;
    };
    return Object.freeze({ kind: "acquired" as const, release });
  } catch (error) {
    try { db?.close(); } catch { /* content-safe classification below */ }
    const code = error && typeof error === "object"
      ? Object.getOwnPropertyDescriptor(error, "code")?.value
      : undefined;
    return Object.freeze({ kind: code === "SQLITE_BUSY" ? "busy" as const : "unavailable" as const });
  }
};

export const holdOfflineModelPipelineForProcess = (resourceDigest: string): void => {
  const root = offlineModelPipelineLockRoot();
  const coordinate = join(root, resourceDigest);
  if (PROCESS_LOCKS.has(coordinate)) return;
  const attempt = tryAcquireOfflineModelPipelineLock(resourceDigest, root);
  if (attempt.kind === "busy") throw new Error("offline model pipeline busy");
  if (attempt.kind === "unavailable") throw new Error("offline model pipeline unavailable");
  PROCESS_LOCKS.set(coordinate, attempt.release);
  if (!exitHookInstalled) {
    exitHookInstalled = true;
    process.once("exit", () => {
      for (const release of PROCESS_LOCKS.values()) release();
      PROCESS_LOCKS.clear();
    });
  }
};

type HoldResource = (resourceDigest: string) => void;

/**
 * Placed beneath the QA verdict cache: a hit never calls this port, while the
 * first real provider operation holds the resource until process exit.
 */
export const withOfflineModelPipelineExclusivity = (
  inner: ModelPort,
  resourceDigest: string,
  hold: HoldResource = holdOfflineModelPipelineForProcess,
): ModelPort => {
  if (!DIGEST.test(resourceDigest)) throw new TypeError("offline model pipeline invalid resource");
  let held = false;
  const ensureHeld = () => {
    if (held) return;
    hold(resourceDigest);
    held = true;
  };
  return Object.freeze({
    async invoke(request: ModelInvokeRequest): Promise<unknown> {
      ensureHeld();
      return inner.invoke(request);
    },
    initialPromptIdentity(request: ModelInvokeRequest): ModelInitialPromptIdentity | undefined {
      return inner.initialPromptIdentity?.(request);
    },
    async invokeWithMetadata(request: ModelInvokeRequest): Promise<ModelInvocationSuccess> {
      ensureHeld();
      if (inner.invokeWithMetadata) return inner.invokeWithMetadata(request);
      return {
        result: await inner.invoke(request),
        successful_prompt_digest: "0".repeat(64),
        attempt: 0,
      };
    },
    validateCachedResult(request: ModelInvokeRequest, candidate: unknown): CachedModelResultValidation {
      return inner.validateCachedResult?.(request, candidate) ?? { ok: false };
    },
    async render(request: { strategy: string; version: string; input: unknown }) {
      ensureHeld();
      return inner.render(request);
    },
    async compose(request: { strategy: string; version: string; input: unknown }) {
      ensureHeld();
      return inner.compose(request);
    },
  });
};
