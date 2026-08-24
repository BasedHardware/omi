import { afterEach, describe, expect, it, vi } from "vitest";

const posthogResults = vi.fn();

vi.mock("@/lib/posthog", () => ({ posthogResults }));

const ENV_KEYS = [
  "POSTHOG_PERSONAL_API_KEY",
  "POSTHOG_PROJECT_ID",
  "POSTHOG_HOST",
] as const;
const originalEnv = Object.fromEntries(
  ENV_KEYS.map((key) => [key, process.env[key]]),
);

function configurePosthog() {
  process.env.POSTHOG_PERSONAL_API_KEY = "phx_test";
  process.env.POSTHOG_PROJECT_ID = "1";
  process.env.POSTHOG_HOST = "https://posthog.test";
}

afterEach(() => {
  vi.resetModules();
  posthogResults.mockReset();
  for (const key of ENV_KEYS) {
    if (originalEnv[key] == null) delete process.env[key];
    else process.env[key] = originalEnv[key];
  }
});

describe("computeKFactor referral funnel", () => {
  it("is unavailable when PostHog credentials are missing", async () => {
    delete process.env.POSTHOG_PERSONAL_API_KEY;
    delete process.env.POSTHOG_PROJECT_ID;
    const { computeKFactor } =
      await import("@/app/api/omi/stats/k-factor/posthog/route");

    await expect(computeKFactor(30)).resolves.toMatchObject({
      available: false,
      kFactor: null,
      reason: "PostHog credentials not configured.",
    });
    expect(posthogResults).not.toHaveBeenCalled();
  });

  it("is available with a zero-count funnel", async () => {
    configurePosthog();
    posthogResults.mockResolvedValue([]);
    const { computeKFactor } =
      await import("@/app/api/omi/stats/k-factor/posthog/route");

    await expect(computeKFactor(30, "all")).resolves.toMatchObject({
      available: true,
      kFactor: null,
      funnel: { issued: 0, captured: 0, granted: 0 },
    });
    expect(posthogResults).toHaveBeenCalledTimes(3);
  });

  it("computes granted users divided by issued users", async () => {
    configurePosthog();
    posthogResults
      .mockResolvedValueOnce([[12]])
      .mockResolvedValueOnce([[9]])
      .mockResolvedValueOnce([[3]]);
    const { computeKFactor } =
      await import("@/app/api/omi/stats/k-factor/posthog/route");

    await expect(computeKFactor(30, "macos")).resolves.toMatchObject({
      available: true,
      kFactor: 0.25,
      funnel: { issued: 12, captured: 9, granted: 3 },
    });
    expect(posthogResults.mock.calls[2][3]).toContain(
      "properties.claimed = true",
    );
  });
});
