import { describe, expect, it } from "vitest";

import {
  applyFirestoreActivationCompat,
  toGrafanaActivationPayload,
  type ViralMetricsPayload,
} from "@/lib/activation-compat";
import { rollUpActivationCohort } from "@/lib/growth-metrics";

const firestore = rollUpActivationCohort([
  { signupAt: "2026-08-03T09:00:00Z", activated: true },
  { signupAt: "2026-08-04T09:00:00Z", activated: false },
  { signupAt: "2026-08-05T09:00:00Z", activated: true },
]);

function viralPayload(): ViralMetricsPayload {
  return {
    activation: [
      {
        date: "2026-08-03",
        signups: 10,
        activated: 0,
        capableSignups: 0,
        capableActivated: 0,
        rate: 0,
      },
    ],
    summary: {
      activationRate: null,
      activationTelemetryCoverage: 0,
      activationSignups: 0,
      activationPooledRate: 0,
      dau: 12,
    },
  };
}

describe("toGrafanaActivationPayload", () => {
  it("exposes rate plus weeks[] with week/date/signups/activated/rate", () => {
    const payload = toGrafanaActivationPayload(firestore);

    expect(payload.rate).toBe(66.7);
    expect(payload.weeks).toEqual([
      {
        week: "2026-08-03",
        date: "2026-08-03",
        signups: 3,
        activated: 2,
        rate: 66.7,
      },
    ]);
  });
});

describe("applyFirestoreActivationCompat", () => {
  it("leaves viral-metrics unchanged when the Firestore cache is missing", () => {
    const viral = viralPayload();
    expect(applyFirestoreActivationCompat(viral, null)).toEqual(viral);
  });

  it("serves Firestore rate and wall series while keeping telemetry coverage", () => {
    const viral = viralPayload();
    const result = applyFirestoreActivationCompat(viral, firestore);

    expect(result.summary.activationRate).toBe(66.7);
    expect(result.summary.activationTelemetryCoverage).toBe(0);
    expect(result.summary.dau).toBe(12);
    expect(result.activationBucket).toBe("week");
    expect(result.activationDaily).toEqual(viral.activation);
    expect(result.activation).toEqual([
      {
        date: "2026-08-03",
        week: "2026-08-03",
        signups: 3,
        activated: 2,
        rate: 66.7,
      },
    ]);
  });

  it("fails open to telemetry when the Firestore cache is partial", () => {
    const viral = viralPayload();
    const result = applyFirestoreActivationCompat(viral, {
      ...firestore,
      erroredUsers: 2,
    });

    expect(result).toEqual(viral);
    expect(result.summary.activationRate).toBeNull();
    expect(result.activationDaily).toBeUndefined();
  });
});
