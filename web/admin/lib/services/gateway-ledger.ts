import { AggregateField } from "firebase-admin/firestore";
import { getDb } from "@/lib/firebase/admin";
import { getPayload, setPayload } from "@/lib/payload-cache";

// Per-attempt LLM spend from the gateway's Firestore ledger.
//
// `llm_gateway_attempts` is a top-level collection with ~200k immutable docs a
// day, so nothing here ever reads documents: every number comes from a
// server-side aggregation (`sum` + `count`) with equality filters only. Unlike
// plain document queries (whose equality filters merge single-field indexes —
// the `scripts/chat_agent_cost_report.py` pattern), SUM aggregations require
// composite indexes that include the summed field. The registry entries cover
// (date, [feature|provider], [payer], estimated_cost_micro_usd); if the
// payer-scoped variant (which drops BYOK attempts) is rejected for a missing
// index, we retry without it and mark the day `byokIncluded` rather than
// dropping the day.
//
// Costs are stored as integer micro-USD and converted to USD at the edge.

const COLLECTION = "llm_gateway_attempts";
const COST_FIELD = "estimated_cost_micro_usd";
const CACHE_VERSION = "v1";
const MICRO_USD_PER_USD = 1_000_000;
const MAX_CONCURRENCY = 8;

// Days this recent may still be filling (late-arriving attempts, retries), so
// their cached aggregation is never trusted.
const VOLATILE_DAYS = 3;

const PROVIDERS = ["openai", "anthropic", "gemini", "openrouter", "perplexity"] as const;

export type FeatureClass = "desktop" | "mobile" | "sharedExtraction" | "sharedChat";

// Which platform's ledger spend a gateway feature represents. `desktop` is
// spend only the desktop app can produce; `sharedExtraction` / `sharedChat` are
// features both platforms drive, and get split by the usage-weighted shares
// downstream. Features absent from this map fall into `unknown`.
//
// The keys are the values of the `X-Omi-LLM-Feature` header the backend sends
// to the gateway. Most come from `backend/utils/llm/model_config.py`, but a
// live usage context wins over the model_config feature
// (`_gateway_usage_headers` in backend/utils/llm/gateway_client.py), so the
// coarse `Features.*` names from `utils/llm/usage_tracker.py` reach the ledger
// too and are mapped here as well.
export const FEATURE_CLASS: Record<string, FeatureClass> = {
  // Desktop-only.
  desktop_proactive_extraction: "desktop",
  desktop_proactive_reasoning: "desktop",
  // Structured lane of the desktop chat router — the automation planner and
  // the local-agent loop (routers/desktop_chat.py `_gateway_feature_for_lane`).
  // No mobile surface selects that lane.
  chat_structured: "desktop",
  // Workstream adjudication runs inside conversation processing on any
  // platform, but only fires when the user already has open workstreams, and
  // workstreams are created only by the desktop "Work on this with Omi"
  // surface (no mobile UI exists for them), so the spend is desktop users'.
  workstream_association: "desktop",

  // Chat-shaped, shared across platforms.
  chat_agent: "sharedChat",
  chat_responses: "sharedChat",
  chat_extraction: "sharedChat",
  chat_graph: "sharedChat",
  persona_chat: "sharedChat",
  persona_chat_premium: "sharedChat",
  fair_use: "sharedChat",
  // `Features.CHAT` usage context (routers/chat.py, chat_sessions.py,
  // utils/llm/chat.py, utils/retrieval/graph.py) — overrides the finer
  // chat_responses / chat_graph labels on the wire.
  chat: "sharedChat",
  // `Features.PERSONA` usage context wraps persona chat streaming as well as
  // persona prompt generation; chat is the dominant spend, so it is classed
  // with the other persona chat features.
  persona: "sharedChat",
  public_shared_conversation_chat: "sharedChat",

  // Extraction-shaped, shared across platforms.
  conv_action_items: "sharedExtraction",
  conv_structure: "sharedExtraction",
  conv_app_result: "sharedExtraction",
  daily_summary: "sharedExtraction",
  external_structure: "sharedExtraction",
  memories: "sharedExtraction",
  x_memory_extraction_flex: "sharedExtraction",
  learnings: "sharedExtraction",
  memory_conflict: "sharedExtraction",
  memory_conflict_flex: "sharedExtraction",
  knowledge_graph: "sharedExtraction",
  memory_l1: "sharedExtraction",
  memory_l2: "sharedExtraction",
  memory_l2_flex: "sharedExtraction",
  goals: "sharedExtraction",
  goals_advice: "sharedExtraction",
  notifications: "sharedExtraction",
  proactive_notification: "sharedExtraction",
  what_matters_now: "sharedExtraction",
  openglass: "sharedExtraction",
  app_generator: "sharedExtraction",
  persona_clone: "sharedExtraction",
  conv_app_select: "sharedExtraction",
  conv_folder: "sharedExtraction",
  conv_discard: "sharedExtraction",
  daily_summary_simple: "sharedExtraction",
  memory_category: "sharedExtraction",
  smart_glasses: "sharedExtraction",
  session_titles: "sharedExtraction",
  followup: "sharedExtraction",
  onboarding: "sharedExtraction",
  app_integration: "sharedExtraction",
  trends: "sharedExtraction",
  translation: "sharedExtraction",
  wrapped_analysis: "sharedExtraction",
  web_search: "sharedExtraction",
  // `Features.*` usage-context names that override the model_config feature.
  conversation_processing: "sharedExtraction",
  conv_apps: "sharedExtraction",
  realtime_integrations: "sharedExtraction",
  subscription_notification: "sharedExtraction",
  // Gateway-side fallback label for /v1/images/generations when the caller
  // sent no feature header; the only product surface reaching that endpoint is
  // the app/persona image generator, which is not desktop-specific.
  image_generation: "sharedExtraction",
  // Shadow comparison runs duplicate the conversation extraction calls and
  // cost real money (utils/llm/conversation_processing.py).
  "conversation_structure.extract.shadow": "sharedExtraction",
  "conversation_action_items.extract.shadow": "sharedExtraction",
};

export interface GatewayLedgerDay {
  date: string; // YYYY-MM-DD
  totalUsd: number;
  byProvider: Record<string, number>;
  byClass: {
    desktop: number;
    mobile: number;
    sharedExtraction: number;
    sharedChat: number;
    unknown: number;
  };
  attemptCount: number;
  byokIncluded: boolean; // true when the payer filter had to be dropped
}

function round(v: number): number {
  return Math.round(v * 100) / 100;
}

function microToUsd(micro: number): number {
  return round((Number.isFinite(micro) ? micro : 0) / MICRO_USD_PER_USD);
}

function cacheKey(date: string): string {
  return `gateway-ledger:${CACHE_VERSION}:${date}`;
}

function formatDate(d: Date): string {
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}-${String(d.getUTCDate()).padStart(2, "0")}`;
}

// Oldest day still considered volatile: anything on or after this recomputes.
function volatileCutoff(): string {
  const d = new Date();
  d.setUTCHours(0, 0, 0, 0);
  d.setUTCDate(d.getUTCDate() - VOLATILE_DAYS);
  return formatDate(d);
}

type Filter = [field: string, value: string];

interface AggResult {
  micro: number;
  count: number;
}

// One global gate over every aggregation this module issues, so the in-flight
// count stays bounded no matter how many days fan out at once. Aggregations are
// cheap per call but a whole window is hundreds of them, and unbounded parallel
// issue trips gRPC stream limits long before it saturates Firestore.
let inFlight = 0;
const waiting: Array<() => void> = [];

async function withSlot<T>(fn: () => Promise<T>): Promise<T> {
  if (inFlight >= MAX_CONCURRENCY) {
    await new Promise<void>((resolve) => waiting.push(resolve));
  }
  inFlight++;
  try {
    return await fn();
  } finally {
    inFlight--;
    waiting.shift()?.();
  }
}

async function aggregate(filters: Filter[]): Promise<AggResult> {
  return withSlot(() => runAggregate(filters));
}

async function runAggregate(filters: Filter[]): Promise<AggResult> {
  let query: FirebaseFirestore.Query = getDb().collection(COLLECTION);
  for (const [field, value] of filters) query = query.where(field, "==", value);
  const snap = await query
    .aggregate({
      micro: AggregateField.sum(COST_FIELD),
      count: AggregateField.count(),
    })
    .get();
  const data = snap.data() as { micro?: number; count?: number };
  return { micro: Number(data.micro ?? 0), count: Number(data.count ?? 0) };
}

// The ledger records BYOK attempts (user-supplied keys) alongside Omi-paid
// ones. We want Omi-paid only; if that filter can't be served we take the
// superset and say so.
function dayFilters(date: string, payerScoped: boolean, extra?: Filter): Filter[] {
  const filters: Filter[] = [["date", date]];
  if (extra) filters.push(extra);
  if (payerScoped) filters.push(["payer", "omi"]);
  return filters;
}

async function computeDay(date: string): Promise<GatewayLedgerDay | null> {
  // Probe with the payer filter first; a rejection (missing index) downgrades
  // the whole day to the BYOK-inclusive superset.
  let payerScoped = true;
  let total: AggResult;
  try {
    total = await aggregate(dayFilters(date, true));
  } catch (err) {
    console.warn(`gateway ledger: payer-scoped aggregation rejected for ${date}, retrying without it:`, err);
    payerScoped = false;
    try {
      total = await aggregate(dayFilters(date, false));
    } catch (err2) {
      console.error(`gateway ledger: aggregation failed for ${date}:`, err2);
      return null;
    }
  }

  const featureNames = Object.keys(FEATURE_CLASS);
  let parts: AggResult[];
  try {
    parts = await Promise.all([
      ...PROVIDERS.map((p) => aggregate(dayFilters(date, payerScoped, ["provider", p]))),
      ...featureNames.map((f) => aggregate(dayFilters(date, payerScoped, ["feature", f]))),
    ]);
  } catch (err) {
    console.error(`gateway ledger: per-slice aggregation failed for ${date}:`, err);
    return null;
  }

  const byProvider: Record<string, number> = {};
  PROVIDERS.forEach((p, i) => {
    byProvider[p] = microToUsd(parts[i].micro);
  });

  const byClass = {
    desktop: 0,
    mobile: 0,
    sharedExtraction: 0,
    sharedChat: 0,
    unknown: 0,
  };
  let knownMicro = 0;
  featureNames.forEach((feature, i) => {
    const micro = parts[PROVIDERS.length + i].micro;
    knownMicro += micro;
    byClass[FEATURE_CLASS[feature]] += micro;
  });

  const totalMicro = total.micro;
  const unknownMicro = Math.max(0, totalMicro - knownMicro);

  return {
    date,
    totalUsd: microToUsd(totalMicro),
    byProvider,
    byClass: {
      desktop: microToUsd(byClass.desktop),
      mobile: microToUsd(byClass.mobile),
      sharedExtraction: microToUsd(byClass.sharedExtraction),
      sharedChat: microToUsd(byClass.sharedChat),
      unknown: microToUsd(unknownMicro),
    },
    attemptCount: total.count,
    byokIncluded: !payerScoped,
  };
}

// Per-day results for `dates`, cached per day because ledger docs are
// immutable once a day has settled. Returns null only when every requested day
// failed — a partially covered window is still useful (days without ledger data
// simply keep the static shares downstream).
export async function fetchGatewayLedgerDays(dates: string[]): Promise<GatewayLedgerDay[] | null> {
  if (dates.length === 0) return null;
  const cutoff = volatileCutoff();

  const cached = await Promise.all(
    dates.map(async (date) => {
      if (date >= cutoff) return null; // still filling; always recompute
      const hit = await getPayload<GatewayLedgerDay>(cacheKey(date));
      return hit?.data ?? null;
    }),
  );

  const missing: number[] = [];
  dates.forEach((_, i) => {
    if (!cached[i]) missing.push(i);
  });

  // Days run together; `aggregate` holds the global in-flight bound.
  const computed = await Promise.all(
    missing.map(async (i) => {
      const day = await computeDay(dates[i]);
      if (day) await setPayload(cacheKey(dates[i]), day);
      return day;
    }),
  );

  const out: GatewayLedgerDay[] = [];
  const byIndex = new Map(missing.map((idx, k) => [idx, computed[k]]));
  dates.forEach((_, i) => {
    const day = cached[i] ?? byIndex.get(i) ?? null;
    if (day) out.push(day);
  });

  return out.length > 0 ? out : null;
}
