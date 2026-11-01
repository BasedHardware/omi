import { describe, expect, it, vi } from "vitest";
import {
  fetchInfraHistory,
  fetchStripeFeeHistory,
  FINOPS_INFRA_QUERY,
  FINOPS_MODULATE_MODELLED_QUERY,
  FINOPS_PLAN_COST_QUERY,
  FINOPS_STRIPE_FEE_QUERY,
  FINOPS_VENDOR_BALANCE_QUERY,
  HEALTH_COST_DAYS,
  parseFinopsHistory,
  parseInfra,
  parsePlanCost,
  parseVendorBalance,
} from "../wall-finops";
import {
  allInCost,
  estimateStatus,
  INFRA_AS_OF,
  INFRA_MONTHLY_USD,
  infraLineFor,
  modulateReconciliation,
  oneTimeExcess,
  SAAS_MONTHLY_USD,
  MARGIN_DAYS_PER_MONTH,
  SONIOX_GAP_FLAG,
  sonioxBalanceInputs,
  sonioxSeriesBroken,
  sttLineFor,
  STRIPE_FEES_AS_OF,
  STRIPE_FEES_MONTHLY_USD,
  STT_MONTHLY_USD,
  VARIABLE_MARGIN_TARGET,
  variableCostDay,
  variableMarginLineStatus,
  variableMarginSeries,
} from "../wall-cost";

const query = vi.hoisted(() => vi.fn());
// Partial: wall-cost.ts also imports `isLlmService` from this module.
vi.mock("@/lib/services/gcp-billing", async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  getGcpBillingClient: () => ({ query }),
}));

const day = (i: number) => `2026-09-${String(i).padStart(2, "0")}`;
/** Flat GCP with a Coldline-migration-like Cloud Storage spike on Sep 20. */
const days = Array.from({ length: 21 }, (_, k) => {
  const i = k + 1;
  const storage = i === 20 ? 14_000 : 200;
  return {
    date: day(i),
    total: 0,
    components: {
      gcpInfra: 1_500 + storage,
      vertexLlm: 100,
      openai: 250,
      anthropic: 20,
      gcpServices: {
        "Cloud Storage": storage,
        Compute: 1_300,
        "Vertex AI": 100,
      },
    },
  };
});
const saasDay = SAAS_MONTHLY_USD / (365.25 / 12);
const sttDay = STT_MONTHLY_USD / (365.25 / 12);
const infraDay = INFRA_MONTHLY_USD / (365.25 / 12);
/** Age of the infra constant at a test time, from the committed as-of date. */
const infraAge = (at: string) =>
  Math.floor(
    (Date.parse(`${at}T00:00:00Z`) - Date.parse(`${INFRA_AS_OF}T00:00:00Z`)) /
      86_400_000
  );

describe("all-in cost", () => {
  it("removes only the excess of a one-time spike", () => {
    const spikes = oneTimeExcess(days);
    expect(Array.from(spikes.keys())).toEqual([day(20)]);
    expect(spikes.get(day(20))).toMatchObject({ usd: 13_800, llmUsd: 0 });
    const { daily } = allInCost(days);
    expect(daily.find((d) => d.date === day(20))!.gcp).toBe(1_700);
  });

  it("counts every line: GCP, Vertex, invoices, Soniox-console STT and fixed SaaS", () => {
    const { daily, missing } = allInCost(days, {
      openai: true,
      anthropic: true,
    });
    const d = daily.find((x) => x.date === day(19))!;
    expect(d).toMatchObject({
      gcp: 1_700,
      vertexLlm: 100,
      openai: 250,
      anthropic: 20,
      saasMeasured: false,
    });
    expect(STT_MONTHLY_USD).toBe(5_300);
    expect(d.stt).toBeCloseTo(sttDay);
    expect(d.total).toBeCloseTo(
      1_700 + 100 + 250 + 20 + sttDay + saasDay + infraDay
    );
    expect(missing).toEqual([]);
  });

  it("names lines it cannot source instead of dropping them", () => {
    const { daily, missing } = allInCost(days, {
      openai: false,
      anthropic: true,
    });
    expect(missing).toEqual(["OpenAI invoice"]);
    expect(daily[0]).toMatchObject({ openai: null });
    // The Anthropic leg with no reported spend is excluded (seats are SaaS
    // cash), not a missing line.
    const zero = allInCost(days, { openai: true, anthropic: false });
    expect(zero.missing).toEqual([]);
    expect(zero.daily[0].anthropic).toBeNull();
  });

  it("counts the Anthropic invoice only when the admin API reports spend", () => {
    const { daily } = allInCost(days, { openai: true, anthropic: true });
    const withSpend = daily.find((x) => x.date === day(19))!;
    expect(withSpend.anthropic).toBe(20);
    expect(withSpend.total).toBeCloseTo(
      1_700 + 100 + 250 + 20 + sttDay + saasDay + infraDay
    );
    // A reported zero (key present, no spend) is not counted and not missing.
    const flat = days.map((d) => ({
      ...d,
      components: { ...d.components, anthropic: 0 },
    }));
    const zero = allInCost(flat, { openai: true, anthropic: true });
    expect(zero.daily.find((x) => x.date === day(19))!.total).toBeCloseTo(
      1_700 + 100 + 250 + sttDay + saasDay + infraDay
    );
    expect(zero.missing).toEqual([]);
  });

  it("needs a week of history before calling anything one-time", () => {
    const early = days.slice(0, 6).map((d, i) =>
      i === 5
        ? {
            ...d,
            components: {
              ...d.components,
              gcpServices: { "Cloud Storage": 9_000 },
            },
          }
        : d
    );
    expect(oneTimeExcess(early).size).toBe(0);
  });

  it("dates each manual estimate and flags it stale past its own threshold", () => {
    expect(estimateStatus(new Date("2026-10-20T00:00Z"))).toEqual([
      {
        line: "STT",
        monthlyUsd: 5_300,
        asOf: "2026-10-16",
        ageDays: 4,
        staleDays: 14,
        stale: false,
      },
      {
        line: "SaaS",
        monthlyUsd: 4_800,
        asOf: "2026-10-16",
        ageDays: 4,
        staleDays: 35,
        stale: false,
      },
      {
        line: "Infra",
        monthlyUsd: INFRA_MONTHLY_USD,
        asOf: INFRA_AS_OF,
        ageDays: infraAge("2026-10-20"),
        staleDays: 35,
        stale: false,
      },
    ]);
    // STT goes stale after 14 days (David 2026-10-22) while SaaS and the infra
    // run-rate constant hold to their monthly 35-day threshold.
    expect(
      estimateStatus(new Date("2026-10-31T00:00Z"), { SaaS: true })
    ).toEqual([
      expect.objectContaining({ line: "STT", ageDays: 15, stale: true }),
      expect.objectContaining({ line: "SaaS", ageDays: 15, stale: false }),
      expect.objectContaining({
        line: "Infra",
        ageDays: infraAge("2026-10-31"),
        stale: false,
      }),
    ]);
    // 2026-12-01 is past every line's threshold from each committed as-of.
    expect(
      estimateStatus(new Date("2026-12-01T00:00Z")).every((e) => e.stale)
    ).toBe(true);
    expect(
      estimateStatus(new Date("2026-12-01T00:00Z"), { SaaS: true, Infra: true })
    ).toEqual([
      expect.objectContaining({ line: "STT", stale: true }),
      expect.objectContaining({ line: "SaaS", stale: false }),
      expect.objectContaining({ line: "Infra", stale: false }),
    ]);
  });

  it("uses a measured STT line for its day and the constant elsewhere", () => {
    const { daily } = allInCost(
      days,
      {},
      {
        sttMeasured: { [day(19)]: { soniox: 99 } },
      }
    );
    expect(daily.find((d) => d.date === day(19))).toMatchObject({
      stt: 99,
      sttMeasured: true,
      sttSonioxMeasured: true,
    });
    expect(daily.find((d) => d.date === day(18))).toMatchObject({
      sttMeasured: false,
    });
    expect(daily.find((d) => d.date === day(18))!.stt).toBeCloseTo(sttDay);
  });

  it("adds Mercury cash for vendors without a usage feed, never for Soniox", () => {
    const sttCash: Record<string, Record<string, number>> = {
      [day(19)]: { modulate: 20, soniox: 500, deepgram: 5 },
      [day(18)]: { modulate: 10 },
    };
    const { daily } = allInCost(
      days,
      {},
      {
        sttMeasured: { [day(19)]: { soniox: 99 } },
        sttCash,
      }
    );
    // Measured Soniox day: usage + Modulate cash + Deepgram's OWN cash (a
    // Soniox measurement never hides another provider); Soniox prepaid cash
    // never stacks on its measured line.
    expect(daily.find((d) => d.date === day(19))).toMatchObject({
      stt: 99 + 20 + 5,
      sttCash: 25,
      sttMeasured: true,
      sttDeepgramUsd: 5,
      sttDeepgramMeasured: false,
    });
    // No measured line: the dated Soniox constant + Modulate cash.
    expect(daily.find((d) => d.date === day(18))).toMatchObject({
      stt: sttDay + 10,
      sttCash: 10,
      sttMeasured: false,
    });
    const deepgramOnly = allInCost(
      days,
      {},
      {
        sttCash: { [day(18)]: { deepgram: 7 } },
      }
    );
    expect(deepgramOnly.daily.find((d) => d.date === day(18))!.stt).toBeCloseTo(
      sttDay + 7
    );
  });

  it("keeps every STT provider separate: Deepgram measured usage is its own line", () => {
    // A day with both providers measured counts both; a Deepgram-only usage
    // aggregate is never presented as Soniox (the constant stays for Soniox).
    const both = allInCost(
      days,
      {},
      {
        sttMeasured: { [day(19)]: { soniox: 99, deepgram: 11 } },
        sttCash: { [day(19)]: { deepgram: 5 } },
      }
    );
    expect(both.daily.find((d) => d.date === day(19))).toMatchObject({
      stt: 110,
      sttSonioxUsd: 99,
      sttDeepgramUsd: 11,
      sttDeepgramMeasured: true,
      sttCash: 0, // measured Deepgram wins over its cash
      sttMeasured: true,
    });
    const deepgramOnly = allInCost(
      days,
      {},
      { sttMeasured: { [day(19)]: { deepgram: 11 } } }
    );
    const d = deepgramOnly.daily.find((x) => x.date === day(19))!;
    expect(d.sttSonioxMeasured).toBe(false);
    expect(d.sttSonioxUsd).toBeCloseTo(sttDay);
    expect(d.sttDeepgramUsd).toBe(11);
    expect(d.sttMeasured).toBe(true);
    expect(d.stt).toBeCloseTo(sttDay + 11);
  });

  it("adds measured Stripe fees and reports the line unavailable, never guessed", () => {
    const withFees = allInCost(days, {}, { stripeFees: { [day(19)]: 12.5 } });
    expect(withFees.daily.find((d) => d.date === day(19))!.fees).toBe(12.5);
    expect(withFees.daily.find((d) => d.date === day(18))!.fees).toBeNull();
    expect(withFees.missing).toEqual([]);
    const unavailable = allInCost(
      days,
      {},
      {},
      "finops key lacks balance-transaction read scope"
    );
    expect(unavailable.daily.every((d) => d.fees === null)).toBe(true);
    expect(unavailable.missing).toEqual(["Stripe processing fees"]);
    // Unavailable fees never change the total: no estimate is invented.
    const totals = (r: ReturnType<typeof allInCost>) =>
      r.daily.map((d) => d.total);
    expect(totals(unavailable)).toEqual(totals(allInCost(days)));
  });

  it("uses measured SaaS including zero and keeps the estimate on other days", () => {
    const { daily } = allInCost(
      days,
      {},
      {
        saasMeasured: { [day(19)]: 0, [day(18)]: 17.25 },
      }
    );
    expect(daily.find((d) => d.date === day(19))).toMatchObject({
      saas: 0,
      saasMeasured: true,
    });
    expect(daily.find((d) => d.date === day(18))).toMatchObject({
      saas: 17.25,
      saasMeasured: true,
    });
    expect(daily.find((d) => d.date === day(17))).toMatchObject({
      saasMeasured: false,
    });
    expect(daily.find((d) => d.date === day(17))!.saas).toBeCloseTo(saasDay);
  });

  it("counts the non-GCP infra run rate in the all-in total, with a dated fallback", () => {
    const { daily } = allInCost(
      days,
      {},
      {
        infraMeasured: { [day(19)]: 41.25, [day(18)]: 0 },
      }
    );
    const d19 = daily.find((d) => d.date === day(19))!;
    expect(d19).toMatchObject({ infra: 41.25, infraMeasured: true });
    expect(d19.total).toBeCloseTo(
      1_700 + 100 + 250 + 20 + sttDay + saasDay + 41.25
    );
    // A measured zero is a measurement, not a missing line.
    expect(daily.find((d) => d.date === day(18))).toMatchObject({
      infra: 0,
      infraMeasured: true,
    });
    // A day without a measured row keeps the dated constant — never silent $0.
    const d17 = daily.find((d) => d.date === day(17))!;
    expect(d17.infraMeasured).toBe(false);
    expect(d17.infra).toBeCloseTo(infraDay);
  });

  it("keeps infra out of the STT line: each line counts its own dollars once", () => {
    // STT cash (Modulate) and a measured infra row on the same day both land
    // in the total exactly once; the STT fields never absorb infra dollars.
    const { daily } = allInCost(
      days,
      {},
      {
        sttCash: { [day(19)]: { modulate: 20 } },
        infraMeasured: { [day(19)]: 41.25 },
      }
    );
    const d = daily.find((x) => x.date === day(19))!;
    expect(d.stt).toBeCloseTo(sttDay + 20);
    expect(d.infra).toBe(41.25);
    expect(d.total).toBeCloseTo(
      1_700 + 100 + 250 + 20 + sttDay + 20 + saasDay + 41.25
    );
  });

  it("floors a partial infra run rate at the dated fallback, still labelled partial (Luna r2 P1)", () => {
    // The ledger starts 2026-07-04; the $12,000 Modal wire of 2026-01-08
    // (≈$1,000/mo) predates it, so until the 400-day backfill a partial row
    // sees only the ≈$114/mo Cloudflare + Hetzner slice (≈$3.75/day). That is
    // a floor, never a replacement for the $1,114/mo constant carrying the
    // known wire: the day shows max(measured, constant) and stays partial.
    const { daily } = allInCost(
      days,
      {},
      {
        infraMeasured: { [day(19)]: 3.75, [day(18)]: 50, [day(17)]: 3.75 },
        infraAnnualPartial: {
          [day(19)]: "history_under_12_months",
          [day(18)]: "history_under_12_months",
        },
      }
    );
    const d19 = daily.find((d) => d.date === day(19))!;
    expect(d19).toMatchObject({
      infraMeasured: true,
      infraMeasuredUsd: 3.75,
      infraPartial: "history_under_12_months",
      infraFloored: true,
      infraFeesCash: 0,
    });
    expect(d19.infra).toBeCloseTo(infraDay);
    expect(d19.total).toBeCloseTo(
      1_700 + 100 + 250 + 20 + sttDay + saasDay + infraDay
    );
    // A partial run rate that rises above the constant is used at once —
    // not hidden behind the constant — and is still labelled partial.
    expect(daily.find((d) => d.date === day(18))).toMatchObject({
      infra: 50,
      infraMeasuredUsd: 50,
      infraPartial: "history_under_12_months",
      infraFloored: false,
    });
    // A complete row below the constant is the measurement: no floor.
    expect(daily.find((d) => d.date === day(17))).toMatchObject({
      infra: 3.75,
      infraPartial: null,
      infraFloored: false,
    });
  });

  it("floors on either partial reason, a partial zero included", () => {
    // `uncategorized_above_threshold` can hide an unmatched annual infra wire
    // just as a short ledger does, so it floors the same way.
    expect(
      infraLineFor(
        day(19),
        {
          infraMeasured: { [day(19)]: 0 },
          infraAnnualPartial: { [day(19)]: "uncategorized_above_threshold" },
        },
        null
      )
    ).toMatchObject({
      usd: infraDay,
      measured: true,
      measuredUsd: 0,
      partial: "uncategorized_above_threshold",
      floored: true,
      feesCash: 0,
    });
    // No row at all: the dated constant, unmeasured, not floored.
    expect(infraLineFor(day(19), {}, null)).toMatchObject({
      usd: infraDay,
      measured: false,
      measuredUsd: null,
      partial: null,
      floored: false,
      feesCash: 0,
    });
  });

  it("counts Mercury stripe_fees cash on the infra line only while the measured fee line is dark (Luna r2 P2)", () => {
    const vendor = {
      infraMeasured: { [day(19)]: 41.25, [day(18)]: 41.25 },
      infraStripeFeesCash: { [day(19)]: 4, [day(18)]: 4 },
      stripeFees: { [day(19)]: 12.5 }, // day 18 has no measured fee row
    };
    const { daily } = allInCost(days, {}, vendor);
    // Day 19: the measured fee line owns the money; infra stays without it.
    const d19 = daily.find((d) => d.date === day(19))!;
    expect(d19).toMatchObject({ infra: 41.25, infraFeesCash: 0, fees: 12.5 });
    expect(d19.total).toBeCloseTo(
      1_700 + 100 + 250 + 20 + sttDay + saasDay + 41.25 + 12.5
    );
    // Day 18: no measured fee for the day — the cash rejoins infra, labelled,
    // so it is on exactly one line.
    const d18 = daily.find((d) => d.date === day(18))!;
    expect(d18).toMatchObject({ infra: 45.25, infraFeesCash: 4, fees: null });
    expect(d18.total).toBeCloseTo(
      1_700 + 100 + 250 + 20 + sttDay + saasDay + 45.25
    );
    // Fee source dark entirely: every day's cash rejoins infra, and the fee
    // line is still reported missing — never dropped from both.
    const dark = allInCost(days, {}, vendor, "fees unavailable");
    expect(dark.daily.find((d) => d.date === day(19))).toMatchObject({
      infra: 45.25,
      infraFeesCash: 4,
      fees: null,
    });
    expect(dark.missing).toContain("Stripe processing fees");
    // The floor and the fee cash compose: constant base + fee cash.
    const floored = infraLineFor(
      day(19),
      {
        ...vendor,
        infraMeasured: { [day(19)]: 3.75 },
        infraAnnualPartial: { [day(19)]: "history_under_12_months" },
      },
      null
    );
    expect(floored.usd).toBeCloseTo(infraDay + 4);
    expect(floored).toMatchObject({ floored: true, feesCash: 4 });
  });
});

describe("FinOps plan cost reader", () => {
  it("drops unsettled days and keeps measured STT by day", () => {
    const h = parsePlanCost(
      JSON.stringify({
        plans: [
          {
            day: "2026-10-13",
            plan: "basic",
            usd: 1000,
            users: 1500,
            varUsd: 400,
            varUsers: 1500,
            settled: true,
          },
          {
            day: "2026-10-13",
            plan: "plus",
            usd: 90,
            users: 95,
            varUsd: null,
            varUsers: null,
            settled: true,
          },
          {
            day: "2026-10-14",
            plan: "basic",
            usd: 1,
            users: 2,
            varUsd: 1,
            varUsers: 2,
            settled: false,
          },
          {
            day: "2026-10-14",
            plan: "plus",
            usd: 1,
            users: 2,
            varUsd: 1,
            varUsers: 2,
            settled: true,
          },
        ],
        stt: [
          { day: "2026-10-13", component: "stt_soniox_measured", usd: 143 },
          { day: "2026-10-13", component: "stt_deepgram_measured", usd: 11 },
        ],
        saas: [
          { day: "2026-10-13", usd: 0, annual_complete: true },
          { day: "2026-10-12", usd: 8.5, annual_complete: true },
          {
            day: "2026-10-11",
            usd: 9.5,
            annual_complete: false,
            annual_reason: "history_under_12_months",
          },
          {
            day: "2026-10-10",
            usd: 7.5,
            annual_complete: false,
            annual_reason: "uncategorized_above_threshold",
          },
          { day: "2026-10-09", usd: 6.5, annual_complete: false },
        ],
        sttCash: [
          { day: "2026-10-13", vendor: "modulate", usd: 19.8 },
          { day: "2026-10-13", vendor: "soniox", usd: 500 },
        ],
      })
    );
    expect(h).toEqual({
      plans: {
        "2026-10-13": {
          basic: { usd: 1000, users: 1500, varUsd: 400, varUsers: 1500 },
          plus: { usd: 90, users: 95, varUsd: 0, varUsers: 0 },
        },
      },
      // Provider-specific: soniox and deepgram stay separate (Luna P1).
      sttMeasured: { "2026-10-13": { soniox: 143, deepgram: 11 } },
      // An annual-history gap keeps the amortized value measured; the day is
      // labelled partial with the producer's reason (a missing reason falls
      // back to the short-history wording).
      saasMeasured: {
        "2026-10-13": 0,
        "2026-10-12": 8.5,
        "2026-10-11": 9.5,
        "2026-10-10": 7.5,
        "2026-10-09": 6.5,
      },
      saasAnnualPartial: {
        "2026-10-11": "history_under_12_months",
        "2026-10-10": "uncategorized_above_threshold",
        "2026-10-09": "history_under_12_months",
      },
      sttCash: { "2026-10-13": { modulate: 19.8, soniox: 500 } },
    });
  });

  it("reads only complete, fresh Mercury SaaS aggregates", () => {
    expect(FINOPS_PLAN_COST_QUERY).toContain("inputs_complete = TRUE");
    expect(FINOPS_PLAN_COST_QUERY).toContain(
      "computed_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 3 DAY)"
    );
    expect(FINOPS_PLAN_COST_QUERY).toContain("mercury_saas_daily");
    expect(FINOPS_PLAN_COST_QUERY).toContain("variable_total");
    expect(FINOPS_PLAN_COST_QUERY).toContain("mercury_vendor_spend_daily");
    // The annual-history status and its reason are selected so the wall can
    // label the measured line partial until the ledger covers 12 months.
    expect(FINOPS_PLAN_COST_QUERY).toContain("annual_history_complete");
    expect(FINOPS_PLAN_COST_QUERY).toContain("annual_history_reason");
  });
});

describe("FinOps infra run-rate reader", () => {
  it("reads complete fresh rows, partial annual history and the excluded fee cash", () => {
    const h = parseInfra(
      JSON.stringify({
        infra: [
          {
            day: "2026-10-13",
            usd: 32.87,
            stripe_fees_usd: "4.1",
            annual_complete: true,
          },
          {
            day: "2026-10-12",
            usd: 0,
            stripe_fees_usd: 0,
            annual_complete: false,
            annual_reason: "history_under_12_months",
          },
          {
            day: "2026-10-11",
            usd: 5,
            annual_complete: false,
            annual_reason: "uncategorized_above_threshold",
          },
          { day: "2026-10-10", usd: 6, annual_complete: false },
        ],
      })
    );
    // Explicit zeroes are measurements; a missing reason falls back to the
    // short-history wording, matching the SaaS reader's contract.
    expect(h.infraMeasured).toEqual({
      "2026-10-13": 32.87,
      "2026-10-12": 0,
      "2026-10-11": 5,
      "2026-10-10": 6,
    });
    expect(h.infraAnnualPartial).toEqual({
      "2026-10-12": "history_under_12_months",
      "2026-10-11": "uncategorized_above_threshold",
      "2026-10-10": "history_under_12_months",
    });
    // NUMERIC arrives as a string; an absent value is no excluded cash.
    expect(h.infraStripeFeesCash).toEqual({
      "2026-10-13": 4.1,
      "2026-10-12": 0,
      "2026-10-11": 0,
      "2026-10-10": 0,
    });
  });

  it("queries the infra table separately from the plan-cost read", () => {
    expect(FINOPS_INFRA_QUERY).toContain("mercury_infra_non_gcp_daily");
    expect(FINOPS_INFRA_QUERY).toContain("inputs_complete = TRUE");
    expect(FINOPS_INFRA_QUERY).toContain(
      "computed_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 3 DAY)"
    );
    // The excluded fee cash rides along so the stack can count it on a
    // fee-dark day; a NULL is no cash, not a failed read.
    expect(FINOPS_INFRA_QUERY).toContain(
      "IFNULL(stripe_fees_usd, 0) AS stripe_fees_usd"
    );
    // A dark infra table must never fail the plan/STT/SaaS read (the fee-table
    // rule): it stays out of the plan-cost query.
    expect(FINOPS_PLAN_COST_QUERY).not.toContain("mercury_infra_non_gcp_daily");
  });

  it("defaults both history reads past the oldest health frame (Luna r2 P2)", async () => {
    // The wall renders HEALTH_COST_DAYS frames ending at the D−2 cutoff, so
    // its oldest day is today−61. Both reads must reach that day unprompted:
    // with the fee source dark, an infra day outside the read silently drops
    // its Mercury stripe_fees cash from the rendered series.
    const today = "2026-10-15";
    const oldest = "2026-08-15"; // today − 61
    query.mockResolvedValueOnce([
      [
        {
          history: JSON.stringify({
            infra: [
              {
                day: oldest,
                usd: 1,
                stripe_fees_usd: 4,
                annual_complete: true,
              },
            ],
          }),
        },
      ],
    ]);
    const infra = await fetchInfraHistory(today);
    const infraCall = query.mock.calls[0][0] as { params: { days: number } };
    expect(infraCall.params.days).toBeGreaterThanOrEqual(HEALTH_COST_DAYS + 1);
    expect(infra.infraStripeFeesCash[oldest]).toBe(4);

    query.mockResolvedValueOnce([
      [{ day: oldest, fee_usd: 5, foreign_transaction_count: 0 }],
    ]);
    const fees = await fetchStripeFeeHistory(today);
    const feeCall = query.mock.calls[1][0] as { params: { days: number } };
    expect(feeCall.params.days).toBeGreaterThanOrEqual(HEALTH_COST_DAYS + 1);
    expect(fees.fees[oldest]).toBe(5);
  });
});

describe("FinOps book history: customer counts and fee coverage", () => {
  it("takes the book-wide paying-customer count per snapshot day, never the plan-row sum", () => {
    const history = parseFinopsHistory(
      JSON.stringify({
        mrr: [
          {
            day: "2026-10-13",
            plan: "unlimited",
            mrr_usd: 60,
            paying_subs: 2_000,
            paying_customers: 3_050,
            non_usd_paying_subs: 1,
            refreshed: "2026-10-13T14:36:00Z",
          },
          {
            day: "2026-10-13",
            plan: "plus",
            mrr_usd: 16,
            paying_subs: 1_100,
            paying_customers: 3_050,
            non_usd_paying_subs: 1,
            refreshed: "2026-10-13T14:36:00Z",
          },
        ],
      })
    );
    // paying_customers repeats on every plan row: take, do not sum (6,100 wrong).
    expect(history.payingCustomers["2026-10-13"]).toBe(3_050);
    expect(history.nonUsdPaying["2026-10-13"]).toBe(1);
    // The item-based plan sum stays as the pre-migration fallback.
    expect(history.paying["2026-10-13"]).toBe(3_100);
  });

  it("parses a legacy table read without the customer-count columns", () => {
    const history = parseFinopsHistory(
      JSON.stringify({
        mrr: [
          {
            day: "2026-10-13",
            plan: "unlimited",
            mrr_usd: 60,
            paying_subs: 2_000,
            refreshed: "2026-10-13T14:36:00Z",
          },
        ],
      })
    );
    expect(history.payingCustomers).toEqual({});
    expect(history.nonUsdPaying).toEqual({});
    expect(history.paying["2026-10-13"]).toBe(2_000);
  });

  it("carries the foreign-fee count so the wall can label coverage partial", () => {
    expect(FINOPS_STRIPE_FEE_QUERY).toContain("foreign_transaction_count");
  });
});

describe("STT vendor lines: Soniox balance deltas and Modulate modelled", () => {
  const bal = (
    over: Partial<Parameters<typeof sttLineFor>[1]["sonioxBalance"]> = {}
  ) => ({
    ready: true,
    firstDay: "2026-10-11",
    lastDay: "2026-10-13",
    asOf: "2026-10-13",
    spend: { "2026-10-12": 175.5, "2026-10-13": 140.25 },
    flags: {},
    ...over,
  });

  it("uses the measured balance-delta day-rate once the series is live", () => {
    const line = sttLineFor("2026-10-13", {
      sonioxBalance: bal(),
      sttCash: { "2026-10-13": { modulate: 20 } },
    });
    expect(line.usd).toBeCloseTo(140.25 + 20);
    expect(line.measured).toBe(true);
    expect(line.sonioxMeasured).toBe(true);
    expect(line.sonioxUsd).toBeCloseTo(140.25);
    expect(line.modulateUsd).toBeCloseTo(20);
    expect(line.modulateModelled).toBe(false);
    expect(line.flag).toBeNull();
    // a legacy usage-summary row never overrides the live balance series
    const legacy = sttLineFor("2026-10-13", {
      sonioxBalance: bal(),
      sttMeasured: { "2026-10-13": { soniox: 99 } },
    });
    expect(legacy.sonioxUsd).toBeCloseTo(140.25);
  });

  it("marks a gap-spread day as an estimate, not a silent measurement", () => {
    const line = sttLineFor("2026-10-12", {
      sonioxBalance: bal({ flags: { "2026-10-12": "gap_spread" } }),
    });
    expect(line.measured).toBe(true);
    expect(line.flag).toBe("gap_spread");
  });

  it("treats a baseline-reset day as unmeasured and flagged, on the labelled fallback — never $0 (Luna r2 P1)", () => {
    const line = sttLineFor("2026-10-13", {
      sonioxBalance: bal({
        spend: { "2026-10-13": null },
        flags: { "2026-10-13": "baseline_reset" },
      }),
    });
    expect(line.measured).toBe(false);
    // The reset day keeps Soniox spend in the total via the dated constant —
    // booking $0 here silently dropped it from all-in cost (Luna r2 P1).
    expect(line.sonioxUsd).toBeCloseTo(STT_MONTHLY_USD / (365.25 / 12));
    expect(line.flag).toBe("baseline_reset");
    // A FinOps usage-summary row for the same day is a better labelled
    // fallback than the console constant.
    const usage = sttLineFor("2026-10-13", {
      sonioxBalance: bal({
        spend: { "2026-10-13": null },
        flags: { "2026-10-13": "baseline_reset" },
      }),
      sttMeasured: { "2026-10-13": { soniox: 160 } },
    });
    expect(usage.sonioxUsd).toBeCloseTo(160);
    expect(usage.flag).toBe("baseline_reset");
  });

  it("never turns a stale snapshot series into $0 spend or a false reset (Luna P1)", () => {
    // The pull stopped after 2026-10-13: days beyond the last covered day are
    // NOT $0-as-reset — they fall back to the dated, unmeasured constant.
    const line = sttLineFor("2026-10-20", {
      sonioxBalance: bal({ asOf: "2026-10-13" }),
    });
    expect(line.sonioxMeasured).toBe(false);
    expect(line.measured).toBe(false);
    expect(line.sonioxUsd).toBeCloseTo(STT_MONTHLY_USD / (365.25 / 12));
    expect(line.flag).toBeNull();
  });

  it("flags a covered day with no published row as a snapshot gap, not a baseline reset", () => {
    const line = sttLineFor("2026-10-12", {
      sonioxBalance: bal({ spend: { "2026-10-13": 140.25 } }),
    });
    expect(line.flag).toBe(SONIOX_GAP_FLAG);
    expect(line.measured).toBe(false);
    // The gap day carries the dated fallback, never a $0 Soniox leg.
    expect(line.sonioxUsd).toBeCloseTo(STT_MONTHLY_USD / (365.25 / 12));
  });

  it("keeps the all-in total up on a snapshot-gap or reset day: fallback, never $0 (Luna r2 P1)", () => {
    // The series covers Sep 11–19; Sep 13 has no published row (snapshot gap)
    // and Sep 14 is a reset row. Neither may drop Soniox spend from the total.
    const vendor = {
      sonioxBalance: {
        ready: true,
        firstDay: day(11),
        lastDay: day(19),
        asOf: day(19),
        spend: { [day(12)]: 175.5, [day(14)]: null },
        flags: { [day(14)]: "baseline_reset" },
      },
    };
    const { daily } = allInCost(
      days,
      { openai: true, anthropic: true },
      vendor
    );
    const noSeries = allInCost(days, { openai: true, anthropic: true });
    const base = noSeries.daily.find((d) => d.date === day(13))!;
    const gap = daily.find((d) => d.date === day(13))!;
    const reset = daily.find((d) => d.date === day(14))!;
    expect(gap.sttFlag).toBe(SONIOX_GAP_FLAG);
    expect(gap.sttSonioxUsd).toBeCloseTo(sttDay);
    expect(gap.total).toBeCloseTo(base.total);
    expect(reset.sttFlag).toBe("baseline_reset");
    expect(reset.sttSonioxUsd).toBeCloseTo(sttDay);
    expect(reset.total).toBeCloseTo(base.total);
    // A published row is still the measured day-rate on its own day.
    const measured = daily.find((d) => d.date === day(12))!;
    expect(measured.sttSonioxMeasured).toBe(true);
    expect(measured.sttSonioxUsd).toBeCloseTo(175.5);
    expect(measured.total).toBeCloseTo(base.total - sttDay + 175.5);
  });

  it("keeps the labelled dated constant until 2 snapshots exist and before the series starts", () => {
    const one = sttLineFor("2026-10-13", {
      sonioxBalance: bal({ ready: false, spend: {} }),
    });
    expect(one.measured).toBe(false);
    expect(one.sonioxUsd).toBeCloseTo(STT_MONTHLY_USD / (365.25 / 12));
    const before = sttLineFor("2026-10-10", { sonioxBalance: bal() });
    expect(before.measured).toBe(false);
    expect(before.sonioxUsd).toBeCloseTo(STT_MONTHLY_USD / (365.25 / 12));
  });

  it("replaces Modulate Mercury cash with the modelled volume line exactly once", () => {
    const line = sttLineFor("2026-10-13", {
      sonioxBalance: bal(),
      modulateModelled: {
        byDay: { "2026-10-13": { usd: 20.5, priceAsOf: "2026-10-18" } },
        price: 0.06,
        priceAsOf: "2026-10-18",
      },
      sttCash: { "2026-10-13": { modulate: 20 } },
    });
    expect(line.usd).toBeCloseTo(140.25 + 20.5);
    expect(line.modulateModelled).toBe(true);
    expect(line.cash).toBe(0); // Mercury cash never stacks under the modelled line
  });

  it("counts Deepgram cash on its own line even when Soniox is measured (Luna P1)", () => {
    const line = sttLineFor("2026-10-13", {
      sonioxBalance: bal(),
      sttCash: { "2026-10-13": { deepgram: 7 } },
    });
    expect(line.usd).toBeCloseTo(140.25 + 7);
    expect(line.cash).toBeCloseTo(7);
    const none = sttLineFor("2026-10-10", {
      sonioxBalance: bal(),
      sttCash: { "2026-10-10": { deepgram: 7 } },
    });
    expect(none.usd).toBeCloseTo(STT_MONTHLY_USD / (365.25 / 12) + 7);
  });

  it("derives series bounds and staleness from the FinOps balance read", () => {
    const inputs = sonioxBalanceInputs(
      {
        snapshots: 3,
        asOf: "2026-10-13",
        spend: { "2026-10-12": 175.5, "2026-10-13": null },
        flags: { "2026-10-13": "baseline_reset" },
      },
      "2026-10-20"
    )!;
    expect(inputs.ready).toBe(true);
    expect(inputs.firstDay).toBe("2026-10-12");
    expect(inputs.lastDay).toBe("2026-10-13");
    // The wall's cutoff is past the last covered day: the series is broken.
    expect(sonioxSeriesBroken({ sonioxBalance: inputs }, "2026-10-18")).toBe(
      true
    );
    expect(sonioxSeriesBroken({ sonioxBalance: inputs }, "2026-10-13")).toBe(
      false
    );
    // Not-yet-live series (1 snapshot) is not "broken", just not ready.
    const one = sonioxBalanceInputs(
      { snapshots: 1, asOf: "2026-10-13", spend: {}, flags: {} },
      "2026-10-20"
    )!;
    expect(one.ready).toBe(false);
    expect(sonioxSeriesBroken({ sonioxBalance: one }, "2026-10-20")).toBe(
      false
    );
    expect(sonioxBalanceInputs(null, "2026-10-20")).toBeUndefined();
    // A broken series makes the STT estimate stale immediately (Luna P1):
    // age-based staleness alone would wait out the constant's threshold.
    const stale = estimateStatus(
      new Date("2026-10-22T00:00:00Z"),
      { STT: false },
      { STT: true }
    ).find((e) => e.line === "STT")!;
    expect(stale.stale).toBe(true);
  });

  it("reconciles Modulate modelled spend against Mercury cash over the trailing window", () => {
    const modelled = {
      byDay: {
        "2026-10-10": { usd: 10 },
        "2026-10-11": { usd: 20 },
        "2026-09-01": { usd: 999 }, // outside the 30-day window
      },
      price: 0.06,
      priceAsOf: "2026-10-18",
    };
    const recon = modulateReconciliation(
      modelled,
      { "2026-10-10": { modulate: 12 }, "2026-10-11": { modulate: 24 } },
      "2026-10-11",
      30
    );
    expect(recon).not.toBeNull();
    expect(recon!.modelledUsd).toBeCloseTo(30);
    expect(recon!.cashUsd).toBeCloseTo(36);
    expect(recon!.variancePct).toBeCloseTo(20);
    expect(modulateReconciliation(undefined, {}, "2026-10-11")).toBeNull();
    expect(
      modulateReconciliation(
        { byDay: {}, price: null, priceAsOf: null },
        {},
        "2026-10-11"
      )
    ).toBeNull();
  });

  it("counts Mercury cash on dates with no modelled row (Luna P2)", () => {
    // Batch usage or a missing metric day: cash exists where the modelled line
    // does not. The reconciliation sums Mercury over the WHOLE window.
    const modelled = {
      byDay: { "2026-10-10": { usd: 10 } },
      price: 0.06,
      priceAsOf: "2026-10-18",
    };
    const cash: Record<string, Record<string, number>> = {
      "2026-10-10": { modulate: 12 },
      "2026-10-11": { modulate: 30 }, // cash-only date
      "2026-10-12": { modulate: 8 }, // cash-only date
    };
    const recon = modulateReconciliation(modelled, cash, "2026-10-12", 30)!;
    expect(recon.modelledUsd).toBeCloseTo(10);
    expect(recon.cashUsd).toBeCloseTo(50);
    expect(recon.variancePct).toBeCloseTo(400);
  });
});

describe("vendor balance and Modulate modelled readers", () => {
  it("parses snapshot count, as-of and flagged spend days", () => {
    const parsed = parseVendorBalance(
      JSON.stringify({
        spend: [
          { day: "2026-10-12", usd: 20.5, flag: "gap_spread" },
          { day: "2026-10-13", usd: null, flag: "baseline_reset" },
        ],
        snapshots: 3,
        latest_ts: "2026-10-13T14:30:00Z",
        as_of: "2026-10-13",
      })
    );
    expect(parsed.snapshots).toBe(3);
    expect(parsed.asOf).toBe("2026-10-13");
    expect(parsed.spend["2026-10-12"]).toBeCloseTo(20.5);
    expect(parsed.spend["2026-10-13"]).toBeNull();
    expect(parsed.flags["2026-10-13"]).toBe("baseline_reset");
    // empty history parses to zero snapshots: the wall keeps its fallbacks
    const empty = parseVendorBalance("{}");
    expect(empty.snapshots).toBe(0);
    expect(empty.spend).toEqual({});
  });

  it("queries the vendor tables separately from the plan-cost read", () => {
    expect(FINOPS_VENDOR_BALANCE_QUERY).toContain("vendor_balance_spend_daily");
    expect(FINOPS_VENDOR_BALANCE_QUERY).toContain("vendor_balance_snapshot");
    expect(FINOPS_VENDOR_BALANCE_QUERY).toContain("vendor = 'soniox'");
    expect(FINOPS_PLAN_COST_QUERY).not.toContain("vendor_balance");
    expect(FINOPS_MODULATE_MODELLED_QUERY).toContain(
      "stt_modulate_modelled_daily"
    );
    expect(FINOPS_MODULATE_MODELLED_QUERY).toContain("price_as_of");
    expect(FINOPS_PLAN_COST_QUERY).not.toContain("stt_modulate_modelled_daily");
  });
});

describe("variable margin (David 2026-10-23: MRR vs the real monthly cost)", () => {
  const d = (i: number) => `2026-10-${String(i).padStart(2, "0")}`;
  /** 21 flat settled days: GCP $1,600/day net of which $95 is the prepaid
   * Vertex reserved SKU, OpenAI $250, Anthropic $10 (out of margin scope). */
  const marginDays = Array.from({ length: 21 }, (_, k) => ({
    date: d(k + 1),
    total: 0,
    components: {
      gcpInfra: 1_500,
      vertexLlm: 100,
      vertexReserved: 95,
      openai: 250,
      anthropic: 10,
      gcpServices: { Compute: 1_500, "Vertex AI": 100 },
    },
  }));
  const cash = Object.fromEntries(
    marginDays.map((x) => [x.date, { modulate: 20 }])
  );
  /** The run-rate month scale is the contract's exact 30.44 (Luna r3 P3), not
   * the all-in calendar 365.25/12 the per-day constants divide by. */
  const monthly = (perDay: number) => perDay * MARGIN_DAYS_PER_MONTH;
  const runScale = MARGIN_DAYS_PER_MONTH / 7;
  /** A dated monthly constant is priced per day at the calendar month and then
   * scaled by the run-rate factor, so it re-enters the month slightly off its
   * face value (× 30.44/30.4375). */
  const toMonth = (monthlyUsd: number) =>
    (monthlyUsd / (365.25 / 12)) * MARGIN_DAYS_PER_MONTH;
  /** The margin scope per day: GCP ex reserved + OpenAI + Soniox console est.
   * + Modulate cash + Stripe-fee baseline est. */
  const dayUsd =
    1_500 +
    100 -
    95 +
    250 +
    STT_MONTHLY_USD / (365.25 / 12) +
    20 +
    STRIPE_FEES_MONTHLY_USD / (365.25 / 12);
  const run = (vendor = {}, coverage = {}, feesCash?: Record<string, number>) =>
    variableMarginSeries(
      allInCost(marginDays, coverage, vendor).daily,
      () => 60_000,
      { feesCash }
    );

  it("excludes only the prepaid Vertex reserved capacity from the GCP line", () => {
    const points = run({ sttCash: cash });
    expect(points).toHaveLength(15); // window ends d(7)..d(21)
    const last = points.at(-1)!;
    expect(last.date).toBe(d(21));
    // GCP keeps every net dollar except the prepaid reserved SKU…
    expect(last.gcpPerMonth).toBeCloseTo(monthly(1_505), 1);
    expect(last.vertexReservedPerMonth).toBeCloseTo(monthly(95), 1);
    // …and the scope is exactly the five definition lines — Anthropic, SaaS,
    // infra and Deepgram stay out (the all-in stack counts those).
    expect(last.costPerMonth).toBeCloseTo(
      last.gcpPerMonth +
        monthly(250) +
        toMonth(STT_MONTHLY_USD) +
        monthly(20) +
        toMonth(STRIPE_FEES_MONTHLY_USD),
      0
    );
    expect(
      variableCostDay(allInCost(marginDays, {}, { sttCash: cash }).daily[0]).usd
    ).toBeCloseTo(dayUsd);
  });

  it("computes (MRR − run rate) ÷ MRR with the 50% target line", () => {
    const last = run({ sttCash: cash }).at(-1)!;
    expect(last.mrr).toBe(60_000);
    expect(last.costPerMonth).toBeCloseTo(monthly(dayUsd), 0);
    expect(last.marginPct).toBeCloseTo(
      (100 * (60_000 - monthly(dayUsd))) / 60_000,
      4
    );
    expect(last.goalCost).toBeCloseTo(60_000 * (1 - VARIABLE_MARGIN_TARGET), 6);
  });

  it("never borrows a neighbour's book: a day without MRR keeps its cost point", () => {
    const points = variableMarginSeries(
      allInCost(marginDays, {}, { sttCash: cash }).daily,
      (day) => (day === d(21) ? null : 60_000)
    );
    const last = points.at(-1)!;
    expect(last.mrr).toBeNull();
    expect(last.marginPct).toBeNull();
    expect(last.costPerMonth).toBeCloseTo(monthly(dayUsd), 0);
    expect(points.at(-2)!.marginPct).not.toBeNull();
  });

  it("a gap in the settled days kills the run rate until the window clears it", () => {
    const withGap = marginDays.filter((x) => x.date !== d(10));
    const points = variableMarginSeries(
      allInCost(withGap, {}, { sttCash: cash }).daily,
      () => 60_000
    );
    // d(7)..d(9) predate the gap; every window ending d(10)..d(16) contains
    // it; d(17) is the first window (d(11)..d(17)) clear of the hole.
    expect(points.map((p) => p.date)).toEqual([
      d(7),
      d(8),
      d(9),
      d(17),
      d(18),
      d(19),
      d(20),
      d(21),
    ]);
  });

  it("keeps a one-time GCP incident in the margin; only the wall excludes it", () => {
    const spiked = marginDays.map((x) =>
      x.date === d(12)
        ? {
            ...x,
            components: {
              ...x.components,
              gcpInfra: 1_500 + 13_800,
              gcpServices: { Compute: 1_500, "Cloud Storage": 13_800 },
            },
          }
        : x
    );
    const dirty = variableMarginSeries(
      allInCost(spiked, {}, { sttCash: cash }).daily,
      () => 60_000
    );
    const clean = run({ sttCash: cash });
    // The margin's GCP input is taken BEFORE the all-in wall's one-time-incident
    // exclusion (Luna r3 P1): its only GCP exclusion is the prepaid Vertex
    // reserved SKU, so a window containing the incident (d(8)..d(14)) carries
    // the full excess in its run rate — one spike day inside the 7-day window,
    // so the increment scales by 30.44/7, not by a full month.
    const dirty14 = dirty.find((p) => p.date === d(14))!;
    const clean14 = clean.find((p) => p.date === d(14))!;
    expect(dirty14.gcpPerMonth).toBeCloseTo(
      clean14.gcpPerMonth + 13_800 * runScale,
      0
    );
    expect(dirty14.costPerMonth).toBeCloseTo(
      clean14.costPerMonth + 13_800 * runScale,
      0
    );
    // A window past the incident is untouched…
    expect(dirty.at(-1)!.costPerMonth).toBeCloseTo(
      clean.at(-1)!.costPerMonth,
      5
    );
    // …and the Health/all-in wall keeps its existing treatment: the same spike
    // is still excluded from that day's all-in total.
    const spikedDay = allInCost(spiked, {}, { sttCash: cash }).daily.find(
      (x) => x.date === d(12)
    )!;
    const cleanDay = allInCost(marginDays, {}, { sttCash: cash }).daily.find(
      (x) => x.date === d(12)
    )!;
    expect(spikedDay.oneTime).toBe(13_800);
    expect(spikedDay.total).toBeCloseTo(cleanDay.total, 5);
  });

  it("names a missing vendor line instead of silently undercounting it", () => {
    // OpenAI leg off, no Modulate cash anywhere: both lines are named, counted
    // as $0, and the disclosure says n/a — never a quiet zero.
    const last = run({}, { openai: false }).at(-1)!;
    expect(last.missing).toEqual(["OpenAI", "Modulate"]);
    expect(last.openaiPerMonth).toBe(0);
    const lines = variableMarginLineStatus(last, {
      now: new Date("2026-10-23T00:00Z"),
    }).join(" · ");
    expect(lines).toContain("OpenAI: n/a (invoice leg off)");
    expect(lines).toContain("Modulate: n/a (no modelled or Mercury-cash line)");
    expect(lines).toContain("Soniox: console est.");
    expect(lines).toContain(
      `Stripe fees: est. $${STRIPE_FEES_MONTHLY_USD.toLocaleString("en-US")}/mo`
    );
    expect(lines).toContain(STRIPE_FEES_AS_OF);
    expect(lines).toContain(`through ${d(21)}`);
  });

  it("says since when a live Soniox series stopped covering the window", () => {
    const bal = {
      ready: true,
      firstDay: d(1),
      lastDay: d(8),
      asOf: d(8),
      spend: Object.fromEntries(
        marginDays.slice(0, 8).map((x) => [x.date, 175])
      ),
      flags: {} as Record<string, string>,
    };
    const broken = run({ sonioxBalance: bal, sttCash: cash }).at(-1)!;
    expect(broken.sonioxMeasured).toBe(false);
    expect(
      variableMarginLineStatus(broken, {
        now: new Date("2026-10-23T00:00Z"),
        soniox: bal,
      }).join(" · ")
    ).toContain(`Soniox: n/a since ${d(8)} — console est.`);
    // While the series covers every window day with a clean row, the line is
    // measured.
    const covered = {
      ...bal,
      lastDay: d(21),
      asOf: d(21),
      spend: Object.fromEntries(marginDays.map((x) => [x.date, 175])),
    };
    const measured = run({ sonioxBalance: covered, sttCash: cash }).at(-1)!;
    expect(measured.sonioxMeasured).toBe(true);
    expect(
      variableMarginLineStatus(measured, {
        now: new Date("2026-10-23T00:00Z"),
        soniox: covered,
      }).join(" · ")
    ).toContain("Soniox: measured $5,327/mo"); // 175/day × 30.44
  });

  it("labels a mixed Soniox window instead of calling it measured", () => {
    // The series covers every window day, but d(15) never published a row: it
    // falls back to the console constant. The latest day is measured, yet the
    // run rate blends sources — a window-end-only flag would hide that
    // (Luna r3 P2), so the flags aggregate over all seven days.
    const bal = {
      ready: true,
      firstDay: d(1),
      lastDay: d(21),
      asOf: d(21),
      spend: Object.fromEntries(marginDays.slice(15).map((x) => [x.date, 175])),
      flags: {} as Record<string, string>,
    };
    const point = run({ sonioxBalance: bal, sttCash: cash }).at(-1)!;
    expect(point.sonioxEstimateDays).toBe(1);
    expect(point.sonioxGapSpreadDays).toBe(0);
    expect(point.sonioxMeasured).toBe(false);
    const text = variableMarginLineStatus(point, {
      now: new Date("2026-10-23T00:00Z"),
      soniox: bal,
    }).join(" · ");
    expect(text).toContain("Soniox: $5,323/mo — 1/7 days est.");
    expect(text).not.toContain("Soniox: measured $5,323/mo"); // never "measured"
  });

  it("carries the Soniox gap_spread flag through an otherwise measured window", () => {
    // A gap_spread row has a non-null spend, but those dollars are an
    // even-spread assumption over a snapshot gap, not a per-day measurement:
    // the flag survives and the window is disclosed as gap-spread (Luna r3 P2).
    const bal = {
      ready: true,
      firstDay: d(1),
      lastDay: d(21),
      asOf: d(21),
      spend: Object.fromEntries(marginDays.map((x) => [x.date, 175])),
      flags: { [d(18)]: "gap_spread" } as Record<string, string>,
    };
    const point = run({ sonioxBalance: bal, sttCash: cash }).at(-1)!;
    expect(point.sonioxEstimateDays).toBe(0);
    expect(point.sonioxGapSpreadDays).toBe(1);
    expect(point.sonioxMeasured).toBe(false);
    expect(
      variableMarginLineStatus(point, {
        now: new Date("2026-10-23T00:00Z"),
        soniox: bal,
      }).join(" · ")
    ).toContain("Soniox: measured $5,327/mo — 1/7 days gap-spread");
  });

  it("discloses the MRR source and its non-USD exclusion with the count", () => {
    const last = run({ sttCash: cash }).at(-1)!;
    const counted = variableMarginLineStatus(last, {
      now: new Date("2026-10-23T00:00Z"),
      nonUsdPaying: 33,
    }).join(" · ");
    expect(counted).toContain(
      "MRR: FinOps plan book $60,000/mo — 33 non-USD paying subs excluded"
    );
    // A legacy table without the count column still names the partial caveat.
    const uncounted = variableMarginLineStatus(last, {
      now: new Date("2026-10-23T00:00Z"),
      nonUsdPaying: null,
    }).join(" · ");
    expect(uncounted).toContain(
      "MRR: FinOps plan book $60,000/mo — non-USD paying subs excluded (count n/a)"
    );
    // A missing book snapshot is named on the status line too — the headline
    // shows no value, and the line says why.
    const noBook = variableMarginSeries(
      allInCost(marginDays, {}, { sttCash: cash }).daily,
      (day) => (day === d(21) ? null : 60_000)
    ).at(-1)!;
    expect(
      variableMarginLineStatus(noBook, {
        now: new Date("2026-10-23T00:00Z"),
      }).join(" · ")
    ).toContain("MRR: n/a (no book snapshot that day)");
  });

  it("uses measured fees, then Mercury fee cash, before the dated baseline", () => {
    const vendor = { sttCash: cash };
    const measured = run({
      ...vendor,
      stripeFees: Object.fromEntries(marginDays.map((x) => [x.date, 90])),
    }).at(-1)!;
    expect(measured.feeSource).toBe("measured");
    expect(measured.feesPerMonth).toBeCloseTo(monthly(90), 1);

    const cashFees = run(
      vendor,
      {},
      Object.fromEntries(marginDays.map((x) => [x.date, 80]))
    ).at(-1)!;
    expect(cashFees.feeSource).toBe("cash");
    expect(cashFees.feesPerMonth).toBeCloseTo(monthly(80), 1);

    const estimate = run(vendor).at(-1)!;
    expect(estimate.feeSource).toBe("estimate");
    expect(estimate.feesPerMonth).toBeCloseTo(
      toMonth(STRIPE_FEES_MONTHLY_USD),
      4
    );
    // The baseline goes stale by its own threshold, named on the disclosure.
    const fresh = variableMarginLineStatus(estimate, {
      now: new Date("2026-10-23T00:00Z"),
    }).join(" · ");
    expect(fresh).not.toContain("STALE");
    const stale = variableMarginLineStatus(estimate, {
      now: new Date("2026-12-01T00:00Z"),
      feesUnavailable: "fee table dark",
    }).join(" · ");
    expect(stale).toContain("Stripe fees: est.");
    expect(stale).toContain("STALE");
    expect(stale).toContain("; measured line unavailable");
  });

  it("with no settled window there is no number, only a disclosure", () => {
    expect(
      variableMarginLineStatus(undefined, {
        now: new Date("2026-10-23T00:00Z"),
      })
    ).toEqual(["Variable margin: no complete settled 7-day cost window yet"]);
  });
});
