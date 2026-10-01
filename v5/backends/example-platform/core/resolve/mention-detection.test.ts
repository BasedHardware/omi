import { expect, test } from "bun:test";
import { buildMentionDetectionRequest, isForcedUnresolvedMention, planMentionDetection } from "./mention-detection";
import type { ProvisionalClaim } from "../schema";

const claim: ProvisionalClaim = {
  claim_lineage_id: "lineage:pronoun", claim_revision_id: "p-pronoun", owner_account_id: "owner", predicate: "works_on",
  arguments: [{ slot_id: "subject", role: "subject", value: { kind: "literal", value: "She" } }],
  temporal_scope: { observed_at: "2026-01-01T00:00:00Z", precision: "instant" }, evidence_refs: ["e-pronoun"], policy_labels: [], source_language: "en",
  scope: { locality: "source_local", scope_ref: null }, lifecycle: "provisional", ambiguity_markers: [], context_packet: { version: "context-v1", referent_refs: [], topic_refs: [] },
};
const evidence = [{ evidence_id: "e-pronoun", event_revision_id: "event:pronoun", source_unit_ref: "unit:pronoun", range: { start: 0, end: 18 }, excerpt: "She works on atlas", source_identity_ref: null, speaker_rendering: "speaker:owner", source_local_mention_ref: null, state: "active" as const, source_trust: "test", policy_labels: [], source_independence_key: "session" }];

test("D40 adversarial detector omission forces a durable unresolved role mention", () => {
  const mentions = planMentionDetection("owner", buildMentionDetectionRequest([claim], evidence), { mentions: [] });
  expect(mentions).toHaveLength(1);
  expect(mentions[0]).toMatchObject({ claim_revision_id: "p-pronoun", slot_id: "subject", surface: "She", resolution: "unresolved", entity_id: null });
  expect(isForcedUnresolvedMention(mentions[0]!)).toBe(true);
});

test("S0 only the extraction-referenced observed speaker inherits segment attestation", () => {
  const attested = {
    ...claim,
    observed_speaker_slot_id: "speaker",
    arguments: [
      { slot_id: "speaker", role: "speaker", surface: "I", span: { start: 0, end: 1 }, value: { kind: "source_local_ref" as const, ref: "speaker:channel-7" } },
      { slot_id: "person", role: "person", surface: "Alice", span: { start: 6, end: 11 }, value: { kind: "source_local_ref" as const, ref: "mention:alice" } },
    ],
  };
  const attestedEvidence = [{ ...evidence[0]!, excerpt: "I met Alice", range: { start: 0, end: 11 }, source_identity_ref: { namespace_instance_ref: "device:owner", local_key: "person:owner", producer: { producer_ref: "producer", contract_ref: "contract" }, asserted_identity: { domain: "person", scope_ref: "owner" } } }];
  const request = buildMentionDetectionRequest([attested], attestedEvidence);
  const mentions = planMentionDetection("owner", request, { mentions: [
    { mention_id: "speaker", claim_revision_id: "p-pronoun", slot_id: "speaker", span: { start: 0, end: 1 }, evidence_id: "e-pronoun", antecedent_handle: null },
    { mention_id: "alice", claim_revision_id: "p-pronoun", slot_id: "person", span: { start: 6, end: 11 }, evidence_id: "e-pronoun", antecedent_handle: null },
  ] });
  expect(mentions.find((mention) => mention.slot_id === "speaker")?.source_identity_ref).not.toBeNull();
  // A non-speaker never inherits the speaker's attestation, but it retains a
  // typed source-local coordinate so a later, independently authorized dream
  // binding has an endpoint to validate.
  expect(mentions.find((mention) => mention.slot_id === "person")?.source_identity_ref).toMatchObject({ namespace_instance_ref: "source-local:e-pronoun" });
});
