import { expect, test } from "bun:test";
import { applyIdentityOperation, buildEntityResolutionRequest, canonicalHandleAt, planEntityResolution, type EntityTable } from "./entities";

const entity = (id: string, handle = id, owner = "owner-1", labels: string[] = []) => ({ entity_id: id, owner_account_id: owner, entity_revision_id: `${id}:r1`, handle, labels });
const handle = (id: string, antecedent_handle: string | null = null) => ({ handle: id, mention_ref: id, antecedent_handle, uncertainty: [] });
const sameConstraint = (id: string, left: string, right: string, effective_at: number) => ({ constraint_id: id, owner_account_id: "owner-1", left_handle: left, right_handle: right, relation: "same" as const, evidence_refs: ["e1"], effective_at, reversed_at: null });

test("T5 adversarial synthetic gold: aliases merge while same-name distinct people do not", () => {
  const table: EntityTable = { owner_account_id: "owner-1", entities: [entity("entity:alice", "alice-rivera", "owner-1", ["Alice Rivera"]), entity("entity:alex-a", "alex-a", "owner-1", ["Alex Morgan"]), entity("entity:alex-b", "alex-b", "owner-1", ["Alex Morgan"])], constraints: [{ ...sameConstraint("distinct-alex", "local:alex-a", "alex-b", 1), relation: "distinct" }] };
  const aliases = planEntityResolution(table, buildEntityResolutionRequest("owner-1", handle("local:alice"), ["e1"], ["entity:alice"]), { decision: "same", entity_id: "entity:alice" });
  const negatives = ["local:alex-a"].map((local) => planEntityResolution(table, buildEntityResolutionRequest("owner-1", handle(local), ["e1"], ["entity:alex-b"]), { decision: "same", entity_id: "entity:alex-b" }));
  expect(aliases).toMatchObject({ outcome: "same", entity_id: "entity:alice" });
  expect(negatives.filter((result) => result.outcome === "same")).toHaveLength(0);
  expect(negatives[0]).toMatchObject({ outcome: "distinct", blockers: ["explicit_distinctness"] });
});

test("T5 resolves antecedent pronouns, owner identity, organizations, and abstains safely", () => {
  const table: EntityTable = { owner_account_id: "owner-1", entities: [entity("entity:owner", "owner", "owner-1", ["Owner account"]), entity("entity:org", "acme", "owner-1", ["Acme Incorporated"])], constraints: [] };
  const pronoun = planEntityResolution(table, buildEntityResolutionRequest("owner-1", handle("local:he", "local:alice"), ["e1"], []), { decision: "abstain" }, new Map([["local:alice", "entity:owner"]]));
  const org = planEntityResolution(table, buildEntityResolutionRequest("owner-1", handle("local:acme"), ["e1"], ["entity:org"]), { decision: "same", entity_id: "entity:org" });
  const bare = planEntityResolution(table, buildEntityResolutionRequest("owner-1", { ...handle("local:bare"), uncertainty: ["unresolved_local_mention"] }, [], []), { decision: "abstain" });
  expect(pronoun).toMatchObject({ outcome: "same", entity_id: "entity:owner" });
  expect(org).toMatchObject({ outcome: "same", entity_id: "entity:org" });
  expect(bare).toMatchObject({ outcome: "abstain", blockers: ["missing_evidence"] });
  const crossOwner = planEntityResolution({ ...table, owner_account_id: "owner-2" }, buildEntityResolutionRequest("owner-1", handle("local:owner"), ["e1"], ["entity:owner"]), { decision: "same", entity_id: "entity:owner" });
  expect(crossOwner).toMatchObject({ outcome: "abstain", blockers: ["account_boundary"] });
});

test("T5 identity history is reversible and as-of resolution cannot use future evidence", () => {
  const initial: EntityTable = { owner_account_id: "owner-1", entities: [entity("entity:z", "z"), entity("entity:a", "a")], constraints: [] };
  const merged = applyIdentityOperation(initial.constraints, { kind: "merge", constraint: sameConstraint("merge-1", "z", "a", 20) });
  const mergedTable = { ...initial, constraints: merged };
  expect(canonicalHandleAt(mergedTable, "entity:z", 10)).toBe("z");
  expect(canonicalHandleAt(mergedTable, "entity:z", 20)).toBe("a");
  const split = applyIdentityOperation(merged, { kind: "split", constraint_id: "merge-1", effective_at: 30 });
  expect(canonicalHandleAt({ ...initial, constraints: split }, "entity:z", 31)).toBe("z");
});
