"use client";

import { useCallback, useEffect, useState } from "react";
import type { TvSnapshot } from "@/lib/tv-snapshot";

function formatCompact(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "—";
  if (Math.abs(value) >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (Math.abs(value) >= 1_000) return `${(value / 1_000).toFixed(1)}K`;
  return Math.round(value).toLocaleString();
}

function formatCurrency(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "—";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(value);
}

function ageLabel(iso: string | undefined): string {
  if (!iso) return "";
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return iso;
  const sec = Math.max(0, Math.round((Date.now() - t) / 1000));
  if (sec < 60) return `updated ${sec}s ago`;
  if (sec < 3600) return `updated ${Math.round(sec / 60)}m ago`;
  return `updated ${Math.round(sec / 3600)}h ago`;
}

type Props = {
  /** Bearer token for /api/tv/snapshot (Firebase ID token or TV share token). */
  getToken: () => Promise<string | null>;
  /** When set, show kiosk chrome (no admin nav). */
  kioskLabel?: string;
  pollMs?: number;
};

export function TvBoard({ getToken, kioskLabel, pollMs = 60_000 }: Props) {
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
      const data = (await res.json()) as TvSnapshot;
      setSnap(data);
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
        new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      );
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);

  const a = snap?.activity;
  const m = snap?.million;
  const r = snap?.revenue;

  return (
    <div className="tv-root min-h-screen text-slate-100">
      <style>{`
        .tv-root {
          background:
            radial-gradient(1200px 600px at 10% -10%, #1a2a55 0%, transparent 55%),
            radial-gradient(900px 500px at 90% 0%, #14263f 0%, transparent 50%),
            #070a12;
          font-family: "SF Pro Display", "Segoe UI", system-ui, sans-serif;
        }
        .tv-tile {
          background: linear-gradient(180deg, #152038, #10182a);
          border: 1px solid rgba(255, 255, 255, 0.06);
          border-radius: 1rem;
          padding: 1rem 1.1rem;
          box-shadow: 0 10px 40px rgba(0, 0, 0, 0.35);
          min-height: 7rem;
        }
        .tv-label {
          color: #8b9bb8;
          font-size: 0.9rem;
          font-weight: 500;
          text-transform: uppercase;
          letter-spacing: 0.06em;
        }
        .tv-value {
          margin-top: 0.4rem;
          font-size: clamp(2rem, 4vw, 3.2rem);
          font-weight: 700;
          font-variant-numeric: tabular-nums;
          letter-spacing: -0.03em;
          line-height: 1.05;
        }
        .tv-detail {
          margin-top: 0.45rem;
          color: #8b9bb8;
          font-size: 0.8rem;
        }
        .tv-section-title {
          color: #8b9bb8;
          font-size: 0.75rem;
          text-transform: uppercase;
          letter-spacing: 0.14em;
          margin: 0 0 0.55rem;
          font-weight: 600;
        }
      `}</style>

      <header className="flex items-start justify-between gap-4 px-6 pt-5 pb-2">
        <div>
          <div className="text-xs uppercase tracking-[0.2em] text-sky-300/80">omi</div>
          <h1 className="text-2xl md:text-3xl font-bold tracking-tight m-0">
            {snap?.title || "Key metrics"}
          </h1>
          <p className="text-slate-400 text-sm m-0 mt-1">
            {kioskLabel ? `${kioskLabel} · ` : ""}
            {ageLabel(snap?.generatedAt)}
            {snap?.partial ? " · partial sources" : ""}
          </p>
        </div>
        <div className="text-right">
          <div className="text-3xl font-semibold tabular-nums">{clock}</div>
          <div className="mt-2 flex flex-wrap gap-1.5 justify-end">
            {snap &&
              Object.entries(snap.sources).map(([k, ok]) => (
                <span
                  key={k}
                  className={`text-[10px] uppercase tracking-wider px-2 py-0.5 rounded-full border ${
                    ok
                      ? "border-emerald-500/40 text-emerald-400"
                      : "border-rose-500/40 text-rose-400"
                  }`}
                >
                  {k}
                </span>
              ))}
          </div>
        </div>
      </header>

      {error && (
        <div className="mx-6 mb-3 rounded-lg border border-amber-500/40 bg-amber-500/10 px-4 py-2 text-amber-100 text-sm">
          {error}
        </div>
      )}

      <main className="px-6 pb-8 space-y-5">
        {r && (
          <section>
            <h2 className="tv-section-title">Revenue</h2>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <div className="tv-tile">
                <div className="tv-label">ARR</div>
                <div className="tv-value">{formatCurrency(r.arr)}</div>
                <div className="tv-detail">Stripe active + past_due plans</div>
              </div>
              <div className="tv-tile">
                <div className="tv-label">MRR</div>
                <div className="tv-value">{formatCurrency(r.mrr)}</div>
              </div>
              {(r.byProduct || []).slice(0, 2).map((p) => (
                <div key={p.productId || p.name} className="tv-tile">
                  <div className="tv-label">{p.name}</div>
                  <div className="tv-value">{formatCurrency(p.mrr * 12)}</div>
                  <div className="tv-detail">
                    {p.subscriptions} subs · ARR from MRR×12
                  </div>
                </div>
              ))}
            </div>
          </section>
        )}

        <section>
          <h2 className="tv-section-title">Active users</h2>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
            <div className="tv-tile">
              <div className="tv-label">DAU 24h</div>
              <div className="tv-value">{formatCompact(a?.dau1d)}</div>
            </div>
            <div className="tv-tile">
              <div className="tv-label">WAU 7d</div>
              <div className="tv-value">{formatCompact(a?.wau7d)}</div>
            </div>
            <div className="tv-tile">
              <div className="tv-label">Desktop DAU</div>
              <div className="tv-value">{formatCompact(a?.desktopDau)}</div>
            </div>
            <div className="tv-tile">
              <div className="tv-label">Mobile DAU</div>
              <div className="tv-value">{formatCompact(a?.mobileDau)}</div>
            </div>
            <div className="tv-tile">
              <div className="tv-label">Chat users</div>
              <div className="tv-value">{formatCompact(a?.chatUsers1d)}</div>
              <div className="tv-detail">24h</div>
            </div>
            <div className="tv-tile">
              <div className="tv-label">Memory users</div>
              <div className="tv-value">{formatCompact(a?.memoryUsers1d)}</div>
              <div className="tv-detail">24h created/extracted</div>
            </div>
          </div>
          {a?.daily && a.daily.length > 1 && (
            <div className="tv-tile mt-3">
              <div className="tv-label mb-2">DAU · 14d</div>
              <Spark values={a.daily.map((d) => d.dau)} />
            </div>
          )}
        </section>

        <section>
          <h2 className="tv-section-title">Growth &amp; product</h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div className="tv-tile col-span-2">
              <div className="tv-label">Days to 1M users</div>
              <div className="tv-value">
                {m?.days == null ? "—" : m.days === 0 ? "✓" : formatCompact(m.days)}
              </div>
              <div className="tv-detail">
                {formatCompact(m?.totalUsers)} persons ·{" "}
                {m?.perDay != null ? `${m.perDay}/day` : "—"} avg new ({m?.rateDays ?? 7}d)
              </div>
            </div>
            <div className="tv-tile">
              <div className="tv-label">Floating bar</div>
              <div className="tv-value">{formatCompact(snap?.features.floatingBarUsers30d)}</div>
              <div className="tv-detail">
                users 30d · {formatCompact(snap?.features.floatingBarQueries30d)} queries
              </div>
            </div>
            <div className="tv-tile">
              <div className="tv-label">Target</div>
              <div className="tv-value">{formatCompact(m?.target ?? 1_000_000)}</div>
              <div className="tv-detail">PostHog persons</div>
            </div>
          </div>
        </section>
      </main>

      <footer className="px-6 pb-4 text-xs text-slate-500 flex justify-between gap-4">
        <span className="truncate">
          {snap?.warnings?.length
            ? `${snap.warnings.length} warning(s): ${snap.warnings[0]}`
            : "Aggregate metrics only · no PII"}
        </span>
        <span>Auto-refresh</span>
      </footer>
    </div>
  );
}

function Spark({ values }: { values: number[] }) {
  if (values.length < 2) return null;
  const w = 640;
  const h = 56;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const pts = values
    .map((v, i) => {
      const x = (i * (w - 8)) / (values.length - 1) + 4;
      const y = h - 4 - ((v - min) / span) * (h - 8);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="w-full h-14" aria-hidden>
      <polyline
        fill="none"
        stroke="rgba(110,168,255,0.95)"
        strokeWidth="2.5"
        points={pts}
      />
    </svg>
  );
}
