import { createHash } from "node:crypto";
import type { Evidence, L1Event, SourceIdentityRef } from "../schema";

/**
 * Corpus provenance is a property of the CORPUS, never of this function.
 *
 * It used to be hardcoded `synthetic`, and the real-data path ran through here:
 * 1,115 real personal utterances were stored as `source_trust: "synthetic"` and
 * `synthetic.chat/utterance`. Anyone filtering for real data found none, and a
 * privacy purge of "synthetic data" would have deleted the real corpus. The
 * defaults below are deliberately not a lie in either direction -- an unlabelled
 * capture is unattested, not synthetic -- so a caller that says nothing can no
 * longer produce a record that claims to be test data.
 */
export interface ConversationProvenance {
  /** Trust label carried onto every event and evidence row. */
  source_trust?: string;
  event_kind?: string;
  payload_schema_ref?: string;
}
export interface ConversationInput extends ConversationProvenance {
  owner_account_id: string;
  capture_session_id: string;
  stream_id: string;
  /** `ingest_time` is the wall clock at which the capture reached us. It is
   * omitted when the source did not record one; it is never a copy of
   * `event_time`, which made every lag/ordering measurement a measurement of
   * itself. */
  utterances: readonly { source_unit_ref: string; speaker_rendering: string | null; source_identity_ref?: SourceIdentityRef | null; mention_ref: string; text: string; event_time: string; ingest_time?: string | null }[];
}

export interface IngestedConversation { events: L1Event[]; evidence: Evidence[]; }
const defaultProvenance = { source_trust: "unattested", event_kind: "capture.transcript/utterance", payload_schema_ref: "capture.transcript/utterance" } as const;
const stableHash = (value: unknown) => createHash("sha256").update(JSON.stringify(value)).digest("hex");

/**
 * Undiarized captures often arrive as one mega-utterance. Char-bounded units keep
 * extract/search/compose from treating a whole meeting as a single cite (compute dial,
 * not a topic ontology). Prefer splitting on whitespace near the budget.
 */
export const EVIDENCE_EXCERPT_BUDGET = 1_500;

export const splitUtteranceText = (text: string, budget = EVIDENCE_EXCERPT_BUDGET): readonly string[] => {
  if (text.length <= budget) return [text];
  const parts: string[] = [];
  let start = 0;
  while (start < text.length) {
    let end = Math.min(start + budget, text.length);
    if (end < text.length) {
      const slice = text.slice(start, end);
      const breakAt = Math.max(slice.lastIndexOf("\n"), slice.lastIndexOf(". "), slice.lastIndexOf(" "));
      if (breakAt > budget * 0.4) end = start + breakAt + 1;
    }
    const part = text.slice(start, end).trim();
    if (part) parts.push(part);
    start = end;
  }
  return parts.length ? parts : [text];
};

/** Expand oversized utterances into budgeted units; preserves speaker channel on every part. */
export const expandUtterancesForBudget = (utterances: ConversationInput["utterances"], budget = EVIDENCE_EXCERPT_BUDGET): ConversationInput["utterances"] =>
  utterances.flatMap((utterance) => {
    const parts = splitUtteranceText(utterance.text, budget);
    if (parts.length === 1) return [utterance];
    return parts.map((text, part) => ({ ...utterance, source_unit_ref: `${utterance.source_unit_ref}:part${part}`, text }));
  });

/** A missing producer namespace is unique per observed source unit, never a shared "unknown" namespace. */
export const sourceIdentityForUtterance = (captureSessionId: string, utterance: ConversationInput["utterances"][number]): SourceIdentityRef =>
  utterance.source_identity_ref ?? {
    namespace_instance_ref: `unscoped:${captureSessionId}:${utterance.source_unit_ref}`,
    local_key: utterance.mention_ref || utterance.source_unit_ref,
    producer: { producer_ref: null, contract_ref: null },
    asserted_identity: { domain: null, scope_ref: null },
  };

/** Stable source-local handles derive only from typed source coordinates. */
export const localHandleForSourceIdentity = (identity: SourceIdentityRef): string =>
  `local:${stableHash({ namespace_instance_ref: identity.namespace_instance_ref, local_key: identity.local_key })}`;

/** Pure B1-minimal mapping of caller-supplied source units to immutable L1 revisions. */
export const ingestConversation = (input: ConversationInput): IngestedConversation => {
  const source_trust = input.source_trust ?? defaultProvenance.source_trust;
  const event_kind = input.event_kind ?? defaultProvenance.event_kind;
  const payload_schema_ref = input.payload_schema_ref ?? defaultProvenance.payload_schema_ref;
  const utterances = expandUtterancesForBudget(input.utterances);
  const events = utterances.map((utterance, index) => {
    const identity = `${input.capture_session_id}:${utterance.source_unit_ref}`;
    const event_revision_id = `event-revision:${stableHash({ identity, text: utterance.text })}`;
    return {
      event_id: `event:${identity}`,
      event_revision_id,
      owner_account_id: input.owner_account_id,
      capture_session_id: input.capture_session_id,
      stream_id: input.stream_id,
      event_kind,
      payload_schema_ref,
      schema_version: "v1",
      payload: { text: utterance.text, source_identity_ref: sourceIdentityForUtterance(input.capture_session_id, utterance), speaker_rendering: utterance.speaker_rendering, source_local_mention_ref: utterance.mention_ref },
      event_time: utterance.event_time,
      ingest_time: utterance.ingest_time ?? null,
      source_sequence: index,
      evidence_addressable_refs: [`evidence:${identity}`],
      source_trust,
      policy_labels: [],
      canonical_redacted_hash: stableHash({ text: utterance.text, source_unit_ref: utterance.source_unit_ref }),
    } satisfies L1Event;
  });
  const evidence = utterances.map((utterance, index) => ({
    evidence_id: `evidence:${input.capture_session_id}:${utterance.source_unit_ref}`,
    event_revision_id: events[index]!.event_revision_id,
    source_unit_ref: utterance.source_unit_ref,
    range: { start: 0, end: utterance.text.length },
    excerpt: utterance.text,
    source_identity_ref: sourceIdentityForUtterance(input.capture_session_id, utterance),
    speaker_rendering: utterance.speaker_rendering,
    source_local_mention_ref: utterance.mention_ref,
    state: "active",
    source_trust,
    // Split of an oversized undiarized capture: speaker channel is not trustworthy for subject:owner.
    policy_labels: /:part\d+$/u.test(utterance.source_unit_ref) ? ["diarization:weak"] : [],
    source_independence_key: `capture:${input.capture_session_id}`,
  } satisfies Evidence));
  return { events, evidence };
};
