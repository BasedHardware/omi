import { projectTreeInputSnapshot } from "../core/retrieve/index";
import { snapshot } from "../core/retrieve/tree.fixture";
import { expect, test } from "bun:test";
import { assertIdentityAcceptance, closeIdentityAcceptance, produceIdentityAcceptanceRenders, runOwnedIdentityAcceptance } from "./prod-local-identity-e2e";

test("identity acceptance rejects unavailable identity and readiness instead of passing denial", () => {
  const valid = { health: 200, ready: 200, authorized: 200, denied: 403 };
  expect(() => assertIdentityAcceptance(valid)).not.toThrow();
  for (const field of ["health", "ready", "authorized", "denied"])
    expect(() => assertIdentityAcceptance({ ...valid, [field]: 503 })).toThrow();
  expect(() => assertIdentityAcceptance({ ...valid, denied: 401 })).toThrow();
});

test("identity acceptance awaits teardown after both startup and proof failure", async () => {
  for (const stage of ["start", "prove"]) {
    const calls: string[] = [];
    let finish!: () => void;
    const cleanup = new Promise<void>(resolve => { finish = resolve; });
    const result = runOwnedIdentityAcceptance(async () => {
      calls.push("start"); if (stage === "start") throw new Error(stage);
    }, async () => { calls.push("prove"); throw new Error(stage); }, async () => {
      calls.push("stop"); await cleanup; calls.push("stopped");
    });
    const outcome = result.then(() => null, cause => cause);
    await Promise.resolve(); await Promise.resolve();
    expect(calls).toContain("stop");
    expect(calls).not.toContain("stopped");
    finish(); expect(await outcome).toMatchObject({ message: stage });
    expect(calls.at(-1)).toBe("stopped");
  }
});


test("identity cleanup drains the process before closing storage and attempts all releases", async () => {
  for (const outcome of [{ kind: "failed" }, { kind: "stopped", drained: false }]) {
    const calls: string[] = [];
    await expect(closeIdentityAcceptance(() => { calls.push("server"); }, async () => {
      calls.push("process"); return outcome;
    }, () => { calls.push("identity"); throw new Error("identity close"); }, () => { calls.push("pool"); }))
      .rejects.toThrow("cleanup failed");
    expect(calls).toEqual(["server", "process", "identity", "pool"]);
  }
});


test("identity acceptance executes the actual empty structural renderer and refuses nonempty sources", async () => {
  const empty = projectTreeInputSnapshot({ ...snapshot(), claims: [], entities: [], events: [], evidence: [], adjacency: [] }, { account_timezone: "UTC" });
  expect(await produceIdentityAcceptanceRenders(empty)).toEqual([]);
  const nonempty = projectTreeInputSnapshot(snapshot(), { account_timezone: "UTC" });
  await expect(produceIdentityAcceptanceRenders(nonempty)).rejects.toThrow("requires an empty account");
});
