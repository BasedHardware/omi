import {
  interpretAggregateResponse,
  type AggregateInterpretation,
} from "@/lib/telemetry/aggregates";
import { connectionBalance } from "@/lib/telemetry/connection-balance";
import {
  compareFallbackTriage,
  fallbackObservationsFromAggregates,
  fallbackObservationsFromLegacy,
  LEGACY_FALLBACK_CONSUMER_AUTHORITATIVE,
} from "@/lib/telemetry/fallback-triage";
import {
  aggregateFixture,
  connectionObservations,
  fallbackAggregateRows,
  fallbackLegacy,
  FIXTURE_CUTOVER,
  FIXTURE_DAYS,
  FIXTURE_NOW,
  floatingVoice,
  historicalPosthogPhysical,
  physicalBetaVoice,
  physicalProductionVoice,
} from "@/lib/telemetry/fixtures";
import { reliabilityReaderConfig } from "@/lib/telemetry/flags";
import { assembleResponseReliability } from "@/lib/telemetry/replacement-reliability";
import { PLAN_ECONOMICS_QUERY } from "@/lib/services/plan-economics";
import { billingTable } from "@/lib/services/gcp-billing";

const channels = new Map([
  ["prod-user", "production" as const],
  ["beta-user", "beta" as const],
]);

function feed(
  body: ReturnType<typeof aggregateFixture>,
  now = FIXTURE_NOW
): AggregateInterpretation {
  return interpretAggregateResponse({ httpStatus: 200, payload: body, now });
}

/**
 * Fixture parity receipt. Live seven-day canary acceptance is pending and is
 * not claimed here. Legacy PostHog voice and fallback consumers stay
 * authoritative until the parent records that acceptance.
 */
export function buildFixtureParityReceipt() {
  const reader = {
    enabled: true,
    cutover: FIXTURE_CUTOVER,
    population: "physical_shortcut" as const,
  };
  const both = assembleResponseReliability({
    days: FIXTURE_DAYS,
    now: FIXTURE_NOW,
    chatRows: [],
    posthogVoiceRows: [],
    chatAvailable: true,
    posthogVoiceAvailable: true,
    channelByActor: channels,
    reader,
    aggregate: feed(
      aggregateFixture({
        voice_rows: [...physicalProductionVoice, ...floatingVoice],
      })
    ),
  });
  const split = assembleResponseReliability({
    days: FIXTURE_DAYS,
    now: FIXTURE_NOW,
    chatRows: [],
    posthogVoiceRows: [],
    chatAvailable: true,
    posthogVoiceAvailable: true,
    channelByActor: channels,
    reader,
    aggregate: feed(
      aggregateFixture({
        voice_rows: [...physicalProductionVoice, ...physicalBetaVoice],
      })
    ),
  });
  const cutover = assembleResponseReliability({
    days: FIXTURE_DAYS,
    now: FIXTURE_NOW,
    chatRows: [],
    posthogVoiceRows: historicalPosthogPhysical,
    chatAvailable: true,
    posthogVoiceAvailable: true,
    channelByActor: channels,
    reader,
    aggregate: feed(aggregateFixture({ voice_rows: physicalProductionVoice })),
  });
  const fallback = compareFallbackTriage(
    fallbackObservationsFromLegacy(fallbackLegacy),
    fallbackObservationsFromAggregates(fallbackAggregateRows)
  );
  const mobile = connectionBalance(connectionObservations, "mobile");
  const macos = connectionBalance(connectionObservations, "macos");
  const readerDefault = reliabilityReaderConfig({});
  return {
    schema_version: 1 as const,
    evidence: "fixture",
    live_seven_day_canary: "pending" as const,
    consumer_switch: "pending" as const,
    reader_flag_default: readerDefault.enabled ? "on" : "off",
    legacy_fallback_consumer_authoritative:
      LEGACY_FALLBACK_CONSUMER_AUTHORITATIVE,
    legacy_posthog_voice_authoritative_until_parent_acceptance: true,
    voice_panel: {
      physical_success:
        split.channels.production.summary.voice?.success ?? null,
      floating_not_substituted: both.voiceSource === "physical_shortcut",
      beta_failure: split.channels.beta.summary.voice?.failure ?? null,
      cutover_success: cutover.summary.voice?.success ?? null,
      partial_is_not_healthy: split.partial === false,
    },
    fallback_triage: {
      equal: fallback.equal,
      recovered: fallback.replacement.byOutcome.recovered,
      degraded: fallback.replacement.byOutcome.degraded,
      exhausted: fallback.replacement.byOutcome.exhausted,
      areas: fallback.replacement.byArea,
    },
    connection_balance: {
      mobile_disconnect_event: mobile.disconnectedEvent,
      macos_disconnect_event: macos.disconnectedEvent,
      mobile_unique_people_disconnected: mobile.uniquePeopleDisconnected,
      mobile_reconnect_volume: mobile.reconnectVolume,
      macos_unique_people_disconnected: macos.uniquePeopleDisconnected,
      macos_reconnect_volume: macos.reconnectVolume,
    },
    warehouse: {
      posthog_gcp_aggregate: false,
      billing_table: billingTable(),
      plan_economics_reads_unit_cost_daily: PLAN_ECONOMICS_QUERY.includes(
        "omi_finops.unit_cost_daily"
      ),
    },
  };
}

export const FIXTURE_PARITY_RECEIPT = buildFixtureParityReceipt();
