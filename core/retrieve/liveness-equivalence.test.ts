import { expect, test } from "bun:test";
import { sha256CanonicalRedacted } from "../ledger";
import { compareStrings } from "../order";
import type { CanonicalClaim, Evidence } from "../schema";
import { genericPolicyClassifier, grantAllows, liveCommittedClaims, project, type CommittedClaim, type CommittedEvidence, type D35LivenessCauses, type GraphSnapshot, type RequestContext } from "./index";

const explicitlySupersedesReference = (newer: CommittedClaim, older: CommittedClaim): boolean => {
  const sourceIds = newer.claim.lifecycle === "canonical" ? newer.claim.source_provisional_revision_ids : [];
  const explicit = newer.claim.lifecycle === "canonical" ? newer.claim.supersedes_revision_ids ?? [] : [];
  return [...sourceIds, ...explicit].includes(older.revision_id);
};

const stableTieBreakReference = (item: CommittedClaim): string => sha256CanonicalRedacted({ revision_id: item.revision_id, claim: item.claim, placement_status: item.placement_status });

const selectLineageHeadReference = (members: readonly CommittedClaim[]): CommittedClaim => {
  const rank = (item: CommittedClaim) => item.placement_status === "canonical" ? 2 : 1;
  if (members.length === 1) return members[0]!;
  const explicitHeads = members.filter((candidate) => !members.some((other) => other !== candidate && explicitlySupersedesReference(other, candidate)));
  if (explicitHeads.length === 1 && members.some((candidate) => explicitlySupersedesReference(explicitHeads[0]!, candidate))) return explicitHeads[0]!;
  if (members.some((member) => member.commit_sequence === undefined)) return [...members].sort((left, right) => compareStrings(stableTieBreakReference(left), stableTieBreakReference(right)))[0]!;
  return [...members].sort((left, right) => {
    const sequence = right.commit_sequence! - left.commit_sequence!;
    if (sequence) return sequence;
    const placement = rank(right) - rank(left);
    return placement || compareStrings(stableTieBreakReference(left), stableTieBreakReference(right));
  })[0]!;
};

/** The allocation-heavy pre-refactor implementation, retained only as an equivalence oracle. */
const currentEvidenceByIdReference = (revisions: readonly CommittedEvidence[]): Map<string, Evidence> => {
  const grouped = new Map<string, CommittedEvidence[]>();
  for (const revision of revisions) grouped.set(revision.evidence.evidence_id, [...(grouped.get(revision.evidence.evidence_id) ?? []), revision]);
  const current = new Map<string, Evidence>();
  for (const [evidenceId, members] of grouped) {
    if (members.length === 1) {
      current.set(evidenceId, members[0]!.evidence);
      continue;
    }
    if (members.some((member) => member.commit_sequence === undefined)) continue;
    const greatest = Math.max(...members.map((member) => member.commit_sequence!));
    const heads = members.filter((member) => member.commit_sequence === greatest);
    if (heads.length === 1) current.set(evidenceId, heads[0]!.evidence);
  }
  return current;
};

const isLiveReference = (claim: CommittedClaim, causes: D35LivenessCauses): boolean => {
  if (causes.purged_claim_revision_ids.includes(claim.revision_id) || causes.forgotten_claim_revision_ids.includes(claim.revision_id)) return false;
  if (claim.claim.lifecycle === "canonical" && claim.claim.evidence_refs.length > 0) {
    const evidenceById = currentEvidenceByIdReference(causes.evidence);
    const citedEvidence = claim.claim.evidence_refs.map((ref) => evidenceById.get(ref)).filter((evidence): evidence is Evidence => evidence !== undefined);
    if (!citedEvidence.some((evidence) => evidence.state === "active")) return false;
  }
  const lineage = causes.lineage_members.filter((member) => member.claim.claim_lineage_id === claim.claim.claim_lineage_id);
  return !lineage.length || selectLineageHeadReference(lineage).revision_id === claim.revision_id;
};

const referenceLiveCommittedClaims = (snapshot: GraphSnapshot, ctx: RequestContext): readonly CommittedClaim[] => {
  const evidenceById = currentEvidenceByIdReference(snapshot.evidence ?? []);
  const eligible = snapshot.claims.filter((item) => item.placement_status !== "consumed").filter((item) => {
    const evidence = item.claim.evidence_refs.map((ref) => evidenceById.get(ref)).filter((entry): entry is Evidence => entry !== undefined);
    return grantAllows(ctx, item.claim, genericPolicyClassifier.classify(item.claim, evidence));
  });
  const causes = (lineage_members: readonly CommittedClaim[]): D35LivenessCauses => ({
    evidence: snapshot.evidence ?? [],
    purged_claim_revision_ids: snapshot.liveness_causes?.purged_claim_revision_ids ?? [],
    forgotten_claim_revision_ids: snapshot.liveness_causes?.forgotten_claim_revision_ids ?? [],
    lineage_members,
  });
  const materiallyLive = eligible.filter((item) => isLiveReference(item, causes([item])));
  const byLineage = new Map<string, CommittedClaim[]>();
  for (const item of materiallyLive) byLineage.set(item.claim.claim_lineage_id, [...(byLineage.get(item.claim.claim_lineage_id) ?? []), item]);
  return [...byLineage.values()].flatMap((members) => members.filter((item) => isLiveReference(item, causes(members)))).sort((left, right) => compareStrings(left.revision_id, right.revision_id));
};

const genericLabels = ["subject:generic", "sensitivity:generic", "capture:generic"];
const privateLabels = ["subject:generic", "sensitivity:private", "capture:generic"];
const committedClaim = (revision_id: string, lineage: string, evidenceRef: string, labels = genericLabels, commit_sequence?: number): CommittedClaim => ({
  revision_id,
  ...(commit_sequence === undefined ? {} : { commit_sequence }),
  placement_status: "canonical",
  claim: {
    claim_lineage_id: lineage,
    claim_revision_id: revision_id,
    owner_account_id: "owner",
    predicate: "remembers",
    arguments: [],
    temporal_scope: { observed_at: "2026-08-11", precision: "day" },
    evidence_refs: [evidenceRef],
    policy_labels: labels,
    source_language: "en",
    scope: { locality: "durable", scope_ref: null },
    lifecycle: "canonical",
    canonical_claim_id: `canonical:${revision_id}`,
    source_provisional_revision_ids: [],
  } satisfies CanonicalClaim,
});

const committedEvidence = (revision_id: string, evidence_id: string, state: "active" | "tombstoned", commit_sequence?: number): CommittedEvidence => ({
  revision_id,
  ...(commit_sequence === undefined ? {} : { commit_sequence }),
  evidence: { evidence_id, event_revision_id: `event:${evidence_id}`, source_unit_ref: null, range: { start: 0, end: 1 }, excerpt: null, source_identity_ref: null, speaker_rendering: null, source_local_mention_ref: null, state, source_trust: "test", policy_labels: [], source_independence_key: evidence_id },
});

const fixture = (reversed: boolean): GraphSnapshot => {
  const claims = [
    committedClaim("generic-old", "lineage:reader-relative", "e:generic", genericLabels, 1),
    committedClaim("private-new", "lineage:reader-relative", "e:private", privateLabels, 2),
    committedClaim("active", "lineage:active", "e:active", genericLabels, 3),
    committedClaim("tombstoned", "lineage:tombstoned", "e:tombstoned", genericLabels, 4),
    committedClaim("corrupt-evidence-head", "lineage:corrupt-evidence-head", "e:tie", genericLabels, 5),
    committedClaim("purged", "lineage:purged", "e:active", genericLabels, 6),
    committedClaim("forgotten", "lineage:forgotten", "e:active", genericLabels, 7),
    committedClaim("missing-sequence-a", "lineage:missing-sequence", "e:active"),
    committedClaim("missing-sequence-b", "lineage:missing-sequence", "e:active"),
  ];
  const evidence = [
    committedEvidence("e:generic:r1", "e:generic", "active", 1),
    committedEvidence("e:private:r1", "e:private", "active", 2),
    committedEvidence("e:active:r1", "e:active", "active", 3),
    committedEvidence("e:tombstoned:r1", "e:tombstoned", "tombstoned", 4),
    committedEvidence("e:tie:r1", "e:tie", "active", 8),
    committedEvidence("e:tie:r2", "e:tie", "tombstoned", 8),
  ];
  return {
    owner_account_id: "owner",
    claims: reversed ? claims.reverse() : claims,
    entities: [],
    evidence: reversed ? evidence.reverse() : evidence,
    liveness_causes: {
      purged_claim_revision_ids: reversed ? ["unused-purge", "purged"] : ["purged", "unused-purge"],
      forgotten_claim_revision_ids: reversed ? ["unused-forget", "forgotten"] : ["forgotten", "unused-forget"],
    },
    adjacency: [],
  };
};

const genericGrant = { grant_id: "generic", policy_classes: [{ subject_class: "generic", sensitivity: "generic", capture_class: "generic" }] };
const cases: readonly { name: string; ctx: RequestContext; reversed: boolean; expectedReaderHead: string }[] = [
  { name: "owner grant, forward order", ctx: { reader_account_id: "owner", grant: genericGrant }, reversed: false, expectedReaderHead: "private-new" },
  { name: "owner grant, reversed order", ctx: { reader_account_id: "owner", grant: genericGrant }, reversed: true, expectedReaderHead: "private-new" },
  { name: "generic reader, forward order", ctx: { reader_account_id: "reader", grant: genericGrant }, reversed: false, expectedReaderHead: "generic-old" },
  { name: "generic reader, reversed order", ctx: { reader_account_id: "reader", grant: genericGrant }, reversed: true, expectedReaderHead: "generic-old" },
];

for (const row of cases) test(`D35 optimized selection matches the pre-refactor reference: ${row.name}`, () => {
  const snapshot = fixture(row.reversed);
  const referenceIds = referenceLiveCommittedClaims(snapshot, row.ctx).map((item) => item.revision_id);
  expect(liveCommittedClaims(snapshot, row.ctx).map((item) => item.revision_id)).toEqual(referenceIds);
  expect(project(snapshot, row.ctx).claims.map((item) => item.revision_id)).toEqual(referenceIds);

  expect(referenceIds).toContain("active");
  expect(referenceIds).toContain(row.expectedReaderHead);
  expect(referenceIds.filter((id) => id.startsWith("missing-sequence-"))).toHaveLength(1);
  expect(referenceIds).not.toContain("tombstoned");
  expect(referenceIds).not.toContain("corrupt-evidence-head");
  expect(referenceIds).not.toContain("purged");
  expect(referenceIds).not.toContain("forgotten");
});
