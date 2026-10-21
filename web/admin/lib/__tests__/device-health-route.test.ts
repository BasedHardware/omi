import { execFileSync } from "node:child_process";
import path from "node:path";
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

// Execute production selection SQL over event fixtures inside the existing
// PostHog mock. The adapter changes dialect only; it does not duplicate guards.
function phoneFixtureRows(
  rows: Array<{
    person_id: string;
    timestamp: number;
    properties: Record<string, unknown>;
  }>
) {
  posthogResults.mockImplementation(async (_h, _p, _k, query: string) => {
    if (query.includes("Mobile Device Health Daily")) return [];
    if (query.includes("SELECT count() AS n")) return [[rows.length]];
    return JSON.parse(
      execFileSync(
        "python3",
        [path.resolve("lib/__tests__/support/phone-health-sql-fixture.py")],
        {
          input: JSON.stringify({ query, rows }),
          encoding: "utf8",
        }
      )
    );
  });
}

function sampleFixture(
  schema: number,
  timestamp: number,
  properties: Record<string, unknown> = {}
) {
  return {
    person_id: "fixture-user",
    timestamp,
    properties: {
      platform: "iOS",
      app_build: "1348",
      app_version: "1.0.559",
      schema_version: schema,
      battery_observation_build: "1348",
      battery_level: 70,
      battery_charging: false,
      previous_battery_level: 72,
      previous_battery_charging: false,
      battery_interval_seconds: 1800,
      battery_interval_validity: "same_build",
      ...properties,
    },
  };
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
        return [["3.0.21", "iOS", "Omi Device", 10, 4, 3, 5.03, 9.61, 0.26, 1]];
      }
      if (query.includes("SELECT count() AS n")) return [[0]];
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
        os: "iOS",
        device_model: "Omi Device",
        firmware_label: "3.0.21 · iOS",
        events: 10,
        users: 4,
        n_valid_drain: 3,
        p50_drain_valid: 5.03,
        p90_drain_valid: 9.61,
        avg_connected_frac: 0.26,
        n_with_cliffs: 1,
      },
    ]);
    // Drain query is empty, so a count query confirms there are no events.
    expect(posthogResults).toHaveBeenCalledTimes(3);
    expect(
      queries().some((query) => query.includes("SELECT count() AS n"))
    ).toBe(true);
  });

  it("reports measured_no_valid_pairs when events exist but no pair survives", async () => {
    configure();
    posthogResults.mockImplementation(async (_h, _p, _k, query: string) => {
      if (query.includes("Mobile Device Health Daily")) return [];
      if (query.includes("SELECT count() AS n")) return [[7]];
      return [];
    });

    const body = await (await GET(request("?days=14"))).json();
    expect(body.phone_health).toEqual({
      status: "measured_no_valid_pairs",
      series: [],
      n_events: 7,
    });
    const countQuery = queries().find((query) =>
      query.includes("SELECT count() AS n")
    );
    expect(countQuery).toContain("event = 'Phone Battery Sample'");
    expect(countQuery).toContain("timestamp >= now() - INTERVAL 14 DAY");
    expect(posthogResults).toHaveBeenCalledTimes(3);
  });

  it("keeps a null valid-drain quantile null", async () => {
    configure();
    posthogResults.mockImplementation(async (_h, _p, _k, query: string) => {
      if (query.includes("Mobile Device Health Daily")) {
        return [["3.0.18", "Android", "Omi", 154, 129, 0, null, null, 0.03, 0]];
      }
      return [["iOS", "1347", "1.0.558", 4, 2, 3.5, 8.1]];
    });

    const body = await (await GET(request("?days=14"))).json();
    expect(body.pendant_health[0].p50_drain_valid).toBeNull();
    expect(body.pendant_health[0].p90_drain_valid).toBeNull();
    expect(body.pendant_health[0].device_model).toBe("Omi");
    expect(body.pendant_health[0].firmware_label).toBe("3.0.18 · Android");
    expect(body.phone_health).toEqual({
      status: "ok",
      series: [
        {
          os: "iOS",
          build: "1347",
          app_version: "1.0.558",
          label: "iOS 1.0.558 (1347)",
          n_pairs: 4,
          n_v1_pairs: 0,
          n_v2_intervals: 0,
          users: 2,
          p50_drain_per_hour: 3.5,
          p90_drain_per_hour: 8.1,
        },
      ],
    });
    // A non-empty pair series skips the event-count query.
    expect(posthogResults).toHaveBeenCalledTimes(2);
  });

  it("sends the pendant quantile guard and a bounded phone window query", async () => {
    configure();
    posthogResults.mockResolvedValue([]);
    await GET(request("?days=14"));
    const sent = queries();
    const pendant = sent.find((query) =>
      query.includes("Mobile Device Health Daily")
    );
    const phone = sent.find((query) => query.includes("FROM pairs"));
    expect(pendant).toBeTruthy();
    expect(phone).toBeTruthy();
    expect(
      pendant!.match(
        /quantileIf\(0\.5\)\(toFloat\(properties\.drain_percent_per_hour\), toFloat\(properties\.drain_percent_per_hour\) BETWEEN 0\.1 AND 100\)/g
      )
    ).toHaveLength(1);
    expect(
      pendant!.match(
        /quantileIf\(0\.9\)\(toFloat\(properties\.drain_percent_per_hour\), toFloat\(properties\.drain_percent_per_hour\) BETWEEN 0\.1 AND 100\)/g
      )
    ).toHaveLength(1);
    expect(pendant).toContain("BETWEEN 0.1 AND 100");
    expect(pendant).toContain("timestamp >= now() - INTERVAL 14 DAY");
    expect(phone).toContain("Phone Battery Sample");
    expect(phone).toContain("timestamp >= now() - INTERVAL 14 DAY");
    expect(phone).toContain("FROM pairs");
    expect(phone).toContain("lagInFrame");
    expect(phone).toContain("quantileIf");
    expect(pendant).toContain(
      "coalesce(nullIf(properties.$os_name,''), properties.platform) AS os"
    );
    expect(pendant).toContain("nullIf(trim(properties.firmware),'')");
    expect(pendant).toContain(
      "trim(properties.firmware) NOT IN ('','Unknown','unknown','26.6','27.0')"
    );
    expect(pendant).toContain(
      "NOT match(trim(properties.firmware), '^[0-9]{2}[.]')"
    );
    expect(pendant).not.toContain("'1.0.4'");
    expect(pendant).toContain("any(properties.device_model) AS device_model");
    expect(pendant).toContain("GROUP BY firmware, os");
    expect(pendant).toContain("HAVING uniqExact(person_id) >= 20");
    expect(pendant).toContain("ORDER BY users DESC");
    expect(pendant).not.toContain("LIMIT");
    expect(phone).toContain(
      "coalesce(nullIf(properties.$app_version,''), nullIf(properties.app_version,''), '') AS app_version"
    );
    expect(phone).toContain("max(app_version) AS app_version");
    expect(phone).not.toContain("any(app_version)");
    expect(phone).toContain("GROUP BY os, build");
    expect(phone).not.toContain("GROUP BY os, build, app_version");
    expect(phone).toContain("p90_drain_per_hour");
    expect(phone).toContain("AS users");
    expect(phone).toContain("AS n_pairs");
  });

  it("prefers self-contained v2 intervals per build and reports both transition counts", async () => {
    configure();
    posthogResults.mockImplementation(async (_h, _p, _k, query: string) => {
      if (query.includes("Mobile Device Health Daily")) return [];
      return [
        ["iOS", "1348", "1.0.559", 5, 3, 0, 4, 9, 5],
        ["Android", "1347", "1.0.558", 7, 4, 2, 6, 7, 0],
      ];
    });
    const body = await (await GET(request())).json();
    expect(body.phone_health.series[0]).toMatchObject({
      n_pairs: 5,
      n_v1_pairs: 9,
      n_v2_intervals: 5,
      p50_drain_per_hour: 0,
    });
    expect(body.phone_health.series[1]).toMatchObject({
      n_pairs: 7,
      n_v1_pairs: 7,
      n_v2_intervals: 0,
    });
    const phone = queries().find((query) => query.includes("FROM pairs"))!;
    expect(phone).toContain("countIf(schema_version = 2) > 0 AS has_v2");
    expect(phone).toContain(
      "if(build_presence.has_v2, interval_schema = 2, interval_schema = 1)"
    );
    expect(phone).toContain("properties.battery_observation_build");
    expect(phone).toContain("properties.battery_interval_seconds");
    expect(phone).toContain("validity = 'same_build'");
    expect(phone).toContain("interval_s BETWEEN 900 AND 7200");
    expect(phone).toContain("charging = false AND previous_charging = false");
    expect(phone).toContain("previous_level - level >= 0");
    expect(phone).toContain(
      "(charging_observed = false OR isNull(charging_observed))"
    );
    // Presence is derived from all samples, not only accepted intervals.
    expect(phone).toContain("FROM samples\n      GROUP BY os, build");
    expect(phone).toContain("WHERE schema_version = 1");
  });

  it("mixed v1/v2 fixture rows select v2 without double-counting the same build", async () => {
    configure();
    phoneFixtureRows([
      sampleFixture(1, 95000, { battery_level: 90 }),
      sampleFixture(1, 96800, { battery_level: 80 }),
      sampleFixture(2, 98600),
    ]);
    const body = await (await GET(request())).json();
    expect(body.phone_health.series).toHaveLength(1);
    expect(body.phone_health.series[0]).toMatchObject({
      n_pairs: 1,
      n_v1_pairs: 1,
      n_v2_intervals: 1,
      p50_drain_per_hour: 4,
    });
  });

  it("mixed-schema fixtures retain a v1-only build alongside a v2 build", async () => {
    configure();
    phoneFixtureRows([
      sampleFixture(1, 95000, { app_build: "1347", battery_level: 90 }),
      sampleFixture(1, 96800, { app_build: "1347", battery_level: 80 }),
      sampleFixture(2, 98600),
    ]);
    const body = await (await GET(request())).json();
    expect(body.phone_health.series).toHaveLength(2);
    expect(body.phone_health.series).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          build: "1347",
          n_pairs: 1,
          n_v1_pairs: 1,
          n_v2_intervals: 0,
          p50_drain_per_hour: 20,
        }),
        expect.objectContaining({
          build: "1348",
          n_pairs: 1,
          n_v1_pairs: 0,
          n_v2_intervals: 1,
          p50_drain_per_hour: 4,
        }),
      ])
    );
  });

  it("invalid v2 baseline suppresses v1 fallback for that build", async () => {
    configure();
    phoneFixtureRows([
      sampleFixture(1, 95000, { battery_level: 90 }),
      sampleFixture(1, 96800, { battery_level: 80 }),
      sampleFixture(2, 98600, {
        battery_interval_validity: "no_baseline",
        previous_battery_level: null,
        battery_interval_seconds: null,
      }),
    ]);
    const body = await (await GET(request())).json();
    expect(body.phone_health).toEqual({
      status: "measured_no_valid_pairs",
      series: [],
      n_events: 3,
    });
  });

  it("zero-drop v2 fixture intervals contribute to the aggregate", async () => {
    configure();
    phoneFixtureRows([sampleFixture(2, 98600, { previous_battery_level: 70 })]);
    const body = await (await GET(request())).json();
    expect(body.phone_health.series[0]).toMatchObject({
      n_pairs: 1,
      n_v2_intervals: 1,
      p50_drain_per_hour: 0,
      p90_drain_per_hour: 0,
    });
  });

  it.each([
    ["null current charging endpoint", { battery_charging: null }],
    ["null previous charging endpoint", { previous_battery_charging: null }],
    ["observed charging", { charging_observed_in_interval: true }],
    ["clock-invalid interval", { battery_interval_validity: "clock_invalid" }],
  ])("excludes v2 fixture with %s", async (_name, properties) => {
    configure();
    phoneFixtureRows([sampleFixture(2, 98600, properties)]);
    const body = await (await GET(request())).json();
    expect(body.phone_health).toEqual({
      status: "measured_no_valid_pairs",
      series: [],
      n_events: 1,
    });
  });

  it("labels a phone build without a version as OS (build)", async () => {
    configure();
    posthogResults.mockImplementation(async (_h, _p, _k, query: string) => {
      if (query.includes("Mobile Device Health Daily")) {
        return [["2.0.10", "", "", 40, 22, 20, 58.2, 70.1, 0.4, 0]];
      }
      return [["Android", "900", "", 3, 21, 2.2, 4.4]];
    });

    const body = await (await GET(request("?days=7"))).json();
    expect(body.days).toBe(7);
    expect(body.pendant_health[0].os).toBe("");
    expect(body.pendant_health[0].device_model).toBe("");
    expect(body.pendant_health[0].firmware_label).toBe("2.0.10");
    expect(body.phone_health).toEqual({
      status: "ok",
      series: [
        {
          os: "Android",
          build: "900",
          app_version: "",
          label: "Android (900)",
          n_pairs: 3,
          n_v1_pairs: 0,
          n_v2_intervals: 0,
          users: 21,
          p50_drain_per_hour: 2.2,
          p90_drain_per_hour: 4.4,
        },
      ],
    });
  });

  it("labels original Friend firmware as Friend v1 and leaves current Omi firmware alone", async () => {
    configure();
    posthogResults.mockImplementation(async (_h, _p, _k, query: string) => {
      if (query.includes("Mobile Device Health Daily")) {
        return [
          ["1.0.4", "iOS", "Friend", 36, 35, 1, 39.44, 39.44, 0.5, 0],
          ["1.0.4", "Android", "", 12, 10, 1, 39.44, 39.44, 0.5, 0],
          ["3.0.21", "iOS", "Omi Device", 100, 80, 90, 5.11, 9.0, 0.4, 1],
        ];
      }
      return [];
    });

    const body = await (await GET(request("?days=7"))).json();
    expect(
      body.pendant_health.map(
        (row: { firmware_label: string }) => row.firmware_label
      )
    ).toEqual([
      "1.0.4 (Friend v1) · iOS",
      "1.0.4 (Friend v1) · Android",
      "3.0.21 · iOS",
    ]);
    expect(body.pendant_health[0].device_model).toBe("Friend");
    expect(body.phone_health.status).toBe("awaiting_instrumentation");
  });

  it("treats unknown charging as drain on both endpoints", async () => {
    configure();
    posthogResults.mockResolvedValue([]);
    await GET(request("?days=14"));
    const phone = queries().find((query) => query.includes("FROM pairs"));
    expect(phone).toContain("(charging = false OR isNull(charging))");
    expect(phone).toContain("(prev_charging = false OR isNull(prev_charging))");
    expect(phone).not.toContain("prev_charging != true");
  });

  it("retries PostHog 504 and does not retry a 400", async () => {
    configure();
    vi.useFakeTimers();
    let phoneAttempts = 0;
    posthogResults.mockImplementation(async (_h, _p, _k, query: string) => {
      if (query.includes("SELECT count() AS n")) return [[0]];
      if (query.includes("FROM pairs")) {
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

  it("leaves 429 to posthogResults and does not retry it outside", async () => {
    configure();
    posthogResults.mockRejectedValue(
      new Error("PostHog API error: 429 throttle")
    );
    const response = await GET(request("?days=14"));
    expect(response.status).toBe(500);
    // Pendant and the pair query each run once. The count query never starts.
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
