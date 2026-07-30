import { createHash } from "node:crypto";
import type { Evidence, L1Event } from "../schema";

export interface SyntheticConversationInput {
  owner_account_id: string;
  capture_session_id: string;
  stream_id: string;
  utterances: readonly { source_unit_ref: string; speaker_ref: string; mention_ref: string; text: string; event_time: string }[];
}

export interface IngestedConversation { events: L1Event[]; evidence: Evidence[]; }
const stableHash = (value: unknown) => createHash("sha256").update(JSON.stringify(value)).digest("hex");

/** Pure B1-minimal mapping of caller-supplied synthetic source units to immutable L1 revisions. */
export const ingestSyntheticConversation = (input: SyntheticConversationInput): IngestedConversation => {
  const events = input.utterances.map((utterance, index) => {
    const identity = `${input.capture_session_id}:${utterance.source_unit_ref}`;
    const event_revision_id = `event-revision:${stableHash({ identity, text: utterance.text })}`;
    return {
      event_id: `event:${identity}`,
      event_revision_id,
      owner_account_id: input.owner_account_id,
      capture_session_id: input.capture_session_id,
      stream_id: input.stream_id,
      event_kind: "synthetic.chat/utterance",
      payload_schema_ref: "synthetic.chat/utterance",
      schema_version: "v1",
      payload: { text: utterance.text, source_local_speaker_ref: utterance.speaker_ref, source_local_mention_ref: utterance.mention_ref },
      event_time: utterance.event_time,
      ingest_time: utterance.event_time,
      source_sequence: index,
      evidence_addressable_refs: [`evidence:${identity}`],
      source_trust: "synthetic",
      policy_labels: [],
      canonical_redacted_hash: stableHash({ text: utterance.text, source_unit_ref: utterance.source_unit_ref }),
    } satisfies L1Event;
  });
  const evidence = input.utterances.map((utterance, index) => ({
    evidence_id: `evidence:${input.capture_session_id}:${utterance.source_unit_ref}`,
    event_revision_id: events[index]!.event_revision_id,
    source_unit_ref: utterance.source_unit_ref,
    range: { start: 0, end: utterance.text.length },
    excerpt: utterance.text,
    source_local_speaker_ref: utterance.speaker_ref,
    source_local_mention_ref: utterance.mention_ref,
    state: "active",
    source_trust: "synthetic",
    policy_labels: [],
    source_independence_key: `capture:${input.capture_session_id}`,
  } satisfies Evidence));
  return { events, evidence };
};
