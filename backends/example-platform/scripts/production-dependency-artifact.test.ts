import { describe, expect, test } from "bun:test";

import {
  PRODUCTION_ARTIFACT_BUN_VERSION,
  PRODUCTION_ARTIFACT_COMMAND_MAX_BUFFER_BYTES,
  PRODUCTION_ARTIFACT_COMMAND_TIMEOUT_MS,
  PRODUCTION_ARTIFACT_MAX_ALLOCATED_KIB,
  PRODUCTION_ARTIFACT_VERSION,
  productionDependencyArtifactPlan,
} from "./production-dependency-artifact";

const root = "/Volumes/Ephemeral/scratch/worktrees/omi-memory-productionization";
const output = "/Volumes/Ephemeral/scratch/omi-production-artifacts/candidate-a";
const commit = "a".repeat(40);

describe("production dependency artifact plan", () => {
  test("freezes committed source, exact install, verification, and runtime smoke order", () => {
    const plan = productionDependencyArtifactPlan({
      project_root: root,
      output_root: output,
      source_commit: commit,
      bun_version: PRODUCTION_ARTIFACT_BUN_VERSION,
      worktree_status: "",
    });
    expect(plan.version).toBe(PRODUCTION_ARTIFACT_VERSION);
    expect(plan.limits).toEqual({
      command_timeout_ms: 600_000,
      command_max_buffer_bytes: 8 * 1_024 * 1_024,
      max_allocated_kib: 512 * 1_024,
    });
    expect(PRODUCTION_ARTIFACT_COMMAND_TIMEOUT_MS).toBe(600_000);
    expect(PRODUCTION_ARTIFACT_COMMAND_MAX_BUFFER_BYTES).toBe(8 * 1_024 * 1_024);
    expect(PRODUCTION_ARTIFACT_MAX_ALLOCATED_KIB).toBe(512 * 1_024);
    expect(plan.commands).toEqual([
      ["git", "archive", "--format=tar", commit],
      ["tar", "-xf", "<archive>", "-C", output],
      ["bun", "install", "--production", "--omit", "optional", "--frozen-lockfile"],
      ["node", "scripts/verify-production-dependency-closure.mjs", "--root", output],
      ["bun", "scripts/verify-firebase-auth-runtime.mjs"],
    ]);
    expect(Object.isFrozen(plan)).toBe(true);
    expect(Object.isFrozen(plan.limits)).toBe(true);
    expect(Object.isFrozen(plan.commands)).toBe(true);
  });

  test("refuses ambiguous and destructive output coordinates", () => {
    const request = {
      project_root: root,
      output_root: output,
      source_commit: commit,
      bun_version: PRODUCTION_ARTIFACT_BUN_VERSION,
      worktree_status: "",
    };
    for (const output_root of ["relative", "/", root, `${root}/artifact`]) {
      expect(() => productionDependencyArtifactPlan({ ...request, output_root })).toThrow();
    }
  });

  test("refuses dirty, version-drifted, malformed, and hostile inputs", () => {
    const request = {
      project_root: root,
      output_root: output,
      source_commit: commit,
      bun_version: PRODUCTION_ARTIFACT_BUN_VERSION,
      worktree_status: "",
    };
    expect(() => productionDependencyArtifactPlan({ ...request, worktree_status: " M package.json" }))
      .toThrow("production_artifact_worktree_not_clean");
    expect(() => productionDependencyArtifactPlan({ ...request, bun_version: "1.3.15" }))
      .toThrow("production_artifact_bun_version_mismatch");
    expect(() => productionDependencyArtifactPlan({ ...request, source_commit: "main" }))
      .toThrow("production_artifact_invalid_source_commit");
    expect(() => productionDependencyArtifactPlan(new Proxy(request, {}) as never))
      .toThrow("production_artifact_invalid_input");
    let getterCalls = 0;
    expect(() => productionDependencyArtifactPlan({
      ...request,
      get source_commit() { getterCalls += 1; return commit; },
    })).toThrow("production_artifact_invalid_input");
    expect(getterCalls).toBe(0);
  });
});
