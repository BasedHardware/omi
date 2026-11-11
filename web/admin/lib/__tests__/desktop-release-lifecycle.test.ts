import { describe, expect, it } from "vitest";

import {
  desktopReleaseLifecycle,
  desktopReleaseLifecycleLabel,
  desktopStableCandidateFromMetadata,
  newestSparkleVersion,
  tagBuildNumber,
} from "../desktop-release-lifecycle";

const completeNomination = {
  stableCandidate: "true",
  stableCandidateTag: "v1.2.3+123-macos",
  stableCandidateSha: "a".repeat(40),
  stableCandidateAt: "2026-07-10T12:00:00Z",
  stableCandidateBy: "release-operator",
  stableCandidateRationale: "soak passed",
  stableCandidateSoakReview: "24h reviewed",
  stableCandidateTelemetryReview: "health reviewed",
  stableCandidateReleaseNotesReview: "rollup reviewed",
};
const expectedNomination = {
  releaseTag: "v1.2.3+123-macos",
};

describe("desktop release lifecycle", () => {
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

  it("rejects a nomination tied to a different release tag", () => {
    expect(
      desktopStableCandidateFromMetadata(completeNomination, {
        releaseTag: "v9.9.9+999-macos",
      }).complete,
    ).toBe(false);
  });

  it("does not require qualification evidence for a stable candidate", () => {
    expect(
      desktopStableCandidateFromMetadata(
        {
          ...completeNomination,
          stableCandidateQualificationEvidence: "",
        },
        expectedNomination,
      ).complete,
    ).toBe(true);
  });

  it("distinguishes candidate, live beta, stable-candidate, and stable", () => {
    const notNominated = desktopStableCandidateFromMetadata(
      {},
      expectedNomination,
    );
    const nominated = desktopStableCandidateFromMetadata(
      completeNomination,
      expectedNomination,
    );

    expect(desktopReleaseLifecycle("candidate", false, notNominated)).toBe(
      "build_candidate",
    );
    expect(desktopReleaseLifecycle("beta", true, notNominated)).toBe(
      "beta_live",
    );
    expect(desktopReleaseLifecycle("beta", true, nominated)).toBe(
      "stable_candidate",
    );
    expect(desktopReleaseLifecycle("stable", true, nominated)).toBe("stable");
  });

  it("uses the canonical operator labels", () => {
    expect(desktopReleaseLifecycleLabel("build_candidate")).toBe(
      "Build candidate",
    );
    expect(desktopReleaseLifecycleLabel("beta_live")).toBe("Beta");
    expect(desktopReleaseLifecycleLabel("stable_candidate")).toBe(
      "Stable candidate",
    );
    expect(desktopReleaseLifecycleLabel("stable")).toBe("Stable");
  });

  it("matches live beta by the newest sparkle version", () => {
    expect(tagBuildNumber("v0.12.172+12172-macos")).toBe(12172);
    expect(
      newestSparkleVersion(
        '<item><sparkle:version>12170</sparkle:version></item><item sparkle:version="12172"/>',
      ),
    ).toBe(12172);
  });
});
