import { describe, expect, it } from "vitest";

import {
  desktopQualificationFromMetadata,
  desktopReleaseLifecycle,
  desktopReleaseLifecycleLabel,
  desktopStableCandidateFromMetadata,
} from "../desktop-release-lifecycle";

const completeNomination = {
  stableCandidate: "true",
  stableCandidateTag: "v1.2.3+123-macos",
  stableCandidateSha: "a".repeat(40),
  stableCandidateAt: "2026-07-10T12:00:00Z",
  stableCandidateBy: "release-operator",
  stableCandidateRationale: "soak passed",
  stableCandidateQualificationEvidence: "qualification-evidence.json",
  stableCandidateSoakReview: "24h reviewed",
  stableCandidateTelemetryReview: "health reviewed",
  stableCandidateReleaseNotesReview: "rollup reviewed",
};
const expectedNomination = {
  releaseTag: "v1.2.3+123-macos",
  qualificationEvidence: "qualification-evidence.json",
};

describe("desktop release lifecycle", () => {
  it("reads canonical qualification metadata", () => {
    const qualification = desktopQualificationFromMetadata({
      qualifiedBeta: "true",
      qualifiedBetaAt: "2026-07-10T10:00:00Z",
      qualifiedBetaEvidence: "qualification-evidence.json",
    });
    expect(qualification).toEqual({
      qualified: true,
      qualifiedAt: "2026-07-10T10:00:00Z",
      evidence: "qualification-evidence.json",
      source: "canonical",
    });
  });

  it("accepts legacy qualification metadata", () => {
    const qualification = desktopQualificationFromMetadata({
      blessed: "true",
      blessedAt: "2026-07-09T10:00:00Z",
      blessedEvidence: "legacy-evidence.json",
    });
    expect(qualification.qualified).toBe(true);
    expect(qualification.source).toBe("legacy");
    expect(qualification.evidence).toBe("legacy-evidence.json");
  });

  it("lets canonical metadata override stale legacy metadata", () => {
    const qualification = desktopQualificationFromMetadata({
      qualifiedBeta: "false",
      blessed: "true",
      blessedEvidence: "legacy-evidence.json",
    });
    expect(qualification.qualified).toBe(false);
    expect(qualification.source).toBe("canonical");
  });

  it("requires every nomination field before declaring a stable candidate", () => {
    expect(
      desktopStableCandidateFromMetadata(completeNomination, expectedNomination)
        .complete,
    ).toBe(true);
    expect(
      desktopStableCandidateFromMetadata(
        {
          ...completeNomination,
          stableCandidateTelemetryReview: "",
        },
        expectedNomination,
      ).complete,
    ).toBe(false);
  });

  it("rejects a nomination tied to stale qualification evidence", () => {
    expect(
      desktopStableCandidateFromMetadata(completeNomination, {
        ...expectedNomination,
        qualificationEvidence: "new-evidence.json",
      }).complete,
    ).toBe(false);
  });

  it("distinguishes all four lifecycle states", () => {
    const unqualified = desktopQualificationFromMetadata({});
    const qualified = desktopQualificationFromMetadata({
      qualifiedBeta: "true",
    });
    const notNominated = desktopStableCandidateFromMetadata(
      {},
      expectedNomination,
    );
    const nominated = desktopStableCandidateFromMetadata(
      completeNomination,
      expectedNomination,
    );

    expect(
      desktopReleaseLifecycle("candidate", unqualified, notNominated),
    ).toBe("build_candidate");
    expect(desktopReleaseLifecycle("beta", qualified, notNominated)).toBe(
      "qualified_beta",
    );
    expect(desktopReleaseLifecycle("beta", qualified, nominated)).toBe(
      "stable_candidate",
    );
    expect(desktopReleaseLifecycle("stable", qualified, nominated)).toBe(
      "stable",
    );
  });

  it("uses the canonical four-state operator labels", () => {
    expect(desktopReleaseLifecycleLabel("build_candidate")).toBe(
      "Build candidate",
    );
    expect(desktopReleaseLifecycleLabel("qualified_beta")).toBe(
      "Qualified beta",
    );
    expect(desktopReleaseLifecycleLabel("stable_candidate")).toBe(
      "Stable candidate",
    );
    expect(desktopReleaseLifecycleLabel("stable")).toBe("Stable");
  });
});
