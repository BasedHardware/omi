import { isProxy } from "node:util/types";

import {
  attributionEvidenceFactorRef,
  type AttributionEvidenceDirection,
  type AttributionEvidenceFactor,
} from "../../../core/consolidate/attribution-belief";
import { hypothesisIdForCalibrationCandidate } from
  "../../../core/consolidate/attribution-calibration";
import { sha256CanonicalContent } from "../../../core/retrieve/content-digest";
import type { L1Event, Evidence, SourceIdentityRef } from "../../../core/schema";
import {
  parseFormationInputSnapshot,
  type FormationInputSnapshot,
} from "../workers/formation-work-producer";
import {
  ATTRIBUTION_BELIEF_SHADOW_INPUT_VERSION,
} from "../workers/attribution-belief-shadow-producer";
import { LISTEN_FORMATION_SOURCE_SCHEMA_VERSION } from "./formation-ingestion";

export const LISTEN_ATTRIBUTION_EVIDENCE_CONTRACT_VERSION =
  "listen-attribution-evidence-v1" as const;

export interface ListenAttributionBeliefInput {
  readonly version: typeof ATTRIBUTION_BELIEF_SHADOW_INPUT_VERSION;
  readonly owner_account_id: string;
  readonly belief_kind: "source_identity";
  readonly about_ref: string;
  readonly observation_ref: string;
  readonly observation_content_digest: string;
  readonly graph_frontier: string;
  readonly hypothesis_candidates: readonly Readonly<{
    kind: "owner" | "source_local" | "unknown";
    target_ref: string | null;
  }>[];
  readonly evidence_factors: readonly AttributionEvidenceFactor[];
  readonly attribution_contract_digest: string;
  readonly aggregation_contract_digest: string;
  readonly created_at_event_time: number;
  readonly previous_revision: null;
}

const fail = (code: string): never => {
  throw new TypeError(`listen attribution belief input ${code}`);
};

const ownValue = (value: unknown, key: string): unknown => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)) {
    fail("invalid_event_payload");
  }
  const descriptor = Object.getOwnPropertyDescriptor(value, key);
  if (!descriptor || !("value" in descriptor) || !descriptor.enumerable) {
    fail("invalid_event_payload");
  }
  return descriptor.value;
};

const compare = (left: string, right: string): number => left < right ? -1 : left > right ? 1 : 0;

const eventTime = (value: string): number => {
  const milliseconds = Date.parse(value);
  if (!Number.isSafeInteger(milliseconds) || milliseconds < 0) fail("invalid_event_time");
  return milliseconds;
};

const sourceCoordinate = (source: SourceIdentityRef): Readonly<{
  namespace_instance_ref: string;
  local_key: string;
}> => Object.freeze({
  namespace_instance_ref: source.namespace_instance_ref,
  local_key: source.local_key,
});

const isProducerNullSource = (source: SourceIdentityRef): boolean =>
  source.producer.producer_ref === null && source.producer.contract_ref === null
    && source.asserted_identity.domain === null && source.asserted_identity.scope_ref === null;

const factor = (input: {
  evidence_ref: string;
  independence_group_ref: string;
  hypothesis_id: string;
  direction: AttributionEvidenceDirection;
  signal: "observed_is_user_true" | "observed_is_user_false" | "diarization_weak";
}): AttributionEvidenceFactor => {
  const core = Object.freeze({
    evidence_ref: input.evidence_ref,
    independence_group_ref: input.independence_group_ref,
    hypothesis_id: input.hypothesis_id,
    direction: input.direction,
    factor_contract_digest: sha256CanonicalContent({
      contract_version: LISTEN_ATTRIBUTION_EVIDENCE_CONTRACT_VERSION,
      signal: input.signal,
    }),
  });
  return Object.freeze({ factor_ref: attributionEvidenceFactorRef(core), ...core });
};

const inputFor = (
  snapshot: Readonly<FormationInputSnapshot>,
  observations: readonly Readonly<{ evidence: Evidence; event: L1Event }>[],
  graphFrontier: string,
): Readonly<ListenAttributionBeliefInput> => {
  if (observations.length === 0) fail("empty_source_channel");
  const first = observations[0]!;
  const observedIsUser = ownValue(first.event.payload, "observed_is_user");
  if (typeof observedIsUser !== "boolean") fail("invalid_observed_is_user");
  const expectedLocalKey = observedIsUser
    ? "observed-channel:is-user" : "observed-channel:not-user";
  const source = first.evidence.source_identity_ref;
  if (source.local_key !== expectedLocalKey
    || !isProducerNullSource(source)) {
    fail("invalid_source_coordinate");
  }
  const expectedNamespace = `listen-session:${sha256CanonicalContent({
    owner_account_id: snapshot.owner_account_id,
    session_id: snapshot.session_id,
  })}`;
  const expectedIndependenceKey = `capture:${snapshot.session_id}`;
  for (const observation of observations) {
    const itemObservedUser = ownValue(observation.event.payload, "observed_is_user");
    const eventSourceIdentity = ownValue(observation.event.payload, "source_identity_ref");
    const evidenceSource = observation.evidence.source_identity_ref;
    if (observation.evidence.state !== "active"
      || observation.event.owner_account_id !== snapshot.owner_account_id
      || observation.event.capture_session_id !== snapshot.session_id
      || observation.evidence.event_revision_id !== observation.event.event_revision_id
      || observation.event.event_kind !== "capture.transcript/listen-segment"
      || observation.event.payload_schema_ref !== LISTEN_FORMATION_SOURCE_SCHEMA_VERSION
      || itemObservedUser !== observedIsUser
      || evidenceSource.namespace_instance_ref !== expectedNamespace
      || evidenceSource.local_key !== expectedLocalKey
      || !isProducerNullSource(evidenceSource)
      || observation.evidence.source_independence_key !== expectedIndependenceKey
      || sha256CanonicalContent(evidenceSource) !== sha256CanonicalContent(source)
      || sha256CanonicalContent(eventSourceIdentity) !== sha256CanonicalContent(evidenceSource)) {
      fail("invalid_listen_observation");
    }
  }

  const sourceTargetRef = `attrtarget1_${sha256CanonicalContent({
    contract_version: LISTEN_ATTRIBUTION_EVIDENCE_CONTRACT_VERSION,
    owner_account_id: snapshot.owner_account_id,
    source_identity: sourceCoordinate(source),
  })}`;
  const aboutRef = `about1_${sha256CanonicalContent({
    contract_version: LISTEN_ATTRIBUTION_EVIDENCE_CONTRACT_VERSION,
    owner_account_id: snapshot.owner_account_id,
    source_identity: sourceCoordinate(source),
  })}`;
  const observationRef = `obsref1_${sha256CanonicalContent({
    contract_version: LISTEN_ATTRIBUTION_EVIDENCE_CONTRACT_VERSION,
    owner_account_id: snapshot.owner_account_id,
    source_identity: sourceCoordinate(source),
    observation_coordinates: observations.map(({ evidence, event }) => ({
      evidence_id: evidence.evidence_id,
      event_revision_id: event.event_revision_id,
    })),
  })}`;
  const observationContentDigest = sha256CanonicalContent({
    contract_version: LISTEN_ATTRIBUTION_EVIDENCE_CONTRACT_VERSION,
    owner_account_id: snapshot.owner_account_id,
    observations,
  });
  const candidates = Object.freeze([
    Object.freeze({ kind: "owner" as const, target_ref: null }),
    Object.freeze({ kind: "source_local" as const, target_ref: sourceTargetRef }),
    Object.freeze({ kind: "unknown" as const, target_ref: null }),
  ]);
  const hypothesisBase = {
    owner_account_id: snapshot.owner_account_id,
    belief_kind: "source_identity" as const,
    about_ref: aboutRef,
  };
  const ownerHypothesis = hypothesisIdForCalibrationCandidate(hypothesisBase, candidates[0]!);
  const sourceHypothesis = hypothesisIdForCalibrationCandidate(hypothesisBase, candidates[1]!);
  const factors = observations.flatMap(({ evidence, event }) => {
    const evidenceRef = `atevidence1_${sha256CanonicalContent({
      contract_version: LISTEN_ATTRIBUTION_EVIDENCE_CONTRACT_VERSION,
      observation_ref: observationRef,
      evidence_id: evidence.evidence_id,
      event_revision_id: event.event_revision_id,
    })}`;
    const independenceGroupRef = `atind1_${sha256CanonicalContent({
      contract_version: LISTEN_ATTRIBUTION_EVIDENCE_CONTRACT_VERSION,
      owner_account_id: snapshot.owner_account_id,
      capture_session_id: snapshot.session_id,
    })}`;
    return [
      factor({
        evidence_ref: evidenceRef,
        independence_group_ref: independenceGroupRef,
        hypothesis_id: observedIsUser ? ownerHypothesis : sourceHypothesis,
        direction: "support",
        signal: observedIsUser ? "observed_is_user_true" : "observed_is_user_false",
      }),
      ...(!observedIsUser ? [factor({
        evidence_ref: evidenceRef,
        independence_group_ref: independenceGroupRef,
        hypothesis_id: ownerHypothesis,
        direction: "counter",
        signal: "observed_is_user_false",
      })] : []),
      ...(evidence.policy_labels.includes("diarization:weak") ? [factor({
        evidence_ref: evidenceRef,
        independence_group_ref: independenceGroupRef,
        hypothesis_id: ownerHypothesis,
        direction: "counter",
        signal: "diarization_weak",
      })] : []),
    ];
  }).sort((left, right) => compare(left.factor_ref, right.factor_ref));

  return Object.freeze({
    version: ATTRIBUTION_BELIEF_SHADOW_INPUT_VERSION,
    owner_account_id: snapshot.owner_account_id,
    belief_kind: "source_identity" as const,
    about_ref: aboutRef,
    observation_ref: observationRef,
    observation_content_digest: observationContentDigest,
    graph_frontier: graphFrontier,
    hypothesis_candidates: candidates,
    evidence_factors: Object.freeze(factors),
    attribution_contract_digest: sha256CanonicalContent({
      contract_version: LISTEN_ATTRIBUTION_EVIDENCE_CONTRACT_VERSION,
      modality: "listen_capture_segment",
    }),
    aggregation_contract_digest: sha256CanonicalContent({
      contract_version: "attribution-evidence-independence-v1",
      grouping: "finalized_capture_session",
    }),
    created_at_event_time: Math.max(...observations.map(({ event }) => eventTime(event.event_time))),
    previous_revision: null,
  });
};

/**
 * Converts finalized Listen observations into modality-neutral belief inputs.
 * The noisy `is_user` bit becomes evidence, never typed owner authority.
 */
export const materializeListenAttributionBeliefInputs = (
  snapshotValue: FormationInputSnapshot,
): readonly Readonly<ListenAttributionBeliefInput>[] => {
  const snapshot = parseFormationInputSnapshot(snapshotValue);
  const targetEvidence = new Set(snapshot.target_evidence_ids);
  const events = new Map(snapshot.events.map((event) => [event.event_revision_id, event]));
  if (events.size !== snapshot.events.length) fail("duplicate_event_revision");
  const graphFrontier = sha256CanonicalContent({
    contract_version: LISTEN_ATTRIBUTION_EVIDENCE_CONTRACT_VERSION,
    owner_account_id: snapshot.owner_account_id,
    work_id: snapshot.work_id,
    input_frontier: snapshot.input_frontier,
    graph_frontier: snapshot.graph_frontier,
  });
  const grouped = new Map<string, Array<{ evidence: Evidence; event: L1Event }>>();
  for (const evidence of snapshot.evidence.filter((item) => targetEvidence.has(item.evidence_id))) {
      const event = events.get(evidence.event_revision_id);
      if (!event) fail("missing_event");
      const group = sha256CanonicalContent(sourceCoordinate(evidence.source_identity_ref));
      const observations = grouped.get(group) ?? [];
      observations.push({ evidence, event });
      grouped.set(group, observations);
  }
  if ([...grouped.values()].reduce((total, rows) => total + rows.length, 0) !== targetEvidence.size
    || grouped.size === 0) fail("target_evidence_mismatch");
  const output = [...grouped.values()]
    .map((observations) => inputFor(snapshot, Object.freeze(observations), graphFrontier))
    .sort((left, right) => compare(left.about_ref, right.about_ref));
  return Object.freeze(output);
};
