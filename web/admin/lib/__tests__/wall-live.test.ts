import { describe, expect, it } from "vitest";
import {
  allInCost,
  BillingDay,
  CostDay,
  OPENROUTER_DAILY_USD,
  sonioxRate7d,
  SonioxBalanceInputs,
  variableCostDay,
  variableMarginSeries,
} from "../wall-cost";
import {
  DAY_MS,
  LIVE_KEEP_DAYS,
  LiveDay,
  LiveDoc,
  liveWindow,
  mergeLiveDoc,
  meteredUsd,
  parseLiveDoc,
} from "../wall-live";
import {
  liveCostDay,
  liveCostDays,
  reconcileLive,
  spliceCostDays,
  trailingMean,
} from "../wall-live-margin";
import RATES from "../omi-tv-live-rates.json";

const at = (day: string, hour = 12) =>
  Date.parse(`${day}T${String(hour).padStart(2, "0")}:00:00Z`);
const iso = (ms: number) => new Date(ms).toISOString().slice(0, 10);
const shift = (day: string, n: number) =>
  iso(Date.parse(`${day}T00:00:00Z`) + n * DAY_MS);

/** A settled-shaped day from billing components, same path the wall uses. */
function billingDay(date: string, gcpInfra: number, dev = 0): BillingDay {
  return {
    date,
    total: gcpInfra,
    components: {
      gcpInfra,
      vertexLlm: 0,
      vertexReserved: 0,
      openai: 0,
      anthropic: 0,
      gcpServices: {},
      gcpDevUsd: dev,
    },
  };
}

function settledDays(end: string, n: number): CostDay[] {
  const days: BillingDay[] = [];
  for (let k = n - 1; k >= 0; k--)
    days.push(billingDay(shift(end, -k), 1_000, 100));
  return allInCost(
    days,
    { openai: true, anthropic: true },
    {
      sttCash: Object.fromEntries(days.map((d) => [d.date, { modulate: 57 }])),
      stripeFees: Object.fromEntries(days.map((d) => [d.date, 50])),
    }
  ).daily;
}

const metered = (cloudRun: number) => ({
  cloudRun,
  firestore: 0,
  gcs: 0,
  logging: 0,
});
function liveDay(
  date: string,
  fraction: number,
  producedAt: number,
  cr = 0
): LiveDay {
  return {
    date,
    queryEnd: new Date(
      Date.parse(`${date}T00:00:00Z`) + fraction * DAY_MS
    ).toISOString(),
    fraction,
    metered: metered(cr),
    producedAt: new Date(producedAt).toISOString(),
  };
}

describe("spliceCostDays: each UTC day in exactly one source", () => {
  it("takes settled through the cutoff and live after it, never both", () => {
    const cutoff = "2026-10-30"; // D-2 with today 2026-11-01
    const settled = settledDays(cutoff, 3); // 10-28..10-30
    // A live copy of the cutoff day and of the day after must not double count.
    const live = [
      liveCostDay(
        liveDay("2026-10-30", 1, at("2026-10-31", 0), 1),
        settled[2],
        null
      ),
      liveCostDay(
        liveDay("2026-10-31", 1, at("2026-11-01", 0), 1),
        settled[2],
        null
      ),
      liveCostDay(
        liveDay("2026-11-01", 0.5, at("2026-11-01", 12), 1),
        settled[2],
        null
      ),
    ];
    const out = spliceCostDays(settled, live, cutoff);
    const dates = out.map((d) => d.date);
    expect(dates).toEqual([
      "2026-10-28",
      "2026-10-29",
      "2026-10-30",
      "2026-10-31",
      "2026-11-01",
    ]);
    expect(new Set(dates).size).toBe(dates.length);
    // The cutoff day comes from settled billing, not from its live estimate.
    expect(out[2]).toBe(settled[2]);
  });

  it("fails loudly when one side carries the same day twice", () => {
    const settled = settledDays("2026-10-30", 2);
    expect(() =>
      spliceCostDays([...settled, settled[0]], [], "2026-10-30")
    ).toThrow(/counted twice/);
  });

  it("a settled day after the cutoff is dropped, so billing lag cannot double count", () => {
    const settled = settledDays("2026-10-31", 2); // includes 10-31 > cutoff
    const live = [
      liveCostDay(
        liveDay("2026-10-31", 1, at("2026-11-01", 0), 1),
        settled[1],
        null
      ),
    ];
    const out = spliceCostDays(settled, live, "2026-10-30");
    expect(out.filter((d) => d.date === "2026-10-31")).toHaveLength(1);
    expect(out.at(-1)!.total).toBe(live[0].total);
  });
});

describe("liveCostDays: freshness and the partial-day rule", () => {
  const now = at("2026-11-01", 6); // 06:00 UTC on 11-01
  const base = trailingMean(settledDays("2026-10-30", 7))!;
  const doc = (days: LiveDay[]): LiveDoc => ({
    days: Object.fromEntries(days.map((d) => [d.date, d])),
  });

  it("uses yesterday (closed) and today (partial, fresh, past 2 hours)", () => {
    const today = liveDay("2026-11-01", 6 / 24, now - 60_000, 10);
    const yesterday = liveDay("2026-10-31", 1, now - 3_600_000, 10);
    const out = liveCostDays(doc([yesterday, today]), base, now, 500);
    expect(out.map((d) => d.date)).toEqual(["2026-10-31", "2026-11-01"]);
  });

  it("omits a partial today before 2 hours of data", () => {
    const early = liveDay("2026-11-01", 1 / 24, now - 60_000, 10);
    const out = liveCostDays(doc([early]), base, now, 500);
    expect(out).toHaveLength(0);
  });

  it("omits a partial day whose producer run is stale", () => {
    const stale = liveDay("2026-11-01", 6 / 24, now - 60 * 60_000, 10);
    expect(liveCostDays(doc([stale]), base, now, 500)).toHaveLength(0);
  });

  it("scales metered lines to a full day and keeps the Soniox measured rate", () => {
    const full = liveCostDay(liveDay("2026-10-31", 1, now, 100), base, 500);
    const half = liveCostDay(liveDay("2026-10-31", 0.5, now, 50), base, 500);
    expect(full.gcp).toBeCloseTo(half.gcp, 6);
    expect(full.sttSonioxUsd).toBe(500);
    expect(full.sttSonioxMeasured).toBe(false); // a 7-day rate, disclosed as est.
    expect(full.vertexReserved).toBe(RATES.vertexReservedDay);
  });
});

describe("producer math and document", () => {
  it("meters Cloud Run from instance-seconds, Firestore by read and write, GCS and logs", () => {
    const m = meteredUsd({
      crInstanceSeconds: { backend: 1000, unknownsvc: 100 },
      fsReads: 1_000_000,
      fsWrites: 100_000,
      gcsA: 1_000_000,
      gcsB: 1_000_000,
      logBytes: 1e9,
    });
    const backend = RATES.crSpecs.backend;
    expect(m.cloudRun).toBeCloseTo(
      1000 * (backend.vcpu * RATES.crVcpuS + backend.gib * RATES.crGibS) +
        100 *
          (RATES.crDefaultSpec.vcpu * RATES.crVcpuS +
            RATES.crDefaultSpec.gib * RATES.crGibS),
      9
    );
    expect(m.firestore).toBeCloseTo(
      RATES.fsReadReq * 1e6 + RATES.fsWriteReq * 1e5,
      9
    );
    expect(m.gcs).toBeCloseTo(RATES.gcsA * 1e6 + RATES.gcsB * 1e6, 9);
    expect(m.logging).toBeCloseTo(RATES.logPerByte * 1e9, 9);
  });

  it("covers yesterday fully and today up to now minus the 5-minute lag", () => {
    // At 00:03 UTC the metered window ends 5 minutes earlier, at 23:58: yesterday
    // is not closed yet and today has no metered window at all.
    const early = at("2026-11-01", 0) + 3 * 60_000;
    expect(liveWindow("2026-10-31", early)!.fraction).toBeCloseTo(
      (DAY_MS - 2 * 60_000) / DAY_MS,
      9
    );
    expect(liveWindow("2026-11-01", early)).toBeNull();
    // At 00:06 yesterday closes (fraction 1) and today's window opens.
    const later = at("2026-11-01", 0) + 6 * 60_000;
    expect(liveWindow("2026-10-31", later)!.fraction).toBe(1);
    expect(liveWindow("2026-11-01", later)!.end).toBe(
      at("2026-11-01", 0) + 60_000
    );
    const noon = liveWindow("2026-11-01", at("2026-11-01", 6));
    expect(noon!.end).toBe(at("2026-11-01", 6) - 5 * 60_000);
  });

  it("merges a run into the document, replacing a day and pruning old days", () => {
    const now = at("2026-11-02", 1);
    const stale = liveDay(
      shift("2026-11-02", -(LIVE_KEEP_DAYS + 2)),
      1,
      now,
      1
    );
    const old = liveDay("2026-10-31", 1, now, 1);
    const merged = mergeLiveDoc(
      { days: { [old.date]: old, [stale.date]: stale } },
      [liveDay("2026-10-31", 1, now, 9)],
      now
    );
    expect(Object.keys(merged.days)).toEqual(["2026-10-31"]);
    expect(merged.days["2026-10-31"].metered.cloudRun).toBe(9);
  });

  it("parses only well-formed stored days", () => {
    const good = liveDay("2026-10-31", 1, at("2026-11-01", 0), 1);
    const parsed = parseLiveDoc({
      days: { "2026-10-31": good, "2026-10-30": { date: "2026-10-30" } },
    });
    expect(Object.keys(parsed!.days)).toEqual(["2026-10-31"]);
    expect(parseLiveDoc("not a doc")).toBeNull();
  });
});

describe("sonioxRate7d: the measured trailing rate replaces the console constant", () => {
  const bal = (spend: Record<string, number | null>): SonioxBalanceInputs => ({
    ready: true,
    firstDay: "2026-10-01",
    lastDay: "2026-10-31",
    asOf: "2026-10-31",
    spend,
    flags: {},
  });

  it("averages the last 7 measured days, skipping a reset day", () => {
    const spend: Record<string, number | null> = {};
    for (let i = 1; i <= 10; i++) spend[shift("2026-10-31", -10 + i)] = i * 10;
    spend["2026-10-31"] = null; // baseline reset: not $0
    const rate = sonioxRate7d(bal(spend), "2026-10-31");
    const values = Object.keys(spend)
      .filter((d) => d <= "2026-10-31" && spend[d] != null)
      .sort()
      .slice(-7)
      .map((d) => spend[d] as number);
    expect(rate).toBeCloseTo(values.reduce((s, v) => s + v, 0) / 7, 9);
    expect(rate).not.toBeNull();
  });

  it("is null with fewer than 7 measured days (the dated constant stays the last rung)", () => {
    expect(
      sonioxRate7d(bal({ "2026-10-30": 100, "2026-10-31": 100 }), "2026-10-31")
    ).toBeNull();
    expect(sonioxRate7d(undefined, "2026-10-31")).toBeNull();
  });
});

describe("reconcileLive at D+2: the live estimate against the settled cutoff", () => {
  it("computes variance as the live margin minus the settled margin, in points", () => {
    const cutoff = "2026-10-30";
    const settled = settledDays(cutoff, 7);
    const mrr = () => 60_000;
    const doc: LiveDoc = { days: {} };
    for (const d of settled)
      doc.days[d.date] = liveDay(d.date, 1, at(shift(d.date, 1), 0), 0);
    const r = reconcileLive(settled, doc, cutoff, null, mrr);
    expect(r.through).toBe(cutoff);
    expect(r.livePct).not.toBeNull();
    expect(r.settledPct).not.toBeNull();
    expect(r.variancePp).toBeCloseTo(
      (r.livePct as number) - (r.settledPct as number),
      9
    );
  });

  it("has no variance when any day of the window lacks a stored live value", () => {
    const cutoff = "2026-10-30";
    const settled = settledDays(cutoff, 7);
    const doc: LiveDoc = {
      days: { [cutoff]: liveDay(cutoff, 1, at("2026-10-31", 0), 0) },
    };
    const r = reconcileLive(settled, doc, cutoff, null, () => 60_000);
    expect(r.livePct).toBeNull();
    expect(r.variancePp).toBeNull();
  });
});

describe("margin scope: dev GCP out, Modulate at cash, OpenRouter in", () => {
  it("prices a day with dev excluded, Modulate cash and the OpenRouter estimate", () => {
    const day = allInCost(
      [billingDay("2026-10-30", 1_000, 300)],
      { openai: true, anthropic: true },
      { sttCash: { "2026-10-30": { modulate: 57 } } }
    ).daily[0];
    const v = variableCostDay(day);
    expect(day.gcpDev).toBe(300);
    expect(v.gcp).toBeCloseTo(1_000 - 300, 6); // the dev net is out of GCP
    expect(v.modulate).toBe(57); // Mercury cash, not the modelled line
    expect(v.openrouter).toBe(OPENROUTER_DAILY_USD);
    expect(v.gcpDev).toBe(300); // still visible on its own line
    expect(v.missing).not.toContain("Modulate");
  });

  it("names a day with no Modulate cash row instead of pricing it at $0", () => {
    const day = allInCost(
      [billingDay("2026-10-30", 1_000)],
      { openai: true },
      {}
    ).daily[0];
    expect(variableCostDay(day).missing).toContain("Modulate");
  });

  it("the live headline window uses the spliced days and the book on or before each day", () => {
    const settled = settledDays("2026-10-30", 7);
    const base = trailingMean(settled)!;
    const now = at("2026-11-01", 6);
    const doc: LiveDoc = {
      days: {
        "2026-10-31": liveDay("2026-10-31", 1, now - 60_000, 10),
        "2026-11-01": liveDay("2026-11-01", 6 / 24, now - 60_000, 10),
      },
    };
    const spliced = [...settled, ...liveCostDays(doc, base, now, null)];
    const points = variableMarginSeries(spliced, () => 60_000, {});
    expect(points.at(-1)!.date).toBe("2026-11-01");
    expect(points.at(-1)!.marginPct).not.toBeNull();
  });
});
