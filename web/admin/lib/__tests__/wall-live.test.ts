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
  estimatedServices,
  meteredUsd,
  parseLiveDoc,
} from "../wall-live";
import {
  liveCostDay,
  liveCostDays,
  liveDayStates,
  liveUntilGap,
  reconcileLive,
  spliceCostDays,
  trailingMean,
} from "../wall-live-margin";
import RATES from "../omi-tv-live-rates.json";
import { buildLiveWrite, liveDocFromRows } from "../wall-live-bq";

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
    runAt: new Date(now).toISOString(),
    days: Object.fromEntries(days.map((d) => [d.date, d])),
  });

  it("uses yesterday (closed) and today (partial, fresh, past 2 hours)", () => {
    const today = liveDay("2026-11-01", 6 / 24, now - 60_000, 10);
    const yesterday = liveDay("2026-10-31", 1, now - 60_000, 10);
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
      seen: { cloudRun: true, firestore: true, gcs: true, logging: true },
    });
    const backend = RATES.crSpecs.backend;
    if (!m) throw new Error("all families seen: metering must return");
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
      runAt: new Date(now).toISOString(),
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

describe("Luna r1 fixes: unavailable metering, pricing flags, trailing basis, dev, freshness, midnight", () => {
  const seenAll = { cloudRun: true, firestore: true, gcs: true, logging: true };
  const q = (over: Partial<Parameters<typeof meteredUsd>[0]> = {}) => ({
    crInstanceSeconds: { backend: 1000 },
    fsReads: 1,
    fsWrites: 1,
    gcsA: 1,
    gcsB: 1,
    logBytes: 1,
    seen: seenAll,
    ...over,
  });

  it("an empty Monitoring series is unavailable, never a $0 reading", () => {
    expect(meteredUsd(q({ seen: { ...seenAll, cloudRun: false } }))).toBeNull();
    expect(
      meteredUsd(q({ seen: { ...seenAll, firestore: false } }))
    ).toBeNull();
    expect(meteredUsd(q({ seen: { ...seenAll, logging: false } }))).toBeNull();
    expect(meteredUsd(q())).not.toBeNull();
  });

  it("names unmapped Cloud Run services as estimated instead of pricing them silently", () => {
    expect(
      estimatedServices(
        q({ crInstanceSeconds: { backend: 1, "no-such-svc": 1 } })
      )
    ).toEqual(["no-such-svc"]);
    expect(estimatedServices(q())).toEqual([]);
  });

  it("a $399 cash top-up on one of seven days is about $57/day, not $399/day", () => {
    const days = settledDays("2026-10-30", 7).map((d, i) => ({
      ...d,
      modulateCashUsd: i === 3 ? 399 : 0,
    }));
    const base = trailingMean(days)!;
    expect(base.modulateCashUsd).toBeCloseTo(399 / 7, 6);
  });

  it("live days keep the trailing settled dev rate on the dev line, and dev stays out of margin", () => {
    const base = trailingMean(settledDays("2026-10-30", 7))!;
    const live = liveCostDay(
      liveDay("2026-10-31", 1, Date.now(), 10),
      base,
      500
    );
    expect(live.gcpDev).toBeCloseTo(base.gcpDev, 6);
    expect(live.gcpDev).toBeGreaterThan(0);
    const scope = variableCostDay(live);
    expect(scope.gcpDev).toBeCloseTo(base.gcpDev, 6);
    // Dev is added into live gcp and removed again by the margin, so margin
    // GCP equals the metered prod window only.
    expect(scope.gcp).toBeCloseTo(
      live.gcp - base.gcpDev + live.vertexLlm - live.vertexReserved,
      6
    );
  });

  it("a closed day whose own row is older than the staleness limit is stale, even when another row is fresh", () => {
    const now = at("2026-11-01", 6);
    const yesterdayOld = liveDay("2026-10-31", 1, now - 3 * 3_600_000, 10);
    const todayFresh = liveDay("2026-11-01", 6 / 24, now, 10);
    const doc: LiveDoc = {
      runAt: new Date(now).toISOString(),
      days: {
        [yesterdayOld.date]: yesterdayOld,
        [todayFresh.date]: todayFresh,
      },
    };
    const base = trailingMean(settledDays("2026-10-30", 7));
    const used = liveCostDays(doc, base, now, 500).map((d) => d.date);
    expect(used).toEqual(["2026-11-01"]);
    const states = liveDayStates(doc, now);
    expect(states.find((s) => s.date === "2026-10-31")!.state).toBe("stale");
    expect(states.find((s) => s.date === "2026-11-01")!.state).toBe("fresh");
  });

  it("a day the producer did not supply cuts the live days after it (no window across a hole)", () => {
    const settled = settledDays("2026-10-28", 14); // settled ends D-4 here
    const d2 = liveDay("2026-10-30", 1, at("2026-11-01"), 10);
    const today = liveDay("2026-11-01", 1, at("2026-11-01"), 10);
    const base = trailingMean(settled.slice(-7))!;
    const now = at("2026-11-01", 6);
    const live = liveCostDays(
      {
        runAt: new Date(now).toISOString(),
        days: { [d2.date]: d2, [today.date]: today },
      },
      base,
      now,
      500,
      "2026-10-28"
    );
    // 10-29 is missing from both sources: nothing after it is used.
    expect(liveUntilGap("2026-10-28", live)).toEqual([]);
    const withD29 = liveCostDays(
      {
        runAt: new Date(now).toISOString(),
        days: {
          "2026-10-29": liveDay("2026-10-29", 1, at("2026-11-01"), 10),
          [d2.date]: d2,
          [today.date]: today,
        },
      },
      base,
      now,
      500,
      "2026-10-28"
    );
    // 10-31 is missing from both, so today (11-01) is cut off behind it.
    expect(liveUntilGap("2026-10-28", withD29).map((d) => d.date)).toEqual([
      "2026-10-29",
      "2026-10-30",
    ]);
  });

  it("settled ending at D-3 with live D-2 and D-1: no day falls in neither source", () => {
    const settled = settledDays("2026-10-29", 14); // billing newest day is D-3
    const now = at("2026-11-01", 6);
    const doc: LiveDoc = {
      runAt: new Date(now).toISOString(),
      days: {
        "2026-10-30": liveDay("2026-10-30", 1, now, 10),
        "2026-10-31": liveDay("2026-10-31", 1, now, 10),
      },
    };
    const live = liveCostDays(
      doc,
      trailingMean(settled.slice(-7)),
      now,
      500,
      "2026-10-29"
    );
    const spliced = spliceCostDays(settled, live, "2026-10-29");
    const dates = spliced.map((d) => d.date);
    for (let i = 1; i < dates.length; i++)
      expect(shift(dates[i - 1], 1)).toBe(dates[i]);
    expect(dates.at(-1)).toBe("2026-10-31");
  });
});

describe("liveDayStates: the status names stale and missing live days", () => {
  it("a closed day the producer skipped reads missing, a partial day with an old value reads stale", () => {
    const now = at("2026-11-01", 6);
    const doc: LiveDoc = {
      runAt: new Date(now).toISOString(),
      days: {
        "2026-11-01": liveDay("2026-11-01", 6 / 24, now - 3_600_000, 10),
      },
    };
    const states = liveDayStates(doc, now);
    expect(states.find((s) => s.date === "2026-10-31")!.state).toBe("missing");
    expect(states.find((s) => s.date === "2026-11-01")!.state).toBe("stale");
  });
});

describe("BigQuery live rows (item 9): write and read map one to one", () => {
  it("builds one parameterised transaction per produced day plus a prune, with no interpolated values", () => {
    const now = at("2026-11-02", 6);
    const day = liveDay("2026-11-01", 1, now, 10);
    const { query, params } = buildLiveWrite(
      [{ ...day, estimated: ["x-svc"] }],
      new Date(now),
      "2026-10-19"
    );
    expect(query).toContain("BEGIN TRANSACTION");
    expect(query).toContain("COMMIT TRANSACTION");
    expect(query).toContain("based-hardware.omi_tv.live_day");
    expect(query).not.toContain("2026-11-01"); // values travel as parameters
    expect(params.d0).toBeDefined();
    expect(params.e0).toBe("x-svc");
  });

  it("rebuilds the document from rows: runAt is the latest run, malformed rows are dropped", () => {
    const now = at("2026-11-02", 6);
    const rows = [
      {
        day: "2026-11-01",
        produced_at: { value: new Date(now - 60_000).toISOString() },
        run_at: { value: new Date(now - 60_000).toISOString() },
        query_end: { value: new Date(at("2026-11-02", 0)).toISOString() },
        fraction: 1,
        cloud_run_usd: 10,
        firestore_usd: 1,
        gcs_usd: 1,
        logging_usd: 1,
        estimated_services: "a,b",
      },
      {
        day: "2026-11-02",
        produced_at: "x",
        run_at: "x",
        query_end: "x",
        fraction: 1,
        cloud_run_usd: NaN,
        firestore_usd: 1,
        gcs_usd: 1,
        logging_usd: 1,
        estimated_services: "",
      },
    ];
    const doc = liveDocFromRows(rows);
    expect(Object.keys(doc.days)).toEqual(["2026-11-01"]);
    expect(doc.days["2026-11-01"].estimated).toEqual(["a", "b"]);
    expect(doc.runAt).toBe(new Date(now - 60_000).toISOString());
  });

  it("request-billed backfill is estimated on the tile even though it has a size", () => {
    expect(
      estimatedServices({
        crInstanceSeconds: { "backend-sync-backfill": 1, backend: 1 },
        fsReads: 0,
        fsWrites: 0,
        gcsA: 0,
        gcsB: 0,
        logBytes: 0,
        seen: { cloudRun: true, firestore: true, gcs: true, logging: true },
      })
    ).toEqual(["backend-sync-backfill"]);
  });
});
