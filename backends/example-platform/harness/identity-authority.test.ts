import { expect, test } from "bun:test";
import { ingestConversation, localHandleForSourceIdentity } from "../core/extract/ingest";
import { buildEntityResolutionRequest, planEntityResolution } from "../core/resolve/entities";
import type { IdentityAuthorization, IdentityEndpoint, SourceIdentityRef } from "../core/schema";
import { invokeEntityStrategy } from "../drivers/model/entity-edge";
import { DeterministicFakeModel } from "../drivers/model/port";
import { identityThreatFixtures, source, withFetchDisabled } from "./identity-fixtures";

const endpoint = (identity: SourceIdentityRef): IdentityEndpoint => ({ kind: "source_identity", source_identity_ref: identity });
const entityEndpoint = (entity_id: string): IdentityEndpoint => ({ kind: "entity", entity_id });
const ownerAuthorization = (identity: SourceIdentityRef, entity_id: string): IdentityAuthorization => ({ authorization_id: `auth:${entity_id}`, owner_account_id: "owner", endpoints: [endpoint(identity), entityEndpoint(entity_id)], relation: "same", support: { kind: "owner_confirmation", confirmation_ref: `confirmation:${entity_id}` }, standing_policy_ref: null, namespace_scope: { namespace_instance_ref: identity.namespace_instance_ref, identity_domain: identity.asserted_identity.domain, scope_ref: identity.asserted_identity.scope_ref }, authority_policy_version: "identity-policy:v1", evaluated_frontier: 7, actor_provenance: { actor_ref: "owner", producer_ref: null }, lifecycle: "active", superseded_by: null });
const ownerContext = (authorization: IdentityAuthorization) => ({ owner_confirmations: [{ confirmation_ref: (authorization.support as { confirmation_ref: string }).confirmation_ref, owner_account_id: "owner", endpoints: authorization.endpoints, relation: authorization.relation }], producer_assertions: [], standing_policies: [] });

test("I0/I1 hermetic fixtures preserve typed provenance and never use fetch or a real model", async () => {
  await withFetchDisabled(async () => {
    const [left, right] = identityThreatFixtures.same_display_different_namespaces;
    const repeated = identityThreatFixtures.repeated_same_namespace_key;
    const unknown = identityThreatFixtures.unknown_provenance;
    expect(left).not.toEqual(right);
    expect(repeated[0]).toEqual(repeated[1]);
    expect(unknown[0]!.namespace_instance_ref).not.toBe(unknown[1]!.namespace_instance_ref);
    const latin = ingestConversation({ owner_account_id: "owner", capture_session_id: "session:latin", stream_id: "stream", utterances: [{ source_unit_ref: "u1", source_identity_ref: left, speaker_rendering: identityThreatFixtures.renderings.latin, mention_ref: "m", text: "David spoke", event_time: "2026-01-01" }] });
    const cyrillic = ingestConversation({ owner_account_id: "owner", capture_session_id: "session:cyrillic", stream_id: "stream", utterances: [{ source_unit_ref: "u1", source_identity_ref: left, speaker_rendering: identityThreatFixtures.renderings.cyrillic, mention_ref: "m", text: "Давид spoke", event_time: "2026-01-01" }] });
    const missingA = ingestConversation({ owner_account_id: "owner", capture_session_id: "session:a", stream_id: "stream", utterances: [{ source_unit_ref: "u", speaker_rendering: "David", mention_ref: "m", text: "David", event_time: "2026-01-01" }] });
    const missingB = ingestConversation({ owner_account_id: "owner", capture_session_id: "session:b", stream_id: "stream", utterances: [{ source_unit_ref: "u", speaker_rendering: "Давид", mention_ref: "m", text: "Давид", event_time: "2026-01-01" }] });
    expect(latin.evidence[0]!.source_identity_ref).toEqual(cyrillic.evidence[0]!.source_identity_ref);
    expect(latin.evidence[0]!.speaker_rendering).not.toEqual(cyrillic.evidence[0]!.speaker_rendering);
    expect(missingA.evidence[0]!.source_identity_ref!.namespace_instance_ref).not.toBe(missingB.evidence[0]!.source_identity_ref!.namespace_instance_ref);
    expect(localHandleForSourceIdentity(left)).not.toBe(localHandleForSourceIdentity(right));
    await new DeterministicFakeModel({ decision: "abstain" }).invoke({ strategy: "local-handle-durable-entity", version: "v1", input: {} });
  });
});

test("I3 candidate permutations change coverage only; unsupported first-choice models abstain while exact owner authority is stable", async () => {
  const identity = source("namespace:ranking", "42");
  const table = { owner_account_id: "owner", entities: [{ entity_id: "entity:first", owner_account_id: "owner", entity_revision_id: "entity:first:r1", handle: "first", labels: ["David"] }, { entity_id: "entity:target", owner_account_id: "owner", entity_revision_id: "entity:target:r1", handle: "target", labels: ["David"] }], constraints: [] };
  const model = new DeterministicFakeModel((request) => ({ decision: "same", entity_id: (request.input as { candidate_entity_ids: string[] }).candidate_entity_ids[0]! }));
  const resolve = (order: string[], authorizations: readonly IdentityAuthorization[] = []) => invokeEntityStrategy(model, table, "owner", { handle: localHandleForSourceIdentity(identity), mention_ref: "model-chosen-id", antecedent_handle: null, uncertainty: [] }, ["evidence:immutable"], order, new Map(), identity, { snapshot_id: `snapshot:${order.join(":")}`, owner_account_id: "owner", frontier: 7, candidates: order.map((entity_id) => ({ entity_id, owner_account_id: "owner" })), derivations: order.map((entity_id) => ({ artifact_kind: "candidate_derivation" as const, derivation_id: `d:${entity_id}`, owner_account_id: "owner", source_ref: "source", candidate_entity_id: entity_id, strategy_ref: "ranker", input_refs: ["evidence:immutable"] })) }, authorizations, authorizations.length ? ownerContext(authorizations[0]!) : undefined);
  expect(await resolve(["entity:first", "entity:target"])).toMatchObject({ outcome: "abstain" });
  expect(await resolve(["entity:target", "entity:first"])).toMatchObject({ outcome: "abstain" });
  const targetAuthorization = ownerAuthorization(identity, "entity:target");
  expect(await resolve(["entity:target", "entity:first"], [targetAuthorization])).toMatchObject({ outcome: "same", entity_id: "entity:target" });
  expect(await resolve(["entity:first", "entity:target"], [targetAuthorization])).toMatchObject({ outcome: "same", entity_id: "entity:target" });
  const omitted = buildEntityResolutionRequest("owner", { handle: localHandleForSourceIdentity(identity), mention_ref: "m", antecedent_handle: null, uncertainty: [] }, ["evidence:immutable"], ["entity:first"], undefined, identity, { snapshot_id: "omitted", owner_account_id: "owner", frontier: 7, candidates: [{ entity_id: "entity:first", owner_account_id: "owner" }], derivations: [] }, [targetAuthorization], ownerContext(targetAuthorization));
  expect(planEntityResolution(table, omitted, { decision: "same", entity_id: "entity:target" })).toMatchObject({ outcome: "abstain", blockers: ["candidate_snapshot_boundary"] });
});

test("I0/I3 two-slot mixed authorization fails closed for the whole durable claim", async () => {
  const [authorizedIdentity, unsupportedIdentity] = identityThreatFixtures.two_slot_mixed_authorization;
  const targetAuthorization = ownerAuthorization(authorizedIdentity, "entity:target");
  const table = { owner_account_id: "owner", entities: [{ entity_id: "entity:target", owner_account_id: "owner", entity_revision_id: "entity:target:r1", handle: "target", labels: ["David"] }], constraints: [] };
  const model = new DeterministicFakeModel({ decision: "same", entity_id: "entity:target" });
  const resolveSlot = (identity: SourceIdentityRef) => invokeEntityStrategy(model, table, "owner", { handle: localHandleForSourceIdentity(identity), mention_ref: "model-id", antecedent_handle: null, uncertainty: [] }, ["evidence:immutable"], ["entity:target"], new Map(), identity, { snapshot_id: `snapshot:${identity.local_key}`, owner_account_id: "owner", frontier: 7, candidates: [{ entity_id: "entity:target", owner_account_id: "owner" }], derivations: [{ artifact_kind: "candidate_derivation" as const, derivation_id: `d:${identity.local_key}`, owner_account_id: "owner", source_ref: identity.local_key, candidate_entity_id: "entity:target", strategy_ref: "ranker", input_refs: ["evidence:immutable"] }] }, [targetAuthorization], ownerContext(targetAuthorization));
  const results = await Promise.all([resolveSlot(authorizedIdentity), resolveSlot(unsupportedIdentity)]);
  expect(results[0]).toMatchObject({ outcome: "same", entity_id: "entity:target" });
  expect(results[1]).toMatchObject({ outcome: "abstain" });
  expect(results.every((result) => result.outcome === "same")).toBe(false);
});
