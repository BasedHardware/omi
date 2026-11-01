import { expect, it } from "vitest";
import {
  buildResponseReliabilityPayload,
  responseReliabilityQueries,
} from "../response-reliability";
import {
  DESKTOP_HEALTH_EVENT_COUNT_MULTIPLIER,
  DESKTOP_HEALTH_EVENT_SAMPLING_CUTOVER,
  DESKTOP_HEALTH_EVENT_WEIGHT_SQL,
  desktopHealthEventWeightSql,
} from "../telemetry/desktop-health-sampling";
import {
  fallbackObservationsFromLegacy,
  fallbackObservationsFromAggregates,
  LEGACY_FALLBACK_EXHAUSTED_QUERY,
  LEGACY_FALLBACK_TRIAGE_QUERY,
} from "../telemetry/fallback-triage";

it("weights only the physical PostHog arm and both fallback query volumes at event time", () => {
  const { chat, voice } = responseReliabilityQueries(30);
  const [physical, floating] = voice.split("UNION ALL");
  expect(DESKTOP_HEALTH_EVENT_COUNT_MULTIPLIER).toBe(10);
  expect(DESKTOP_HEALTH_EVENT_SAMPLING_CUTOVER).toBe("2026-10-17T03:43:08Z");
  expect(DESKTOP_HEALTH_EVENT_WEIGHT_SQL).toBe(
    "if(timestamp >= toDateTime('2026-10-17 03:43:08', 'UTC'), 10, 1)"
  );
  expect(physical).toContain(
    `sum(${DESKTOP_HEALTH_EVENT_WEIGHT_SQL}) AS event_count`
  );
  expect(physical).toContain(
    `duration_ms)) * ${DESKTOP_HEALTH_EVENT_WEIGHT_SQL}`
  );
  for (const query of [chat, floating]) {
    expect(query).not.toContain(
      `sum(${DESKTOP_HEALTH_EVENT_WEIGHT_SQL}) AS event_count`
    );
    expect(query).toContain("count() AS event_count");
  }
  for (const query of [
    LEGACY_FALLBACK_EXHAUSTED_QUERY,
    LEGACY_FALLBACK_TRIAGE_QUERY,
  ])
    expect(query).toContain(
      `sum(${DESKTOP_HEALTH_EVENT_WEIGHT_SQL}) AS event_count`
    );
  expect(desktopHealthEventWeightSql("2026-10-22T00:00:00Z")).toContain(
    "timestamp >= toDateTime('2026-10-22 00:00:00', 'UTC')"
  );
});
it("stays disarmed without a confirmed instant and rejects non-UTC/invalid constants", () => {
  expect(desktopHealthEventWeightSql(null)).toBe("1");
  for (const value of [
    "provisional",
    "2026-10-22",
    "2026-10-22T00:00:00+01:00",
    "2026-99-99T00:00:00Z",
  ])
    expect(() => desktopHealthEventWeightSql(value)).toThrow(
      "Invalid desktop health sampling cutover"
    );
});
it("corrected counts flow through volume panels while success ratios and latency remain ratios", () => {
  // Post-cutover query estimates: sampled 2 successes / 1 failure, 4s + 8s latency.
  const p = buildResponseReliabilityPayload({
    days: 1,
    now: new Date("2026-10-22T12:00Z"),
    chatAvailable: true,
    voiceAvailable: true,
    chatRows: [
      [
        "2026-10-22",
        "chat_agent_query_completed",
        "main_chat",
        "none",
        3,
        9000,
      ],
    ],
    voiceRows: [
      [
        "2026-10-22",
        "voice_turn_started",
        "unknown",
        "none",
        "hold",
        "hold",
        30,
        0,
        "physical_shortcut",
      ],
      [
        "2026-10-22",
        "voice_turn_terminal",
        "success",
        "none",
        "hold",
        "hold",
        20,
        120000,
        "physical_shortcut",
      ],
      [
        "2026-10-22",
        "voice_turn_terminal",
        "failure",
        "provider",
        "hold",
        "hold",
        10,
        0,
        "physical_shortcut",
      ],
    ],
  });
  expect(p.summary.voice).toMatchObject({
    attempts: 30,
    success: 20,
    failure: 10,
    successRate: 66.67,
    averageFullAnswerSeconds: 6,
  });
  expect(p.summary.chat?.success).toBe(3);
  expect(p.daily[0]).toMatchObject({
    voiceSuccess: 20,
    voiceFailure: 10,
    voiceSuccessRate: 66.67,
  });
  expect(p.failureReasons).toContainEqual({
    source: "voice",
    reason: "provider",
    count: 10,
  });
  expect(p.voiceRoutes[0].successRate).toBe(66.67);
});
it("never rescales unsampled replacement rows or double-scales weighted fallback rows", () => {
  const p = buildResponseReliabilityPayload({
    days: 1,
    now: new Date("2026-10-22T12:00Z"),
    chatAvailable: false,
    voiceAvailable: true,
    chatRows: [],
    voiceRows: [
      [
        "2026-10-22",
        "voice_turn_terminal",
        "success",
        "none",
        "hold",
        "hold",
        2,
        12000,
        "physical_shortcut",
        "person",
        2,
      ],
    ],
  });
  expect(p.summary.voice).toMatchObject({
    success: 2,
    averageFullAnswerSeconds: 6,
  });
  expect(
    fallbackObservationsFromLegacy([
      {
        day: "2026-10-21",
        area: "ptt_cascade",
        reason: "timeout",
        outcome: "exhausted",
        count: 5,
      },
      {
        day: "2026-10-22",
        area: "ptt_cascade",
        reason: "timeout",
        outcome: "exhausted",
        count: 10,
      },
    ]).byOutcome.exhausted
  ).toBe(15);
  expect(
    fallbackObservationsFromAggregates([
      {
        day: "2026-10-22",
        family: "fallback",
        platform: "macos",
        channel: "production",
        durations: {},
        dimensions: {
          area: "ptt_cascade",
          reason: "timeout",
          outcome: "exhausted",
        },
        counters: { observations: 2 },
      },
    ]).byOutcome.exhausted
  ).toBe(2);
});
