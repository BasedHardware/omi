import { describe, expect, it } from "vitest";
import { parsePlanCost } from "../wall-finops";
import {
  allInCost,
  estimateStatus,
  oneTimeExcess,
  SAAS_MONTHLY_USD,
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

  it("dates each manual estimate and flags it stale after 35 days", () => {
    expect(estimateStatus(new Date("2026-11-20T23:00Z"))).toEqual([
      {
        line: "STT",
        monthlyUsd: 5_300,
        asOf: "2026-10-16",
        ageDays: 35,
        stale: false,
      },
      {
        line: "SaaS",
        monthlyUsd: 4_800,
        asOf: "2026-10-16",
        ageDays: 35,
        stale: false,
      },
    ]);
    expect(
      estimateStatus(new Date("2026-11-21T00:00Z")).every((e) => e.stale)
    ).toBe(true);
  });

  it("uses a measured STT line for its day and the constant elsewhere", () => {
    const { daily } = allInCost(days, {}, { [day(19)]: 99 });
    expect(daily.find((d) => d.date === day(19))).toMatchObject({
      stt: 99,
      sttMeasured: true,
    });
    expect(daily.find((d) => d.date === day(18))).toMatchObject({
      sttMeasured: false,
    });
    expect(daily.find((d) => d.date === day(18))!.stt).toBeCloseTo(sttDay);
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
            settled: true,
          },
          {
            day: "2026-10-13",
            plan: "plus",
            usd: 90,
            users: 95,
            settled: true,
          },
          {
            day: "2026-10-14",
            plan: "basic",
            usd: 1,
            users: 2,
            settled: false,
          },
          { day: "2026-10-14", plan: "plus", usd: 1, users: 2, settled: true },
        ],
        stt: [{ day: "2026-10-13", usd: 143 }],
      })
    );
    expect(h).toEqual({
      plans: {
        "2026-10-13": {
          basic: { usd: 1000, users: 1500 },
          plus: { usd: 90, users: 95 },
        },
      },
      sttMeasured: { "2026-10-13": 143 },
    });
  });
});
