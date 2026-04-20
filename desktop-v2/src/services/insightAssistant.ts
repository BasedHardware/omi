/**
 * InsightAssistant — TypeScript port of
 * `desktop/Desktop/Sources/ProactiveAssistants/Assistants/Insight/InsightAssistant.swift`.
 *
 * Two-phase Gemini tool-calling pipeline:
 *
 * Phase 1 (text-only, max 7 iter): activity summary + SQL investigation. Model
 *   calls `execute_sql` against the Rewind screenshots DB, then decides to
 *   `request_screenshot` with an ID + findings, or `no_insight`.
 *
 * Phase 2 (single vision conversation, max 5 iter): load the chosen screenshot
 *   image, present it alongside the Phase 1 findings, allow the model to
 *   cross-reference via further `execute_sql` calls, then either
 *   `provide_insight` or `no_insight`.
 *
 * Storage: insights are inserted into the shared `memories` table with
 * `tags = ["tips", "<category>"]`. Local-first, then synced to backend
 * `/v3/memories` with the same tags. The `InsightStore` reads from this
 * table filtered by the "tips" tag.
 */

import { invoke } from "@tauri-apps/api/core";
import { api } from "@/services/api";
import {
  CapturedFrame,
  setFrameHandler,
} from "@/services/proactiveAssistant";
import {
  isAppAllowed,
  useInsightAssistantSettings,
} from "@/services/insightAssistantSettings";
import { useMemoryStore } from "@/stores/memoryStore";
import { useInsightStore } from "@/stores/insightStore";
import { notify } from "@/services/notifications";
import { getScreenshotImage } from "@/services/rewind";

export type InsightCategory = "productivity" | "communication" | "learning" | "other";

export interface ExtractedInsight {
  insight: string;
  headline: string | null;
  reasoning: string | null;
  category: InsightCategory;
  sourceApp: string;
  confidence: number;
}

export interface InsightExtractionResult {
  hasInsight: boolean;
  insight: ExtractedInsight | null;
  contextSummary: string;
  currentActivity: string;
}

// ---------------------------------------------------------------------------
// Gemini plumbing
// ---------------------------------------------------------------------------

interface GeminiFunctionCall {
  name: string;
  args: Record<string, unknown>;
}

interface GeminiPart {
  text?: string;
  inlineData?: { mimeType: string; data: string };
  functionCall?: GeminiFunctionCall;
  functionResponse?: { name: string; response: { result: string } };
  thoughtSignature?: string;
}

interface GeminiContent {
  role: "user" | "model";
  parts: GeminiPart[];
}

interface GeminiToolDecl {
  name: string;
  description: string;
  parameters: Record<string, unknown>;
}

interface GeminiResponse {
  candidates?: Array<{
    content?: { parts?: GeminiPart[] };
    finishReason?: string;
  }>;
}

const GEMINI_MODEL = "gemini-pro-latest";
const GEMINI_PATH = `/v1/proxy/gemini/models/${GEMINI_MODEL}:generateContent`;

const SCHEMA_APPENDIX =
  "\n\nDATABASE SCHEMA for execute_sql:\n" +
  "screenshots table columns: id INTEGER, timestamp TEXT, app_name TEXT, window_title TEXT, ocr_text TEXT\n" +
  "Note: the underlying column names are snake_case (app_name, window_title, ocr_text, timestamp).";

const PHASE1_TOOLS: GeminiToolDecl[] = [
  {
    name: "execute_sql",
    description:
      "Execute a SQL query on the local screenshots database to investigate screen activity. The screenshots table has: id INTEGER, timestamp TEXT, app_name TEXT, window_title TEXT, ocr_text TEXT. Use this to read OCR text from interesting windows, check what the user was doing, etc. SELECT queries only against the 'screenshots' table. Aggregates (COUNT/SUM/AVG/MIN/MAX) and GROUP BY/ORDER BY/HAVING/WHERE/LIMIT are allowed. Auto-limited to 50 rows.",
    parameters: {
      type: "object",
      properties: {
        query: { type: "string", description: "SQL SELECT query on the screenshots table" },
      },
      required: ["query"],
    },
  },
  {
    name: "request_screenshot",
    description:
      "Request to view a specific screenshot. Call this when you've found something interesting via SQL and want to see the actual screen. Provide the screenshot ID and a summary of your findings so far.",
    parameters: {
      type: "object",
      properties: {
        screenshot_id: {
          type: "integer",
          description: "The screenshot ID from the screenshots table",
        },
        findings: {
          type: "string",
          description:
            "Summary of what you found during investigation — what app, what OCR text caught your attention, and what you suspect might be worth highlighting",
        },
      },
      required: ["screenshot_id", "findings"],
    },
  },
  {
    name: "no_insight",
    description:
      "Call this when there is nothing worth surfacing as an insight. Nothing qualifies as a specific, non-obvious observation. This ends the analysis.",
    parameters: {
      type: "object",
      properties: {
        context_summary: { type: "string", description: "Brief summary of what user is looking at" },
        current_activity: { type: "string", description: "High-level description of user's activity" },
      },
      required: ["context_summary", "current_activity"],
    },
  },
];

const PHASE2_TOOLS: GeminiToolDecl[] = [
  {
    name: "execute_sql",
    description:
      "Cross-reference your findings by querying the database. Use this to check if an issue was resolved in later screenshots, verify context across time, or look up related activity. SELECT queries only against the 'screenshots' table.",
    parameters: {
      type: "object",
      properties: {
        query: { type: "string", description: "SQL SELECT query on the screenshots table" },
      },
      required: ["query"],
    },
  },
  {
    name: "provide_insight",
    description:
      "Call this when you have a specific, non-obvious insight for the user based on the screenshot and your investigation findings. You should cross-reference first using execute_sql to verify the issue is still relevant.",
    parameters: {
      type: "object",
      properties: {
        advice: {
          type: "string",
          description:
            "The insight text (1-2 sentences, max 100 chars). Start with what you noticed, then why it matters.",
        },
        headline: {
          type: "string",
          description:
            "Ultra-short observation (max 5 words) for notification preview.",
        },
        reasoning: {
          type: "string",
          description: "Brief explanation of why this insight is relevant",
        },
        category: {
          type: "string",
          description: "Category of insight",
          enum: ["productivity", "communication", "learning", "other"],
        },
        source_app: { type: "string", description: "App where context was observed" },
        confidence: {
          type: "number",
          description: "Confidence score 0.0-1.0",
        },
        context_summary: { type: "string", description: "Brief summary of what user is looking at" },
        current_activity: { type: "string", description: "High-level description of user's activity" },
      },
      required: [
        "advice",
        "headline",
        "category",
        "source_app",
        "confidence",
        "context_summary",
        "current_activity",
      ],
    },
  },
  {
    name: "no_insight",
    description:
      "Call this when the screenshot doesn't reveal anything worth surfacing, or when cross-referencing shows the issue was already resolved.",
    parameters: {
      type: "object",
      properties: {
        context_summary: { type: "string", description: "Brief summary of what user is looking at" },
        current_activity: { type: "string", description: "High-level description of user's activity" },
      },
      required: ["context_summary", "current_activity"],
    },
  },
];

async function callGemini(
  systemPrompt: string,
  contents: GeminiContent[],
  tools: GeminiToolDecl[],
  forceToolCall: boolean,
): Promise<GeminiPart[]> {
  const body = {
    system_instruction: { parts: [{ text: systemPrompt }] },
    contents,
    tools: [{ function_declarations: tools }],
    tool_config: forceToolCall
      ? { function_calling_config: { mode: "ANY" } }
      : { function_calling_config: { mode: "AUTO" } },
    generationConfig: { maxOutputTokens: 2048, temperature: 0.2 },
  };
  const resp = await api.post<GeminiResponse>(GEMINI_PATH, body);
  return resp?.candidates?.[0]?.content?.parts ?? [];
}

// ---------------------------------------------------------------------------
// Module state
// ---------------------------------------------------------------------------

const MAX_PREVIOUS_INSIGHTS = 50;
const MAX_INSIGHTS_IN_PROMPT = 30;
const MAX_SQL_PER_PHASE = 8;
const PHASE1_MAX_ITER = 7;
const PHASE2_MAX_ITER = 5;

const previousInsights: ExtractedInsight[] = [];
let lastAnalysisAt = 0;
let inflight = false;
let handlerInstalled = false;

// ---------------------------------------------------------------------------
// Hydration (previous insights from local DB)
// ---------------------------------------------------------------------------

interface LocalMemoryRow {
  id: string;
  content: string;
  category: string;
  source_app?: string | null;
  tags_json?: string | null;
  headline?: string | null;
  reasoning?: string | null;
  confidence?: number | null;
}

async function hydratePreviousInsights(): Promise<void> {
  try {
    const rows = await invoke<LocalMemoryRow[]>("get_memories_by_tag", {
      tag: "tips",
      limit: MAX_PREVIOUS_INSIGHTS,
    });
    if (!Array.isArray(rows)) return;
    for (const row of rows) {
      const category = inferCategoryFromTags(row.tags_json ?? null);
      previousInsights.push({
        insight: row.content,
        headline: row.headline ?? null,
        reasoning: row.reasoning ?? null,
        category,
        sourceApp: row.source_app ?? "",
        confidence: row.confidence ?? 0,
      });
    }
    if (previousInsights.length > 0) {
      console.info(
        `[InsightAssistant] hydrated ${previousInsights.length} previous tips for dedup`,
      );
    }
  } catch (err) {
    console.warn("[InsightAssistant] hydrate failed:", err);
  }
}

function inferCategoryFromTags(tagsJson: string | null): InsightCategory {
  if (!tagsJson) return "other";
  try {
    const arr = JSON.parse(tagsJson);
    if (!Array.isArray(arr)) return "other";
    for (const t of arr) {
      if (typeof t !== "string") continue;
      const lower = t.toLowerCase();
      if (lower === "productivity" || lower === "communication" || lower === "learning") {
        return lower as InsightCategory;
      }
    }
  } catch {
    // ignored
  }
  return "other";
}

// ---------------------------------------------------------------------------
// Activity summary
// ---------------------------------------------------------------------------

interface SqlRows {
  columns: string[];
  rows: unknown[][];
  truncated?: boolean;
}

function parseSqlResponse(raw: string): SqlRows | null {
  const stripped = raw.endsWith("...truncated")
    ? raw.slice(0, -"...truncated".length)
    : raw;
  try {
    const parsed = JSON.parse(stripped) as SqlRows;
    if (!parsed || !Array.isArray(parsed.columns) || !Array.isArray(parsed.rows)) {
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
}

async function buildActivitySummary(): Promise<string> {
  const sql =
    "SELECT app_name, window_title, COUNT(*) as cnt FROM screenshots " +
    "WHERE timestamp > datetime('now', '-30 minutes') " +
    "GROUP BY app_name, window_title ORDER BY cnt DESC LIMIT 30";
  let raw: string;
  try {
    raw = await invoke<string>("execute_insight_sql", { query: sql });
  } catch (err) {
    console.warn("[InsightAssistant] activity summary SQL failed:", err);
    return "";
  }
  if (raw.startsWith("REJECTED:")) {
    console.warn("[InsightAssistant] activity summary rejected:", raw);
    return "";
  }
  const parsed = parseSqlResponse(raw);
  if (!parsed || parsed.rows.length === 0) return "";

  const totalScreenshots = parsed.rows.reduce((acc, row) => {
    const cnt = Number(row[2] ?? 0);
    return acc + (Number.isFinite(cnt) ? cnt : 0);
  }, 0);

  const lines: string[] = [];
  lines.push(`ACTIVITY SUMMARY (last 30 min, ${totalScreenshots} screenshots):`);
  lines.push("App | Window | Screenshots | Est. Duration");
  lines.push("-".repeat(60));
  for (const row of parsed.rows) {
    const app = String(row[0] ?? "Unknown");
    const window = String(row[1] ?? "");
    const count = Number(row[2] ?? 0);
    const estMin = (count / 60).toFixed(1);
    const windowDisplay = window ? window.slice(0, 50) : "(no title)";
    lines.push(`${app} | ${windowDisplay} | ${count} | ${estMin} min`);
  }
  return lines.join("\n");
}

// ---------------------------------------------------------------------------
// Prompt helpers
// ---------------------------------------------------------------------------

function timeLabel(d: Date): string {
  const hours = d.getHours();
  const mins = d.getMinutes();
  const ampm = hours >= 12 ? "PM" : "AM";
  const h12 = hours % 12 === 0 ? 12 : hours % 12;
  const mm = String(mins).padStart(2, "0");
  const weekday = d.toLocaleDateString(undefined, { weekday: "long" });
  return `${h12}:${mm} ${ampm}, ${weekday}`;
}

function buildPhase1Prompt(
  frame: CapturedFrame,
  activitySummary: string,
): string {
  let prompt = `CURRENT APP: ${frame.appName}.`;
  if (frame.windowTitle) {
    prompt += ` Window: "${frame.windowTitle}".`;
  }
  prompt += ` Time: ${timeLabel(frame.captureTime)}.`;

  if (activitySummary) {
    prompt += "\n\n" + activitySummary;
  }

  if (previousInsights.length > 0) {
    prompt += "\n\nPREVIOUSLY PROVIDED INSIGHTS (do not repeat these or semantically similar):\n";
    const slice = previousInsights.slice(0, MAX_INSIGHTS_IN_PROMPT);
    slice.forEach((a, i) => {
      prompt += `${i + 1}. ${a.insight}`;
      if (a.reasoning) prompt += ` (Reasoning: ${a.reasoning})`;
      prompt += "\n";
    });
    prompt += "\nOnly provide an insight if there's a genuinely NEW non-obvious observation not covered above.";
  } else {
    prompt += "\n\nOnly provide an insight if there's something specific and non-obvious that would help.";
  }

  prompt +=
    "\n\nInvestigate the activity summary. Scan OCR from the TOP 3-5 apps (not just the dominant one) — the best insights often come from browsers, communication apps, and notes, not just the app with the most screenshots. Skip apps with < 10 screenshots. When you've identified the most interesting screenshot, call request_screenshot with the ID and your findings. Or call no_insight if nothing qualifies.";

  return prompt;
}

// ---------------------------------------------------------------------------
// Tool helpers
// ---------------------------------------------------------------------------

async function runInsightSql(query: string): Promise<string> {
  try {
    return await invoke<string>("execute_insight_sql", { query });
  } catch (err) {
    return `ERROR: ${String(err)}`;
  }
}

function parseScreenshotId(args: Record<string, unknown>): number | null {
  const raw = args.screenshot_id;
  if (typeof raw === "number" && Number.isFinite(raw)) return Math.trunc(raw);
  if (typeof raw === "string") {
    const n = Number.parseInt(raw, 10);
    return Number.isFinite(n) ? n : null;
  }
  return null;
}

function parseProvideInsight(
  args: Record<string, unknown>,
  fallbackApp: string,
): InsightExtractionResult {
  // The Gemini tool payload keeps the legacy "advice" field name on the wire
  // (matching the Swift ExtractedInsight coding keys) so we decode it the
  // same way here.
  const insightText = typeof args.advice === "string" ? args.advice : "";
  const headline = typeof args.headline === "string" ? args.headline : null;
  const reasoning = typeof args.reasoning === "string" ? args.reasoning : null;
  const categoryStr = typeof args.category === "string" ? args.category.toLowerCase() : "other";
  const category: InsightCategory = ["productivity", "communication", "learning", "other"].includes(
    categoryStr,
  )
    ? (categoryStr as InsightCategory)
    : "other";
  const sourceApp = typeof args.source_app === "string" && args.source_app ? args.source_app : fallbackApp;
  const contextSummary = typeof args.context_summary === "string" ? args.context_summary : "";
  const currentActivity = typeof args.current_activity === "string" ? args.current_activity : "";

  let confidence = 0.5;
  const c = args.confidence;
  if (typeof c === "number" && Number.isFinite(c)) confidence = c;
  else if (typeof c === "string") {
    const n = Number.parseFloat(c);
    if (Number.isFinite(n)) confidence = n;
  }

  return {
    hasInsight: true,
    insight: {
      insight: insightText,
      headline,
      reasoning,
      category,
      sourceApp,
      confidence,
    },
    contextSummary,
    currentActivity,
  };
}

// ---------------------------------------------------------------------------
// Core two-phase extraction
// ---------------------------------------------------------------------------

async function loadScreenshotBase64(id: number): Promise<string | null> {
  try {
    const data = await getScreenshotImage(id);
    return typeof data === "string" && data.length > 0 ? data : null;
  } catch (err) {
    console.warn("[InsightAssistant] get_screenshot_image failed:", err);
    return null;
  }
}

async function runTwoPhaseExtraction(
  frame: CapturedFrame,
): Promise<InsightExtractionResult | null> {
  const settings = useInsightAssistantSettings.getState();
  const systemPrompt = settings.analysisPrompt + SCHEMA_APPENDIX;

  const activitySummary = await buildActivitySummary();
  const phase1Prompt = buildPhase1Prompt(frame, activitySummary);

  // -------- PHASE 1 --------
  const contents: GeminiContent[] = [
    { role: "user", parts: [{ text: phase1Prompt }] },
  ];

  let chosenScreenshotId: number | null = null;
  let investigationFindings: string | null = null;
  let sqlCountPhase1 = 0;

  for (let iter = 0; iter < PHASE1_MAX_ITER; iter++) {
    let parts: GeminiPart[];
    try {
      parts = await callGemini(systemPrompt, contents, PHASE1_TOOLS, iter === 0);
    } catch (err) {
      console.warn("[InsightAssistant] Phase 1 Gemini call failed:", err);
      return null;
    }
    const fnCall = parts.find((p) => p.functionCall)?.functionCall;
    if (!fnCall) {
      console.info("[InsightAssistant] Phase 1 — no tool call on iter", iter);
      break;
    }
    const args = (fnCall.args ?? {}) as Record<string, unknown>;

    if (fnCall.name === "execute_sql") {
      if (sqlCountPhase1 >= MAX_SQL_PER_PHASE) {
        contents.push({ role: "model", parts: [{ functionCall: fnCall }] });
        contents.push({
          role: "user",
          parts: [
            {
              functionResponse: {
                name: fnCall.name,
                response: {
                  result:
                    "ERROR: too many SQL calls in this phase — choose a screenshot with request_screenshot or call no_insight.",
                },
              },
            },
          ],
        });
        continue;
      }
      const query = String(args.query ?? "");
      sqlCountPhase1++;
      const result = await runInsightSql(query);
      contents.push({ role: "model", parts: [{ functionCall: fnCall }] });
      contents.push({
        role: "user",
        parts: [
          {
            functionResponse: {
              name: fnCall.name,
              response: { result },
            },
          },
        ],
      });
      continue;
    }

    if (fnCall.name === "request_screenshot") {
      const id = parseScreenshotId(args);
      investigationFindings = typeof args.findings === "string" ? args.findings : "";
      if (id != null) {
        chosenScreenshotId = id;
      }
      break;
    }

    if (fnCall.name === "no_insight") {
      return {
        hasInsight: false,
        insight: null,
        contextSummary: String(args.context_summary ?? "No context"),
        currentActivity: String(args.current_activity ?? "Unknown"),
      };
    }

    console.info("[InsightAssistant] Phase 1 unknown tool:", fnCall.name);
    break;
  }

  if (chosenScreenshotId == null || investigationFindings == null) {
    console.info("[InsightAssistant] Phase 1 exhausted without request_screenshot");
    return null;
  }

  // -------- PHASE 2 --------
  const imageBase64 = await loadScreenshotBase64(chosenScreenshotId);
  if (!imageBase64) {
    console.info(
      "[InsightAssistant] Phase 2 — failed to load screenshot",
      chosenScreenshotId,
    );
    return null;
  }

  const phase2Prompt =
    `INVESTIGATION FINDINGS:\n${investigationFindings}\n\n` +
    "The screenshot below is from the app/window identified during investigation.\n\n" +
    "Before surfacing an insight, CROSS-REFERENCE your findings:\n" +
    "- Use execute_sql to check if this issue was resolved in later screenshots\n" +
    "- Check if the user moved on to something else (the issue may be stale)\n" +
    "- Verify the context is still relevant by looking at nearby timestamps\n\n" +
    "Then call provide_insight if the observation is still valid, or no_insight if it was resolved or is no longer relevant.";

  const phase2Contents: GeminiContent[] = [
    {
      role: "user",
      parts: [
        { text: phase2Prompt },
        { inlineData: { mimeType: "image/jpeg", data: imageBase64 } },
      ],
    },
  ];

  let sqlCountPhase2 = 0;

  for (let iter = 0; iter < PHASE2_MAX_ITER; iter++) {
    let parts: GeminiPart[];
    try {
      parts = await callGemini(systemPrompt, phase2Contents, PHASE2_TOOLS, iter === 0);
    } catch (err) {
      console.warn("[InsightAssistant] Phase 2 Gemini call failed:", err);
      return null;
    }
    const fnCall = parts.find((p) => p.functionCall)?.functionCall;
    if (!fnCall) {
      console.info("[InsightAssistant] Phase 2 — no tool call on iter", iter);
      break;
    }
    const args = (fnCall.args ?? {}) as Record<string, unknown>;

    if (fnCall.name === "execute_sql") {
      if (sqlCountPhase2 >= MAX_SQL_PER_PHASE) {
        phase2Contents.push({ role: "model", parts: [{ functionCall: fnCall }] });
        phase2Contents.push({
          role: "user",
          parts: [
            {
              functionResponse: {
                name: fnCall.name,
                response: {
                  result:
                    "ERROR: too many SQL calls in this phase — call provide_insight or no_insight now.",
                },
              },
            },
          ],
        });
        continue;
      }
      const query = String(args.query ?? "");
      sqlCountPhase2++;
      const result = await runInsightSql(query);
      phase2Contents.push({ role: "model", parts: [{ functionCall: fnCall }] });
      phase2Contents.push({
        role: "user",
        parts: [
          {
            functionResponse: {
              name: fnCall.name,
              response: { result },
            },
          },
        ],
      });
      continue;
    }

    if (fnCall.name === "provide_insight") {
      return parseProvideInsight(args, frame.appName);
    }

    if (fnCall.name === "no_insight") {
      return {
        hasInsight: false,
        insight: null,
        contextSummary: String(args.context_summary ?? "No context"),
        currentActivity: String(args.current_activity ?? "Unknown"),
      };
    }

    console.info("[InsightAssistant] Phase 2 unknown tool:", fnCall.name);
    break;
  }

  return null;
}

// ---------------------------------------------------------------------------
// Persistence (local-first, backend sync)
// ---------------------------------------------------------------------------

interface BackendMemoryResponse {
  id: string;
  message?: string;
}

async function persistInsight(
  insight: ExtractedInsight,
  frame: CapturedFrame,
  result: InsightExtractionResult,
): Promise<void> {
  const id =
    typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
      ? crypto.randomUUID()
      : `ins_${Date.now()}_${Math.floor(Math.random() * 1e9)}`;

  const tags = ["tips", insight.category];
  const tagsJson = JSON.stringify(tags);

  try {
    await invoke<string>("insert_memory", {
      input: {
        id,
        content: insight.insight,
        category: "system",
        visibility: "private",
        confidence: insight.confidence,
        source_app: insight.sourceApp,
        window_title: frame.windowTitle,
        context_summary: result.contextSummary,
        current_activity: result.currentActivity,
        headline: insight.headline,
        reasoning: insight.reasoning,
        tags_json: tagsJson,
        screenshot_id: frame.dbId,
      },
    });
  } catch (err) {
    console.warn("[InsightAssistant] local insert failed:", err);
    return;
  }

  // Push the freshly-created insight into the in-memory store so the Insights
  // page updates immediately — no need to wait on the next refresh.
  try {
    useInsightStore.getState().prependLocalInsight({
      id,
      content: insight.insight,
      category: insight.category,
      sourceApp: insight.sourceApp,
      confidence: insight.confidence,
      headline: insight.headline,
      reasoning: insight.reasoning,
      contextSummary: result.contextSummary,
      currentActivity: result.currentActivity,
      createdAt: new Date().toISOString(),
    });
  } catch (err) {
    console.warn("[InsightAssistant] insightStore prepend failed:", err);
  }

  const payload = {
    content: insight.insight,
    visibility: "private",
    category: "system",
    confidence: insight.confidence,
    source_app: insight.sourceApp,
    context_summary: result.contextSummary,
    tags,
    reasoning: insight.reasoning ?? "",
    current_activity: result.currentActivity,
    source: "screenshot",
    window_title: frame.windowTitle,
    headline: insight.headline ?? "",
  };

  try {
    const resp = await api.post<BackendMemoryResponse>("/v3/memories", payload);
    if (resp?.id) {
      try {
        await invoke("set_memory_backend_id", { id, backendId: resp.id });
      } catch (err) {
        console.warn("[InsightAssistant] set_memory_backend_id failed:", err);
      }
    }
  } catch (err) {
    console.warn("[InsightAssistant] backend sync failed:", err);
  }

  try {
    await useMemoryStore.getState().loadMemories();
  } catch (err) {
    console.warn("[InsightAssistant] loadMemories refresh failed:", err);
  }
}

// ---------------------------------------------------------------------------
// Frame handler
// ---------------------------------------------------------------------------

async function handleFrame(frame: CapturedFrame): Promise<void> {
  if (inflight) return;
  const settings = useInsightAssistantSettings.getState();
  if (!settings.enabled) return;
  if (!isAppAllowed(frame.appName)) return;

  const intervalMs = settings.extractionIntervalSeconds * 1000;
  if (Date.now() - lastAnalysisAt < intervalMs) return;

  inflight = true;
  lastAnalysisAt = Date.now();
  try {
    console.info(`[InsightAssistant] analyzing frame app=${frame.appName}`);
    const result = await runTwoPhaseExtraction(frame);
    if (!result || !result.hasInsight || !result.insight) return;

    const insight = result.insight;
    if (insight.confidence < settings.minConfidence) {
      console.info(
        `[InsightAssistant] filtered ${(insight.confidence * 100).toFixed(0)}% < ${(settings.minConfidence * 100).toFixed(0)}%: "${insight.insight}"`,
      );
      return;
    }

    console.info(
      `[InsightAssistant] extracted [${insight.category}] "${insight.insight}" conf=${insight.confidence.toFixed(2)}`,
    );

    previousInsights.unshift(insight);
    if (previousInsights.length > MAX_PREVIOUS_INSIGHTS) {
      previousInsights.pop();
    }

    await persistInsight(insight, frame, result);

    if (settings.notificationsEnabled) {
      const body = insight.headline || insight.insight;
      void notify("Insight", body);
    }
  } catch (err) {
    console.warn("[InsightAssistant] handleFrame error:", err);
  } finally {
    inflight = false;
  }
}

// ---------------------------------------------------------------------------
// Lifecycle
// ---------------------------------------------------------------------------

export function initInsightAssistant(): void {
  if (handlerInstalled) return;
  void hydratePreviousInsights();
  setFrameHandler((frame) => {
    void handleFrame(frame);
  });
  handlerInstalled = true;
  console.info("[InsightAssistant] started");
}

export function stopInsightAssistant(): void {
  // proactiveAssistant only supports a single frame handler; replacing it with
  // a no-op effectively detaches us until another caller registers a handler.
  if (handlerInstalled) {
    setFrameHandler(() => {});
    handlerInstalled = false;
  }
  lastAnalysisAt = 0;
  inflight = false;
  previousInsights.length = 0;
  console.info("[InsightAssistant] stopped");
}
