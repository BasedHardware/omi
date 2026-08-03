import { expect, test } from "bun:test";
import { applyIdentityOperation, buildEntityResolutionRequest, canonicalHandleAt, identityConstraintConflicts, planEntityResolution, type EntityTable } from "./entities";

const entity = (id: string, handle = id, owner = "owner-1", labels: string[] = []) => ({ entity_id: id, owner_account_id: owner, entity_revision_id: `${id}:r1`, handle, labels });
const handle = (id: string, antecedent_handle: string | null = null) => ({ handle: id, mention_ref: id, antecedent_handle, uncertainty: [] });
const sameConstraint = (id: string, left: string, right: string, effective_at: number) => ({ constraint_id: id, owner_account_id: "owner-1", endpoints: [{ kind: "entity" as const, entity_id: left.startsWith("entity:") ? left : `entity:${left}` }, { kind: "entity" as const, entity_id: right.startsWith("entity:") ? right : `entity:${right}` }] as const, left_handle: `legacy:${left}`, right_handle: `legacy:${right}`, relation: "same" as const, evidence_refs: ["e1"], effective_at, reversed_at: null });

test("T5 D47 adversarial: aliases and same-name candidates both abstain without typed authority", () => {
  const table: EntityTable = { owner_account_id: "owner-1", entities: [entity("entity:alice", "alice-rivera", "owner-1", ["Alice Rivera"]), entity("entity:alex-a", "alex-a", "owner-1", ["Alex Morgan"]), entity("entity:alex-b", "alex-b", "owner-1", ["Alex Morgan"])], constraints: [{ ...sameConstraint("distinct-alex", "local:alex-a", "alex-b", 1), relation: "distinct" }] };
  const aliases = planEntityResolution(table, buildEntityResolutionRequest("owner-1", handle("local:alice"), ["e1"], ["entity:alice"]), { decision: "same", entity_id: "entity:alice" });
  const negatives = ["local:alex-a"].map((local) => planEntityResolution(table, buildEntityResolutionRequest("owner-1", handle(local), ["e1"], ["entity:alex-b"]), { decision: "same", entity_id: "entity:alex-b" }));
  expect(aliases).toMatchObject({ outcome: "abstain" });
  expect(negatives.filter((result) => result.outcome === "same")).toHaveLength(0);
  expect(negatives[0]).toMatchObject({ outcome: "abstain" });
});

test("T5 resolves prior authorized antecedents but naked organization identity abstains", () => {
  const table: EntityTable = { owner_account_id: "owner-1", entities: [entity("entity:owner", "owner", "owner-1", ["Owner account"]), entity("entity:org", "acme", "owner-1", ["Acme Incorporated"])], constraints: [] };
  const pronoun = planEntityResolution(table, buildEntityResolutionRequest("owner-1", handle("local:he", "local:alice"), ["e1"], [], undefined, undefined, undefined, undefined, undefined, "unit:1", [{ coreference_support_id: "coref:alice-he", owner_account_id: "owner-1", discourse_unit_ref: "unit:1", antecedent_mention_id: "alice", anaphor_mention_id: "local:he", evidence_refs: ["e1"], lineage_refs: ["mention:alice", "mention:local:he"], lifecycle: "active" }]), { decision: "abstain" }, new Map([["local:alice", { entity_id: "entity:owner", mention_id: "alice", discourse_unit_ref: "unit:1" }]]));
  const org = planEntityResolution(table, buildEntityResolutionRequest("owner-1", handle("local:acme"), ["e1"], ["entity:org"]), { decision: "same", entity_id: "entity:org" });
  const bare = planEntityResolution(table, buildEntityResolutionRequest("owner-1", { ...handle("local:bare"), uncertainty: ["unresolved_local_mention"] }, [], []), { decision: "abstain" });
  expect(pronoun).toMatchObject({ outcome: "same", entity_id: "entity:owner" });
  expect(org).toMatchObject({ outcome: "abstain" });
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

test("P0-b adversarial: model antecedents need persisted, same-unit lineage before using a durable binding", () => {
  const table: EntityTable = { owner_account_id: "owner-1", entities: [entity("entity:alice")], constraints: [] };
  const request = (unit: string, supports: readonly import("../schema").CoreferenceSupport[] = []) => buildEntityResolutionRequest("owner-1", handle("local:she", "local:alice"), ["e:she"], [], undefined, undefined, undefined, undefined, undefined, unit, supports);
  const bindings = new Map([["local:alice", { entity_id: "entity:alice", mention_id: "m-alice", discourse_unit_ref: "unit:one" }]]);
  expect(planEntityResolution(table, request("unit:one"), { decision: "abstain" }, bindings)).toMatchObject({ outcome: "abstain", blockers: ["missing_persisted_in_unit_coreference_support"] });
  const crossUnit = { coreference_support_id: "coref:cross", owner_account_id: "owner-1", discourse_unit_ref: "unit:two", antecedent_mention_id: "m-alice", anaphor_mention_id: "local:she", evidence_refs: ["e:she"], lineage_refs: ["mention:m-alice", "mention:local:she"], lifecycle: "active" as const };
  expect(planEntityResolution(table, request("unit:one", [crossUnit]), { decision: "abstain" }, bindings)).toMatchObject({ outcome: "abstain" });
  const supported = { ...crossUnit, coreference_support_id: "coref:in-unit", discourse_unit_ref: "unit:one" };
  expect(planEntityResolution(table, request("unit:one", [supported]), { decision: "abstain" }, bindings)).toMatchObject({ outcome: "same", entity_id: "entity:alice" });
});

test("I4 relation closure is typed, transitive, and reversible", () => {
  const pair = (id: string, left: string, right: string, relation: "same" | "distinct", effective_at = 1) => ({ constraint_id: id, owner_account_id: "owner-1", endpoints: [{ kind: "entity" as const, entity_id: left }, { kind: "entity" as const, entity_id: right }] as const, left_handle: "same rendering", right_handle: "same rendering", relation, identity_authorization: undefined, effective_at, reversed_at: null });
  const sameAB = pair("same:ab", "entity:a", "entity:b", "same");
  const distinctBC = pair("distinct:bc", "entity:b", "entity:c", "distinct");
  const sameAC = pair("same:ac", "entity:a", "entity:c", "same", 2);
  expect(identityConstraintConflicts([sameAB, distinctBC], sameAC)).toBe(true);
  expect(() => applyIdentityOperation([sameAB, distinctBC], { kind: "merge", constraint: sameAC })).toThrow("equivalence class");
  // A split closes a `same` edge. Aimed at the `distinct` edge it is inert, so
  // the merge that edge forbids stays forbidden: reversing a separation is a
  // different, separately authorized act.
  const misaimed = applyIdentityOperation([sameAB, distinctBC], { kind: "split", constraint_id: "distinct:bc", effective_at: 2 });
  expect(misaimed.find((constraint) => constraint.constraint_id === "distinct:bc")?.reversed_at).toBeNull();
  expect(() => applyIdentityOperation(misaimed, { kind: "merge", constraint: sameAC })).toThrow("equivalence class");
  // Splitting the `same` edge instead removes the path that made A and C
  // conflict, and the merge becomes admissible.
  const reversed = applyIdentityOperation([sameAB, distinctBC], { kind: "split", constraint_id: "same:ab", effective_at: 2 });
  expect(() => applyIdentityOperation(reversed, { kind: "merge", constraint: sameAC })).not.toThrow();
  const targetlessDistinct = planEntityResolution({ owner_account_id: "owner-1", entities: [entity("entity:a")], constraints: [] }, buildEntityResolutionRequest("owner-1", handle("local:identical-label"), ["e1"], ["entity:a"]), { decision: "distinct" });
  expect(targetlessDistinct).toMatchObject({ outcome: "abstain", blockers: ["distinct_requires_pair_specific_authorization"] });
});
