import { afterEach, describe, expect, test } from "bun:test";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

import { CachingModelPort, type VerdictStore } from "../drivers/model/verdict-cache";
import { DeterministicFakeModel } from "../drivers/model/port";
import {
  offlineModelPipelineResourceDigest,
  tryAcquireOfflineModelPipelineLock,
  withOfflineModelPipelineExclusivity,
} from "./offline-model-pipeline-lock";

const roots: string[] = [];
const temporaryRoot = () => {
  const root = mkdtempSync(join(tmpdir(), "omi-pipeline-lock-test-"));
  roots.push(root);
  return root;
};

afterEach(() => {
  while (roots.length) rmSync(roots.pop()!, { recursive: true, force: true });
});

describe("offline model-pipeline resource lock", () => {
  test("excludes the same resource, permits distinct resources, and reacquires after release", () => {
    const root = temporaryRoot();
    const firstDigest = offlineModelPipelineResourceDigest({ credential: "credential-a" });
    const secondDigest = offlineModelPipelineResourceDigest({ credential: "credential-b" });
    const first = tryAcquireOfflineModelPipelineLock(firstDigest, root);
    expect(first.kind).toBe("acquired");
    expect(tryAcquireOfflineModelPipelineLock(firstDigest, root).kind).toBe("busy");
    const distinct = tryAcquireOfflineModelPipelineLock(secondDigest, root);
    expect(distinct.kind).toBe("acquired");
    if (distinct.kind === "acquired") distinct.release();
    if (first.kind === "acquired") first.release();
    const reacquired = tryAcquireOfflineModelPipelineLock(firstDigest, root);
    expect(reacquired.kind).toBe("acquired");
    if (reacquired.kind === "acquired") reacquired.release();
  });

  test("excludes an independent process using the same resource", async () => {
    const root = temporaryRoot();
    const resource = offlineModelPipelineResourceDigest({ credential: "cross-process-key" });
    const held = tryAcquireOfflineModelPipelineLock(resource, root);
    expect(held.kind).toBe("acquired");
    const moduleUrl = pathToFileURL(join(import.meta.dir, "offline-model-pipeline-lock.ts")).href;
    const child = Bun.spawn([
      process.execPath,
      "-e",
      `import { tryAcquireOfflineModelPipelineLock } from ${JSON.stringify(moduleUrl)}; console.log(tryAcquireOfflineModelPipelineLock(${JSON.stringify(resource)}, ${JSON.stringify(root)}).kind);`,
    ], { stdout: "pipe", stderr: "pipe" });
    const [exitCode, stdout, stderr] = await Promise.all([
      child.exited,
      new Response(child.stdout).text(),
      new Response(child.stderr).text(),
    ]);
    expect({ exitCode, stdout: stdout.trim(), stderr }).toEqual({
      exitCode: 0,
      stdout: "busy",
      stderr: "",
    });
    if (held.kind === "acquired") held.release();
  });

  test("maps aliases of one credential together and keeps opaque overrides secret-free", () => {
    expect(offlineModelPipelineResourceDigest({ credential: "same-key" }))
      .toBe(offlineModelPipelineResourceDigest({ credential: "same-key" }));
    expect(offlineModelPipelineResourceDigest({ credential: "same-key" }))
      .not.toBe(offlineModelPipelineResourceDigest({ credential: "other-key" }));
    const explicit = offlineModelPipelineResourceDigest({
      credential: "ignored-secret",
      explicit_resource_id: "provider-resource-generation-7",
    });
    expect(explicit).toMatch(/^[a-f0-9]{64}$/);
    expect(explicit).not.toContain("ignored-secret");
    expect(explicit).not.toContain("provider-resource");
  });

  test("acquires lazily once for actual model work", async () => {
    let holds = 0;
    const model = withOfflineModelPipelineExclusivity(
      new DeterministicFakeModel({ decision: "accept_ltm" }),
      "a".repeat(64),
      () => { holds += 1; },
    );
    expect(holds).toBe(0);
    await model.invoke({ strategy: "test", version: "v1", input: {} });
    await model.render({ strategy: "test", version: "v1", input: {} });
    await model.compose({ strategy: "test", version: "v1", input: {} });
    expect(holds).toBe(1);
  });

  test("a legacy verdict-cache hit never acquires the provider resource", async () => {
    let holds = 0;
    const locked = withOfflineModelPipelineExclusivity(
      new DeterministicFakeModel({ should_not_run: true }),
      "b".repeat(64),
      () => { holds += 1; },
    );
    const hitStore: VerdictStore = {
      get: () => JSON.stringify({ cached: true }),
      set: () => { throw new Error("cache hit must not write"); },
    };
    const cached = new CachingModelPort(locked, hitStore, "test");
    expect(await cached.invoke({ strategy: "test", version: "v1", input: {} }))
      .toEqual({ cached: true });
    expect(holds).toBe(0);

    const missStore: VerdictStore = { get: () => undefined, set: () => undefined };
    const missed = new CachingModelPort(locked, missStore, "test");
    await missed.invoke({ strategy: "test", version: "v1", input: {} });
    expect(holds).toBe(1);
  });
});
