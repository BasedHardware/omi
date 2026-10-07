import { afterEach, describe, expect, it, vi } from "vitest";

import { computeOnboarding } from "@/app/api/omi/stats/onboarding/posthog/route";

const ENV_KEYS = [
  "POSTHOG_PERSONAL_API_KEY",
  "POSTHOG_PROJECT_ID",
  "POSTHOG_HOST",
] as const;
const originalEnv = Object.fromEntries(
  ENV_KEYS.map((key) => [key, process.env[key]])
);

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  for (const key of ENV_KEYS) {
    if (originalEnv[key] == null) delete process.env[key];
    else process.env[key] = originalEnv[key];
  }
});

function configure() {
  process.env.POSTHOG_PERSONAL_API_KEY = "phx_test";
  process.env.POSTHOG_PROJECT_ID = "1";
  process.env.POSTHOG_HOST = "https://posthog.test";
}

function errorResponse(status: number, body: string) {
  return {
    ok: false,
    status,
    text: async () => body,
    json: async () => {
      throw new Error(`PostHog ${status} has no results body`);
    },
  };
}

function okResponse(results: unknown[][]) {
  return {
    ok: true,
    status: 200,
    json: async () => ({ results }),
    text: async () => "",
  };
}

function querySent(fetchMock: ReturnType<typeof vi.fn>, call = 0): string {
  const init = fetchMock.mock.calls[call][1] as { body: string };
  return JSON.parse(init.body).query.query as string;
}

describe("computeOnboarding PostHog fetch", () => {
  it("fails when PostHog returns 504 on every attempt", async () => {
    configure();
    vi.useFakeTimers();
    const fetchMock = vi.fn(async () =>
      errorResponse(504, "Query has hit the max execution time")
    );
    vi.stubGlobal("fetch", fetchMock);
    const errorLog = vi.spyOn(console, "error").mockImplementation(() => {});

    const pending = computeOnboarding(30).then(
      () => ({ failed: false as const }),
      (error: unknown) => ({ failed: true as const, error })
    );
    await vi.runAllTimersAsync();
    const outcome = await pending;

    expect(outcome.failed).toBe(true);
    if (!outcome.failed) return;
    expect(outcome.error).toMatchObject({
      name: "PostHogError",
      status: 504,
      message: "PostHog API error: 504",
    });
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(errorLog).toHaveBeenCalledTimes(1);
    expect(errorLog).toHaveBeenCalledWith(
      "PostHog onboarding API error:",
      504,
      "Query has hit the max execution time"
    );
  });

  it("succeeds when the first attempt is 504 and the second is ok", async () => {
    configure();
    vi.useFakeTimers();
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(errorResponse(504, "timeout"))
      .mockResolvedValueOnce(
        okResponse([["user-1", "Onboarding Step Completed", "promise"]])
      );
    vi.stubGlobal("fetch", fetchMock);
    const errorLog = vi.spyOn(console, "error").mockImplementation(() => {});

    const pending = computeOnboarding(30);
    await vi.runAllTimersAsync();
    const payload = await pending;

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(errorLog).not.toHaveBeenCalled();
    expect(payload.days).toBe(30);
    expect(payload.totalUsers).toBe(1);
    expect(payload.truncated).toBe(false);
    expect(payload.steps[0]).toMatchObject({ key: "promise", users: 1 });
  });

  it("bounds the outer events scan at days + 60 and keeps the entrant window", async () => {
    configure();
    const fetchMock = vi.fn(async () => okResponse([]));
    vi.stubGlobal("fetch", fetchMock);

    await computeOnboarding(30);

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const query = querySent(fetchMock);
    const days = 30;
    const entryWindow = days + 60;
    expect(query).toContain(`first_event_at >= now() - INTERVAL ${days} DAY`);
    expect(query).toContain(`timestamp >= now() - INTERVAL ${entryWindow} DAY`);
    // Outer scan: the completion read, not the entrant CTE.
    expect(query).toMatch(
      new RegExp(
        `AND timestamp >= now\\(\\) - INTERVAL ${entryWindow} DAY\\s+AND COALESCE\\(person_id, distinct_id\\) IN \\(SELECT actor_id FROM entrant_actors\\)`
      )
    );
    // Same window on the CTE's events read. The entrant predicate stays `days`.
    expect(query).toMatch(
      new RegExp(
        `AND timestamp >= now\\(\\) - INTERVAL ${entryWindow} DAY\\s+GROUP BY actor_id`
      )
    );
    expect(query).toContain("SELECT * FROM (");
    expect(query).toContain("LIMIT 50000");
  });
});
