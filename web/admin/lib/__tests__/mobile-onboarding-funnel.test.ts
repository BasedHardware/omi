import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  computeMobileOnboarding,
  MOBILE_STEPS,
  TUTORIAL_STEPS,
} from "@/lib/mobile-onboarding-funnel";
import { POSTHOG_SERVED_MAX_ROWS } from "@/lib/posthog";

beforeEach(() => {
  vi.stubEnv("POSTHOG_PERSONAL_API_KEY", "phx_test");
  vi.stubEnv("POSTHOG_PROJECT_ID", "1");
  vi.stubEnv("POSTHOG_HOST", "https://posthog.test/");
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
  vi.restoreAllMocks();
});
function mockRows(results: unknown[][]) {
  const fetchMock = vi
    .fn()
    .mockResolvedValue({ ok: true, json: async () => ({ results }) });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}
function query(fetchMock: ReturnType<typeof vi.fn>) {
  return JSON.parse(fetchMock.mock.calls[0][1].body).query.query as string;
}
function assertGuard(q: string) {
  expect(q).toContain("SELECT * FROM (");
  expect(q).toContain(`LIMIT ${POSTHOG_SERVED_MAX_ROWS}`);
  expect(q).toContain("properties.platform IN ('ios', 'android')");
  expect(q).toContain("COALESCE(person_id, distinct_id)");
  expect(q).not.toContain("properties.$os");
}

describe("mobile onboarding completion funnel", () => {
  it("queries exact mobile events, saved speech, entry window and distinct actor groups", async () => {
    const fetchMock = mockRows([]);
    await computeMobileOnboarding("first-run", 14);
    const q = query(fetchMock);
    assertGuard(q);
    for (const step of MOBILE_STEPS) expect(q).toContain(`'${step.event}'`);
    expect(q).toContain("properties.journey = 'onboarding'");
    expect(q).toContain("properties.surface = 'onboarding'");
    expect(q).toContain("timestamp >= now() - INTERVAL 14 DAY");
    expect(q).toContain("timestamp >= entrants.entered_at");
    expect(q).toContain("properties.completion_mode = 'saved'");
    expect(q).toContain("properties.source = 'first_run'");
    expect(q).toContain("GROUP BY actor_id, event");
    expect(q).toContain("UNION ALL SELECT actor_id, 'Product Journey Started'");
    expect(q).not.toContain("Onboarding Step Speech Profile Continued");
    expect(fetchMock.mock.calls[0][0]).toBe(
      "https://posthog.test/api/projects/1/query/"
    );
  });
  it("deduplicates navigation, retains no-step entrants, and does not gate completion on Setup/speech", async () => {
    mockRows([
      ["a", "Product Journey Started"],
      ["a", "Product Journey Started"],
      ["b", "Product Journey Started"],
      ["silent", "Product Journey Started"],
      ["a", "Onboarding Step Name Completed"],
      ["a", "Onboarding Step Name Completed"],
      ["b", "Onboarding Step Name Completed"],
      ["a", "Onboarding Completed"],
      ["b", "Onboarding Step Setup Completed"],
      ["b", "Guided Intro Completed"],
    ]);
    const p = await computeMobileOnboarding("first-run", 30);
    expect(p.totalUsers).toBe(3);
    if (!("steps" in p)) throw new Error("Missing steps");
    expect(p.steps.find((s) => s.key === "name")).toMatchObject({
      users: 2,
      completionRate: 66.67,
    });
    expect(p.steps.find((s) => s.key === "completed")).toMatchObject({
      users: 1,
    });
    expect(p.steps.find((s) => s.key === "setup")).toMatchObject({
      optional: true,
      users: 1,
    });
    expect(p.methodology).toContain("not view");
  });
});

describe("CV1 auto tutorial", () => {
  const row = (
    actor: string,
    event: string,
    step: string,
    source: string,
    second: number
  ) => [
    actor,
    event,
    step,
    source,
    `2026-10-01T00:00:${String(second).padStart(2, "0")}.000Z`,
  ];
  it("keeps settings starts to bound auto attempts and queries step/source/timestamps", async () => {
    const fetchMock = mockRows([]);
    await computeMobileOnboarding("tutorial", 30);
    const q = query(fetchMock);
    assertGuard(q);
    for (const event of [
      "Started",
      "Step Completed",
      "Completed",
      "Abandoned",
    ]) {
      expect(q).toContain(`'Device Onboarding ${event}'`);
    }
    expect(q).toContain("toString(properties.step)");
    expect(q).toContain("toString(properties.source)");
    expect(q).toContain("timestamp AS event_at");
    expect(q).toContain("GROUP BY actor_id, event, step, source, event_at");
    expect(q).not.toContain("properties.source = 'auto'");
  });
  it("credits distinct auto persons within their attempt, excludes settings and closes terminals", async () => {
    mockRows(
      [
        row("a", "Device Onboarding Started", "", "auto", 0),
        ...TUTORIAL_STEPS.map((step, i) =>
          row("a", "Device Onboarding Step Completed", step, "", i + 1)
        ),
        row(
          "a",
          "Device Onboarding Step Completed",
          "transcription_demo",
          "",
          1
        ),
        row("a", "Device Onboarding Completed", "", "", 6),
        row("a", "Device Onboarding Abandoned", "0", "", 7),
        row("b", "Device Onboarding Started", "", "auto", 0),
        row(
          "b",
          "Device Onboarding Step Completed",
          "transcription_demo",
          "",
          1
        ),
        row("b", "Device Onboarding Started", "", "settings", 2),
        row(
          "b",
          "Device Onboarding Step Completed",
          "single_press_ask_question",
          "",
          3
        ),
        row("b", "Device Onboarding Abandoned", "1", "", 4),
        row("c", "Device Onboarding Started", "", "auto", 0),
        row("c", "Device Onboarding Abandoned", "0", "", 1),
        row("settings", "Device Onboarding Started", "", "settings", 0),
        row("orphan", "Device Onboarding Abandoned", "5", "", 1),
      ].reverse()
    );
    const p = await computeMobileOnboarding("tutorial", 30);
    expect(p.totalUsers).toBe(3);
    if (!("steps" in p) || !("abandonment" in p))
      throw new Error("Missing tutorial");
    expect(p.steps.map((s) => s.users)).toEqual([3, 2, 1, 1, 1, 1, 1, 1]);
    expect(p.abandonment.map((s) => s.users)).toEqual([1, 0, 0, 0, 0, 0]);
  });
  it("does not stitch incomplete steps across separate auto attempts", async () => {
    mockRows([
      row("a", "Device Onboarding Started", "", "auto", 0),
      row("a", "Device Onboarding Step Completed", "transcription_demo", "", 1),
      row("a", "Device Onboarding Started", "", "auto", 2),
      ...TUTORIAL_STEPS.slice(1).map((step, i) =>
        row("a", "Device Onboarding Step Completed", step, "", i + 3)
      ),
      row("a", "Device Onboarding Completed", "", "", 9),
    ]);
    const p = await computeMobileOnboarding("tutorial", 30);
    if (!("steps" in p)) throw new Error("Missing steps");
    expect(p.steps.map((s) => s.users)).toEqual([1, 1, 0, 0, 0, 0, 0, 0]);
  });
});

describe("pendant attach", () => {
  it("joins mobile completers to earliest later CV1 pairing, bounded at 30d", async () => {
    const fetchMock = mockRows([]);
    await computeMobileOnboarding("attach", 90);
    const q = query(fetchMock);
    assertGuard(q);
    expect(q).toContain("event = 'Onboarding Completed'");
    expect(q).toContain("min(timestamp) AS completed_at");
    expect(q).toContain("event = 'Device Paired'");
    expect(q).toContain("properties.hardware_family = 'omi_cv1'");
    expect(q).toContain("minIf(dateDiff('second', completed_at, paired_at)");
    expect(q).toContain("paired_at > completed_at");
    expect(q).toContain("paired_at <= completed_at + INTERVAL 30 DAY");
    expect(q).toContain("LEFT JOIN pairs");
    expect(q).not.toContain("first_paired_at");
    expect(q).not.toContain("Device Connected");
  });
  it("reports 7d/30d shares including unpaired people and separately mature cohorts", async () => {
    mockRows([
      ["a", 40 * 86400, 7 * 86400],
      ["b", 40 * 86400, 30 * 86400],
      ["c", 40 * 86400, 0],
      ["new", 86400, 10],
    ]);
    const p = await computeMobileOnboarding("attach", 90);
    if (!("windows" in p)) throw new Error("Missing windows");
    expect(p.totalUsers).toBe(4);
    expect(p.windows[0]).toMatchObject({
      attachedUsers: 2,
      attachRate: 50,
      matureUsers: 3,
      matureAttachedUsers: 1,
      matureAttachRate: 33.33,
    });
    expect(p.windows[1]).toMatchObject({
      attachedUsers: 3,
      attachRate: 75,
      matureAttachedUsers: 2,
    });
    expect(p.description).toContain("pending volume check");
  });
});

describe("mobile PostHog boundary", () => {
  it("flags the served row ceiling", async () => {
    mockRows(
      Array.from({ length: POSTHOG_SERVED_MAX_ROWS }, () => [
        "a",
        "Product Journey Started",
      ])
    );
    expect((await computeMobileOnboarding("first-run", 30)).truncated).toBe(
      true
    );
  });
  it("retries transient errors, then returns the payload", async () => {
    vi.useFakeTimers();
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: false, status: 504 })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ results: [] }) });
    vi.stubGlobal("fetch", fetchMock);
    const pending = computeMobileOnboarding("tutorial", 30);
    await vi.runAllTimersAsync();
    expect((await pending).totalUsers).toBe(0);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
  it("throws PostHogError after exhausted retries", async () => {
    vi.useFakeTimers();
    const fetchMock = vi.fn().mockResolvedValue({ ok: false, status: 429 });
    vi.stubGlobal("fetch", fetchMock);
    const pending = computeMobileOnboarding("attach", 30).catch((e) => e);
    await vi.runAllTimersAsync();
    expect(await pending).toMatchObject({ name: "PostHogError", status: 429 });
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });
  it("rejects credentials, malformed results and unsafe windows", async () => {
    const fetchMock = mockRows([]);
    await expect(computeMobileOnboarding("first-run", NaN)).rejects.toThrow(
      "days must"
    );
    expect(fetchMock).not.toHaveBeenCalled();
    vi.stubEnv("POSTHOG_PERSONAL_API_KEY", "");
    await expect(computeMobileOnboarding("first-run", 30)).rejects.toThrow(
      "credentials not configured"
    );
    vi.stubEnv("POSTHOG_PERSONAL_API_KEY", "test");
    fetchMock.mockResolvedValue({ ok: true, json: async () => ({}) });
    await expect(computeMobileOnboarding("first-run", 30)).rejects.toThrow(
      "Invalid PostHog results"
    );
  });
});
