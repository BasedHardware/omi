import { expect, test } from "bun:test";
import { placementConversation } from "../../harness/fixtures";
import { EVIDENCE_EXCERPT_BUDGET, expandUtterancesForBudget, ingestConversation, splitUtteranceText } from "./ingest";
import { groundedExtractionInvariantPrefix, groundedPrompt } from "./grounded";
import type { WritingContext } from "../retrieve/writing-context";

test("T2 synthetic conversation maps to addressable L1 evidence with stable hashes", () => {
  const first = ingestConversation(placementConversation);
  const second = ingestConversation(placementConversation);
  expect(first).toEqual(second);
  expect(first.events).toHaveLength(3);
  expect(first.evidence[1]).toMatchObject({ speaker_rendering: "speaker:bob", source_local_mention_ref: "mention:he", range: { start: 0, end: 33 }, source_identity_ref: { namespace_instance_ref: "unscoped:synthetic-session-1:turn-2", local_key: "mention:he" } });
  expect(first.events[1]!.evidence_addressable_refs).toContain(first.evidence[1]!.evidence_id);
  expect(first.evidence[1]!.excerpt).toBe((first.events[1]!.payload as { text: string }).text);
});

test("evidence budget splits mega-utterances without changing speaker channel", () => {
  const text = ("Hello Mira. ".repeat(200) + "I am Nora. Nice to meet you. ".repeat(50)).slice(0, EVIDENCE_EXCERPT_BUDGET * 3 + 100);
  const parts = splitUtteranceText(text);
  expect(parts.length).toBeGreaterThan(1);
  expect(Math.max(...parts.map((part) => part.length))).toBeLessThanOrEqual(EVIDENCE_EXCERPT_BUDGET);
  const owner = {
    namespace_instance_ref: "device",
    local_key: "person:owner",
    producer: { producer_ref: "p", contract_ref: "c" },
    asserted_identity: { domain: "person", scope_ref: "owner" },
  };
  const expanded = expandUtterancesForBudget([{
    source_unit_ref: "turn-mega",
    speaker_rendering: "Owner",
    source_identity_ref: owner,
    mention_ref: "owner",
    text,
    event_time: "2026-01-01T00:00:00Z",
  }]);
  expect(expanded.length).toBe(parts.length);
  expect(expanded.every((utterance) => utterance.source_identity_ref?.local_key === "person:owner")).toBe(true);
  const ingested = ingestConversation({
    owner_account_id: "owner",
    capture_session_id: "session-mega",
    stream_id: "stream",
    utterances: [{
      source_unit_ref: "turn-mega",
      speaker_rendering: "Owner",
      source_identity_ref: owner,
      mention_ref: "owner",
      text,
      event_time: "2026-01-01T00:00:00Z",
    }],
  });
  expect(ingested.evidence.length).toBe(parts.length);
  expect(ingested.evidence.every((item) => (item.excerpt?.length ?? 0) <= EVIDENCE_EXCERPT_BUDGET)).toBe(true);
  expect(ingested.evidence.every((item) => item.source_identity_ref?.local_key === "person:owner")).toBe(true);
  expect(ingested.evidence.every((item) => item.policy_labels?.includes("diarization:weak"))).toBe(true);
});

test("grounded v6 prompt keeps channel invariants for multi-party / undiarized speech", () => {
  expect(groundedExtractionInvariantPrefix.startsWith("grounded-extraction-v6")).toBe(true);
  expect(groundedExtractionInvariantPrefix).toContain("Diarization may be missing or wrong");
  expect(groundedExtractionInvariantPrefix).toContain("never assign another person's self-introduction");
  const emptyContext: WritingContext = {
    frontier: { graph_head: "g", policy_version: "p", predicate_alias_generation: "a", authorization_generation: "i", stm_generation: "s" },
    entity_candidates: [],
    predicate_signatures: [],
    open_propositions: [],
  };
  const prompt = groundedPrompt(emptyContext, [{
    evidence_id: "e1",
    event_revision_id: "event",
    source_unit_ref: "u",
    range: { start: 0, end: 40 },
    excerpt: "Nice to meet you, Mira. I am Nora.",
    source_identity_ref: null,
    speaker_rendering: "Owner",
    source_local_mention_ref: null,
    state: "active",
    source_trust: "test",
    policy_labels: [],
    source_independence_key: "k",
  }]);
  expect(groundedExtractionInvariantPrefix).toContain("when unsure whose 'I' it is, omit the owner-about claim");
  expect(prompt).toContain("several people talk inside one excerpt");
  expect(prompt).toContain("Owner self-id claims belong only to clear self-introductions");
});
