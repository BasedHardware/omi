import { homedir } from "node:os";
import { isAbsolute, relative, resolve, sep } from "node:path";
import { types } from "node:util";

export const PRODUCTION_ARTIFACT_VERSION = "production-dependency-artifact-v1" as const;
export const PRODUCTION_ARTIFACT_BUN_VERSION = "1.3.14" as const;
export const PRODUCTION_ARTIFACT_COMMAND_TIMEOUT_MS = 600_000 as const;
export const PRODUCTION_ARTIFACT_COMMAND_MAX_BUFFER_BYTES = 8 * 1_024 * 1_024;
export const PRODUCTION_ARTIFACT_MAX_ALLOCATED_KIB = 512 * 1_024;

export interface ProductionDependencyArtifactPlan {
  readonly version: typeof PRODUCTION_ARTIFACT_VERSION;
  readonly project_root: string;
  readonly output_root: string;
  readonly source_commit: string;
  readonly limits: {
    readonly command_timeout_ms: typeof PRODUCTION_ARTIFACT_COMMAND_TIMEOUT_MS;
    readonly command_max_buffer_bytes: number;
    readonly max_allocated_kib: number;
  };
  readonly commands: readonly (readonly string[])[];
}

const commitPattern = /^[0-9a-f]{40}$/;

const inside = (root: string, candidate: string): boolean => {
  const path = relative(root, candidate);
  return path === "" || (path !== ".." && !path.startsWith(`..${sep}`) && !isAbsolute(path));
};

export const productionDependencyArtifactPlan = (input: Readonly<{
  project_root: string;
  output_root: string;
  source_commit: string;
  bun_version: string;
  worktree_status: string;
}>): Readonly<ProductionDependencyArtifactPlan> => {
  if (input === null || typeof input !== "object" || Array.isArray(input)
    || types.isProxy(input) || Object.getPrototypeOf(input) !== Object.prototype) {
    throw new TypeError("production_artifact_invalid_input");
  }
  const expected = ["bun_version", "output_root", "project_root", "source_commit", "worktree_status"];
  const keys = Reflect.ownKeys(input);
  if (keys.some((key) => typeof key !== "string")
    || (keys as string[]).sort().join("\0") !== expected.join("\0")) {
    throw new TypeError("production_artifact_invalid_input");
  }
  const values: Record<string, unknown> = {};
  for (const key of expected) {
    const descriptor = Object.getOwnPropertyDescriptor(input, key);
    if (!descriptor || !("value" in descriptor) || !descriptor.enumerable
      || typeof descriptor.value !== "string") {
      throw new TypeError("production_artifact_invalid_input");
    }
    values[key] = descriptor.value;
  }
  const projectRootValue = values["project_root"] as string;
  const outputRootValue = values["output_root"] as string;
  const sourceCommit = values["source_commit"] as string;
  const bunVersion = values["bun_version"] as string;
  const worktreeStatus = values["worktree_status"] as string;
  const projectRoot = resolve(projectRootValue);
  if (!isAbsolute(projectRootValue) || !isAbsolute(outputRootValue)) {
    throw new TypeError("production_artifact_absolute_path_required");
  }
  const outputRoot = resolve(outputRootValue);
  if (outputRoot === "/" || outputRoot === resolve(homedir())
    || inside(projectRoot, outputRoot)) {
    throw new TypeError("production_artifact_unsafe_output");
  }
  if (bunVersion !== PRODUCTION_ARTIFACT_BUN_VERSION) {
    throw new TypeError("production_artifact_bun_version_mismatch");
  }
  if (worktreeStatus !== "") {
    throw new TypeError("production_artifact_worktree_not_clean");
  }
  if (!commitPattern.test(sourceCommit)) {
    throw new TypeError("production_artifact_invalid_source_commit");
  }
  return Object.freeze({
    version: PRODUCTION_ARTIFACT_VERSION,
    project_root: projectRoot,
    output_root: outputRoot,
    source_commit: sourceCommit,
    limits: Object.freeze({
      command_timeout_ms: PRODUCTION_ARTIFACT_COMMAND_TIMEOUT_MS,
      command_max_buffer_bytes: PRODUCTION_ARTIFACT_COMMAND_MAX_BUFFER_BYTES,
      max_allocated_kib: PRODUCTION_ARTIFACT_MAX_ALLOCATED_KIB,
    }),
    commands: Object.freeze([
      Object.freeze(["git", "archive", "--format=tar", sourceCommit]),
      Object.freeze(["tar", "-xf", "<archive>", "-C", outputRoot]),
      Object.freeze(["bun", "install", "--production", "--omit", "optional", "--frozen-lockfile"]),
      Object.freeze(["node", "scripts/verify-production-dependency-closure.mjs", "--root", outputRoot]),
      Object.freeze(["bun", "scripts/verify-firebase-auth-runtime.mjs"]),
    ]),
  });
};
