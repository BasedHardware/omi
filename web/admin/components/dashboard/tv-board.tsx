"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  CartesianGrid,
  Line,
  LineChart,
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

type Props = {
  getToken: () => Promise<string | null>;
  kioskLabel?: string;
  pollMs?: number;
  showAdminChrome?: boolean;
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

function downsample(series: SeriesPoint[], max = 48): SeriesPoint[] {
  if (series.length <= max) return series;
  const out: SeriesPoint[] = [];
  const step = (series.length - 1) / (max - 1);
  for (let i = 0; i < max; i++) {
    out.push(series[Math.round(i * step)]);
  }
  return out;
}

function shortTime(t: number, hours: number): string {
  const d = new Date(t * 1000);
  if (hours <= 24) {
    return d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  }
  return d.toLocaleString([], { month: "short", day: "numeric", hour: "numeric" });
}

function MultiLineChart({
  series,
  hours,
  keys = PLATS as unknown as string[],
  colors = PLAT_COLORS,
}: {
  series: SeriesPoint[];
  hours: number;
  keys?: string[];
  colors?: Record<string, string>;
}) {
  const data = useMemo(() => {
    return downsample(sliceSeries(series, hours)).map((p) => ({
      ...p,
      label: shortTime(p.t, hours),
    }));
  }, [series, hours]);

  if (data.length < 2) {
    return <div className="tv-empty">No trend yet</div>;
  }

  return (
    <ResponsiveContainer width="100%" height="100%">
      <LineChart data={data} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
        <CartesianGrid stroke="rgba(255,255,255,0.04)" vertical={false} />
        <XAxis
          dataKey="label"
          tick={{ fill: "#6b7382", fontSize: 10, fontFamily: plexMono.style.fontFamily }}
          tickLine={false}
          axisLine={false}
          minTickGap={28}
          interval="preserveStartEnd"
        />
        <YAxis hide domain={["auto", "auto"]} />
        <Tooltip
          contentStyle={{
            background: "#14161c",
            border: "1px solid rgba(255,255,255,0.1)",
            borderRadius: 6,
            fontSize: 11,
            fontFamily: plexMono.style.fontFamily,
          }}
          labelStyle={{ color: "#9aa3b2" }}
        />
        {keys.map((k) => (
          <Line
            key={k}
            type="monotone"
            dataKey={k}
            stroke={colors[k] || "#c5cdd8"}
            strokeWidth={1.5}
            dot={false}
            isAnimationActive={false}
            connectNulls
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}

function SingleLineChart({
  series,
  hours,
  color = "#c5cdd8",
  dataKey = "v",
}: {
  series: SeriesPoint[];
  hours: number;
  color?: string;
  dataKey?: string;
}) {
  const data = useMemo(() => {
    return downsample(sliceSeries(series, hours)).map((p) => ({
      ...p,
      label: shortTime(p.t, hours),
      v: (p as Record<string, number | undefined>)[dataKey] ?? p.v ?? p.total ?? p.memories_created,
    }));
  }, [series, hours, dataKey]);

  if (data.length < 2) return <div className="tv-empty">No trend yet</div>;

  return (
    <ResponsiveContainer width="100%" height="100%">
      <LineChart data={data} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
        <CartesianGrid stroke="rgba(255,255,255,0.04)" vertical={false} />
        <XAxis
          dataKey="label"
          tick={{ fill: "#6b7382", fontSize: 10, fontFamily: plexMono.style.fontFamily }}
          tickLine={false}
          axisLine={false}
          minTickGap={32}
          interval="preserveStartEnd"
        />
        <YAxis hide domain={["auto", "auto"]} />
        <Tooltip
          contentStyle={{
            background: "#14161c",
            border: "1px solid rgba(255,255,255,0.1)",
            borderRadius: 6,
            fontSize: 11,
            fontFamily: plexMono.style.fontFamily,
          }}
        />
        <Line
          type="monotone"
          dataKey="v"
          stroke={color}
          strokeWidth={1.6}
          dot={false}
          isAnimationActive={false}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}

function PlatLegend({
  platforms,
  hoursKey,
}: {
  platforms: Record<string, number | null | Record<string, number | null>>;
  hoursKey: string;
}) {
  return (
    <div className="tv-plat">
      {PLATS.map((p) => {
        const raw = platforms[p];
        const v =
          raw == null
            ? null
            : typeof raw === "number"
              ? raw
              : (raw as Record<string, number | null>)[hoursKey];
        if (v == null && raw == null) return null;
        return (
          <span key={p}>
            <i style={{ background: PLAT_COLORS[p] }} />
            {PLAT_LABEL[p]} <b>{fmt(typeof v === "number" ? v : null)}</b>
          </span>
        );
      })}
    </div>
  );
}

export function TvBoard({
  getToken,
  kioskLabel,
  pollMs = 60_000,
  showAdminChrome = false,
}: Props) {
  const [snap, setSnap] = useState<TvSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [clock, setClock] = useState("");
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
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [getToken]);

  useEffect(() => {
    void load();
    const id = setInterval(() => void load(), pollMs);
    return () => clearInterval(id);
  }, [load, pollMs]);

  useEffect(() => {
    const tick = () =>
      setClock(
        new Date().toLocaleString([], {
          weekday: "short",
          month: "short",
          day: "numeric",
          hour: "numeric",
          minute: "2-digit",
        }),
      );
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);

  const a = snap?.activity;
  const actSlot = a?.byHours?.[hk];
  const conv = snap?.features.conversation;
  const chat = snap?.features.chat;
  const habit = snap?.features.habit;
  const fun = snap?.fun;
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
    const rest = all.slice(5).reduce((s, p) => s + p.arr, 0);
    const top = all.slice(0, 5);
    if (rest > 0) top.push({ name: "Other", arr: rest, subs: 0 });
    return top;
  }, [r?.byProduct]);
  const maxArr = products[0]?.arr || 1;
  const sumArr = products.reduce((s, p) => s + p.arr, 0) || 1;

  const live = !snap ? "down" : snap.partial || error ? "stale" : "";
  const wlabel = WINDOW_LABEL[hours];

  return (
    <div className={`tv-shell ${plexSans.className}`}>
      <style>{`
        .tv-shell {
          --bg:#0c0d10; --panel:#14161c; --line:rgba(255,255,255,.08);
          --ink:#f2f3f5; --muted:#9aa3b2; --dim:#6b7382;
          --ok:#5bb98c; --warn:#d4b45a; --bad:#d48890;
          --gap:.45vw; --radius:.35vw;
          --fs-lead:3.5vw; --fs-hero:2.75vw; --fs-stat:1.7vw;
          --fs-label:.78vw; --fs-chip:.86vw; --fs-fine:.72vw;
          color:var(--ink); background:var(--bg);
          height:100vh; width:100vw; overflow:hidden;
          display:grid; grid-template-rows:auto 1fr auto;
          -webkit-font-smoothing:antialiased;
          font-family:${plexSans.style.fontFamily}, system-ui, sans-serif;
        }
        .tv-shell *{box-sizing:border-box}
        .tv-mono{font-family:${plexMono.style.fontFamily}, ui-monospace, monospace}
        .tv-rail{display:flex;align-items:center;justify-content:space-between;gap:1vw;
          padding:.55vw 1vw .35vw;border-bottom:1px solid var(--line)}
        .tv-brand{display:flex;align-items:baseline;gap:.5vw}
        .tv-dot{width:.4vw;height:.4vw;min-width:7px;min-height:7px;border-radius:50%;
          background:var(--ok);align-self:center}
        .tv-dot.stale{background:var(--warn)}.tv-dot.down{background:var(--bad)}
        .tv-brand-name{font-size:1.15vw;font-weight:600;letter-spacing:-.02em}
        .tv-brand-sub{font-size:var(--fs-label);text-transform:uppercase;letter-spacing:.18em;color:var(--dim)}
        .tv-rail-right{display:flex;align-items:center;gap:.85vw}
        .tv-fresh,.tv-status{font-size:var(--fs-fine);color:var(--muted)}
        .tv-status{color:var(--warn);max-width:16vw;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
        .tv-clock{font-size:1vw;font-weight:500;font-variant-numeric:tabular-nums}
        .tv-toggle{display:inline-flex;gap:.12vw}
        .tv-toggle button{appearance:none;border:0;background:transparent;color:var(--dim);
          font-size:var(--fs-fine);font-weight:500;letter-spacing:.04em;padding:.12vw .42vw;
          cursor:pointer;border-bottom:2px solid transparent;
          font-family:${plexMono.style.fontFamily}, monospace}
        .tv-toggle button.active{color:var(--ink);border-bottom-color:var(--ink)}
        .tv-chrome a{font-size:var(--fs-fine);color:var(--dim);text-decoration:none;
          border:1px solid var(--line);padding:.15vw .45vw;border-radius:999px}
        .tv-chrome a:hover{color:var(--ink)}
        .tv-board{display:grid;grid-template-columns:repeat(12,1fr);grid-template-rows:1.28fr 1fr 1fr;
          gap:var(--gap);padding:.4vw 1vw .3vw;min-height:0}
        .tv-panel{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);
          padding:.5vw .65vw .4vw;min-height:0;display:flex;flex-direction:column;overflow:hidden}
        .tv-panel h2{margin:0 0 .22vw;display:flex;align-items:baseline;gap:.45vw;font-weight:500;font-size:inherit}
        .tv-eyebrow{font-size:var(--fs-label);text-transform:uppercase;letter-spacing:.14em;color:var(--muted)}
        .tv-h2sub{font-size:var(--fs-fine);color:var(--dim);margin-left:auto;
          font-family:${plexMono.style.fontFamily}, monospace}
        .tv-body{flex:1;min-height:0;display:flex;flex-direction:column}
        .tv-stat-row{display:flex;align-items:flex-end;justify-content:space-between;gap:.5vw;flex:0 0 auto}
        .tv-stat{display:flex;flex-direction:column;gap:.08vw;min-width:0}
        .tv-value{font-family:${plexMono.style.fontFamily}, monospace;font-size:var(--fs-stat);
          font-weight:500;letter-spacing:-.03em;line-height:.95;font-variant-numeric:tabular-nums}
        .tv-lead .tv-value{font-size:var(--fs-lead)}
        .tv-hero .tv-value{font-size:var(--fs-hero)}
        .tv-caption{font-size:var(--fs-fine);text-transform:uppercase;letter-spacing:.1em;color:var(--muted)}
        .tv-side .tv-value{font-size:var(--fs-stat);color:var(--muted)}
        .tv-plat{display:flex;flex-wrap:wrap;gap:.2vw .7vw;margin-top:.2vw;font-size:var(--fs-chip);color:var(--muted)}
        .tv-plat span{display:inline-flex;align-items:baseline;gap:.22vw}
        .tv-plat i{width:.42vw;height:.16vw;min-width:6px;min-height:2px;align-self:center;display:inline-block}
        .tv-plat b{font-family:${plexMono.style.fontFamily}, monospace;font-weight:500;color:var(--ink);font-variant-numeric:tabular-nums}
        .tv-chart{position:relative;flex:1 1 0;min-height:0;margin-top:.12vw}
        .tv-empty{height:100%;display:grid;place-items:center;color:var(--dim);font-size:var(--fs-chip)}
        .tv-rev{flex:1;min-height:0;display:flex;flex-direction:column;gap:.28vw}
        .tv-rev-head .tv-value{font-size:2.05vw}
        .tv-rev-list{flex:1 1 0;min-height:0;display:flex;flex-direction:column;justify-content:center;gap:.28vw;overflow:hidden}
        .tv-rev-row{display:grid;grid-template-columns:5.4vw 1fr 3.3vw;align-items:center;gap:.35vw;font-size:var(--fs-chip)}
        .tv-rev-row .name{color:var(--muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
        .tv-rev-row .bar{height:.38vw;min-height:4px;background:rgba(255,255,255,.06);overflow:hidden}
        .tv-rev-row .bar>i{display:block;height:100%;background:#d4a574}
        .tv-rev-row:nth-child(2) .bar>i{background:#7eb8b0}
        .tv-rev-row:nth-child(3) .bar>i{background:#8eb4e0}
        .tv-rev-row:nth-child(4) .bar>i{background:#d4b45a}
        .tv-rev-row:nth-child(5) .bar>i{background:#d48890}
        .tv-rev-row:nth-child(6) .bar>i{background:#8b93a3}
        .tv-rev-row .amt{font-family:${plexMono.style.fontFamily}, monospace;font-weight:500;text-align:right;font-variant-numeric:tabular-nums}
        .tv-rev-row .pct{color:var(--dim);margin-left:.18em}
        .tv-mixbar{display:flex;width:100%;height:.5vw;min-height:5px;overflow:hidden;background:rgba(255,255,255,.04);margin-top:.15vw}
        .tv-mixbar>i{display:block;height:100%}
        .tv-mixcap{margin-top:.2vw;font-size:var(--fs-fine);text-transform:uppercase;letter-spacing:.1em;color:var(--dim)}
        .tv-foot{display:flex;justify-content:space-between;align-items:center;gap:1vw;
          padding:.32vw 1vw .45vw;border-top:1px solid var(--line)}
        .tv-warn{font-size:var(--fs-fine);color:var(--warn);max-width:70%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;
          font-family:${plexMono.style.fontFamily}, monospace}
        .tv-hint{font-size:var(--fs-fine);color:var(--dim);text-transform:uppercase;letter-spacing:.12em}
        #p-dau{grid-column:1/7;grid-row:1}
        #p-mem{grid-column:7/10;grid-row:1}
        #p-rev{grid-column:10/13;grid-row:1/3}
        #p-conv{grid-column:1/4;grid-row:2}
        #p-chat{grid-column:4/7;grid-row:2}
        #p-habit{grid-column:7/10;grid-row:2}
        #p-mil{grid-column:1/9;grid-row:3}
        #p-stick{grid-column:9/13;grid-row:3}
        @media (max-width:1100px){
          .tv-shell{height:auto;min-height:100vh;overflow:auto;
            --fs-lead:2.2rem;--fs-hero:1.75rem;--fs-stat:1.2rem;--fs-label:.65rem;--fs-chip:.72rem;--fs-fine:.62rem;--gap:.5rem;--radius:.4rem}
          .tv-board{grid-template-columns:1fr 1fr;grid-template-rows:auto}
          .tv-panel{grid-column:auto!important;grid-row:auto!important;min-height:14rem}
          #p-dau,#p-mil,#p-rev{grid-column:1/-1!important}
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
            <span className="tv-status">
              {snap.warnings?.[0] || "partial sources"}
            </span>
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
          <time className="tv-clock tv-mono">{clock}</time>
          {showAdminChrome ? (
            <span className="tv-chrome">
              <Link href="/dashboard/tv-links">links</Link>{" "}
              <Link href="/dashboard">exit</Link>
            </span>
          ) : null}
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
            <PlatLegend platforms={actSlot?.platforms || {}} hoursKey={hk} />
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
                <div className="tv-value">{fmt(fun?.memoriesByHours?.[hk])}</div>
                <div className="tv-caption">created · {wlabel}</div>
              </div>
            </div>
            <div className="tv-chart">
              <SingleLineChart
                series={fun?.series || []}
                hours={hours}
                color="#c5cdd8"
                dataKey="memories_created"
              />
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
                    {fmt(r.subscriptionCount)} subscriptions
                  </div>
                </div>
                <div className="tv-rev-list">
                  {products.map((p) => {
                    const w = Math.max(2, Math.round((p.arr / maxArr) * 100));
                    const pct = Math.round((p.arr / sumArr) * 100);
                    return (
                      <div className="tv-rev-row" key={p.name}>
                        <span className="name">{p.name}</span>
                        <span className="bar">
                          <i style={{ width: `${w}%` }} />
                        </span>
                        <span className="amt">
                          {fmtMoney(p.arr)}
                          <span className="pct">{pct}%</span>
                        </span>
                      </div>
                    );
                  })}
                </div>
                <div className="tv-mixbar" aria-hidden>
                  {products.map((p, i) => {
                    const colors = ["#d4a574", "#7eb8b0", "#8eb4e0", "#d4b45a", "#d48890", "#8b93a3"];
                    return (
                      <i
                        key={p.name}
                        style={{
                          width: `${Math.max(1.5, (p.arr / sumArr) * 100)}%`,
                          background: colors[i % colors.length],
                        }}
                      />
                    );
                  })}
                </div>
                <div className="tv-mixcap">product mix · list-price ARR</div>
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
                <div className="tv-caption">users · {wlabel}</div>
              </div>
            </div>
            <PlatLegend platforms={conv?.platforms || {}} hoursKey={hk} />
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
                <div className="tv-caption">users · {wlabel}</div>
              </div>
            </div>
            <PlatLegend platforms={chat?.platforms || {}} hoursKey={hk} />
            <div className="tv-chart">
              <MultiLineChart series={chat?.series || []} hours={hours} />
            </div>
          </div>
        </section>

        <section className="tv-panel tv-hero" id="p-habit">
          <h2>
            <span className="tv-eyebrow">Habit forming</span>
            <span className="tv-h2sub">{wlabel}</span>
          </h2>
          <div className="tv-body">
            <div className="tv-stat-row">
              <div className="tv-stat">
                <div className="tv-value">{fmt(habit?.byHours?.[hk])}</div>
                <div className="tv-caption">users · {wlabel}</div>
              </div>
            </div>
            <PlatLegend platforms={habit?.platforms || {}} hoursKey={hk} />
            <div className="tv-chart">
              <MultiLineChart series={habit?.series || []} hours={hours} />
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
              <SingleLineChart series={m?.series || []} hours={24 * 30} color="#c5cdd8" />
            </div>
          </div>
        </section>

        <section className="tv-panel tv-hero" id="p-stick">
          <h2>
            <span className="tv-eyebrow">Stickiness</span>
            <span className="tv-h2sub">DAU / WAU</span>
          </h2>
          <div className="tv-body">
            <div className="tv-stat-row">
              <div className="tv-stat">
                <div className="tv-value">
                  {a?.wau && actSlot?.total
                    ? `${Math.round((Number(actSlot.total) / a.wau) * 1000) / 10}%`
                    : "—"}
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
            : "aggregate metrics · no PII"}
        </span>
        <span className="tv-hint">auto-refresh</span>
      </footer>
    </div>
  );
}
