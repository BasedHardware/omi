import { describe, expect, test } from "bun:test";

import { createAuthorizedLedgerWriteContextIssuer } from "../auth/authorized-context-internal";
import {
  defineMemoryQueryEvaluationGraphSource,
  inspectMemoryQueryEvaluationGraphSource,
} from "./memory-query-evaluation-graph-source";

const issuer = createAuthorizedLedgerWriteContextIssuer();
const context = (capability = "memories.experiments.shadow") => issuer.issue({
  context_version: "authorized-ledger-write-context-v1",
  principal_id: "worker:query-source", account_id: "account:alice",
  application_id: "app:evaluator", credential_id: "credential:evaluator",
  credential_generation: 1, capability, grant_id: "grant:evaluator", grant_version: 1,
  account_epoch: 7, destination_activation_revision: 17, lifecycle_state: "active",
  deletion_epoch: null, authentication_strength: "service-workload",
  issued_at_epoch_seconds: 100, expires_at_epoch_seconds: 200,
  authorization_state_digest: "a".repeat(64),
}, 150);

const request = {
  source_kind: "authorized_graph_snapshot" as const,
  source_ref: "source:query",
  input_frontier: "frontier:query",
};

describe("sealed memory query evaluation graph source", () => {
  test("forwards one minted authority context and exact frozen request", async () => {
    const calls: unknown[][] = [];
    const source = defineMemoryQueryEvaluationGraphSource(async (...args) => {
      calls.push(args);
      return { kind: "not_found" };
    });
    const authorized = context();
    expect(inspectMemoryQueryEvaluationGraphSource(source)).toBe(source);
    expect(await source.load(authorized, request)).toEqual({ kind: "not_found" });
    expect(calls).toHaveLength(1);
    expect(calls[0]![0]).toBe(authorized);
    expect(calls[0]![1]).toEqual(request);
    expect(calls[0]![1]).not.toBe(request);
    expect(Object.isFrozen(calls[0]![1])).toBe(true);
    expect(Object.keys(source)).toEqual(["load"]);
    expect(Object.isFrozen(source)).toBe(true);
  });

  test("wrong capability and forged contexts fail before implementation", async () => {
    let calls = 0;
    const source = defineMemoryQueryEvaluationGraphSource(async () => {
      calls += 1;
      return { kind: "not_found" };
    });
    await expect(source.load(context("memories.work.execute"), request))
      .rejects.toThrow("capability_denied");
    await expect(source.load({ ...context() } as never, request))
      .rejects.toThrow("not issued by auth composition");
    expect(calls).toBe(0);
  });

  test("hostile requests and unbranded lookalikes fail closed", async () => {
    let calls = 0;
    const source = defineMemoryQueryEvaluationGraphSource(async () => {
      calls += 1;
      return { kind: "not_found" };
    });
    for (const candidate of [
      { ...request, source_kind: "formation_input_snapshot" },
      { ...request, extra: true },
      new Proxy(request, {}),
    ]) await expect(source.load(context(), candidate as never)).rejects.toThrow("invalid_request");
    let getters = 0;
    const accessor = Object.create(Object.prototype, {
      source_kind: { enumerable: true, value: request.source_kind },
      source_ref: { enumerable: true, get: () => { getters += 1; return request.source_ref; } },
      input_frontier: { enumerable: true, value: request.input_frontier },
    });
    await expect(source.load(context(), accessor)).rejects.toThrow("invalid_request");
    expect(getters).toBe(0);
    expect(calls).toBe(0);
    expect(() => inspectMemoryQueryEvaluationGraphSource({ load: source.load }))
      .toThrow("unverified_source");
  });

  test("construction snapshots the implementation binding", async () => {
    let implementation = async () => ({ kind: "not_found", marker: "first" });
    const source = defineMemoryQueryEvaluationGraphSource(implementation);
    implementation = async () => ({ kind: "not_found", marker: "second" });
    expect(await source.load(context(), request)).toEqual({ kind: "not_found", marker: "first" });
  });
});
