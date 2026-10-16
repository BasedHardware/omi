/** All-in daily cost for the TV wall ("count every cost line", David 2026-10-16).
 *
 * total = GCP net of credits (spend-based CUD arrives as FEE_UTILIZATION_OFFSET
 *         credits) − one-time incident excess
 *       + OpenAI + Anthropic invoices (billing-mode legs)
 *       + STT vendors (Soniox/Deepgram: not in any automated feed, so the FinOps
 *         modelled low estimate, labelled "modelled")
 *       + SaaS at a fixed monthly estimate (labelled "fixed estimate").
 * A line that cannot be sourced is reported in `missing`, never dropped silently.
 */
import { isLlmService } from "./services/gcp-billing";

export const SAAS_MONTHLY_USD = 4800; // "Omi Cost vs Revenue" artifact, Oct 2026 row
const DAYS_PER_MONTH = 365.25 / 12;
/** A GCP service-day is a one-time incident when it exceeds its trailing
 * 14-day median by both $500 and 2× (e.g. the 2026-09-07 Coldline migration:
 * Cloud Storage $13,967 against ~$200/day). Only the excess is excluded. */
export const ONE_TIME = { lookbackDays: 14, minExcessUsd: 500, multiple: 2 };

export interface BillingDay {
  date: string;
  total: number;
  components?: Record<string, unknown>;
}
export interface CostDay {
  date: string;
  gcp: number;
  vertexLlm: number;
  openai: number | null;
  anthropic: number | null;
  stt: number | null;
  saas: number;
  oneTime: number;
  total: number;
}

const median = (xs: number[]) => {
  if (!xs.length) return 0;
  const s = [...xs].sort((a, b) => a - b);
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
};

export function oneTimeExcess(days: BillingDay[]) {
  const sorted = [...days].sort((a, b) => a.date.localeCompare(b.date));
  const out = new Map<
    string,
    { usd: number; llmUsd: number; services: string[] }
  >();
  sorted.forEach((day, i) => {
    const services = (day.components?.gcpServices || {}) as Record<
      string,
      number
    >;
    const prior = sorted.slice(Math.max(0, i - ONE_TIME.lookbackDays), i);
    if (prior.length < 7) return; // not enough history to call a spike
    for (const [service, usd] of Object.entries(services)) {
      const base = median(
        prior.map(
          (d) =>
            ((d.components?.gcpServices || {}) as Record<string, number>)[
              service
            ] ?? 0
        )
      );
      const excess = usd - base;
      if (excess >= ONE_TIME.minExcessUsd && usd >= ONE_TIME.multiple * base) {
        const entry = out.get(day.date) || { usd: 0, llmUsd: 0, services: [] };
        entry.usd += excess;
        if (isLlmService(service)) entry.llmUsd += excess;
        entry.services.push(service);
        out.set(day.date, entry);
      }
    }
  });
  return out;
}

/** STT for a day: the FinOps modelled value, or the trailing 7-day mean of it
 * when the producer has not reached that day yet (FinOps lags to D−3). */
function sttFor(date: string, stt: Record<string, number> | null) {
  if (!stt) return null;
  if (stt[date] != null) return stt[date];
  const prior = Object.keys(stt)
    .filter((d) => d < date)
    .sort()
    .slice(-7);
  return prior.length
    ? prior.reduce((s, d) => s + stt[d], 0) / prior.length
    : null;
}

export function allInCost(
  days: BillingDay[],
  stt: Record<string, number> | null,
  coverage: { openai?: boolean; anthropic?: boolean } = {}
) {
  const oneTime = oneTimeExcess(days);
  const missing: string[] = [];
  if (coverage.openai === false) missing.push("OpenAI invoice");
  if (coverage.anthropic === false) missing.push("Anthropic invoice");
  if (!stt) missing.push("STT model (FinOps)");
  const saas = SAAS_MONTHLY_USD / DAYS_PER_MONTH;
  const daily: CostDay[] = [...days]
    .sort((a, b) => a.date.localeCompare(b.date))
    .map((d) => {
      const c = (d.components || {}) as Record<string, number>;
      const excess = oneTime.get(d.date)?.usd ?? 0;
      const llmExcess = oneTime.get(d.date)?.llmUsd ?? 0;
      const hasComponents = d.components != null;
      const openai = coverage.openai === false ? null : c.openai ?? 0;
      const anthropic = coverage.anthropic === false ? null : c.anthropic ?? 0;
      // Without components the billing total is GCP + invoices already.
      const gcpNet = hasComponents
        ? (c.gcpInfra ?? 0) + (c.vertexLlm ?? 0)
        : d.total;
      const vertexLlm = (c.vertexLlm ?? 0) - llmExcess;
      const gcp = gcpNet - excess - vertexLlm;
      const sttUsd = sttFor(d.date, stt);
      const total =
        gcp +
        vertexLlm +
        (openai ?? 0) +
        (anthropic ?? 0) +
        (sttUsd ?? 0) +
        saas;
      return {
        date: d.date,
        gcp,
        vertexLlm,
        openai,
        anthropic,
        stt: sttUsd,
        saas,
        oneTime: excess,
        total,
      };
    });
  return { daily, oneTime, missing };
}
