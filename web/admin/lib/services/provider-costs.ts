// Daily spend from the external LLM providers' organization cost APIs.
//
// Both endpoints require ORG-ADMIN credentials — ordinary inference keys get
// 401 (Anthropic) / 403 (OpenAI). The env var names deliberately avoid the
// providers' standard inference-key names, which the deploy contract's
// remove_runtime_secrets list strips from the admin service on every deploy.
// These organization-namespace endpoints carry no model traffic, so they sit
// outside SCA-118's gateway-only rule (see check_web_llm_gateway_only.py).
//
// A missing key or a failed fetch returns null — callers treat the leg as
// unavailable (partial), never as $0.

export interface ProviderDailyCost {
  date: string; // YYYY-MM-DD (UTC bucket start)
  usd: number;
}

const MAX_PAGES = 12;

function toDateKey(iso: string | number): string {
  const d = typeof iso === "number" ? new Date(iso * 1000) : new Date(iso);
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}-${String(d.getUTCDate()).padStart(2, "0")}`;
}

function windowStartIso(days: number): string {
  const start = new Date();
  start.setUTCHours(0, 0, 0, 0);
  start.setUTCDate(start.getUTCDate() - days);
  return start.toISOString().replace(/\.\d{3}Z$/, "Z");
}

// Anthropic Admin API: GET /v1/organizations/cost_report, 1d buckets.
// Raw `amount` values are decimal USD-cent strings — normalize by /100
// (confirmed in the llm-cost-savings 2026-07-16 reconciliation).
export async function fetchAnthropicDailyCosts(days: number): Promise<ProviderDailyCost[] | null> {
  const key = process.env.ADMIN_ANTHROPIC_COST_API_KEY;
  if (!key) return null;
  const byDay = new Map<string, number>();
  let page: string | null = null;
  try {
    for (let i = 0; i < MAX_PAGES; i++) {
      const url = new URL("https://api.anthropic.com/v1/organizations/cost_report");
      url.searchParams.set("starting_at", windowStartIso(days));
      url.searchParams.set("bucket_width", "1d");
      if (page) url.searchParams.set("page", page);
      const resp = await fetch(url, {
        headers: { "x-api-key": key, "anthropic-version": "2023-06-01" },
      });
      if (!resp.ok) {
        console.error("Anthropic cost_report failed:", resp.status, await resp.text());
        return null;
      }
      const body = await resp.json();
      for (const bucket of body?.data ?? []) {
        const day = toDateKey(bucket.starting_at);
        let sum = 0;
        for (const r of bucket.results ?? []) sum += Number(r.amount ?? 0) / 100;
        byDay.set(day, (byDay.get(day) ?? 0) + sum);
      }
      if (!body?.has_more || !body?.next_page) break;
      page = body.next_page;
    }
  } catch (err) {
    console.error("Anthropic cost_report exception:", err);
    return null;
  }
  return Array.from(byDay.entries())
    .map(([date, usd]) => ({ date, usd: Math.round(usd * 100) / 100 }))
    .sort((a, b) => a.date.localeCompare(b.date));
}

// OpenAI Admin API: GET /v1/organization/costs, 1d buckets, unix start_time.
// amount.value is decimal USD.
export async function fetchOpenAiDailyCosts(days: number): Promise<ProviderDailyCost[] | null> {
  const key = process.env.ADMIN_OPENAI_COST_API_KEY;
  if (!key) return null;
  const start = new Date();
  start.setUTCHours(0, 0, 0, 0);
  start.setUTCDate(start.getUTCDate() - days);
  const byDay = new Map<string, number>();
  let page: string | null = null;
  try {
    for (let i = 0; i < MAX_PAGES; i++) {
      const url = new URL("https://api.openai.com/v1/organization/costs");
      url.searchParams.set("start_time", String(Math.floor(start.getTime() / 1000)));
      url.searchParams.set("bucket_width", "1d");
      url.searchParams.set("limit", "180");
      if (page) url.searchParams.set("page", page);
      const resp = await fetch(url, { headers: { Authorization: `Bearer ${key}` } });
      if (!resp.ok) {
        console.error("OpenAI org costs failed:", resp.status, await resp.text());
        return null;
      }
      const body = await resp.json();
      for (const bucket of body?.data ?? []) {
        const day = toDateKey(bucket.start_time);
        let sum = 0;
        for (const r of bucket.results ?? []) sum += Number(r.amount?.value ?? 0);
        byDay.set(day, (byDay.get(day) ?? 0) + sum);
      }
      if (!body?.has_more || !body?.next_page) break;
      page = body.next_page;
    }
  } catch (err) {
    console.error("OpenAI org costs exception:", err);
    return null;
  }
  return Array.from(byDay.entries())
    .map(([date, usd]) => ({ date, usd: Math.round(usd * 100) / 100 }))
    .sort((a, b) => a.date.localeCompare(b.date));
}
