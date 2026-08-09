"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { IBM_Plex_Mono, IBM_Plex_Sans } from "next/font/google";
import type { SeriesPoint, TvSnapshot, WindowHours } from "@/lib/tv-snapshot";

const plexSans = IBM_Plex_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  display: "swap",
});
const plexMono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  display: "swap",
});

const PLAT_COLORS: Record<string, string> = {
  macos: "#8eb4e0",
  windows: "#a89fd4",
  ios: "#7eb8b0",
  android: "#d4a574",
};
const PLAT_LABEL: Record<string, string> = {
  macos: "Mac",
  windows: "Win",
  ios: "iOS",
  android: "Android",
};
const PLATS = ["macos", "windows", "ios", "android"] as const;
const WINDOW_LABEL: Record<number, string> = { 12: "12h", 24: "1d", 72: "3d" };
const PIE_COLORS = ["#d4a574", "#7eb8b0", "#8eb4e0", "#d4b45a", "#d48890", "#8b93a3", "#a89fd4"];

type Props = {
  getToken: () => Promise<string | null>;
  kioskLabel?: string;
  pollMs?: number;
};

function fmt(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return "—";
  const n = Number(v);
  if (Math.abs(n) >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (Math.abs(n) >= 10_000) return `${Math.round(n / 1000)}k`;
  if (Number.isInteger(n) || Math.abs(n) >= 100) return Math.round(n).toLocaleString();
  return (Math.round(n * 10) / 10).toLocaleString();
}

function fmtMoney(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return "—";
  const n = Number(v);
  const abs = Math.abs(n);
  const sign = n < 0 ? "-" : "";
  if (abs >= 1_000_000) return `${sign}$${(abs / 1_000_000).toFixed(2)}M`;
  if (abs >= 10_000) return `${sign}$${Math.round(abs / 1000)}k`;
  if (abs >= 1000) return `${sign}$${(abs / 1000).toFixed(1)}k`;
  return `${sign}$${Math.round(abs).toLocaleString()}`;
}

function shortProduct(name: string): string {
  return (
    name
      .replace(/^Omi\s+/i, "")
      .replace(/\s+Monthly (Plan|Subscription)$/i, "")
      .replace(/\s+v2$/i, " v2") || "—"
  );
}

function ageLabel(iso?: string): string {
  if (!iso) return "no data";
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return iso;
  const sec = Math.max(0, Math.round((Date.now() - t) / 1000));
  if (sec < 60) return `updated ${sec}s ago`;
  if (sec < 3600) return `updated ${Math.round(sec / 60)}m ago`;
  return `updated ${Math.round(sec / 3600)}h ago`;
}

function sliceSeries(series: SeriesPoint[], hours: number): SeriesPoint[] {
  if (!series?.length) return [];
  const cut = Date.now() / 1000 - hours * 3600;
  return series.filter((p) => p.t >= cut);
}

function downsample(series: SeriesPoint[], max = 42): SeriesPoint[] {
  if (series.length <= max) return series;
  const out: SeriesPoint[] = [];
  const step = (series.length - 1) / (max - 1);
  for (let i = 0; i < max; i++) out.push(series[Math.round(i * step)]);
  return out;
}

/** Index each series to its first positive value (= 1.0) so left edges align. */
function indexToStart(values: Array<number | null | undefined>): Array<number | null> {
  let base: number | null = null;
  for (const v of values) {
    if (v == null || !Number.isFinite(Number(v)) || Number(v) <= 0) continue;
    base = Number(v);
    break;
  }
  if (base == null) return values.map(() => null);
  return values.map((v) => {
    if (v == null || !Number.isFinite(Number(v))) return null;
    return Number(v) / base!;
  });
}

function seriesStats(values: Array<number | null | undefined>): {
  latest: number | null;
  peak: number | null;
  trough: number | null;
} {
  const nums = values
    .map((v) => (v == null || !Number.isFinite(Number(v)) ? null : Number(v)))
    .filter((v): v is number => v != null);
  if (!nums.length) return { latest: null, peak: null, trough: null };
  let latest: number | null = null;
  for (let i = values.length - 1; i >= 0; i--) {
    const v = values[i];
    if (v != null && Number.isFinite(Number(v))) {
      latest = Number(v);
      break;
    }
  }
  return {
    latest,
    peak: Math.max(...nums),
    trough: Math.min(...nums),
  };
}

function shortTime(t: number, hours: number): string {
  const d = new Date(t * 1000);
  if (hours <= 24) {
    return d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  }
  return d.toLocaleString([], { month: "short", day: "numeric", hour: "numeric" });
}

type BuiltChart = {
  data: Array<Record<string, number | string | null>>;
  activeKeys: string[];
  stats: Record<string, { latest: number | null; peak: number | null; trough: number | null }>;
};

function buildIndexedChart(series: SeriesPoint[], hours: number): BuiltChart {
  const sliced = downsample(sliceSeries(series, hours));
  const rawByKey: Record<string, Array<number | null>> = {};
  for (const k of PLATS) rawByKey[k] = sliced.map((p) => {
    const v = p[k];
    return v == null || !Number.isFinite(Number(v)) ? null : Number(v);
  });

  const stats: BuiltChart["stats"] = {};
  const indexed: Record<string, Array<number | null>> = {};
  const activeKeys: string[] = [];
  for (const k of PLATS) {
    stats[k] = seriesStats(rawByKey[k]);
    const has = rawByKey[k].some((v) => v != null && v > 0);
    if (!has) continue;
    activeKeys.push(k);
    indexed[k] = indexToStart(rawByKey[k]);
  }

  const data = sliced.map((p, i) => {
    const row: Record<string, number | string | null> = {
      t: p.t,
      label: shortTime(p.t, hours),
    };
    for (const k of activeKeys) {
      row[k] = indexed[k][i];
      row[`${k}_raw`] = rawByKey[k][i];
    }
    return row;
  });

  return { data, activeKeys, stats };
}

function MultiLineChart({
  series,
  hours,
}: {
  series: SeriesPoint[];
  hours: number;
}) {
  const { data, activeKeys, stats } = useMemo(
    () => buildIndexedChart(series, hours),
    [series, hours],
  );

  if (data.length < 2 || !activeKeys.length) {
    return <div className="tv-empty">No trend yet</div>;
  }

  // Tight Y domain around indexed series so small relative moves are visible
  const allIdx = data.flatMap((row) =>
    activeKeys
      .map((k) => row[k])
      .filter((v): v is number => typeof v === "number" && Number.isFinite(v)),
  );
  let yMin = Math.min(...allIdx);
  let yMax = Math.max(...allIdx);
  if (yMin === yMax) {
    yMin = Math.max(0, yMin - 0.05);
    yMax = yMax + 0.05;
  } else {
    const pad = (yMax - yMin) * 0.2;
    yMin = Math.max(0, yMin - pad);
    yMax = yMax + pad;
  }

  return (
    <div className="tv-chart-wrap">
      <div className="tv-chart-main">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid stroke="rgba(255,255,255,0.045)" vertical={false} />
            <XAxis
              dataKey="label"
              tick={{ fill: "#6b7382", fontSize: 10, fontFamily: plexMono.style.fontFamily }}
              tickLine={false}
              axisLine={false}
              minTickGap={28}
              interval="preserveStartEnd"
            />
            <YAxis
              domain={[yMin, yMax]}
              width={36}
              tick={{ fill: "#6b7382", fontSize: 10, fontFamily: plexMono.style.fontFamily }}
              tickLine={false}
              axisLine={false}
              tickFormatter={(v: number) => `${Math.round(v * 100)}%`}
            />
            <Tooltip
              contentStyle={{
                background: "#14161c",
                border: "1px solid rgba(255,255,255,0.1)",
                borderRadius: 6,
                fontSize: 11,
                fontFamily: plexMono.style.fontFamily,
              }}
              labelStyle={{ color: "#9aa3b2" }}
              formatter={(value: number, name: string, item) => {
                const raw = item?.payload?.[`${name}_raw`];
                const pct = value == null ? "—" : `${Math.round(value * 100)}% of start`;
                const abs = raw == null ? "" : ` · now ${fmt(Number(raw))}`;
                return [`${pct}${abs}`, PLAT_LABEL[name] || name];
              }}
            />
            {activeKeys.map((k) => (
              <Line
                key={k}
                type="monotone"
                dataKey={k}
                name={k}
                stroke={PLAT_COLORS[k]}
                strokeWidth={1.7}
                dot={false}
                isAnimationActive={false}
                connectNulls
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
      <div className="tv-end-labels">
        {activeKeys.map((k) => (
          <span key={k} style={{ color: PLAT_COLORS[k] }}>
            {PLAT_LABEL[k]} {fmt(stats[k]?.latest)}
          </span>
        ))}
      </div>
    </div>
  );
}

function SingleLineChart({
  series,
  hours,
  color = "#c5cdd8",
}: {
  series: SeriesPoint[];
  hours: number;
  color?: string;
}) {
  const data = useMemo(() => {
    return downsample(sliceSeries(series, hours)).map((p) => ({
      t: p.t,
      label: shortTime(p.t, hours),
      v: p.v ?? p.total ?? null,
    }));
  }, [series, hours]);

  if (data.length < 2) return <div className="tv-empty">No trend yet</div>;

  const nums = data.map((d) => d.v).filter((v): v is number => v != null);
  let yMin = Math.min(...nums);
  let yMax = Math.max(...nums);
  const pad = yMin === yMax ? Math.max(1, Math.abs(yMin) * 0.05) : (yMax - yMin) * 0.15;
  yMin = Math.max(0, yMin - pad);
  yMax = yMax + pad;

  return (
    <ResponsiveContainer width="100%" height="100%">
      <LineChart data={data} margin={{ top: 8, right: 4, left: 0, bottom: 0 }}>
        <CartesianGrid stroke="rgba(255,255,255,0.045)" vertical={false} />
        <XAxis
          dataKey="label"
          tick={{ fill: "#6b7382", fontSize: 10, fontFamily: plexMono.style.fontFamily }}
          tickLine={false}
          axisLine={false}
          minTickGap={32}
          interval="preserveStartEnd"
        />
        <YAxis
          domain={[yMin, yMax]}
          width={40}
          tick={{ fill: "#6b7382", fontSize: 10, fontFamily: plexMono.style.fontFamily }}
          tickLine={false}
          axisLine={false}
          tickFormatter={(v: number) => fmt(v)}
        />
        <Tooltip
          contentStyle={{
            background: "#14161c",
            border: "1px solid rgba(255,255,255,0.1)",
            borderRadius: 6,
            fontSize: 11,
            fontFamily: plexMono.style.fontFamily,
          }}
          formatter={(value: number) => [fmt(value), ""]}
        />
        <Line
          type="monotone"
          dataKey="v"
          stroke={color}
          strokeWidth={1.7}
          dot={false}
          isAnimationActive={false}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}

function PlatStats({
  platforms,
  hoursKey,
  series,
  hours,
}: {
  platforms: Record<string, number | null | Record<string, number | null>>;
  hoursKey: string;
  series: SeriesPoint[];
  hours: number;
}) {
  const built = useMemo(() => buildIndexedChart(series, hours), [series, hours]);

  return (
    <div className="tv-plat">
      {PLATS.map((p) => {
        const raw = platforms[p];
        const windowVal =
          raw == null
            ? null
            : typeof raw === "number"
              ? raw
              : (raw as Record<string, number | null>)[hoursKey];
        const st = built.stats[p];
        // Prefer window total if present; else series latest
        const latest = windowVal != null ? windowVal : st?.latest ?? null;
        if (latest == null && st?.peak == null) return null;
        return (
          <span key={p} className="tv-plat-item">
            <i style={{ background: PLAT_COLORS[p] }} />
            <b className="tv-plat-name">{PLAT_LABEL[p]}</b>
            <b className="tv-plat-now">{fmt(latest)}</b>
            {st?.peak != null && st?.trough != null ? (
              <em className="tv-plat-range">
                ↑{fmt(st.peak)} ↓{fmt(st.trough)}
              </em>
            ) : null}
          </span>
        );
      })}
    </div>
  );
}

function TvClock() {
  return <TvClock />;
}

export function TvBoard({
  getToken,
  kioskLabel,
  pollMs = 60_000,
}: Props) {
  const [snap, setSnap] = useState<TvSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [hours, setHours] = useState<WindowHours>(72);
  const hk = String(hours);

  const load = useCallback(async () => {
    try {
      const token = await getToken();
      if (!token) {
        setError("Missing auth token");
        return;
      }
      const res = await fetch("/api/tv/snapshot", {
        headers: { Authorization: `Bearer ${token}` },
        cache: "no-store",
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.error || `HTTP ${res.status}`);
      }
      setSnap((await res.json()) as TvSnapshot);
      setError(null);
    } catch (e) {
      setSnap(null);
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [getToken]);

  useEffect(() => {
    void load();
    const id = setInterval(() => void load(), pollMs);
    return () => clearInterval(id);
  }, [load, pollMs]);

  const a = snap?.activity;
  const actSlot = a?.byHours?.[hk];
  const conv = snap?.features?.conversation;
  const chat = snap?.features?.chat;
  const mem = snap?.features?.memories;
  const m = snap?.million;
  const r = snap?.revenue;

  const products = useMemo(() => {
    const all = (r?.byProduct || [])
      .map((p) => ({
        name: shortProduct(p.name),
        arr: p.arr,
        subs: p.subscriptions,
      }))
      .filter((p) => p.arr > 0)
      .sort((x, y) => y.arr - x.arr);
    const restArr = all.slice(5).reduce((s, p) => s + p.arr, 0);
    const restSubs = all.slice(5).reduce((s, p) => s + p.subs, 0);
    const top = all.slice(0, 5);
    if (restArr > 0) top.push({ name: "Other", arr: restArr, subs: restSubs });
    return top;
  }, [r?.byProduct]);
  const maxArr = products[0]?.arr || 1;
  const sumArr = products.reduce((s, p) => s + p.arr, 0) || 1;
  const pieData = products.map((p) => ({ name: p.name, value: p.arr }));

  const live = !snap ? "down" : snap.partial || error ? "stale" : "";
  const wlabel = WINDOW_LABEL[hours];

  const stickiness =
    a?.wau && actSlot?.total
      ? Math.round((Number(actSlot.total) / a.wau) * 1000) / 10
      : null;

  return (
    <div className={`tv-shell ${plexSans.className}`}>
      <style>{`
        .tv-shell {
          --bg:#0c0d10; --panel:#14161c; --line:rgba(255,255,255,.08);
          --ink:#f2f3f5; --muted:#9aa3b2; --dim:#6b7382;
          --ok:#5bb98c; --warn:#d4b45a; --bad:#d48890;
          --gap:.45vw; --radius:.35vw;
          --fs-lead:3.4vw; --fs-hero:2.6vw; --fs-stat:1.65vw;
          --fs-label:.78vw; --fs-chip:.82vw; --fs-fine:.7vw;
          color:var(--ink); background:var(--bg);
          height:100vh; width:100vw; overflow:hidden;
          display:grid; grid-template-rows:auto 1fr auto;
          -webkit-font-smoothing:antialiased;
          font-family:${plexSans.style.fontFamily}, system-ui, sans-serif;
        }
        .tv-shell *{box-sizing:border-box}
        .tv-mono{font-family:${plexMono.style.fontFamily}, ui-monospace, monospace}
        .tv-rail{display:flex;align-items:center;justify-content:space-between;gap:1vw;
          padding:.5vw 1vw .3vw;border-bottom:1px solid var(--line)}
        .tv-brand{display:flex;align-items:baseline;gap:.5vw}
        .tv-dot{width:.4vw;height:.4vw;min-width:7px;min-height:7px;border-radius:50%;
          background:var(--ok);align-self:center}
        .tv-dot.stale{background:var(--warn)}.tv-dot.down{background:var(--bad)}
        .tv-brand-name{font-size:1.1vw;font-weight:600;letter-spacing:-.02em}
        .tv-brand-sub{font-size:var(--fs-label);text-transform:uppercase;letter-spacing:.18em;color:var(--dim)}
        .tv-rail-right{display:flex;align-items:center;gap:.8vw}
        .tv-fresh,.tv-status{font-size:var(--fs-fine);color:var(--muted)}
        .tv-status{color:var(--warn);max-width:14vw;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
        .tv-clock{font-size:.95vw;font-weight:500;font-variant-numeric:tabular-nums}
        .tv-toggle{display:inline-flex;gap:.1vw}
        .tv-toggle button{appearance:none;border:0;background:transparent;color:var(--dim);
          font-size:var(--fs-fine);font-weight:500;letter-spacing:.04em;padding:.1vw .4vw;
          cursor:pointer;border-bottom:2px solid transparent;
          font-family:${plexMono.style.fontFamily}, monospace}
        .tv-toggle button.active{color:var(--ink);border-bottom-color:var(--ink)}
        .tv-chrome a{font-size:var(--fs-fine);color:var(--dim);text-decoration:none;
          border:1px solid var(--line);padding:.12vw .42vw;border-radius:999px}
        .tv-chrome a:hover{color:var(--ink)}
        .tv-board{display:grid;grid-template-columns:repeat(12,1fr);grid-template-rows:1.25fr 1fr 1fr;
          gap:var(--gap);padding:.35vw 1vw .28vw;min-height:0}
        .tv-panel{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);
          padding:.45vw .6vw .35vw;min-height:0;display:flex;flex-direction:column;overflow:hidden}
        .tv-panel h2{margin:0 0 .18vw;display:flex;align-items:baseline;gap:.4vw;font-weight:500;font-size:inherit}
        .tv-eyebrow{font-size:var(--fs-label);text-transform:uppercase;letter-spacing:.14em;color:var(--muted)}
        .tv-h2sub{font-size:var(--fs-fine);color:var(--dim);margin-left:auto;
          font-family:${plexMono.style.fontFamily}, monospace}
        .tv-body{flex:1;min-height:0;display:flex;flex-direction:column}
        .tv-stat-row{display:flex;align-items:flex-end;justify-content:space-between;gap:.5vw;flex:0 0 auto}
        .tv-stat{display:flex;flex-direction:column;gap:.06vw;min-width:0}
        .tv-value{font-family:${plexMono.style.fontFamily}, monospace;font-size:var(--fs-stat);
          font-weight:500;letter-spacing:-.03em;line-height:.95;font-variant-numeric:tabular-nums}
        .tv-lead .tv-value{font-size:var(--fs-lead)}
        .tv-hero .tv-value{font-size:var(--fs-hero)}
        .tv-caption{font-size:var(--fs-fine);text-transform:uppercase;letter-spacing:.1em;color:var(--muted)}
        .tv-side .tv-value{font-size:var(--fs-stat);color:var(--muted)}
        .tv-plat{display:flex;flex-wrap:wrap;gap:.15vw .55vw;margin-top:.15vw;font-size:var(--fs-chip);color:var(--muted)}
        .tv-plat-item{display:inline-flex;align-items:baseline;gap:.18vw}
        .tv-plat i{width:.4vw;height:.15vw;min-width:6px;min-height:2px;align-self:center;display:inline-block}
        .tv-plat-name{font-weight:500;color:var(--muted)}
        .tv-plat-now{font-family:${plexMono.style.fontFamily}, monospace;font-weight:600;color:var(--ink);font-variant-numeric:tabular-nums}
        .tv-plat-range{font-style:normal;font-family:${plexMono.style.fontFamily}, monospace;font-size:.72em;color:var(--dim);margin-left:.15em}
        .tv-chart{position:relative;flex:1 1 0;min-height:0;margin-top:.08vw}
        .tv-chart-wrap{height:100%;display:grid;grid-template-columns:1fr auto;gap:.25vw;min-height:0}
        .tv-chart-main{min-width:0;min-height:0}
        .tv-end-labels{display:flex;flex-direction:column;justify-content:center;gap:.2vw;
          font-family:${plexMono.style.fontFamily}, monospace;font-size:var(--fs-fine);font-weight:600;
          white-space:nowrap;padding-right:.1vw}
        .tv-empty{height:100%;display:grid;place-items:center;color:var(--dim);font-size:var(--fs-chip)}
        .tv-rev{flex:1;min-height:0;display:grid;grid-template-rows:auto 1fr auto;gap:.2vw}
        .tv-rev-head .tv-value{font-size:1.95vw}
        .tv-rev-mid{min-height:0;display:grid;grid-template-columns:1.05fr .95fr;gap:.35vw}
        .tv-rev-list{min-height:0;display:flex;flex-direction:column;justify-content:center;gap:.22vw;overflow:hidden}
        .tv-rev-row{display:grid;grid-template-columns:4.8vw 1fr 2.9vw;align-items:center;gap:.28vw;font-size:var(--fs-chip)}
        .tv-rev-row .name{color:var(--muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
        .tv-rev-row .bar{height:.34vw;min-height:4px;background:rgba(255,255,255,.06);overflow:hidden}
        .tv-rev-row .bar>i{display:block;height:100%}
        .tv-rev-row .amt{font-family:${plexMono.style.fontFamily}, monospace;font-weight:500;text-align:right;font-variant-numeric:tabular-nums}
        .tv-rev-row .pct{color:var(--dim);margin-left:.12em;font-size:.9em}
        .tv-pie{min-height:0;position:relative}
        .tv-pie-center{position:absolute;inset:0;display:grid;place-items:center;pointer-events:none;
          font-family:${plexMono.style.fontFamily}, monospace;font-size:.85vw;color:var(--muted);text-align:center;line-height:1.15}
        .tv-pie-center b{display:block;color:var(--ink);font-size:1.05vw;font-weight:500}
        .tv-foot{display:flex;justify-content:space-between;align-items:center;gap:1vw;
          padding:.28vw 1vw .4vw;border-top:1px solid var(--line)}
        .tv-warn{font-size:var(--fs-fine);color:var(--warn);max-width:70%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;
          font-family:${plexMono.style.fontFamily}, monospace}
        .tv-hint{font-size:var(--fs-fine);color:var(--dim);text-transform:uppercase;letter-spacing:.12em}
        #p-dau{grid-column:1/7;grid-row:1}
        #p-mem{grid-column:7/10;grid-row:1}
        #p-rev{grid-column:10/13;grid-row:1/3}
        #p-conv{grid-column:1/5;grid-row:2}
        #p-chat{grid-column:5/10;grid-row:2}
        #p-mil{grid-column:1/8;grid-row:3}
        #p-stick{grid-column:8/13;grid-row:3}
        @media (max-width:1100px){
          .tv-shell{height:auto;min-height:100vh;overflow:auto;
            --fs-lead:2.1rem;--fs-hero:1.7rem;--fs-stat:1.15rem;--fs-label:.65rem;--fs-chip:.7rem;--fs-fine:.62rem;--gap:.5rem;--radius:.4rem}
          .tv-board{grid-template-columns:1fr 1fr;grid-template-rows:auto}
          .tv-panel{grid-column:auto!important;grid-row:auto!important;min-height:14rem}
          #p-dau,#p-mil,#p-rev{grid-column:1/-1!important}
          .tv-rev-mid{grid-template-columns:1fr}
        }
      `}</style>

      <header className="tv-rail">
        <div className="tv-brand">
          <span className={`tv-dot ${live}`} />
          <span className="tv-brand-name">omi</span>
          <span className="tv-brand-sub">
            {kioskLabel ? `${kioskLabel} · ` : ""}product pulse
          </span>
        </div>
        <div className="tv-rail-right">
          {error ? <span className="tv-status">{error}</span> : null}
          {snap?.partial ? (
            <span className="tv-status">{snap.warnings?.[0] || "partial sources"}</span>
          ) : null}
          <span className="tv-fresh tv-mono">{ageLabel(snap?.generatedAt)}</span>
          <div className="tv-toggle" role="group" aria-label="Time window">
            {([12, 24, 72] as WindowHours[]).map((h) => (
              <button
                key={h}
                type="button"
                className={hours === h ? "active" : ""}
                onClick={() => setHours(h)}
              >
                {WINDOW_LABEL[h]}
              </button>
            ))}
          </div>
          <TvClock />
        </div>
      </header>

      <main className="tv-board">
        <section className="tv-panel tv-lead" id="p-dau">
          <h2>
            <span className="tv-eyebrow">Active users</span>
            <span className="tv-h2sub">{wlabel}</span>
          </h2>
          <div className="tv-body">
            <div className="tv-stat-row">
              <div className="tv-stat">
                <div className="tv-value">{fmt(actSlot?.total)}</div>
                <div className="tv-caption">active users · {wlabel}</div>
              </div>
              <div className="tv-side">
                <div className="tv-stat">
                  <div className="tv-value">{fmt(a?.wau)}</div>
                  <div className="tv-caption">weekly active</div>
                </div>
              </div>
            </div>
            <PlatStats
              platforms={actSlot?.platforms || {}}
              hoursKey={hk}
              series={a?.series || []}
              hours={hours}
            />
            <div className="tv-chart">
              <MultiLineChart series={a?.series || []} hours={hours} />
            </div>
          </div>
        </section>

        <section className="tv-panel tv-hero" id="p-mem">
          <h2>
            <span className="tv-eyebrow">Memories created</span>
            <span className="tv-h2sub">{wlabel}</span>
          </h2>
          <div className="tv-body">
            <div className="tv-stat-row">
              <div className="tv-stat">
                <div className="tv-value">{fmt(mem?.byHours?.[hk])}</div>
                <div className="tv-caption">events · {wlabel}</div>
              </div>
            </div>
            <PlatStats
              platforms={mem?.platforms || {}}
              hoursKey={hk}
              series={mem?.series || []}
              hours={hours}
            />
            <div className="tv-chart">
              <MultiLineChart series={mem?.series || []} hours={hours} />
            </div>
          </div>
        </section>

        <section className="tv-panel" id="p-rev">
          <h2>
            <span className="tv-eyebrow">Annual recurring revenue</span>
            <span className="tv-h2sub">Stripe</span>
          </h2>
          <div className="tv-body">
            {!r ? (
              <div className="tv-empty">Revenue hidden</div>
            ) : r.unavailable ? (
              <div className="tv-empty">Stripe not configured</div>
            ) : (
              <div className="tv-rev">
                <div className="tv-rev-head">
                  <div className="tv-value">{fmtMoney(r.arr)}</div>
                  <div className="tv-caption">
                    {fmt(r.subscriptionCount)} subscriptions · MRR {fmtMoney(r.mrr)}
                  </div>
                </div>
                <div className="tv-rev-mid">
                  <div className="tv-rev-list">
                    {products.map((p, i) => {
                      const w = Math.max(2, Math.round((p.arr / maxArr) * 100));
                      const pct = Math.round((p.arr / sumArr) * 100);
                      return (
                        <div className="tv-rev-row" key={p.name}>
                          <span className="name">{p.name}</span>
                          <span className="bar">
                            <i
                              style={{
                                width: `${w}%`,
                                background: PIE_COLORS[i % PIE_COLORS.length],
                              }}
                            />
                          </span>
                          <span className="amt">
                            {fmtMoney(p.arr)}
                            <span className="pct">{pct}%</span>
                          </span>
                        </div>
                      );
                    })}
                  </div>
                  <div className="tv-pie">
                    <ResponsiveContainer width="100%" height="100%">
                      <PieChart>
                        <Pie
                          data={pieData}
                          dataKey="value"
                          nameKey="name"
                          innerRadius="58%"
                          outerRadius="88%"
                          paddingAngle={1.5}
                          stroke="rgba(12,13,16,0.6)"
                          strokeWidth={1}
                          isAnimationActive={false}
                        >
                          {pieData.map((_, i) => (
                            <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                          ))}
                        </Pie>
                        <Tooltip
                          contentStyle={{
                            background: "#14161c",
                            border: "1px solid rgba(255,255,255,0.1)",
                            borderRadius: 6,
                            fontSize: 11,
                            fontFamily: plexMono.style.fontFamily,
                          }}
                          formatter={(value: number, name: string) => [
                            fmtMoney(value),
                            name,
                          ]}
                        />
                      </PieChart>
                    </ResponsiveContainer>
                    <div className="tv-pie-center">
                      <span>
                        <b>{fmtMoney(r.arr)}</b>
                        ARR mix
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>
        </section>

        <section className="tv-panel tv-hero" id="p-conv">
          <h2>
            <span className="tv-eyebrow">Conversations</span>
            <span className="tv-h2sub">{wlabel}</span>
          </h2>
          <div className="tv-body">
            <div className="tv-stat-row">
              <div className="tv-stat">
                <div className="tv-value">{fmt(conv?.byHours?.[hk])}</div>
                <div className="tv-caption">users starting rec · {wlabel}</div>
              </div>
            </div>
            <PlatStats
              platforms={conv?.platforms || {}}
              hoursKey={hk}
              series={conv?.series || []}
              hours={hours}
            />
            <div className="tv-chart">
              <MultiLineChart series={conv?.series || []} hours={hours} />
            </div>
          </div>
        </section>

        <section className="tv-panel tv-hero" id="p-chat">
          <h2>
            <span className="tv-eyebrow">Chat</span>
            <span className="tv-h2sub">{wlabel}</span>
          </h2>
          <div className="tv-body">
            <div className="tv-stat-row">
              <div className="tv-stat">
                <div className="tv-value">{fmt(chat?.byHours?.[hk])}</div>
                <div className="tv-caption">users sending msgs · {wlabel}</div>
              </div>
            </div>
            <PlatStats
              platforms={chat?.platforms || {}}
              hoursKey={hk}
              series={chat?.series || []}
              hours={hours}
            />
            <div className="tv-chart">
              <MultiLineChart series={chat?.series || []} hours={hours} />
            </div>
          </div>
        </section>

        <section className="tv-panel tv-hero" id="p-mil">
          <h2>
            <span className="tv-eyebrow">Days until million users</span>
            <span className="tv-h2sub">{m?.rateDays ?? 7}d avg</span>
          </h2>
          <div className="tv-body">
            <div className="tv-stat-row">
              <div className="tv-stat">
                <div className="tv-value">
                  {m?.days == null ? "—" : m.days === 0 ? "0" : fmt(m.days)}
                </div>
                <div className="tv-caption">
                  {fmt(m?.totalUsers)} users · +{fmt(m?.perDay)}/day
                </div>
              </div>
            </div>
            <div className="tv-chart">
              <SingleLineChart series={m?.series || []} hours={24 * 40} color="#c5cdd8" />
            </div>
          </div>
        </section>

        <section className="tv-panel tv-hero" id="p-stick">
          <h2>
            <span className="tv-eyebrow">Stickiness</span>
            <span className="tv-h2sub">window / WAU</span>
          </h2>
          <div className="tv-body">
            <div className="tv-stat-row">
              <div className="tv-stat">
                <div className="tv-value">
                  {stickiness == null ? "—" : `${stickiness}%`}
                </div>
                <div className="tv-caption">
                  {fmt(actSlot?.total)} of {fmt(a?.wau)} weekly actives
                </div>
              </div>
            </div>
            <div className="tv-chart">
              <MultiLineChart series={a?.series || []} hours={hours} />
            </div>
          </div>
        </section>
      </main>

      <footer className="tv-foot">
        <span className="tv-warn">
          {snap?.warnings?.length
            ? `${snap.warnings.length} warning(s): ${snap.warnings[0]}`
            : "lines indexed to window start · absolute latest on right"}
        </span>
        <span className="tv-hint">auto-refresh</span>
      </footer>
    </div>
  );
}
