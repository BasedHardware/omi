export type DesktopReleaseChannel = "candidate" | "beta" | "stable" | null;
export type DesktopReleaseLifecycle =
  | "build_candidate"
  | "beta_live"
  | "stable_candidate"
  | "stable";

export interface DesktopStableCandidate {
  complete: boolean;
  nominatedAt: string | null;
  nominatedBy: string | null;
}

const LIFECYCLE_LABELS: Record<DesktopReleaseLifecycle, string> = {
  build_candidate: "Build candidate",
  beta_live: "Beta",
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

export function desktopStableCandidateFromMetadata(
  metadata: Record<string, string>,
  expected: { releaseTag: string },
): DesktopStableCandidate {
  const required = [
    metadata.stableCandidateTag,
    metadata.stableCandidateSha,
    metadata.stableCandidateAt,
    metadata.stableCandidateBy,
    metadata.stableCandidateRationale,
    metadata.stableCandidateSoakReview,
    metadata.stableCandidateTelemetryReview,
    metadata.stableCandidateReleaseNotesReview,
  ];
  const referencesCurrentRelease =
    metadata.stableCandidateTag?.trim() === expected.releaseTag;
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
  betaLive: boolean,
  stableCandidate: DesktopStableCandidate,
): DesktopReleaseLifecycle {
  if (channel === "stable") return "stable";
  if (betaLive && stableCandidate.complete) return "stable_candidate";
  if (betaLive) return "beta_live";
  return "build_candidate";
}

export function tagBuildNumber(tag: string): number | null {
  const match = tag.match(/\+(\d+)-macos$/);
  if (!match) return null;
  return Number.parseInt(match[1], 10);
}

export function newestSparkleVersion(appcast: string): number | null {
  const versions: number[] = [];
  // `exec` loops rather than `for...of matchAll()`: this package targets es5,
  // where iterating an IterableIterator is a compile error (TS2802).
  const patterns = [/<sparkle:version>(\d+)<\/sparkle:version>/g, /sparkle:version="(\d+)"/g];
  for (const pattern of patterns) {
    let match = pattern.exec(appcast);
    while (match !== null) {
      versions.push(Number.parseInt(match[1], 10));
      match = pattern.exec(appcast);
    }
  }
  return versions.length ? Math.max(...versions) : null;
}
