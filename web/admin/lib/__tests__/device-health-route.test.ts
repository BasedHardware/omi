import { NextRequest, NextResponse } from "next/server";
import { afterEach, describe, expect, it, vi } from "vitest";

const { posthogResults, verifyAdmin } = vi.hoisted(() => ({
  posthogResults: vi.fn(),
  verifyAdmin: vi.fn(async () => ({ uid: "admin" })),
}));
vi.mock("@/lib/posthog", () => ({ posthogResults }));
vi.mock("@/lib/auth", () => ({ verifyAdmin }));

import { GET } from "@/app/api/omi/stats/device-health/route";

const ENV_KEYS = [
  "POSTHOG_PERSONAL_API_KEY",
  "POSTHOG_PROJECT_ID",
  "POSTHOG_HOST",
] as const;
const originalEnv = Object.fromEntries(
  ENV_KEYS.map((key) => [key, process.env[key]])
);

function configure() {
  process.env.POSTHOG_PERSONAL_API_KEY = "phx_test";
  process.env.POSTHOG_PROJECT_ID = "302298";
  process.env.POSTHOG_HOST = "https://posthog.test";
}

function request(query = "") {
  return new NextRequest(
    `http://localhost/api/omi/stats/device-health${query}`
  );
}

function queries(): string[] {
  return posthogResults.mock.calls.map((call) => call[3] as string);
}

afterEach(() => {
  vi.useRealTimers();
  posthogResults.mockReset();
  vi.mocked(verifyAdmin).mockResolvedValue({ uid: "admin" } as never);
  for (const key of ENV_KEYS) {
    if (originalEnv[key] == null) delete process.env[key];
    else process.env[key] = originalEnv[key];
  }
});

describe("device health stats route", () => {
  it("caps days at 30 and defaults a missing or invalid value to 14", async () => {
    configure();
    posthogResults.mockResolvedValue([]);

    const capped = await GET(request("?days=90"));
    expect(capped.status).toBe(200);
    expect(await capped.json()).toMatchObject({ days: 30 });
    for (const query of queries()) {
      expect(query).toContain("INTERVAL 30 DAY");
      expect(query).not.toContain("INTERVAL 90");
    }

    posthogResults.mockClear();
    const fallback = await GET(request("?days=nope"));
    expect((await fallback.json()).days).toBe(14);
    for (const query of queries()) {
      expect(query).toContain("INTERVAL 14 DAY");
    }

    posthogResults.mockClear();
    const omitted = await GET(request());
    expect((await omitted.json()).days).toBe(14);
  });

  it("returns awaiting_instrumentation when the phone query is empty", async () => {
    configure();
    posthogResults.mockImplementation(async (_h, _p, _k, query: string) => {
      if (query.includes("Mobile Device Health Daily")) {
        return [["3.0.21", 10, 4, 3, 5.03, 9.61, 0.26, 1]];
      }
      return [];
    });

    const response = await GET(request("?days=14"));
    expect(response.status).toBe(200);
    const body = await response.json();
    expect(body.phone_health).toEqual({
      status: "awaiting_instrumentation",
      series: [],
    });
    expect(body.pendant_health).toEqual([
      {
        firmware: "3.0.21",
        events: 10,
        users: 4,
        n_valid_drain: 3,
        p50_drain_valid: 5.03,
        p90_drain_valid: 9.61,
        avg_connected_frac: 0.26,
        n_with_cliffs: 1,
      },
    ]);
    expect(posthogResults).toHaveBeenCalledTimes(2);
  });

  it("keeps a null valid-drain quantile null", async () => {
    configure();
    posthogResults.mockImplementation(async (_h, _p, _k, query: string) => {
      if (query.includes("Mobile Device Health Daily")) {
        return [["3.0.18", 154, 129, 0, null, null, 0.03, 0]];
      }
      return [["iOS", "992", 4, 2, 3.5, 8.1]];
    });

    const body = await (await GET(request("?days=14"))).json();
    expect(body.pendant_health[0].p50_drain_valid).toBeNull();
    expect(body.pendant_health[0].p90_drain_valid).toBeNull();
    expect(body.phone_health).toEqual({
      status: "ok",
      series: [
        {
          os: "iOS",
          build: "992",
          label: "iOS 992",
          n_pairs: 4,
          users: 2,
          p50_drain_per_hour: 3.5,
          p90_drain_per_hour: 8.1,
        },
      ],
    });
  });

  it("sends the pendant quantile guard and a bounded phone window query", async () => {
    configure();
    posthogResults.mockResolvedValue([]);
    await GET(request("?days=14"));
    const sent = queries();
    const pendant = sent.find((query) =>
      query.includes("Mobile Device Health Daily")
    );
    const phone = sent.find((query) => query.includes("Phone Battery Sample"));
    expect(pendant).toBeTruthy();
    expect(phone).toBeTruthy();
    expect(pendant).toContain("quantileIf");
    expect(pendant).toContain("BETWEEN 0.1 AND 100");
    expect(pendant).toContain("timestamp >= now() - INTERVAL 14 DAY");
    expect(phone).toContain("Phone Battery Sample");
    expect(phone).toContain("timestamp >= now() - INTERVAL 14 DAY");
    expect(phone).toContain("FROM pairs");
    expect(phone).toContain("lagInFrame");
    expect(phone).not.toContain("quantileIf");
  });

  it("retries PostHog 504 and does not retry a 400", async () => {
    configure();
    vi.useFakeTimers();
    let phoneAttempts = 0;
    posthogResults.mockImplementation(async (_h, _p, _k, query: string) => {
      if (query.includes("Phone Battery Sample")) {
        phoneAttempts += 1;
        if (phoneAttempts < 3)
          throw new Error("PostHog API error: 504 timeout");
        return [];
      }
      return [];
    });

    const pending = GET(request("?days=14"));
    await vi.runAllTimersAsync();
    const retried = await pending;
    expect(retried.status).toBe(200);
    expect(phoneAttempts).toBe(3);
    expect((await retried.json()).phone_health.status).toBe(
      "awaiting_instrumentation"
    );

    vi.useRealTimers();
    posthogResults.mockReset();
    posthogResults.mockRejectedValue(
      new Error("PostHog API error: 400 bad query")
    );
    const rejected = await GET(request("?days=14"));
    expect(rejected.status).toBe(500);
    expect(posthogResults).toHaveBeenCalledTimes(2);
  });

  it("does not query PostHog without credentials or when auth fails", async () => {
    delete process.env.POSTHOG_PERSONAL_API_KEY;
    delete process.env.POSTHOG_PROJECT_ID;
    const missing = await GET(request());
    expect(missing.status).toBe(500);
    expect(posthogResults).not.toHaveBeenCalled();

    configure();
    vi.mocked(verifyAdmin).mockResolvedValue(
      NextResponse.json({ error: "Forbidden" }, { status: 403 }) as never
    );
    const forbidden = await GET(request());
    expect(forbidden.status).toBe(403);
    expect(posthogResults).not.toHaveBeenCalled();
  });
});
