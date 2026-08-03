import { expect, test } from "bun:test";
import { DeterministicFakeModel } from "../drivers/model/port";
import { runResolution } from "./resolution-run";

test("T8 D47 adversarial: model distinct/same does not mint or merge a durable cluster", async () => {
  const model = new DeterministicFakeModel((request) => {
    const input = request.input as { local_handle: { mention_ref: string } };
    return input.local_handle.mention_ref === "m-1" ? { decision: "distinct" } : { decision: "same", entity_id: "cluster:m-1" };
  });
  const result = await runResolution([
    { mention_id: "m-2", name: "Alice", type: "person", session_id: "s-2", examples: ["Alice joined."] },
    { mention_id: "m-1", name: "Alice Rivera", type: "person", session_id: "s-1", examples: ["Alice Rivera joined."] },
  ], model, { owner_account_id: "owner-1", owner: { label: "David" } });
  expect(result.assignments).toEqual({ "m-1": "UNRESOLVED", "m-2": "UNRESOLVED" });
  expect(result.clusters).toEqual({});
});
