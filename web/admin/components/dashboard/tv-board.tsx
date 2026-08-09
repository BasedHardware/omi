"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  Area,
  AreaChart,
  ResponsiveContainer,
  Tooltip,
  YAxis,
} from "recharts";
import { IBM_Plex_Mono, IBM_Plex_Sans } from "next/font/google";
import type { TvSnapshot } from "@/lib/tv-snapshot";

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

const S = {
  line: "#c5cdd8",
  blue: "#8eb4e0",
  amber: "#d4a574",
  aqua: "#7eb8b0",
  violet: "#a89fd4",
  rose: "#d48890",
  muted: "#9aa3b2",
  dim: "#6b7382",
  ink: "#f2f3f5",
  ok: "#5bb98c",
  warn: "#d4b45a",
};

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

function ageLabel(iso?: string): string {
  if (!iso) return "no snapshot";
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return iso;
  const sec = Math.max(0, Math.round((Date.now() - t) / 1000));
  if (sec < 60) return `${sec}s ago`;
  if (sec < 3600) return `${Math.round(sec / 60)}m ago`;
  return `${Math.round(sec / 3600)}h ago`;
}

function shortProduct(name: string): string {
  return name.replace(/^Omi\s+/i, "").replace(/\s+Monthly (Plan|Subscription)$/i, "") || "—";
}

function MiniArea({
  data,
  color = S.line,
  money = false,
}: {
  data: Array<{ v: number }>;
  color?: string;
  money?: boolean;
}) {
  if (!data || data.length < 2) {
    return <div className="tv-empty-chart">No trend yet</div>;
  }
  return (
    <ResponsiveContainer width="100%" height="100%">
      <AreaChart data={data} margin={{ top: 4, right: 0, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id={`g-${color.replace("#", "")}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity={0.35} />
            <stop offset="100%" stopColor={color} stopOpacity={0.02} />
          </linearGradient>
        </defs>
        <YAxis hide domain={["dataMin", "dataMax"]} />
        <Tooltip
          contentStyle={{
            background: "#14161c",
            border: "1px solid rgba(255,255,255,0.1)",
            borderRadius: 6,
            fontSize: 12,
            fontFamily: plexMono.style.fontFamily,
          }}
          labelStyle={{ display: "none" }}
          formatter={(value: number) => [money ? fmtMoney(value) : fmt(value), ""]}
        />
        <Area
          type="monotone"
          dataKey="v"
          stroke={color}
          strokeWidth={1.6}
          fill={`url(#g-${color.replace("#", "")})`}
          isAnimationActive={false}
          dot={false}
        />
      </AreaChart>
    </ResponsiveContainer>
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
  const m = snap?.million;
  const r = snap?.revenue;
  const f = snap?.features;

  const dauSeries = useMemo(
    () => (a?.daily || []).map((d) => ({ v: d.dau, day: d.day })),
    [a?.daily],
  );
  const millionSeries = useMemo(
    () => (m?.series || []).map((d) => ({ v: d.total, day: d.day })),
    [m?.series],
  );
  const newUserSeries = useMemo(
    () => (m?.series || []).map((d) => ({ v: d.newUsers, day: d.day })),
    [m?.series],
  );

  const stickiness =
    a?.dau1d != null && a?.wau7d != null && a.wau7d > 0
      ? Math.round((a.dau1d / a.wau7d) * 1000) / 10
      : null;

  const products = useMemo(() => {
    const all = (r?.byProduct || [])
      .map((p) => ({
        name: shortProduct(p.name),
        arr: (p.mrr || 0) * 12,
        subs: p.subscriptions || 0,
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

  const liveState = !snap
    ? "down"
    : snap.partial
      ? "stale"
      : error
        ? "down"
        : "";

  return (
    <div className={`tv-shell ${plexSans.className} ${plexMono.className}`}>
      <style>{`
        .tv-shell {
          --bg: #0c0d10;
          --panel: #14161c;
          --line: rgba(255,255,255,0.08);
          --ink: #f2f3f5;
          --muted: #9aa3b2;
          --dim: #6b7382;
          --ok: #5bb98c;
          --warn: #d4b45a;
          --bad: #d48890;
          --s1: #8eb4e0;
          --s2: #d4a574;
          --s3: #7eb8b0;
          --s4: #a89fd4;
          --gap: 0.45vw;
          --radius: 0.35vw;
          --fs-lead: 3.4vw;
          --fs-hero: 2.7vw;
          --fs-stat: 1.75vw;
          --fs-label: 0.78vw;
          --fs-chip: 0.86vw;
          --fs-fine: 0.72vw;
          color: var(--ink);
          background: var(--bg);
          height: 100vh;
          width: 100vw;
          overflow: hidden;
          display: grid;
          grid-template-rows: auto 1fr auto;
          -webkit-font-smoothing: antialiased;
        }
        .tv-shell * { box-sizing: border-box; }
        .tv-rail {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 1vw;
          padding: 0.55vw 1vw 0.35vw;
          border-bottom: 1px solid var(--line);
        }
        .tv-brand { display: flex; align-items: baseline; gap: 0.5vw; }
        .tv-dot {
          width: 0.4vw; height: 0.4vw; min-width: 7px; min-height: 7px;
          border-radius: 50%; background: var(--ok); align-self: center;
        }
        .tv-dot.stale { background: var(--warn); }
        .tv-dot.down { background: var(--bad); }
        .tv-brand-name {
          font-size: 1.15vw; font-weight: 600; letter-spacing: -0.02em;
        }
        .tv-brand-sub {
          font-size: var(--fs-label); text-transform: uppercase;
          letter-spacing: 0.18em; color: var(--dim);
        }
        .tv-rail-right {
          display: flex; align-items: center; gap: 0.9vw;
        }
        .tv-fresh, .tv-status {
          font-family: ${plexMono.style.fontFamily};
          font-size: var(--fs-fine); color: var(--muted);
        }
        .tv-status { color: var(--warn); max-width: 18vw; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .tv-clock {
          font-family: ${plexMono.style.fontFamily};
          font-size: 1vw; font-weight: 500; font-variant-numeric: tabular-nums;
        }
        .tv-chrome a {
          font-size: var(--fs-fine);
          color: var(--dim);
          text-decoration: none;
          border: 1px solid var(--line);
          padding: 0.2vw 0.5vw;
          border-radius: 999px;
        }
        .tv-chrome a:hover { color: var(--ink); border-color: var(--muted); }
        .tv-board {
          display: grid;
          grid-template-columns: repeat(12, 1fr);
          grid-template-rows: 1.28fr 1fr 1fr;
          gap: var(--gap);
          padding: 0.4vw 1vw 0.3vw;
          min-height: 0;
        }
        .tv-panel {
          background: var(--panel);
          border: 1px solid var(--line);
          border-radius: var(--radius);
          padding: 0.5vw 0.65vw 0.4vw;
          min-height: 0;
          display: flex;
          flex-direction: column;
          overflow: hidden;
        }
        .tv-panel h2 {
          margin: 0 0 0.25vw;
          display: flex; align-items: baseline; gap: 0.45vw;
          font-weight: 500; font-size: inherit;
        }
        .tv-eyebrow {
          font-size: var(--fs-label);
          text-transform: uppercase;
          letter-spacing: 0.14em;
          color: var(--muted);
        }
        .tv-h2-sub {
          font-family: ${plexMono.style.fontFamily};
          font-size: var(--fs-fine);
          color: var(--dim);
          margin-left: auto;
        }
        .tv-body { flex: 1; min-height: 0; display: flex; flex-direction: column; }
        .tv-stat-row {
          display: flex; align-items: flex-end; justify-content: space-between;
          gap: 0.5vw; flex: 0 0 auto;
        }
        .tv-stat { display: flex; flex-direction: column; gap: 0.1vw; min-width: 0; }
        .tv-value {
          font-family: ${plexMono.style.fontFamily};
          font-size: var(--fs-stat);
          font-weight: 500;
          letter-spacing: -0.03em;
          line-height: 0.95;
          font-variant-numeric: tabular-nums;
        }
        .tv-lead .tv-value { font-size: var(--fs-lead); }
        .tv-hero .tv-value { font-size: var(--fs-hero); }
        .tv-caption {
          font-size: var(--fs-fine);
          text-transform: uppercase;
          letter-spacing: 0.1em;
          color: var(--muted);
        }
        .tv-side {
          display: flex; align-items: flex-end; gap: 0.9vw;
        }
        .tv-side .tv-value { font-size: var(--fs-stat); color: var(--muted); }
        .tv-plat {
          display: flex; flex-wrap: wrap; gap: 0.25vw 0.75vw;
          margin-top: 0.25vw; font-size: var(--fs-chip); color: var(--muted);
        }
        .tv-plat span { display: inline-flex; align-items: baseline; gap: 0.25vw; }
        .tv-plat i {
          width: 0.45vw; height: 0.18vw; min-width: 6px; min-height: 2px;
          align-self: center; display: inline-block;
        }
        .tv-plat b {
          font-family: ${plexMono.style.fontFamily};
          font-weight: 500; color: var(--ink); font-variant-numeric: tabular-nums;
        }
        .tv-chart { position: relative; flex: 1 1 0; min-height: 0; margin-top: 0.15vw; }
        .tv-empty-chart {
          height: 100%; display: grid; place-items: center;
          color: var(--dim); font-size: var(--fs-chip);
        }
        .tv-rev { flex: 1; min-height: 0; display: flex; flex-direction: column; gap: 0.3vw; }
        .tv-rev-head .tv-value { font-size: 2.1vw; }
        .tv-rev-list {
          flex: 1 1 0; min-height: 0; display: flex; flex-direction: column;
          justify-content: center; gap: 0.3vw; overflow: hidden;
        }
        .tv-rev-row {
          display: grid; grid-template-columns: 5.2vw 1fr 3.4vw;
          align-items: center; gap: 0.35vw; font-size: var(--fs-chip);
        }
        .tv-rev-row .name { color: var(--muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .tv-rev-row .bar {
          height: 0.38vw; min-height: 4px; background: rgba(255,255,255,0.06); overflow: hidden;
        }
        .tv-rev-row .bar > i { display: block; height: 100%; background: var(--s2); }
        .tv-rev-row:nth-child(2) .bar > i { background: var(--s3); }
        .tv-rev-row:nth-child(3) .bar > i { background: var(--s1); }
        .tv-rev-row:nth-child(4) .bar > i { background: var(--warn); }
        .tv-rev-row:nth-child(5) .bar > i { background: #d48890; }
        .tv-rev-row:nth-child(6) .bar > i { background: #8b93a3; }
        .tv-rev-row .amt {
          font-family: ${plexMono.style.fontFamily};
          font-weight: 500; text-align: right; font-variant-numeric: tabular-nums;
        }
        .tv-rev-row .pct { color: var(--dim); margin-left: 0.2em; }
        .tv-rev-trend {
          flex: 0 0 auto; height: auto; border-top: 1px solid var(--line);
          padding-top: 0.45vw; min-height: 0;
        }
        .tv-mixbar {
          display: flex; width: 100%; height: 0.55vw; min-height: 6px;
          overflow: hidden; background: rgba(255,255,255,0.04);
        }
        .tv-mixbar > i { display: block; height: 100%; }
        .tv-mixbar-cap {
          margin-top: 0.25vw;
          font-size: var(--fs-fine);
          text-transform: uppercase;
          letter-spacing: 0.1em;
          color: var(--dim);
        }
        .tv-foot {
          display: flex; justify-content: space-between; align-items: center;
          gap: 1vw; padding: 0.35vw 1vw 0.5vw; border-top: 1px solid var(--line);
        }
        .tv-warn {
          font-family: ${plexMono.style.fontFamily};
          font-size: var(--fs-fine); color: var(--warn);
          max-width: 70%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
        }
        .tv-hint { font-size: var(--fs-fine); color: var(--dim); text-transform: uppercase; letter-spacing: 0.12em; }
        #p-dau { grid-column: 1 / 7; grid-row: 1; }
        #p-mem { grid-column: 7 / 10; grid-row: 1; }
        #p-rev { grid-column: 10 / 13; grid-row: 1 / 3; }
        #p-chat { grid-column: 1 / 4; grid-row: 2; }
        #p-habit { grid-column: 4 / 7; grid-row: 2; }
        #p-stick { grid-column: 7 / 10; grid-row: 2; }
        #p-mil { grid-column: 1 / 9; grid-row: 3; }
        #p-new { grid-column: 9 / 13; grid-row: 3; }
        @media (max-width: 1100px) {
          .tv-shell { height: auto; min-height: 100vh; overflow: auto; --fs-lead: 2.2rem; --fs-hero: 1.8rem; --fs-stat: 1.25rem; --fs-label: 0.65rem; --fs-chip: 0.75rem; --fs-fine: 0.65rem; --gap: 0.5rem; --radius: 0.4rem; }
          .tv-board { grid-template-columns: 1fr 1fr; grid-template-rows: auto; }
          .tv-panel { grid-column: auto !important; grid-row: auto !important; min-height: 14rem; }
          #p-dau, #p-mil, #p-rev { grid-column: 1 / -1 !important; }
          .tv-rev-trend { height: 5rem; }
        }
      `}</style>

      <header className="tv-rail">
        <div className="tv-brand">
          <span className={`tv-dot ${liveState}`} />
          <span className="tv-brand-name">omi</span>
          <span className="tv-brand-sub">
            {kioskLabel ? `${kioskLabel} · ` : ""}product pulse
          </span>
        </div>
        <div className="tv-rail-right">
          {error ? <span className="tv-status">{error}</span> : null}
          <span className="tv-fresh">{ageLabel(snap?.generatedAt)}</span>
          <time className="tv-clock">{clock}</time>
          {showAdminChrome ? (
            <span className="tv-chrome">
              <Link href="/dashboard/tv-links">links</Link>{" "}
              <Link href="/dashboard">exit</Link>
            </span>
          ) : null}
        </div>
      </header>

      <main className="tv-board">
        {/* Active users — lead */}
        <section className="tv-panel tv-lead" id="p-dau">
          <h2>
            <span className="tv-eyebrow">Active users</span>
            <span className="tv-h2-sub">24h / 7d</span>
          </h2>
          <div className="tv-body">
            <div className="tv-stat-row">
              <div className="tv-stat">
                <div className="tv-value">{fmt(a?.dau1d)}</div>
                <div className="tv-caption">DAU · last 24h</div>
              </div>
              <div className="tv-side">
                <div className="tv-stat">
                  <div className="tv-value">{fmt(a?.wau7d)}</div>
                  <div className="tv-caption">WAU</div>
                </div>
              </div>
            </div>
            <div className="tv-plat">
              <span>
                <i style={{ background: S.blue }} /> Mac <b>{fmt(a?.desktopDau)}</b>
              </span>
              <span>
                <i style={{ background: S.aqua }} /> Mobile <b>{fmt(a?.mobileDau)}</b>
              </span>
              <span>
                <i style={{ background: S.amber }} /> Chat <b>{fmt(a?.chatUsers1d)}</b>
              </span>
            </div>
            <div className="tv-chart">
              <MiniArea data={dauSeries} color={S.blue} />
            </div>
          </div>
        </section>

        {/* Memories */}
        <section className="tv-panel tv-hero" id="p-mem">
          <h2>
            <span className="tv-eyebrow">Memory users</span>
            <span className="tv-h2-sub">24h</span>
          </h2>
          <div className="tv-body">
            <div className="tv-stat-row">
              <div className="tv-stat">
                <div className="tv-value">{fmt(a?.memoryUsers1d)}</div>
                <div className="tv-caption">created / extracted</div>
              </div>
            </div>
            <div className="tv-chart">
              <MiniArea data={dauSeries} color={S.aqua} />
            </div>
          </div>
        </section>

        {/* Revenue tall */}
        <section className="tv-panel" id="p-rev">
          <h2>
            <span className="tv-eyebrow">Annual recurring revenue</span>
            <span className="tv-h2-sub">Stripe</span>
          </h2>
          <div className="tv-body">
            {r == null ? (
              <div className="tv-empty-chart">Revenue hidden on this link</div>
            ) : r.unavailable ? (
              <div className="tv-empty-chart">Stripe not configured</div>
            ) : (
              <div className="tv-rev">
                <div className="tv-rev-head">
                  <div className="tv-value">{fmtMoney(r.arr)}</div>
                  <div className="tv-caption">
                    {fmt(r.subscriptionCount)} subscriptions · MRR {fmtMoney(r.mrr)}
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
                <div className="tv-rev-trend">
                  <div className="tv-mixbar" aria-hidden>
                    {products.map((p, i) => {
                      const colors = [S.amber, S.aqua, S.blue, S.warn, S.rose, "#8b93a3"];
                      const pct = Math.max(1.5, (p.arr / sumArr) * 100);
                      return (
                        <i
                          key={p.name}
                          style={{
                            width: `${pct}%`,
                            background: colors[i % colors.length],
                          }}
                          title={`${p.name} ${fmtMoney(p.arr)}`}
                        />
                      );
                    })}
                  </div>
                  <div className="tv-mixbar-cap">product mix · list-price ARR</div>
                </div>
              </div>
            )}
          </div>
        </section>

        {/* Chat */}
        <section className="tv-panel tv-hero" id="p-chat">
          <h2>
            <span className="tv-eyebrow">Chat</span>
            <span className="tv-h2-sub">24h</span>
          </h2>
          <div className="tv-body">
            <div className="tv-stat-row">
              <div className="tv-stat">
                <div className="tv-value">{fmt(a?.chatUsers1d)}</div>
                <div className="tv-caption">users sending messages</div>
              </div>
            </div>
            <div className="tv-chart">
              <MiniArea data={dauSeries} color={S.violet} />
            </div>
          </div>
        </section>

        {/* Habit / floating bar */}
        <section className="tv-panel tv-hero" id="p-habit">
          <h2>
            <span className="tv-eyebrow">Habit forming</span>
            <span className="tv-h2-sub">30d</span>
          </h2>
          <div className="tv-body">
            <div className="tv-stat-row">
              <div className="tv-stat">
                <div className="tv-value">{fmt(f?.floatingBarUsers30d)}</div>
                <div className="tv-caption">
                  floating bar users · {fmt(f?.floatingBarQueries30d)} queries
                </div>
              </div>
            </div>
            <div className="tv-chart">
              <MiniArea data={newUserSeries} color={S.amber} />
            </div>
          </div>
        </section>

        {/* Stickiness instead of M1 retention */}
        <section className="tv-panel tv-hero" id="p-stick">
          <h2>
            <span className="tv-eyebrow">Stickiness</span>
            <span className="tv-h2-sub">DAU / WAU</span>
          </h2>
          <div className="tv-body">
            <div className="tv-stat-row">
              <div className="tv-stat">
                <div className="tv-value">
                  {stickiness == null ? "—" : `${stickiness}%`}
                </div>
                <div className="tv-caption">
                  {fmt(a?.dau1d)} of {fmt(a?.wau7d)} weekly actives today
                </div>
              </div>
            </div>
            <div className="tv-chart">
              <MiniArea data={dauSeries} color={S.line} />
            </div>
          </div>
        </section>

        {/* Days to 1M */}
        <section className="tv-panel tv-hero" id="p-mil">
          <h2>
            <span className="tv-eyebrow">Days until million users</span>
            <span className="tv-h2-sub">{m?.rateDays ?? 7}d avg</span>
          </h2>
          <div className="tv-body">
            <div className="tv-stat-row">
              <div className="tv-stat">
                <div className="tv-value">
                  {m?.days == null ? "—" : m.days === 0 ? "0" : fmt(m.days)}
                </div>
                <div className="tv-caption">
                  {fmt(m?.totalUsers)} persons · +{fmt(m?.perDay)}/day
                </div>
              </div>
            </div>
            <div className="tv-chart">
              <MiniArea data={millionSeries} color={S.line} />
            </div>
          </div>
        </section>

        {/* New users pace */}
        <section className="tv-panel tv-hero" id="p-new">
          <h2>
            <span className="tv-eyebrow">New persons / day</span>
            <span className="tv-h2-sub">PostHog</span>
          </h2>
          <div className="tv-body">
            <div className="tv-stat-row">
              <div className="tv-stat">
                <div className="tv-value">{fmt(m?.perDay)}</div>
                <div className="tv-caption">avg over {m?.rateDays ?? 7}d</div>
              </div>
            </div>
            <div className="tv-chart">
              <MiniArea data={newUserSeries} color={S.aqua} />
            </div>
          </div>
        </section>
      </main>

      <footer className="tv-foot">
        <span className="tv-warn">
          {snap?.warnings?.length
            ? `${snap.warnings.length} warning(s): ${snap.warnings[0]}`
            : "Aggregate metrics · no PII"}
        </span>
        <span className="tv-hint">auto-refresh</span>
      </footer>
    </div>
  );
}
