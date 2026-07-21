import { describe, expect, it } from "vitest";

import {
  buildChannelReliabilityPayloads,
  buildResponseReliabilityPayload,
  responseReliabilityQueries,
} from "../response-reliability";

describe("response reliability", () => {
  it("aggregates delivery rate, failures, exclusions, gaps, and full-answer speed", () => {
    const payload = buildResponseReliabilityPayload({
      days: 7,
      now: new Date("2026-07-20T12:00:00Z"),
      chatAvailable: true,
      voiceAvailable: true,
      chatRows: [
        [
          "2026-07-20",
          "chat_agent_query_started",
          "main_chat",
          "unknown",
          12,
          0,
        ],
        [
          "2026-07-20",
          "chat_agent_query_completed",
          "main_chat",
          "unknown",
          8,
          32_000,
        ],
        ["2026-07-20", "chat_agent_error", "main_chat", "timeout", 2, 0],
        [
          "2026-07-20",
          "chat_agent_query_cancelled",
          "main_chat",
          "unknown",
          1,
          0,
        ],
      ],
      voiceRows: [
        [
          "2026-07-20",
          "voice_turn_started",
          "unknown",
          "unknown",
          "unknown",
          "hold",
          6,
          0,
        ],
        [
          "2026-07-20",
          "voice_turn_terminal",
          "success",
          "success",
          "hub",
          "hold",
          4,
          20_000,
        ],
        [
          "2026-07-20",
          "voice_turn_terminal",
          "failure",
          "playback_failed",
          "hub",
          "hold",
          1,
          0,
        ],
        [
          "2026-07-20",
          "voice_turn_terminal",
          "excluded",
          "cancelled",
          "hub",
          "hold",
          1,
          0,
        ],
      ],
    });

    expect(payload.summary.chat).toMatchObject({
      attempts: 12,
      success: 8,
      failure: 2,
      excluded: 1,
      unresolved: 1,
      successRate: 80,
      averageFullAnswerSeconds: 4,
    });
    expect(payload.summary.voice).toMatchObject({
      attempts: 6,
      success: 4,
      failure: 1,
      excluded: 1,
      unresolved: 0,
      successRate: 80,
      averageFullAnswerSeconds: 5,
    });
    expect(payload.summary.overall).toMatchObject({
      success: 12,
      failure: 3,
      successRate: 80,
    });
    expect(payload.failureReasons).toEqual([
      { source: "chat", reason: "timeout", count: 2 },
      { source: "voice", reason: "playback_failed", count: 1 },
    ]);
    expect(payload.availability.voiceCoverageStart).toBe("2026-07-20");
    expect(payload.daily.at(-1)).toMatchObject({
      chatSuccessRate: 80,
      voiceSuccessRate: 80,
      chatAverageSeconds: 4,
      voiceAverageSeconds: 5,
    });
  });

  it("marks an unavailable source partial instead of fabricating zero reliability", () => {
    const payload = buildResponseReliabilityPayload({
      days: 7,
      now: new Date("2026-07-20T12:00:00Z"),
      chatAvailable: true,
      voiceAvailable: false,
      chatRows: [
        [
          "2026-07-20",
          "chat_agent_query_completed",
          "main_chat",
          "unknown",
          2,
          4_000,
        ],
      ],
      voiceRows: [],
    });

    expect(payload.partial).toBe(true);
    expect(payload.summary.chat?.successRate).toBe(100);
    expect(payload.summary.voice).toBeNull();
    expect(payload.daily.at(-1)?.voiceSuccessRate).toBeNull();
  });

  it("shows historical floating voice reliability until physical shortcut telemetry exists", () => {
    const legacy = [
      [
        "2026-07-20",
        "voice_turn_started",
        "unknown",
        "unknown",
        "floating_voice",
        "legacy",
        5,
        0,
        "floating_voice",
      ],
      [
        "2026-07-20",
        "voice_turn_terminal",
        "success",
        "unknown",
        "floating_voice",
        "legacy",
        4,
        8_000,
        "floating_voice",
      ],
      [
        "2026-07-20",
        "voice_turn_terminal",
        "failure",
        "timeout",
        "floating_voice",
        "legacy",
        1,
        0,
        "floating_voice",
      ],
    ];
    const legacyPayload = buildResponseReliabilityPayload({
      days: 7,
      now: new Date("2026-07-20T12:00:00Z"),
      chatAvailable: true,
      voiceAvailable: true,
      chatRows: [],
      voiceRows: legacy,
    });

    expect(legacyPayload.summary.voice).toMatchObject({
      attempts: 5,
      success: 4,
      failure: 1,
      successRate: 80,
      averageFullAnswerSeconds: 2,
    });

    const physicalPayload = buildResponseReliabilityPayload({
      days: 7,
      now: new Date("2026-07-20T12:00:00Z"),
      chatAvailable: true,
      voiceAvailable: true,
      chatRows: [],
      voiceRows: [
        ...legacy,
        [
          "2026-07-20",
          "voice_turn_started",
          "unknown",
          "unknown",
          "hub",
          "hold",
          2,
          0,
          "physical_shortcut",
        ],
        [
          "2026-07-20",
          "voice_turn_terminal",
          "success",
          "success",
          "hub",
          "hold",
          2,
          6_000,
          "physical_shortcut",
        ],
      ],
    });

    expect(physicalPayload.summary.voice).toMatchObject({
      attempts: 2,
      success: 2,
      failure: 0,
      successRate: 100,
      averageFullAnswerSeconds: 3,
    });
  });

  it("splits response reliability by the user's release channel", () => {
    const chatRows = [
      [
        "2026-07-20",
        "chat_agent_query_started",
        "main_chat",
        "unknown",
        2,
        0,
        "prod-user",
      ],
      [
        "2026-07-20",
        "chat_agent_query_completed",
        "main_chat",
        "unknown",
        2,
        4_000,
        "prod-user",
      ],
      [
        "2026-07-20",
        "chat_agent_query_started",
        "main_chat",
        "unknown",
        1,
        0,
        "beta-user",
      ],
      [
        "2026-07-20",
        "chat_agent_error",
        "main_chat",
        "timeout",
        1,
        0,
        "beta-user",
      ],
    ];
    const channels = buildChannelReliabilityPayloads({
      days: 7,
      now: new Date("2026-07-20T12:00:00Z"),
      chatAvailable: true,
      voiceAvailable: true,
      chatRows,
      voiceRows: [],
      channelByActor: new Map([
        ["prod-user", "production"],
        ["beta-user", "beta"],
      ]),
    });

    expect(channels.production.summary.chat).toMatchObject({
      attempts: 2,
      success: 2,
      failure: 0,
      successRate: 100,
    });
    expect(channels.beta.summary.chat).toMatchObject({
      attempts: 1,
      success: 0,
      failure: 1,
      successRate: 0,
    });
  });

  it("clamps the query window before interpolating HogQL", () => {
    const queries = responseReliabilityQueries(500);
    expect(queries.chat).toContain("toStartOfDay(now()) - INTERVAL 89 DAY");
    expect(queries.voice).toContain("toStartOfDay(now()) - INTERVAL 89 DAY");
    expect(queries.voice).toContain(
      "toString(properties.surface) = 'floating_voice'",
    );
    expect(queries.chat).toContain("distinct_id AS actor_id");
    expect(queries.voice).toContain("distinct_id AS actor_id");
  });
});
