import { expect, test } from "bun:test";
import { blockIdentityClusters, blockMentionClusters, buildReferentProfiles, invokeBlockedIdentityAdjudication, invokeIdentityAdjudication, proposeProfileOverlaps, selectSettleableIdentityClusterDigests } from "./identity";

const identity = (key: string) => ({ namespace_instance_ref: `namespace:${key}`, local_key: key, producer: { producer_ref: "test", contract_ref: "test" }, asserted_identity: { domain: null, scope_ref: null } });
const mention = (id: string, claim_revision_id: string, source: ReturnType<typeof identity>) => ({ mention_id: id, owner_account_id: "owner", claim_revision_id, span: { start: 0, end: 1 }, evidence_id: `evidence:${id}`, source_identity_ref: source, speaker_rendering: null, slot_id: "subject", surface: `surface-only:${id}`, antecedent_handle: null, resolution: "unresolved" as const, entity_id: null });
const claim = (id: string, evidence_ref: string, object: string) => ({ revision_id: id, claim: { predicate: "generic/statement", polarity: "positive" as const, evidence_refs: [evidence_ref], temporal_scope: { observed_at: "2026-01-01T00:00:00Z" }, arguments: [{ slot_id: "subject", role: "subject", value: { kind: "source_local_ref", ref: `local:${id}` } }, { slot_id: "object", role: "object", value: { kind: "literal", value: object } }] } });
const evidence = (id: string, excerpt: string, event_revision_id: string) => ({ revision_id: `evidence-revision:${id}`, evidence: { evidence_id: id, event_revision_id, source_unit_ref: id, range: { start: 0, end: excerpt.length }, excerpt, source_identity_ref: identity(`evidence:${id}`), speaker_rendering: null, source_local_mention_ref: null, state: "active" as const, source_trust: "test", policy_labels: [], source_independence_key: `capture:${id}` } });
const event = (id: string, session: string) => ({ revision_id: id, event: { event_id: id, event_revision_id: id, owner_account_id: "owner", capture_session_id: session, stream_id: "test", event_kind: "text", payload_schema_ref: "test", schema_version: "test", payload: {}, event_time: "2026-01-01T00:00:00Z", ingest_time: "2026-01-01T00:00:00Z", source_sequence: 1, evidence_addressable_refs: [], source_trust: "test", policy_labels: [], canonical_redacted_hash: id } });
const proposalModel = (response: unknown) => ({ async invoke(): Promise<unknown> { return response; } });
const identityContract = {
  model_version: "model-v1",
  adjudication_version: "dream-identity-v1",
  verification_version: "dream-identity-verify-v2",
  naming_version: "dream-naming-check-v1",
  self_reference_version: "dream-self-reference-v1",
  prompt_version: "prompt-v1",
  policy_version: "policy-v1",
  schema_version: "schema-v1",
  code_version: "code-v1",
};

test("identity adjudication rejects a same-claim group before it can be admitted", async () => {
  const first = mention("mention:first", "claim:one", identity("first"));
  const second = { ...mention("mention:second", "claim:one", identity("second")), slot_id: "object" };
  const sharedClaim = claim("claim:one", "evidence:one", "atlas");
  const profiles = buildReferentProfiles([first, second], [sharedClaim]);
  const proposal = await invokeIdentityAdjudication(proposalModel({ partition_hash: "same-claim", same_groups: [[first.mention_id, second.mention_id]], uncertain_pairs: [] }), profiles);
  expect(proposal.same_groups).toEqual([]);
  expect(proposal.rejected_same_groups).toEqual([{ group_mention_ids: [first.mention_id, second.mention_id], reason: "same_claim_revision_id", retryable: false }]);
});

test("profiles carry grounded discriminators while predicate and role alone remain inert", () => {
  const a = mention("mention:a", "claim:a", identity("a")), b = mention("mention:b", "claim:b", identity("b"));
  const c = mention("mention:c", "claim:c", identity("c")), d = mention("mention:d", "claim:d", identity("d"));
  const profiles = buildReferentProfiles(
    [a, b, c, d],
    [claim("claim:a", "evidence:a", "atlas"), claim("claim:b", "evidence:b", "zephyr"), claim("claim:c", "evidence:c", "atlas"), claim("claim:d", "evidence:d", "atlas")],
    [evidence("evidence:a", "first independent context", "event:a"), evidence("evidence:b", "second unrelated context", "event:b"), evidence("evidence:c", "shared grounded context", "event:c"), evidence("evidence:d", "shared grounded context", "event:d")],
    [event("event:a", "session:a"), event("event:b", "session:b"), event("event:c", "session:c"), event("event:d", "session:d")],
  );
  expect(profiles[0]!.discriminating_claims[0]).toMatchObject({ other_arguments: [{ role: "object", value: { kind: "literal", value: "atlas" } }], evidence_context: [{ excerpt: "first independent context", capture_session_id: "session:a" }], observed_at: "2026-01-01T00:00:00Z" });
  // The mention surface is not a profile field. Evidence excerpts are retained
  // as grounding facts, which is distinct from using a surface as an ID key.
  expect(JSON.stringify(profiles)).not.toContain("surface-only:");
  expect(proposeProfileOverlaps(profiles)).toEqual([[c.mention_id, d.mention_id]]);
});

test("the partition key is derived from the answer, never taken from the model", async () => {
  const a = mention("mention:a", "claim:a", identity("a")), b = mention("mention:b", "claim:b", identity("b"));
  const profiles = buildReferentProfiles([a, b], [claim("claim:a", "evidence:a", "atlas"), claim("claim:b", "evidence:b", "atlas")]);
  const group = [[a.mention_id, b.mention_id]];
  const honest = await invokeIdentityAdjudication(proposalModel({ same_groups: group, uncertain_pairs: [] }), profiles);
  // A hash a model states is unverifiable, and a wrong one silently defeats the
  // repeat-proposal guard that reads it. Same answer, same key, either way.
  const lying = await invokeIdentityAdjudication(proposalModel({ partition_hash: "whatever-the-model-said", same_groups: group, uncertain_pairs: [] }), profiles);
  expect(honest.partition_hash).toBe(lying.partition_hash);
  expect(honest.partition_hash).not.toContain("whatever");
  const different = await invokeIdentityAdjudication(proposalModel({ same_groups: [], uncertain_pairs: [] }), profiles);
  expect(different.partition_hash).not.toBe(honest.partition_hash);
});

test("blocking clusters by normalized surface, pre-rejects same-claim clusters, and caps high-frequency surfaces", async () => {
  const shared = (id: string, claimId: string, surface: string) => ({ ...mention(id, claimId, identity(id)), surface });
  const a = shared("mention:omi-a", "claim:a", "Omi"), b = shared("mention:omi-b", "claim:b", " omi  ");
  const single1 = shared("mention:one-claim-a", "claim:same", "atlas"), single2 = shared("mention:one-claim-b", "claim:same", "Atlas");
  const noisy = Array.from({ length: 5 }, (_, index) => shared(`mention:i-${index}`, `claim:i-${index}`, "i"));
  const { clusters, oversize, single_claim } = blockMentionClusters([a, b, single1, single2, ...noisy], 4);
  expect(clusters.map((cluster) => cluster.map((item) => item.mention_id))).toEqual([["mention:omi-a", "mention:omi-b"]]);
  expect(single_claim.map((cluster) => cluster.map((item) => item.mention_id))).toEqual([["mention:one-claim-a", "mention:one-claim-b"]]);
  expect(oversize).toHaveLength(1);
  expect(oversize[0]).toHaveLength(5);

  const calls: number[] = [];
  const model = { async invoke(request: { strategy: string; input: unknown }): Promise<unknown> {
    if (request.strategy === "identity-naming-check") return { names_specific_referent: true };
    if (request.strategy === "identity-verification") return { verdict: "same", who: "the omi wearable" };
    const profiles = (request.input as { profiles: readonly { mention_id: string }[] }).profiles;
    calls.push(profiles.length);
    return { same_groups: [profiles.map((profile) => profile.mention_id)], uncertain_pairs: [] };
  } };
  const proposal = await invokeBlockedIdentityAdjudication(model, {
    mentions: [a, b, single1, single2, ...noisy],
    claims: [claim("claim:a", "evidence:a", "atlas"), claim("claim:b", "evidence:b", "atlas"), claim("claim:same", "evidence:s", "atlas"), ...noisy.map((_, index) => claim(`claim:i-${index}`, `evidence:i-${index}`, "atlas"))],
    max_cluster_size: 4,
  });
  // Only the admissible cluster is adjudicated; the rest are durable rejections.
  expect(calls).toEqual([2]);
  expect(proposal.same_groups).toEqual([["mention:omi-a", "mention:omi-b"]]);
  expect(proposal.rejected_same_groups).toEqual([
    { group_mention_ids: ["mention:one-claim-a", "mention:one-claim-b"], reason: "same_claim_revision_id", retryable: false },
    { group_mention_ids: noisy.map((item) => item.mention_id).sort(), reason: "ambiguous_high_frequency_surface", retryable: false },
  ]);
});

test("a failed adjudication batch loses only its own candidates and the union hash is batch-independent", async () => {
  const shared = (id: string, claimId: string, surface: string) => ({ ...mention(id, claimId, identity(id)), surface });
  const a = shared("mention:a1", "claim:a1", "alpha"), b = shared("mention:a2", "claim:a2", "alpha");
  const c = shared("mention:b1", "claim:b1", "beta"), d = shared("mention:b2", "claim:b2", "beta");
  const claims = [claim("claim:a1", "evidence:a1", "x"), claim("claim:a2", "evidence:a2", "x"), claim("claim:b1", "evidence:b1", "x"), claim("claim:b2", "evidence:b2", "x")];
  const failing = { async invoke(request: { strategy: string; input: unknown }): Promise<unknown> {
    if (request.strategy === "identity-naming-check") return { names_specific_referent: true };
    if (request.strategy === "identity-verification") return { verdict: "same", who: "beta thing" };
    const profiles = (request.input as { profiles: readonly { mention_id: string }[] }).profiles;
    if (profiles.some((profile) => profile.mention_id.startsWith("mention:a"))) throw new Error("prompt too long");
    return { same_groups: [profiles.map((profile) => profile.mention_id)], uncertain_pairs: [] };
  } };
  // Budget of 1 forces one cluster per batch, so the failure isolates cleanly.
  const proposal = await invokeBlockedIdentityAdjudication(failing, { mentions: [a, b, c, d], claims, batch_profile_budget: 1 });
  expect(proposal.same_groups).toEqual([["mention:b1", "mention:b2"]]);
  expect(proposal.rejected_same_groups).toEqual([{ group_mention_ids: ["mention:a1", "mention:a2"], reason: "adjudication_failed", retryable: true }]);

  const healthy = { async invoke(request: { strategy: string; input: unknown }): Promise<unknown> {
    if (request.strategy === "identity-naming-check") return { names_specific_referent: true };
    if (request.strategy === "identity-verification") return { verdict: "same", who: "beta thing" };
    const profiles = (request.input as { profiles: readonly { mention_id: string }[] }).profiles;
    return { same_groups: profiles.some((profile) => profile.mention_id.startsWith("mention:b")) ? [["mention:b1", "mention:b2"]] : [], uncertain_pairs: [] };
  } };
  const batched = await invokeBlockedIdentityAdjudication(healthy, { mentions: [a, b, c, d], claims, batch_profile_budget: 1 });
  const onePass = await invokeBlockedIdentityAdjudication(healthy, { mentions: [a, b, c, d], claims, batch_profile_budget: 1_000_000 });
  expect(batched.partition_hash).toBe(onePass.partition_hash);
});


test("the batching budget is costed by an injected function, and the injection cannot change the answer", async () => {
  const identityA = identity("cost");
  const a = mention("mention:c1", "claim:c1", identityA), b = mention("mention:c2", "claim:c2", identityA);
  const claims = [claim("claim:c1", "evidence:c1", "thing"), claim("claim:c2", "evidence:c2", "thing")];
  const model = { async invoke(request: { strategy: string; input: unknown }): Promise<unknown> {
    if (request.strategy === "identity-naming-check") return { names_specific_referent: true };
    if (request.strategy === "identity-verification") return { verdict: "same", who: "beta thing" };
    return { same_groups: [(request.input as { profiles: readonly { mention_id: string }[] }).profiles.map((profile) => profile.mention_id)], uncertain_pairs: [] };
  } };

  const seen: number[] = [];
  // A cost function that reports a fraction of the storage size is exactly the
  // prompt-shaped case: the same clusters pack into fewer, fuller batches.
  const cheap = (profiles: readonly unknown[]) => { const n = Math.ceil(JSON.stringify(profiles).length / 10); seen.push(n); return n; };
  const withDefault = await invokeBlockedIdentityAdjudication(model, { mentions: [a, b], claims });
  const withInjected = await invokeBlockedIdentityAdjudication(model, { mentions: [a, b], claims, profile_cost: cheap as never });
  expect(seen.length).toBeGreaterThan(0);
  // Costing is a packing decision only: the admitted partition is identical, so
  // the partition hash -- and therefore cycle dedup -- is unaffected.
  expect(withInjected.partition_hash).toBe(withDefault.partition_hash);
  expect(withInjected.same_groups).toEqual(withDefault.same_groups);
});

test("verification refutes an unproven group and the refusal is a durable rejection", async () => {
  const shared = (id: string, claimId: string, surface: string) => ({ ...mention(id, claimId, identity(id)), surface });
  const a = shared("mention:v1", "claim:v1", "she"), b = shared("mention:v2", "claim:v2", "she");
  const claims = [claim("claim:v1", "evidence:v1", "x"), claim("claim:v2", "evidence:v2", "x")];
  const model = { async invoke(request: { strategy: string; input: unknown }): Promise<unknown> {
    if (request.strategy === "identity-naming-check") return { names_specific_referent: true };
    if (request.strategy === "identity-verification") return { verdict: "not_proven" };
    const profiles = (request.input as { profiles: readonly { mention_id: string }[] }).profiles;
    return { same_groups: [{ members: profiles.map((profile) => profile.mention_id), who: "some woman" }], uncertain_pairs: [] };
  } };
  const proposal = await invokeBlockedIdentityAdjudication(model, { mentions: [a, b], claims });
  expect(proposal.same_groups).toEqual([]);
  expect(proposal.rejected_same_groups).toEqual([{ group_mention_ids: ["mention:v1", "mention:v2"], reason: "identity_not_proven_on_verification", retryable: false }]);
});

test("a named group carries its who through verification into the proposal", async () => {
  const shared = (id: string, claimId: string, surface: string) => ({ ...mention(id, claimId, identity(id)), surface });
  const a = shared("mention:n1", "claim:n1", "omi"), b = shared("mention:n2", "claim:n2", "Omi");
  const claims = [claim("claim:n1", "evidence:n1", "x"), claim("claim:n2", "evidence:n2", "x")];
  const model = { async invoke(request: { strategy: string; input: unknown }): Promise<unknown> {
    if (request.strategy === "identity-naming-check") return { names_specific_referent: true };
    if (request.strategy === "identity-verification") return { verdict: "same", who: "the Omi wearable device" };
    const profiles = (request.input as { profiles: readonly { mention_id: string }[] }).profiles;
    return { same_groups: [{ members: profiles.map((profile) => profile.mention_id), who: "Omi device" }], uncertain_pairs: [] };
  } };
  const proposal = await invokeBlockedIdentityAdjudication(model, { mentions: [a, b], claims });
  expect(proposal.same_groups).toEqual([["mention:n1", "mention:n2"]]);
  expect(proposal.same_group_who).toEqual(["the Omi wearable device"]);
});


test("a distinctive recurring surface commits by recurrence without the adversarial pass; a deictic one does not", async () => {
  const shared = (id: string, claimId: string, surface: string) => ({ ...mention(id, claimId, identity(id)), surface });
  const omi1 = shared("mention:r-omi-1", "claim:r1", "Omi"), omi2 = shared("mention:r-omi-2", "claim:r2", "omi");
  const me1 = shared("mention:r-me-1", "claim:m1", "me"), me2 = shared("mention:r-me-2", "claim:m2", "me");
  const claims = [claim("claim:r1", "evidence:r1", "x"), claim("claim:r2", "evidence:r2", "x"), claim("claim:m1", "evidence:m1", "x"), claim("claim:m2", "evidence:m2", "x")];
  const verifyCalls: string[] = [];
  const model = { async invoke(request: { strategy: string; input: unknown }): Promise<unknown> {
    if (request.strategy === "identity-naming-check") return { names_specific_referent: true };
    if (request.strategy === "identity-verification") {
      verifyCalls.push(JSON.stringify((request.input as { surfaces?: readonly string[] }).surfaces));
      return { verdict: "not_proven" };
    }
    const profiles = (request.input as { profiles: readonly { mention_id: string }[] }).profiles;
    const ids = profiles.map((profile) => profile.mention_id);
    const groups = [];
    if (ids.includes("mention:r-omi-1")) groups.push({ members: ["mention:r-omi-1", "mention:r-omi-2"], who: "the Omi device", kind: "named_individual" });
    if (ids.includes("mention:r-me-1")) groups.push({ members: ["mention:r-me-1", "mention:r-me-2"], who: "me", kind: "deictic_or_generic" });
    return { same_groups: groups, uncertain_pairs: [] };
  } };
  const proposal = await invokeBlockedIdentityAdjudication(model, { mentions: [omi1, omi2, me1, me2], claims });
  // Omi commits on recurrence, never verified; "me" is deictic so it faces the
  // verifier, which refutes it.
  expect(proposal.same_groups).toEqual([["mention:r-omi-1", "mention:r-omi-2"]]);
  expect(proposal.same_group_lane).toEqual(["recurrence"]);
  expect(verifyCalls).toHaveLength(1);
  expect(verifyCalls[0]).toContain("me");
  expect(proposal.rejected_same_groups).toEqual([{ group_mention_ids: ["mention:r-me-1", "mention:r-me-2"], reason: "identity_not_proven_on_verification", retryable: false }]);
});

test("a producer-backed identity admits on its coordinate alone -- no verifier, labelled by the speaker rendering", async () => {
  const owner = identity("person:owner");
  const en = { ...mention("mention:owner-en", "claim:o1", owner), surface: "I", evidence_id: "evidence:o1" };
  const ru = { ...mention("mention:owner-ru", "claim:o2", owner), surface: "я", evidence_id: "evidence:o2" };
  const claims = [claim("claim:o1", "evidence:o1", "x"), claim("claim:o2", "evidence:o2", "x")];
  // Nothing in the surfaces relates them; only the producer's key does.
  expect(blockMentionClusters([en, ru]).clusters).toEqual([]);
  const seen: string[][] = [];
  const named = (id: string, excerpt: string, eventId: string) => { const row = evidence(id, excerpt, eventId); return { ...row, evidence: { ...row.evidence, speaker_rendering: "Dazheng" } }; };
  const model = { async invoke(request: { strategy: string; input: unknown }): Promise<unknown> {
    // The card test SELECTS the label for a producer group; the diarization
    // rendering "Dazheng" passes it. Admission never asks the verifier: the
    // shared producer coordinate is the evidence, and surfaces ("I" / "я")
    // could never prove what the producer already asserts.
    if (request.strategy === "speaker-self-reference") return { self_referring: (request.input as { phrases: string[] }).phrases.map(() => true) };
    if (request.strategy === "identity-naming-check") return { names_specific_referent: (request.input as { label: string | null }).label === "Dazheng" };
    if (request.strategy === "identity-verification") throw new Error("verifier must not be consulted for a producer-backed group");
    const profiles = (request.input as { profiles: readonly { mention_id: string }[] }).profiles;
    seen.push(profiles.map((profile) => profile.mention_id));
    return { same_groups: [profiles.map((profile) => profile.mention_id)], uncertain_pairs: [] };
  } };
  const proposal = await invokeBlockedIdentityAdjudication(model, {
    mentions: [en, ru], claims,
    evidence: [named("evidence:o1", "dazheng shipped the ingest path", "event:o1"), named("evidence:o2", "dazheng reviewed it again later", "event:o2")],
    events: [event("event:o1", "session:o1"), event("event:o2", "session:o2")],
  });
  expect(seen).toEqual([["mention:owner-en", "mention:owner-ru"]]);
  expect(proposal.same_groups).toEqual([["mention:owner-en", "mention:owner-ru"]]);
  expect(proposal.same_group_lane).toEqual(["producer"]);
  expect(proposal.same_group_who).toEqual(["Dazheng"]);
});

test("a producer-backed group whose renderings fail the card test admits anyway under a neutral label", async () => {
  const owner = identity("person:owner");
  const a = { ...mention("mention:own-a", "claim:na", owner), surface: "я", evidence_id: "evidence:na" };
  const b = { ...mention("mention:own-b", "claim:nb", owner), surface: "мне", evidence_id: "evidence:nb" };
  const claims = [claim("claim:na", "evidence:na", "x"), claim("claim:nb", "evidence:nb", "x")];
  const junk = (id: string, excerpt: string, eventId: string) => { const row = evidence(id, excerpt, eventId); return { ...row, evidence: { ...row.evidence, speaker_rendering: "Ну" } }; };
  const model = { async invoke(request: { strategy: string; input: unknown }): Promise<unknown> {
    // Diarization mislabeled the speaker "Ну"; the card test refuses it as a
    // name. A plain label must never block a producer-authorized identity.
    if (request.strategy === "speaker-self-reference") return { self_referring: (request.input as { phrases: string[] }).phrases.map(() => true) };
    if (request.strategy === "identity-naming-check") return { names_specific_referent: false };
    if (request.strategy === "identity-verification") throw new Error("verifier must not be consulted for a producer-backed group");
    const profiles = (request.input as { profiles: readonly { mention_id: string }[] }).profiles;
    return { same_groups: [profiles.map((profile) => profile.mention_id)], uncertain_pairs: [] };
  } };
  const proposal = await invokeBlockedIdentityAdjudication(model, {
    mentions: [a, b], claims,
    evidence: [junk("evidence:na", "поехали дальше", "event:na"), junk("evidence:nb", "и мне тоже", "event:nb")],
    events: [event("event:na", "session:na"), event("event:nb", "session:nb")],
  });
  expect(proposal.same_groups).toEqual([["mention:own-a", "mention:own-b"]]);
  expect(proposal.same_group_lane).toEqual(["producer"]);
  expect(proposal.same_group_who).toEqual(["owner"]);
});

test("a null-producer span-local identity never blocks by identity", async () => {
  const spanLocal = { namespace_instance_ref: "namespace:span", local_key: "speaker:unknown", producer: { producer_ref: null, contract_ref: null }, asserted_identity: { domain: null, scope_ref: null } } as unknown as ReturnType<typeof identity>;
  const a = { ...mention("mention:span-1", "claim:s1", spanLocal), surface: "he" };
  const b = { ...mention("mention:span-2", "claim:s2", spanLocal), surface: "him" };
  const claims = [claim("claim:s1", "evidence:s1", "x"), claim("claim:s2", "evidence:s2", "x")];
  // The key is identical, but a synthetic identity asserts nothing across spans.
  expect(blockIdentityClusters([a, b]).clusters).toEqual([]);
  const strategies: string[] = [];
  const model = { async invoke(request: { strategy: string }): Promise<unknown> { strategies.push(request.strategy); return { same_groups: [], uncertain_pairs: [] }; } };
  const proposal = await invokeBlockedIdentityAdjudication(model, { mentions: [a, b], claims });
  expect(strategies).toEqual([]);
  expect(proposal.same_groups).toEqual([]);
  expect(proposal.rejected_same_groups).toEqual([]);
});

test("an oversize identity cluster is sampled across sessions and its remainder is never rejected", async () => {
  const owner = identity("person:owner");
  const members = Array.from({ length: 6 }, (_, index) => ({ ...mention(`mention:o-${index}`, `claim:o-${index}`, owner), surface: `distinct-${index}` }));
  const session = (index: number) => index < 3 ? "session:a" : "session:b";
  const claims = members.map((_, index) => claim(`claim:o-${index}`, `evidence:o-${index}`, "x"));
  const sampled = ["mention:o-0", "mention:o-1", "mention:o-3", "mention:o-4"];
  // Round-robin over sessions, not first-N: two drawn from each session.
  expect(blockIdentityClusters(members, 4, new Map(members.map((item, index) => [item.claim_revision_id, session(index)]))).clusters
    .map((cluster) => cluster.map((item) => item.mention_id))).toEqual([sampled]);
  const sizes: number[] = [];
  const model = { async invoke(request: { strategy: string; input: unknown }): Promise<unknown> {
    if (request.strategy === "speaker-self-reference") return { self_referring: (request.input as { phrases: string[] }).phrases.map(() => true) };
    if (request.strategy === "identity-naming-check") return { names_specific_referent: true };
    if (request.strategy === "identity-verification") return { verdict: "same", who: "Dazheng" };
    const profiles = (request.input as { profiles: readonly { mention_id: string }[] }).profiles;
    sizes.push(profiles.length);
    return { same_groups: [profiles.map((profile) => profile.mention_id)], uncertain_pairs: [] };
  } };
  const proposal = await invokeBlockedIdentityAdjudication(model, {
    mentions: members, claims, max_cluster_size: 4,
    evidence: members.map((_, index) => evidence(`evidence:o-${index}`, "dazheng said it again", `event:o-${index}`)),
    events: members.map((_, index) => event(`event:o-${index}`, session(index))),
  });
  expect(sizes).toEqual([4]);
  expect(proposal.same_groups).toEqual([sampled]);
  // The producer asserts sameness; the unsampled two are for the next cycle.
  expect(proposal.rejected_same_groups).toEqual([]);
});

test("surface and identity blocking coexist without emitting a duplicate group", async () => {
  const boss = identity("person:boss");
  const b1 = { ...mention("mention:b1", "claim:b1", boss), surface: "boss" };
  const b2 = { ...mention("mention:b2", "claim:b2", boss), surface: "Boss" };
  const o1 = { ...mention("mention:o1", "claim:c1", identity("o1")), surface: "Omi" };
  const o2 = { ...mention("mention:o2", "claim:c2", identity("o2")), surface: "omi" };
  const claims = [claim("claim:b1", "evidence:b1", "x"), claim("claim:b2", "evidence:b2", "x"), claim("claim:c1", "evidence:c1", "x"), claim("claim:c2", "evidence:c2", "x")];
  const seen: string[] = [];
  const model = { async invoke(request: { strategy: string; input: unknown }): Promise<unknown> {
    if (request.strategy === "speaker-self-reference") return { self_referring: (request.input as { phrases: string[] }).phrases.map(() => true) };
    if (request.strategy === "identity-naming-check") return { names_specific_referent: true };
    if (request.strategy === "identity-verification") return { verdict: "same", who: (request.input as { surfaces: readonly string[] }).surfaces.join(" ") };
    const ids = (request.input as { profiles: readonly { mention_id: string }[] }).profiles.map((profile) => profile.mention_id);
    seen.push(...ids);
    return { same_groups: [ids.filter((id) => id.startsWith("mention:b")), ids.filter((id) => id.startsWith("mention:o"))].filter((group) => group.length > 1), uncertain_pairs: [] };
  } };
  const proposal = await invokeBlockedIdentityAdjudication(model, { mentions: [b1, b2, o1, o2], claims });
  // The boss pair blocks on both surface and identity; the identical cluster is
  // carried once, so no mention is profiled or grouped twice.
  expect(seen.sort()).toEqual(["mention:b1", "mention:b2", "mention:o1", "mention:o2"]);
  expect(proposal.same_groups).toEqual([["mention:b1", "mention:b2"], ["mention:o1", "mention:o2"]]);
});

test("a verified group sheds same-sentence hitchhikers whose surfaces share nothing with the identity", async () => {
  const shared = (id: string, claimId: string, surface: string) => ({ ...mention(id, claimId, identity(id)), surface });
  const ny1 = shared("mention:p-ny-1", "claim:p1", "new york"), ny2 = shared("mention:p-ny-2", "claim:p2", "New York");
  const rider1 = shared("mention:p-rider-1", "claim:p3", "not that"), rider2 = shared("mention:p-rider-2", "claim:p4", "not that");
  const claims = [claim("claim:p1", "evidence:p1", "x"), claim("claim:p2", "evidence:p2", "x"), claim("claim:p3", "evidence:p3", "x"), claim("claim:p4", "evidence:p4", "x")];
  const model = { async invoke(request: { strategy: string; input: unknown }): Promise<unknown> {
    if (request.strategy === "identity-naming-check") return { names_specific_referent: true };
    if (request.strategy === "identity-verification") return { verdict: "same", who: "New York" };
    const profiles = (request.input as { profiles: readonly { mention_id: string }[] }).profiles;
    const ids = profiles.map((profile) => profile.mention_id);
    // The model over-merges the whole batch into one "New York" group.
    return { same_groups: ids.length > 2 ? [{ members: ids, who: "New York", kind: "deictic_or_generic" }] : [], uncertain_pairs: [] };
  } };
  const proposal = await invokeBlockedIdentityAdjudication(model, { mentions: [ny1, ny2, rider1, rider2], claims });
  expect(proposal.same_groups).toEqual([["mention:p-ny-1", "mention:p-ny-2"]]);
  expect(proposal.rejected_same_groups).toContainEqual({ group_mention_ids: ["mention:p-rider-1", "mention:p-rider-2"], reason: "member_surface_unrelated_to_verified_identity", retryable: true });
});

test("the card test rejects a deictic that names itself, even when the adjudicator calls it a named individual", async () => {
  const shared = (id: string, claimId: string, surface: string) => ({ ...mention(id, claimId, identity(id)), surface });
  const him1 = shared("mention:him-1", "claim:h1", "him"), him2 = shared("mention:him-2", "claim:h2", "him");
  const claims = [claim("claim:h1", "evidence:h1", "x"), claim("claim:h2", "evidence:h2", "x")];
  const checked: (string | null)[] = [];
  const model = { async invoke(request: { strategy: string; input: unknown }): Promise<unknown> {
    // The recurrence lane's grounding gate cannot reject this: who="him"
    // grounds verbatim in surface "him". Only the card test can.
    if (request.strategy === "identity-naming-check") { checked.push((request.input as { label: string | null }).label); return { names_specific_referent: false }; }
    if (request.strategy === "identity-verification") return { verdict: "same", who: "him" };
    const profiles = (request.input as { profiles: readonly { mention_id: string }[] }).profiles;
    return { same_groups: [{ members: profiles.map((profile) => profile.mention_id), who: "him", kind: "named_individual" }], uncertain_pairs: [] };
  } };
  const proposal = await invokeBlockedIdentityAdjudication(model, { mentions: [him1, him2], claims });
  expect(checked).toEqual(["him"]);
  expect(proposal.same_groups).toEqual([]);
  expect(proposal.rejected_same_groups).toEqual([{ group_mention_ids: ["mention:him-1", "mention:him-2"], reason: "identity_reference_context_dependent", retryable: false }]);
});

test("the card test runs on the FINAL label, catching a verified merge whose name fell back to a deictic surface", async () => {
  const shared = (id: string, claimId: string, surface: string) => ({ ...mention(id, claimId, identity(id)), surface });
  const i1 = shared("mention:i-1", "claim:i1", "i"), i2 = shared("mention:i-2", "claim:i2", "i");
  const claims = [claim("claim:i1", "evidence:i1", "x"), claim("claim:i2", "evidence:i2", "x")];
  const checked: (string | null)[] = [];
  const model = { async invoke(request: { strategy: string; input: unknown }): Promise<unknown> {
    if (request.strategy === "identity-naming-check") { checked.push((request.input as { label: string | null }).label); return { names_specific_referent: false }; }
    // The verifier names someone the excerpts DO utter, so admission grounding
    // passes; but "dazheng" never appears in the members' own surfaces, so the
    // label falls back to the dominant surface -- the deictic "i".
    if (request.strategy === "identity-verification") return { verdict: "same", who: "dazheng" };
    const profiles = (request.input as { profiles: readonly { mention_id: string }[] }).profiles;
    return { same_groups: [{ members: profiles.map((profile) => profile.mention_id), who: "the speaker", kind: "deictic_or_generic" }], uncertain_pairs: [] };
  } };
  const proposal = await invokeBlockedIdentityAdjudication(model, {
    mentions: [i1, i2], claims,
    evidence: [evidence("evidence:i1", "dazheng shipped the ingest path", "event:i1"), evidence("evidence:i2", "dazheng reviewed it again later", "event:i2")],
    events: [event("event:i1", "session:i1"), event("event:i2", "session:i2")],
  });
  expect(checked).toEqual(["i"]);
  expect(proposal.same_groups).toEqual([]);
  expect(proposal.rejected_same_groups).toEqual([{ group_mention_ids: ["mention:i-1", "mention:i-2"], reason: "identity_reference_context_dependent", retryable: false }]);
});

test("a naming-check error fails closed as a retryable rejection, never an admission", async () => {
  const shared = (id: string, claimId: string, surface: string) => ({ ...mention(id, claimId, identity(id)), surface });
  const a = shared("mention:nc-1", "claim:nc1", "omi"), b = shared("mention:nc-2", "claim:nc2", "Omi");
  const claims = [claim("claim:nc1", "evidence:nc1", "x"), claim("claim:nc2", "evidence:nc2", "x")];
  const model = { async invoke(request: { strategy: string; input: unknown }): Promise<unknown> {
    if (request.strategy === "identity-naming-check") throw new Error("model unavailable");
    if (request.strategy === "identity-verification") return { verdict: "same", who: "Omi" };
    const profiles = (request.input as { profiles: readonly { mention_id: string }[] }).profiles;
    return { same_groups: [{ members: profiles.map((profile) => profile.mention_id), who: "Omi", kind: "named_individual" }], uncertain_pairs: [] };
  } };
  const proposal = await invokeBlockedIdentityAdjudication(model, { mentions: [a, b], claims });
  expect(proposal.same_groups).toEqual([]);
  expect(proposal.rejected_same_groups).toEqual([{ group_mention_ids: ["mention:nc-1", "mention:nc-2"], reason: "naming_check_failed", retryable: true }]);
});

test("identity settlement is scoped to the complete adjudicator contract and binding state", async () => {
  const shared = identity("settlement-person");
  const a = mention("mention:settle-a", "claim:settle-a", shared);
  const b = mention("mention:settle-b", "claim:settle-b", shared);
  const claims = [claim("claim:settle-a", "evidence:settle-a", "atlas"), claim("claim:settle-b", "evidence:settle-b", "atlas")];
  let calls = 0;
  const model = { async invoke(): Promise<unknown> { calls += 1; return { same_groups: [], uncertain_pairs: [] }; } };

  const first = await invokeBlockedIdentityAdjudication(model, { mentions: [a, b], claims, adjudication_contract: identityContract });
  const settled = new Set(first.adjudicated_cluster_digests ?? []);
  expect(settled.size).toBe(1);

  calls = 0;
  const repeat = await invokeBlockedIdentityAdjudication(model, { mentions: [a, b], claims, adjudication_contract: identityContract, settled_cluster_digests: settled });
  expect(calls).toBe(0);
  expect(repeat.skipped_settled_clusters).toBe(1);

  calls = 0;
  await invokeBlockedIdentityAdjudication(model, { mentions: [a, b], claims, adjudication_contract: { ...identityContract, prompt_version: "prompt-v2" }, settled_cluster_digests: settled });
  expect(calls).toBeGreaterThan(0);

  calls = 0;
  await invokeBlockedIdentityAdjudication(model, { mentions: [{ ...a, entity_id: "entity:settled" }, b], claims, adjudication_contract: identityContract, settled_cluster_digests: settled });
  expect(calls).toBeGreaterThan(0);
});

test("identity settlement is per cluster and withholds only retryable-touched work", async () => {
  const mia = identity("mia"), noa = identity("noa");
  const mentions = [
    mention("mention:mia-a", "claim:mia-a", mia), mention("mention:mia-b", "claim:mia-b", mia),
    mention("mention:noa-a", "claim:noa-a", noa), mention("mention:noa-b", "claim:noa-b", noa),
  ];
  const claims = mentions.map((item) => claim(item.claim_revision_id, item.evidence_id, "atlas"));
  const model = { async invoke(): Promise<unknown> { return { same_groups: [], uncertain_pairs: [] }; } };
  const proposal = await invokeBlockedIdentityAdjudication(model, { mentions, claims, batch_profile_budget: 1, adjudication_contract: identityContract });
  expect(proposal.cluster_membership).toHaveLength(2);
  expect(new Set(proposal.cluster_membership?.flatMap((item) => item.mention_ids))).toEqual(new Set(mentions.map((item) => item.mention_id)));

  const settleable = selectSettleableIdentityClusterDigests({
    proposal,
    retryable_group_mention_ids: [["mention:mia-a"]],
  });
  expect(settleable).toHaveLength(1);
  const settledMembership = proposal.cluster_membership?.find((item) => item.digest === settleable[0]);
  expect(settledMembership?.mention_ids).toEqual(["mention:noa-a", "mention:noa-b"]);
});

test("identity settlement requires explicit contract coordinates", async () => {
  const shared = identity("contract-required");
  const mentions = [mention("mention:contract-a", "claim:contract-a", shared), mention("mention:contract-b", "claim:contract-b", shared)];
  const claims = mentions.map((item) => claim(item.claim_revision_id, item.evidence_id, "atlas"));
  await expect(invokeBlockedIdentityAdjudication(proposalModel({ same_groups: [], uncertain_pairs: [] }), { mentions, claims, settled_cluster_digests: new Set(["digest"]) }))
    .rejects.toThrow("identity settlement requires a complete adjudication contract");
});
