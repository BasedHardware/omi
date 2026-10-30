import { cleanup, render, within } from "@testing-library/react";
import { beforeAll, describe, expect, it, vi } from "vitest";

import {
  reliabilityPanelSnapshot,
  ResponseReliabilityFixturePanels,
} from "@/components/dashboard/response-reliability-summary";
import { interpretAggregateResponse } from "@/lib/telemetry/aggregates";
import { fetchTelemetryAggregates } from "@/lib/telemetry/client";
import { connectionBalance } from "@/lib/telemetry/connection-balance";
import {
  compareFallbackTriage,
  fallbackObservationsFromAggregates,
  fallbackObservationsFromLegacy,
  LEGACY_FALLBACK_CONSUMER_AUTHORITATIVE,
  LEGACY_FALLBACK_EXHAUSTED_QUERY,
} from "@/lib/telemetry/fallback-triage";
import {
  aggregateFixture,
  chatRows,
  connectionObservations,
  fallbackAggregateRows,
  fallbackLegacy,
  FIXTURE_CUTOVER,
  FIXTURE_DAYS,
  FIXTURE_NOW,
  floatingVoice,
  historicalPosthogPhysical,
  mismatchedActorVoice,
  missingActorVoice,
  nullLatencyVoice,
  physicalBetaVoice,
  physicalProductionVoice,
} from "@/lib/telemetry/fixtures";
import { reliabilityReaderConfig } from "@/lib/telemetry/flags";
import { buildFixtureParityReceipt } from "@/lib/telemetry/parity-receipt";
import { assembleResponseReliability } from "@/lib/telemetry/replacement-reliability";
import { billingTable } from "@/lib/services/gcp-billing";
import { PLAN_ECONOMICS_QUERY } from "@/lib/services/plan-economics";

const channels = new Map([
  ["prod-user", "production" as const],
  ["beta-user", "beta" as const],
]);

const physicalReader = {
  enabled: true,
  cutover: FIXTURE_CUTOVER,
  population: "physical_shortcut" as const,
};

function feed(body: unknown, httpStatus = 200, now = FIXTURE_NOW) {
  return interpretAggregateResponse({ httpStatus, payload: body, now });
}

function assemble(
  aggregate: ReturnType<typeof feed> | null,
  extras: Partial<Parameters<typeof assembleResponseReliability>[0]> = {}
) {
  return assembleResponseReliability({
    days: FIXTURE_DAYS,
    now: FIXTURE_NOW,
    chatRows,
    posthogVoiceRows: [],
    chatAvailable: true,
    posthogVoiceAvailable: true,
    channelByActor: channels,
    reader: physicalReader,
    aggregate,
    ...extras,
  });
}

describe("replacement reliability reader", () => {
  it("keeps physical counts, rates, exclusions, unresolved, and duration means", () => {
    const payload = assemble(
      feed(
        aggregateFixture({
          voice_rows: [...physicalProductionVoice, ...physicalBetaVoice],
        })
      )
    );
    expect(payload.voiceSource).toBe("physical_shortcut");
    expect(payload.channels.production.summary.voice).toMatchObject({
      attempts: 6,
      success: 4,
      failure: 1,
      excluded: 1,
      unresolved: 0,
      successRate: 80,
      averageFullAnswerSeconds: 5,
    });
    expect(payload.channels.production.availability.voiceCoverageStart).toBe(
      "2026-10-10"
    );
    expect(payload.channels.beta.summary.voice).toMatchObject({
      attempts: 2,
      success: 0,
      failure: 2,
      successRate: 0,
      averageFullAnswerSeconds: null,
    });
    expect(payload.channels.beta.voiceSource).toBe("physical_shortcut");
    expect(payload.partial).toBe(false);
  });

  it("does not substitute floating voice when physical telemetry is absent", () => {
    const payload = assemble(
      feed(aggregateFixture({ voice_rows: floatingVoice }))
    );
    expect(payload.voiceSource).toBeNull();
    expect(payload.summary.voice).toBeNull();
    expect(payload.availability.voice).toBe(false);
    expect(payload.partial).toBe(true);
    expect(payload.channels.production.summary.voice).toBeNull();
    expect(
      payload.channels.production.daily.every(
        (point) => point.voiceSuccessRate == null
      )
    ).toBe(true);
  });

  it("keeps both populations separate when each is selected explicitly", () => {
    const body = aggregateFixture({
      voice_rows: [...physicalProductionVoice, ...floatingVoice],
    });
    const physical = assemble(feed(body));
    const floating = assemble(feed(body), {
      reader: {
        enabled: true,
        cutover: FIXTURE_CUTOVER,
        population: "floating_voice",
      },
    });
    expect(physical.channels.production.summary.voice?.success).toBe(4);
    expect(physical.voiceSource).toBe("physical_shortcut");
    expect(floating.channels.production.summary.voice).toMatchObject({
      attempts: 10,
      success: 9,
      failure: 1,
      successRate: 90,
    });
    expect(floating.voiceSource).toBe("floating_voice");
  });

  it("leaves a null successful latency as null and does not invent zero seconds", () => {
    const payload = assemble(
      feed(aggregateFixture({ voice_rows: nullLatencyVoice }))
    );
    expect(payload.channels.production.summary.voice).toMatchObject({
      success: 2,
      successRate: 100,
      averageFullAnswerSeconds: null,
    });
  });

  it("excludes actor/channel mismatches and missing actors instead of reclassifying them", () => {
    const payload = assemble(
      feed(
        aggregateFixture({
          voice_rows: [
            ...physicalProductionVoice,
            ...mismatchedActorVoice,
            ...missingActorVoice,
          ],
        })
      )
    );
    expect(payload.channels.production.summary.voice?.success).toBe(4);
    expect(payload.channels.beta.summary.voice).toBeNull();
    expect(payload.partial).toBe(true);
  });

  it("marks partial, unavailable, truncated, and stale feeds as not healthy", () => {
    const partial = assemble(
      feed(
        aggregateFixture({
          partial: true,
          voice_rows: physicalProductionVoice,
        })
      )
    );
    expect(partial.partial).toBe(true);
    expect(partial.channels.production.summary.voice?.success).toBe(4);

    const unavailable = assemble(
      feed(
        aggregateFixture({
          available: false,
          voice_rows: physicalProductionVoice,
        })
      )
    );
    expect(unavailable.summary.voice).toBeNull();
    expect(unavailable.partial).toBe(true);
    expect(
      unavailable.channels.production.summary.voice?.successRate
    ).toBeUndefined();

    const truncated = assemble(
      feed(
        {
          detail: {
            code: "telemetry_query_truncated",
            message: "aggregate response exceeds 50000 rows",
          },
          voice_rows: physicalProductionVoice,
        },
        503
      )
    );
    expect(truncated.summary.voice).toBeNull();
    expect(truncated.partial).toBe(true);

    const stale = assemble(
      feed(
        aggregateFixture({
          complete_through: "2026-10-08",
          coverage_start: "2026-10-06",
          voice_rows: [
            {
              ...physicalProductionVoice[1],
              day: "2026-10-08",
              count: 2,
              duration_ms: 4_000,
              latency_count: 2,
            },
            {
              ...physicalProductionVoice[1],
              day: "2026-10-10",
              count: 9,
              duration_ms: 9_000,
              latency_count: 2,
            },
          ],
        })
      ),
      { reader: { ...physicalReader, cutover: "2026-10-06" } }
    );
    expect(stale.partial).toBe(true);
    expect(stale.summary.voice?.success).toBe(2);
    expect(stale.summary.voice?.averageFullAnswerSeconds).toBe(2);
    const after = stale.daily.find((point) => point.date === "2026-10-10");
    expect(after?.voiceSuccessRate).toBeNull();
    expect(after?.voiceSuccess).toBe(0);
  });

  it("uses PostHog before the UTC cutover and the aggregate on and after it, never both", () => {
    const payload = assemble(
      feed(aggregateFixture({ voice_rows: physicalProductionVoice })),
      { posthogVoiceRows: historicalPosthogPhysical }
    );
    expect(payload.summary.voice).toMatchObject({
      success: 8,
      attempts: 10,
    });
    const before = payload.daily.find((point) => point.date === "2026-10-09");
    const onCutover = payload.daily.find(
      (point) => point.date === "2026-10-10"
    );
    expect(before?.voiceSuccess).toBe(4);
    expect(onCutover?.voiceSuccess).toBe(4);
  });

  it("keeps the legacy floating fallback only while the reader is off", () => {
    expect(reliabilityReaderConfig({}).enabled).toBe(false);
    expect(
      reliabilityReaderConfig({
        RELIABILITY_REPLACEMENT_READER: "on",
      }).enabled
    ).toBe(false);
    const legacy = assemble(null, {
      reader: {
        enabled: false,
        cutover: null,
        population: "physical_shortcut",
      },
      posthogVoiceRows: [
        [
          "2026-10-10",
          "voice_turn_terminal",
          "success",
          "success",
          "floating_voice",
          "legacy",
          4,
          8_000,
          "floating_voice",
          "prod-user",
        ],
      ],
    });
    expect(legacy.voiceSource).toBe("floating_voice");
    expect(legacy.summary.voice?.success).toBe(4);
    expect(legacy.partial).toBe(false);
  });
});

describe("rendered reliability panel", () => {
  beforeAll(() => {
    class ResizeObserverStub {
      observe() {}
      unobserve() {}
      disconnect() {}
    }
    vi.stubGlobal("ResizeObserver", ResizeObserverStub);
  });
  it("renders identical panels from identical fixtures and matches the reader", () => {
    const payload = assemble(
      feed(
        aggregateFixture({
          voice_rows: [...physicalProductionVoice, ...physicalBetaVoice],
        })
      )
    );
    const again = assemble(
      feed(
        aggregateFixture({
          voice_rows: [...physicalProductionVoice, ...physicalBetaVoice],
        })
      )
    );
    expect(reliabilityPanelSnapshot(payload.channels.production)).toEqual(
      reliabilityPanelSnapshot(again.channels.production)
    );
    expect(reliabilityPanelSnapshot(payload.channels.beta)).toEqual(
      reliabilityPanelSnapshot(again.channels.beta)
    );
    const first = render(<ResponseReliabilityFixturePanels data={payload} />);
    const second = render(<ResponseReliabilityFixturePanels data={again} />);
    expect(first.container.textContent).toBe(second.container.textContent);
    const production = within(first.container).getByTestId(
      "reliability-panel-production"
    );
    const productionView = within(production);
    expect(
      productionView.getByTestId("reliability-voice-success").textContent
    ).toContain("80.0%");
    expect(
      productionView.getByTestId("reliability-voice-success").textContent
    ).toContain("5.0s");
    expect(
      productionView.getByTestId("reliability-voice-population").textContent
    ).toBe("Voice population: physical shortcut");
    const beta = within(
      within(first.container).getByTestId("reliability-panel-beta")
    );
    expect(beta.getByTestId("reliability-voice-success").textContent).toContain(
      "0.0%"
    );
    expect(beta.getByTestId("reliability-voice-success").textContent).toContain(
      "N/A"
    );
    cleanup();
  });

  it("renders partial and unavailable feeds as N/A rather than a healthy zero", () => {
    const unavailable = assemble(
      feed(aggregateFixture({ voice_rows: floatingVoice }))
    );
    const view = render(
      <ResponseReliabilityFixturePanels data={unavailable} />
    );
    const production = within(
      within(view.container).getByTestId("reliability-panel-production")
    );
    expect(production.getByTestId("reliability-partial")).toBeTruthy();
    expect(
      production.getByTestId("reliability-voice-population").textContent
    ).toBe("Voice telemetry unavailable");
    const voice =
      production.getByTestId("reliability-voice-success").textContent ?? "";
    expect(voice).toContain("N/A");
    expect(voice).not.toContain("0.0%");
    expect(voice).not.toContain("0.0s");
    cleanup();

    const nullLatency = assemble(
      feed(aggregateFixture({ voice_rows: nullLatencyVoice }))
    );
    const latency = render(
      <ResponseReliabilityFixturePanels data={nullLatency} />
    );
    const latencyVoice =
      within(
        within(latency.container).getByTestId("reliability-panel-production")
      ).getByTestId("reliability-voice-success").textContent ?? "";
    expect(latencyVoice).toContain("100.0%");
    expect(latencyVoice).toContain("N/A");
    expect(latencyVoice).not.toContain("0.0s");
    cleanup();
  });
});

describe("fallback triage parity", () => {
  it("matches recovered, degraded, exhausted and existing areas without retiring PostHog", () => {
    const comparison = compareFallbackTriage(
      fallbackObservationsFromLegacy(fallbackLegacy),
      fallbackObservationsFromAggregates(fallbackAggregateRows)
    );
    expect(comparison.equal).toBe(true);
    expect(comparison.replacement.byOutcome).toEqual({
      recovered: 4,
      degraded: 2,
      exhausted: 5,
    });
    expect(comparison.replacement.byArea).toMatchObject({
      realtime_hub: 3,
      ptt_cascade: 2,
      screen_task_gate: 1,
      screen_task_extraction: 4,
      other: 1,
    });
    const renamed = fallbackAggregateRows.map((row) => ({
      ...row,
      counters: { observations_total: row.counters.observations },
    }));
    expect(
      compareFallbackTriage(
        fallbackObservationsFromLegacy(fallbackLegacy),
        fallbackObservationsFromAggregates(renamed)
      ).equal
    ).toBe(true);
    expect(LEGACY_FALLBACK_CONSUMER_AUTHORITATIVE).toBe(true);
    expect(LEGACY_FALLBACK_EXHAUSTED_QUERY).toContain("desktop_health_event");
    expect(LEGACY_FALLBACK_EXHAUSTED_QUERY).toContain("fallback_triggered");
    expect(LEGACY_FALLBACK_EXHAUSTED_QUERY).toContain("outcome) = 'exhausted'");
  });
});

describe("connection balance", () => {
  it("maps mobile detailed and macOS disconnected separately from unique people", () => {
    const mobile = connectionBalance(connectionObservations, "mobile");
    const macos = connectionBalance(connectionObservations, "macos");
    expect(mobile).toMatchObject({
      disconnectedEvent: "Device Disconnected Detailed",
      uniquePeopleConnected: 1,
      uniquePeopleDisconnected: 1,
      reconnectVolume: 3,
      connectVolume: 1,
    });
    expect(macos).toMatchObject({
      disconnectedEvent: "Device Disconnected",
      uniquePeopleConnected: 1,
      uniquePeopleDisconnected: 2,
      uniquePeopleRatio: 0.5,
      reconnectVolume: 2,
      connectVolume: 2,
    });
    expect(mobile.reconnectVolume).not.toBe(mobile.uniquePeopleDisconnected);
  });
});

describe("telemetry aggregate client", () => {
  it("sends the admin key server-side and treats a truncated response as unusable", async () => {
    const previousKey = process.env.OMI_API_SECRET_KEY;
    const previousBase = process.env.NEXT_PUBLIC_OMI_API_URL;
    process.env.OMI_API_SECRET_KEY = "server-admin-key";
    process.env.NEXT_PUBLIC_OMI_API_URL = "https://api.example.test";
    const calls: { url: string; headers: Headers }[] = [];
    try {
      const result = await fetchTelemetryAggregates({
        adminUid: "admin-1",
        days: 7,
        channel: "all",
        now: FIXTURE_NOW,
        fetchImpl: (async (url: string, init?: RequestInit) => {
          calls.push({ url, headers: new Headers(init?.headers) });
          return new Response(
            JSON.stringify({ code: "telemetry_unavailable" }),
            { status: 503 }
          );
        }) as typeof fetch,
      });
      expect(calls[0]?.url).toBe(
        "https://api.example.test/v1/telemetry/client/aggregates?days=7&channel=all"
      );
      expect(calls[0]?.headers.get("X-Admin-Key")).toBe("server-admin-key");
      expect(calls[0]?.headers.get("X-Admin-User")).toBe("admin-1");
      expect(calls[0]?.headers.get("Authorization")).toBeNull();
      expect(result.disposition).toBe("unavailable");
      expect(result.usable).toBe(false);
    } finally {
      if (previousKey === undefined) delete process.env.OMI_API_SECRET_KEY;
      else process.env.OMI_API_SECRET_KEY = previousKey;
      if (previousBase === undefined)
        delete process.env.NEXT_PUBLIC_OMI_API_URL;
      else process.env.NEXT_PUBLIC_OMI_API_URL = previousBase;
    }
  });
});

describe("fixture parity receipt", () => {
  it("records fixture equality and leaves the live canary pending", () => {
    const receipt = buildFixtureParityReceipt();
    expect(receipt.live_seven_day_canary).toBe("pending");
    expect(receipt.consumer_switch).toBe("pending");
    expect(receipt.reader_flag_default).toBe("off");
    expect(receipt.voice_panel).toMatchObject({
      physical_success: 4,
      floating_not_substituted: true,
      beta_failure: 2,
      cutover_success: 8,
    });
    expect(receipt.fallback_triage.equal).toBe(true);
    expect(receipt.connection_balance.mobile_reconnect_volume).toBe(3);
    expect(receipt.warehouse.posthog_gcp_aggregate).toBe(false);
    expect(receipt.warehouse.plan_economics_reads_unit_cost_daily).toBe(true);
    expect(PLAN_ECONOMICS_QUERY).toContain("omi_finops.plan_revenue_daily");
    expect(PLAN_ECONOMICS_QUERY).toContain(
      "omi_finops.unit_cost_reconciliation"
    );
    expect(PLAN_ECONOMICS_QUERY).not.toContain("posthog");
    expect(billingTable()).toContain("gcp_billing_export");
    expect(billingTable()).not.toContain("posthog");
  });
});
