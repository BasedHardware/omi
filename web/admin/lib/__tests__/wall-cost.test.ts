import { describe, expect, it } from "vitest";
import {
  FINOPS_MODULATE_MODELLED_QUERY,
  FINOPS_PLAN_COST_QUERY,
  FINOPS_VENDOR_BALANCE_QUERY,
  parsePlanCost,
  parseVendorBalance,
} from "../wall-finops";
import {
  allInCost,
  estimateStatus,
  modulateReconciliation,
  oneTimeExcess,
  SAAS_MONTHLY_USD,
  sttLineFor,
  STT_MONTHLY_USD,
} from "../wall-cost";

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
    expect(d.total).toBeCloseTo(1_700 + 100 + 250 + 20 + sttDay + saasDay);
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
      1_700 + 100 + 250 + 20 + sttDay + saasDay
    );
    // A reported zero (key present, no spend) is not counted and not missing.
    const flat = days.map((d) => ({
      ...d,
      components: { ...d.components, anthropic: 0 },
    }));
    const zero = allInCost(flat, { openai: true, anthropic: true });
    expect(zero.daily.find((x) => x.date === day(19))!.total).toBeCloseTo(
      1_700 + 100 + 250 + sttDay + saasDay
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
    ]);
    // STT goes stale after 14 days (David 2026-10-22) while SaaS holds to 35.
    expect(
      estimateStatus(new Date("2026-10-31T00:00Z"), { SaaS: true })
    ).toEqual([
      expect.objectContaining({ line: "STT", ageDays: 15, stale: true }),
      expect.objectContaining({ line: "SaaS", ageDays: 15, stale: false }),
    ]);
    expect(
      estimateStatus(new Date("2026-11-21T00:00Z")).every((e) => e.stale)
    ).toBe(true);
    expect(
      estimateStatus(new Date("2026-11-21T00:00Z"), { SaaS: true })
    ).toEqual([
      expect.objectContaining({ line: "STT", stale: true }),
      expect.objectContaining({ line: "SaaS", stale: false }),
    ]);
  });

  it("uses a measured STT line for its day and the constant elsewhere", () => {
    const { daily } = allInCost(
      days,
      {},
      {
        sttMeasured: { [day(19)]: 99 },
      }
    );
    expect(daily.find((d) => d.date === day(19))).toMatchObject({
      stt: 99,
      sttMeasured: true,
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
        sttMeasured: { [day(19)]: 99 },
        sttCash,
      }
    );
    // Measured day: usage + Modulate only; Soniox prepaid and Deepgram cash
    // (a measured line exists that day) must not stack on top.
    expect(daily.find((d) => d.date === day(19))).toMatchObject({
      stt: 99 + 20,
      sttCash: 20,
      sttMeasured: true,
    });
    // No measured line: the dated Soniox constant + Modulate (+ Deepgram cash,
    // which has no measured line that day).
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
        stt: [{ day: "2026-10-13", usd: 143 }],
        saas: [
          { day: "2026-10-13", usd: 0 },
          { day: "2026-10-12", usd: 8.5 },
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
      sttMeasured: { "2026-10-13": 143 },
      saasMeasured: { "2026-10-13": 0, "2026-10-12": 8.5 },
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
  });
});

describe("STT vendor lines: Soniox balance deltas and Modulate modelled", () => {
  const bal = (
    over: Partial<Parameters<typeof sttLineFor>[1]["sonioxBalance"]> = {}
  ) => ({
    ready: true,
    firstDay: "2026-10-11",
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
    expect(line.sonioxUsd).toBeCloseTo(140.25);
    expect(line.modulateUsd).toBeCloseTo(20);
    expect(line.modulateModelled).toBe(false);
    expect(line.flag).toBeNull();
    // a legacy usage-summary row never overrides the live balance series
    const legacy = sttLineFor("2026-10-13", {
      sonioxBalance: bal(),
      sttMeasured: { "2026-10-13": 99 },
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

  it("treats a baseline-reset day as unmeasured and flagged, never the constant", () => {
    const line = sttLineFor("2026-10-13", {
      sonioxBalance: bal({
        spend: { "2026-10-13": null },
        flags: { "2026-10-13": "baseline_reset" },
      }),
    });
    expect(line.measured).toBe(false);
    expect(line.sonioxUsd).toBe(0);
    expect(line.flag).toBe("baseline_reset");
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

  it("keeps Deepgram cash off days with a measured Soniox balance line", () => {
    const line = sttLineFor("2026-10-13", {
      sonioxBalance: bal(),
      sttCash: { "2026-10-13": { deepgram: 7 } },
    });
    expect(line.usd).toBeCloseTo(140.25);
    const none = sttLineFor("2026-10-10", {
      sonioxBalance: bal(),
      sttCash: { "2026-10-10": { deepgram: 7 } },
    });
    expect(none.usd).toBeCloseTo(STT_MONTHLY_USD / (365.25 / 12) + 7);
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
