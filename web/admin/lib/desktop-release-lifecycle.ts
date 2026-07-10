export type DesktopReleaseChannel = "candidate" | "beta" | "stable" | null;
export type DesktopReleaseLifecycle =
  "build_candidate" | "qualified_beta" | "stable_candidate" | "stable";

export interface DesktopQualification {
  qualified: boolean;
  qualifiedAt: string | null;
  evidence: string | null;
  source: "canonical" | "legacy";
}

export interface DesktopStableCandidate {
  complete: boolean;
  nominatedAt: string | null;
  nominatedBy: string | null;
}

const LIFECYCLE_LABELS: Record<DesktopReleaseLifecycle, string> = {
  build_candidate: "Build candidate",
  qualified_beta: "Qualified beta",
  stable_candidate: "Stable candidate",
  stable: "Stable",
};

export function desktopReleaseLifecycleLabel(
  lifecycle: DesktopReleaseLifecycle,
): string {
  return LIFECYCLE_LABELS[lifecycle];
}

function isTrueMetadata(value: string | undefined): boolean {
  const normalized = value?.trim().toLowerCase();
  return normalized === "true" || normalized === "1" || normalized === "yes";
}

export function desktopQualificationFromMetadata(
  metadata: Record<string, string>,
): DesktopQualification {
  if (Object.prototype.hasOwnProperty.call(metadata, "qualifiedBeta")) {
    return {
      qualified: isTrueMetadata(metadata.qualifiedBeta),
      qualifiedAt: metadata.qualifiedBetaAt?.trim() || null,
      evidence: metadata.qualifiedBetaEvidence?.trim() || null,
      source: "canonical",
    };
  }
  return {
    qualified: isTrueMetadata(metadata.blessed),
    qualifiedAt: metadata.blessedAt?.trim() || null,
    evidence: metadata.blessedEvidence?.trim() || null,
    source: "legacy",
  };
}

export function desktopStableCandidateFromMetadata(
  metadata: Record<string, string>,
  expected: { releaseTag: string; qualificationEvidence: string | null },
): DesktopStableCandidate {
  const required = [
    metadata.stableCandidateTag,
    metadata.stableCandidateSha,
    metadata.stableCandidateAt,
    metadata.stableCandidateBy,
    metadata.stableCandidateRationale,
    metadata.stableCandidateQualificationEvidence,
    metadata.stableCandidateSoakReview,
    metadata.stableCandidateTelemetryReview,
    metadata.stableCandidateReleaseNotesReview,
  ];
  const referencesCurrentRelease =
    metadata.stableCandidateTag?.trim() === expected.releaseTag &&
    Boolean(expected.qualificationEvidence) &&
    metadata.stableCandidateQualificationEvidence?.trim() ===
      expected.qualificationEvidence;
  return {
    complete:
      isTrueMetadata(metadata.stableCandidate) &&
      required.every((value) => Boolean(value?.trim())) &&
      referencesCurrentRelease,
    nominatedAt: metadata.stableCandidateAt?.trim() || null,
    nominatedBy: metadata.stableCandidateBy?.trim() || null,
  };
}

export function desktopReleaseLifecycle(
  channel: DesktopReleaseChannel,
  qualification: DesktopQualification,
  stableCandidate: DesktopStableCandidate,
): DesktopReleaseLifecycle {
  if (channel === "stable") return "stable";
  if (qualification.qualified && stableCandidate.complete)
    return "stable_candidate";
  if (qualification.qualified) return "qualified_beta";
  return "build_candidate";
}
