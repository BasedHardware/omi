/**
 * TaskAssistant — TypeScript port of
 * `desktop/Desktop/Sources/ProactiveAssistants/Assistants/TaskExtraction/TaskAssistant.swift`.
 *
 * Hooks into the existing proactive frame stream from `proactiveAssistant.ts`
 * (context-switch + 60s fallback). For each frame:
 *
 * 1. Whitelist check (allowed apps + browser-window keywords)
 * 2. Build prompt with active/completed/deleted task context + today's date
 * 3. Run Gemini tool-calling loop (5 tools, max 5 iterations) on
 *    `gemini-pro-latest` via the backend proxy at
 *    `/v1/proxy/gemini/models/.../generateContent`
 * 4. On `extract_task` → validate title (6+ words, proper noun), persist
 *    locally via Rust `upsert_staged_task`, kick off embedding backfill,
 *    POST to backend `/v1/staged-tasks` for cross-device sync.
 *
 * Trigger wiring lives in `services/proactiveTaskTrigger.ts`. This file is
 * the analysis pipeline only.
 */

import { invoke } from "@tauri-apps/api/core";
import { api } from "@/services/api";
import { CapturedFrame } from "@/services/proactiveAssistant";
import {
  embedText,
} from "@/services/embeddingService";
import {
  isAppAllowed,
  isWindowAllowed,
  useTaskAssistantSettings,
} from "@/services/taskAssistantSettings";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface ExtractedTask {
  title: string;
  description: string | null;
  priority: "high" | "medium" | "low";
  source_app: string;
  inferred_deadline: string | null;
  confidence: number;
  tags: string[];
  source_category: string;
  source_subcategory: string;
  relevance_score: number | null;
}

export interface TaskExtractionResult {
  hasNewTask: boolean;
  task: ExtractedTask | null;
  contextSummary: string;
  currentActivity: string;
  searchCount: number;
}

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
    content?: {
      parts?: GeminiPart[];
    };
    finishReason?: string;
  }>;
}

interface SearchHit {
  id: string;
  description: string;
  status: "active" | "completed" | "deleted";
  similarity?: number;
  matchType: "vector" | "fts";
  relevance_score?: number | null;
}

// ---------------------------------------------------------------------------
// Gemini call (proxy)
// ---------------------------------------------------------------------------

const GEMINI_MODEL = "gemini-pro-latest";
const GEMINI_PATH = `/v1/proxy/gemini/models/${GEMINI_MODEL}:generateContent`;

const TOOLS: GeminiToolDecl[] = [
  {
    name: "search_similar",
    description:
      "Search for semantically similar existing tasks using vector similarity. Call this when you see a potential request and want to check for duplicates.",
    parameters: {
      type: "object",
      properties: {
        query: {
          type: "string",
          description: "A concise description of the potential task to search for",
        },
      },
      required: ["query"],
    },
  },
  {
    name: "search_keywords",
    description:
      "Search for existing tasks matching specific keywords. Use this for precise keyword-based matching complementing vector search.",
    parameters: {
      type: "object",
      properties: {
        query: { type: "string", description: "Keywords to search for in existing tasks" },
      },
      required: ["query"],
    },
  },
  {
    name: "no_task_found",
    description:
      "Call this when there is no actionable request on screen. This is the most common outcome (~90% of screenshots). Use for: code editors, terminals, settings, media players, dashboards, or any screen without a direct request from another person or AI.",
    parameters: {
      type: "object",
      properties: {
        context_summary: { type: "string", description: "Brief summary of what the user is looking at" },
        current_activity: { type: "string", description: "What the user is actively doing" },
      },
      required: ["context_summary", "current_activity"],
    },
  },
  {
    name: "extract_task",
    description:
      "Extract a new task that is not already tracked. Call ONLY after searching for duplicates. All fields are required.",
    parameters: {
      type: "object",
      properties: {
        title: {
          type: "string",
          description:
            "Verb-first task title, 6–15 words. MUST name a specific person/project/artifact and a concrete action. If you can't write 6+ specific words, call no_task_found instead.",
        },
        description: { type: "string", description: "Additional context about the task. Empty string if none." },
        priority: { type: "string", description: "Task priority", enum: ["high", "medium", "low"] },
        tags: { type: "array", description: "1-3 relevant tags", items: { type: "string" } },
        source_app: { type: "string", description: "App where the task was found" },
        inferred_deadline: {
          type: "string",
          description:
            "Deadline in yyyy-MM-dd format (e.g. '2025-10-04'). Resolve relative references like 'Thursday' or 'next week' to an actual date. Empty string if no deadline.",
        },
        confidence: { type: "number", description: "Confidence score 0.0-1.0" },
        context_summary: { type: "string", description: "Brief summary of what user is looking at" },
        current_activity: { type: "string", description: "What the user is actively doing" },
        source_category: {
          type: "string",
          description: "Where the task originated",
          enum: [
            "direct_request",
            "self_generated",
            "calendar_driven",
            "reactive",
            "external_system",
            "other",
          ],
        },
        source_subcategory: {
          type: "string",
          description: "Specific origin within category",
          enum: [
            "message", "meeting", "mention", "commitment",
            "idea", "reminder", "goal_subtask",
            "event_prep", "recurring", "deadline",
            "error", "notification", "observation",
            "project_tool", "alert", "documentation", "other",
          ],
        },
        relevance_score: {
          type: "integer",
          description:
            "Where this task ranks relative to existing tasks. 1 = most important/urgent, higher numbers = less important.",
        },
      },
      required: [
        "title", "description", "priority", "tags", "source_app",
        "inferred_deadline", "confidence", "context_summary",
        "current_activity", "source_category", "source_subcategory",
        "relevance_score",
      ],
    },
  },
  {
    name: "reject_task",
    description:
      "Reject task extraction — the potential task is a duplicate, already completed, or was previously rejected by the user.",
    parameters: {
      type: "object",
      properties: {
        reason: { type: "string", description: "Why this task was rejected" },
        context_summary: { type: "string" },
        current_activity: { type: "string" },
      },
      required: ["reason", "context_summary", "current_activity"],
    },
  },
];

async function callGemini(
  systemPrompt: string,
  contents: GeminiContent[],
  forceToolCall: boolean,
): Promise<GeminiPart[]> {
  const body = {
    system_instruction: { parts: [{ text: systemPrompt }] },
    contents,
    tools: [{ function_declarations: TOOLS }],
    tool_config: forceToolCall
      ? { function_calling_config: { mode: "ANY" } }
      : { function_calling_config: { mode: "AUTO" } },
    generationConfig: { maxOutputTokens: 2048, temperature: 0.2 },
  };
  const resp = await api.post<GeminiResponse>(GEMINI_PATH, body);
  return resp?.candidates?.[0]?.content?.parts ?? [];
}

// ---------------------------------------------------------------------------
// Title validation (Swift parity)
// ---------------------------------------------------------------------------

const GENERIC_PATTERNS = [
  "investigate", "check logs", "clean up", "look into",
  "look through", "update to", "fix the", "review the",
  "check the", "modify the", "track the",
];

export function validateTaskTitle(title: string): string | null {
  const trimmed = title.trim();
  if (!trimmed) return "Title is empty";
  const words = trimmed.split(/\s+/);
  if (words.length < 6) return `Title too short (${words.length} words, minimum 6)`;
  const lower = trimmed.toLowerCase();
  for (const p of GENERIC_PATTERNS) {
    if (lower === p || (words.length <= 4 && lower.startsWith(p))) {
      return `Title too generic (matches vague pattern '${p}')`;
    }
  }
  const hasProperNoun = words.slice(1).some((w) => /^[A-Z]/.test(w));
  if (!hasProperNoun) {
    return "Title lacks a specific name (person, project, or app) — no proper nouns found after the verb";
  }
  return null;
}

// ---------------------------------------------------------------------------
// Search executors (call into Rust via invoke)
// ---------------------------------------------------------------------------

interface RustSimilarHit {
  task: { id: string; description: string; deleted: boolean; completed: boolean; relevance_score: number | null };
  similarity: number;
}

async function executeVectorSearch(query: string): Promise<SearchHit[]> {
  try {
    const queryVec = await embedText(query, "RETRIEVAL_QUERY");
    const hits = await invoke<RustSimilarHit[]>("search_similar_staged_tasks", {
      queryEmbedding: Array.from(queryVec),
      topK: 10,
      minSimilarity: 0.3,
    });
    return hits.map((h) => ({
      id: h.task.id,
      description: h.task.description,
      status: h.task.deleted ? "deleted" : h.task.completed ? "completed" : "active",
      similarity: h.similarity,
      matchType: "vector" as const,
      relevance_score: h.task.relevance_score,
    }));
  } catch (err) {
    console.warn("[TaskAssistant] vector search failed:", err);
    return [];
  }
}

interface RustStagedTask {
  id: string;
  description: string;
  deleted: boolean;
  completed: boolean;
  relevance_score: number | null;
}

async function executeKeywordSearch(query: string): Promise<SearchHit[]> {
  try {
    const rows = await invoke<RustStagedTask[]>("search_keywords_staged_tasks", {
      query,
      limit: 10,
    });
    return rows.map((r) => ({
      id: r.id,
      description: r.description,
      status: r.deleted ? "deleted" : r.completed ? "completed" : "active",
      similarity: undefined,
      matchType: "fts" as const,
      relevance_score: r.relevance_score,
    }));
  } catch (err) {
    console.warn("[TaskAssistant] keyword search failed:", err);
    return [];
  }
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

const MESSAGING_APPS = new Set([
  "Telegram", "WhatsApp", "\u200EWhatsApp", "Messages", "Slack", "Discord",
]);

/**
 * Pre-flight whitelist check. Returns true if this frame is worth analyzing.
 * Mirrors `analyze(frame:)` in Swift.
 */
export function shouldAnalyzeFrame(frame: CapturedFrame): boolean {
  const settings = useTaskAssistantSettings.getState();
  if (!settings.enabled) return false;
  const allowedSet = new Set(settings.allowedApps);
  if (!isAppAllowed(frame.appName, allowedSet)) return false;
  if (!isWindowAllowed(frame.appName, frame.windowTitle, settings.browserKeywords)) return false;
  return true;
}

/** Build today's date string for the prompt. */
function todayLabel(): string {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  const weekday = d.toLocaleDateString("en-US", { weekday: "long" });
  return `${y}-${m}-${day} (${weekday})`;
}

async function buildContextBlock(): Promise<string> {
  // Pull recent staged tasks for dedup context. The Swift impl also pulls
  // promoted action_items and goals from the backend; we keep the local
  // staged_tasks slice for now and let the dedup pass handle any cross-pollution.
  let activeBlock = "";
  try {
    const recent = await invoke<RustStagedTask[]>("get_recent_staged_tasks", {
      hours: 168, // 7 days
      limit: 30,
    });
    if (recent.length > 0) {
      activeBlock = "ACTIVE STAGED TASKS (already extracted — do not re-extract duplicates):\n";
      recent.forEach((t, i) => {
        const score = t.relevance_score != null ? ` [score:${t.relevance_score}]` : "";
        activeBlock += `${i + 1}.${score} ${t.description}\n`;
      });
      activeBlock += "\n";
    }
  } catch (err) {
    console.warn("[TaskAssistant] failed to load recent tasks for prompt:", err);
  }
  return activeBlock;
}

/**
 * Run the tool-calling loop. Returns a `TaskExtractionResult` describing the
 * outcome. `null` task means no extraction (no_task_found / reject_task /
 * loop exhausted). Caller is responsible for persisting the result.
 */
export async function extractTaskFromFrame(
  frame: CapturedFrame,
): Promise<TaskExtractionResult> {
  const settings = useTaskAssistantSettings.getState();

  let prompt = `Screenshot from ${frame.appName}. Today is ${todayLabel()}. Analyze this screenshot for any actionable item the user should track.\n\n`;
  prompt +=
    "WHAT COUNTS AS A TASK (any of these — not just external requests):\n" +
    "1. **Requests TO the user** that haven't been resolved (someone asks them to do something).\n" +
    "2. **Commitments FROM the user** in their own messages — explicit \"I'll do X\", \"I'm going to do that\",\n" +
    "   \"Let me handle it\", \"Vou fazer isso\", \"Eu vou comprar Y\", \"Voy a hacerlo\", or any first-person\n" +
    "   statement of intent regardless of language. The user said it, so they own it.\n" +
    "3. **Self-notes / TODOs** — text the user is typing in a notes app, scratchpad, or sticky that reads\n" +
    "   like an action item: \"TODO: …\", \"need to …\", \"buy …\", \"call …\", \"book …\", \"fix …\".\n" +
    "4. **Research / shopping intent** — clear signals the user is deciding whether to act: a product page\n" +
    "   they're studying, a comparison view, a tab with a clear decision to make. Title it as the decision\n" +
    "   (e.g., \"Decide on standing desk: Uplift v Fully\"), not the page contents. Be conservative — a\n" +
    "   single search isn't enough; only flag when the screen shows commitment-shaped behavior\n" +
    "   (cart, side-by-side compare, repeated investigation cues).\n" +
    "5. **External-system action items** — a Linear/Jira/PR/email that's clearly waiting on the user.\n\n" +
    "Default to no_task_found when in doubt. Better to miss one than nag the user with junk.\n\n";
  if (MESSAGING_APPS.has(frame.appName)) {
    prompt +=
      "REMINDER — THIS IS A MESSAGING APP:\n" +
      "- If this screenshot shows a chat sidebar/conversation list rather than an open conversation, SKIP entirely.\n" +
      "- If it shows an open conversation, read the FULL conversation flow between the user and the other person.\n" +
      "- LEFT-SIDE messages = from the other person. RIGHT-SIDE/colored = from the user.\n" +
      "- HIGH PRIORITY: any user message expressing commitment or intent — \"I'll …\", \"I'm going to …\",\n" +
      "  \"Vou fazer …\", \"Voy a …\". Extract these even if no one asked — the user said it, so they own it.\n" +
      "- ALSO: requests the user hasn't replied to yet, or things they agreed to ('Sure, will do').\n" +
      "- Title naming: when there's another person in the thread, name them in the title. For pure\n" +
      "  self-statements, omit the recipient.\n\n";
  }
  prompt += await buildContextBlock();
  prompt +=
    "Analyze this screenshot. If you see a potential task (any of the 5 categories above), search for\n" +
    "duplicates first. If the screen is just code, settings, dashboards, or media with no actionable item,\n" +
    "call no_task_found immediately. Most screenshots (~85%) should still produce no_task_found.";

  const contents: GeminiContent[] = [
    {
      role: "user",
      parts: [
        { text: prompt },
        { inlineData: { mimeType: "image/jpeg", data: frame.imageBase64 } },
      ],
    },
  ];

  let searchCount = 0;
  for (let iter = 0; iter < 5; iter++) {
    let parts: GeminiPart[];
    try {
      parts = await callGemini(settings.analysisPrompt, contents, iter === 0);
    } catch (err) {
      console.warn("[TaskAssistant] Gemini call failed:", err);
      break;
    }
    const fnCall = parts.find((p) => p.functionCall)?.functionCall;
    if (!fnCall) break;
    const args = (fnCall.args ?? {}) as Record<string, unknown>;

    switch (fnCall.name) {
      case "no_task_found":
        return {
          hasNewTask: false,
          task: null,
          contextSummary: String(args.context_summary ?? "No task on screen"),
          currentActivity: String(args.current_activity ?? "Unknown"),
          searchCount,
        };

      case "reject_task":
        return {
          hasNewTask: false,
          task: null,
          contextSummary: String(args.context_summary ?? ""),
          currentActivity: String(args.current_activity ?? ""),
          searchCount,
        };

      case "extract_task": {
        const title = String(args.title ?? "");
        const validationError = validateTaskTitle(title);
        if (validationError) {
          contents.push({ role: "model", parts: [{ functionCall: fnCall }] });
          contents.push({
            role: "user",
            parts: [
              {
                functionResponse: {
                  name: fnCall.name,
                  response: {
                    result: `REJECTED: ${validationError}. Your title was: "${title}". Either rewrite with 6+ words including a specific person/project name and concrete action, or call no_task_found if you cannot be more specific.`,
                  },
                },
              },
            ],
          });
          continue;
        }

        const task: ExtractedTask = {
          title,
          description: typeof args.description === "string" && args.description ? String(args.description) : null,
          priority: (["high", "medium", "low"].includes(String(args.priority))
            ? String(args.priority)
            : "medium") as "high" | "medium" | "low",
          source_app: String(args.source_app ?? frame.appName),
          inferred_deadline:
            typeof args.inferred_deadline === "string" && args.inferred_deadline
              ? String(args.inferred_deadline)
              : null,
          confidence: typeof args.confidence === "number" ? args.confidence : 0.5,
          tags: Array.isArray(args.tags) ? (args.tags as unknown[]).map(String) : [],
          source_category: String(args.source_category ?? "other"),
          source_subcategory: String(args.source_subcategory ?? "other"),
          relevance_score:
            typeof args.relevance_score === "number"
              ? Math.round(args.relevance_score)
              : null,
        };
        return {
          hasNewTask: true,
          task,
          contextSummary: String(args.context_summary ?? ""),
          currentActivity: String(args.current_activity ?? ""),
          searchCount,
        };
      }

      case "search_similar": {
        const query = String(args.query ?? "");
        searchCount++;
        const hits = await executeVectorSearch(query);
        contents.push({ role: "model", parts: [{ functionCall: fnCall }] });
        contents.push({
          role: "user",
          parts: [
            {
              functionResponse: {
                name: fnCall.name,
                response: { result: JSON.stringify(hits) },
              },
            },
          ],
        });
        continue;
      }

      case "search_keywords": {
        const query = String(args.query ?? "");
        searchCount++;
        const hits = await executeKeywordSearch(query);
        contents.push({ role: "model", parts: [{ functionCall: fnCall }] });
        contents.push({
          role: "user",
          parts: [
            {
              functionResponse: {
                name: fnCall.name,
                response: { result: JSON.stringify(hits) },
              },
            },
          ],
        });
        continue;
      }

      default:
        return { hasNewTask: false, task: null, contextSummary: "", currentActivity: "", searchCount };
    }
  }

  return { hasNewTask: false, task: null, contextSummary: "", currentActivity: "", searchCount };
}

// ---------------------------------------------------------------------------
// Persistence — store locally, embed, sync to backend
// ---------------------------------------------------------------------------

interface BackendStagedTask {
  id: string;
}

export async function persistExtractedTask(
  frame: CapturedFrame,
  result: TaskExtractionResult,
): Promise<void> {
  if (!result.hasNewTask || !result.task) return;
  const settings = useTaskAssistantSettings.getState();
  if (result.task.confidence < settings.minConfidence) return;

  const t = result.task;
  const metadata = {
    tags: t.tags,
    context_summary: result.contextSummary,
    current_activity: result.currentActivity,
    source_category: t.source_category,
    source_subcategory: t.source_subcategory,
    inferred_deadline: t.inferred_deadline ?? "",
    window_title: frame.windowTitle,
  };

  let saved: { id: string } | null = null;
  try {
    saved = await invoke<{ id: string }>("upsert_staged_task", {
      input: {
        description: t.title,
        priority: t.priority,
        tags_json: JSON.stringify(t.tags),
        due_at: parseDueDate(t.inferred_deadline),
        confidence: t.confidence,
        source_app: t.source_app,
        window_title: frame.windowTitle,
        context_summary: result.contextSummary,
        current_activity: result.currentActivity,
        metadata_json: JSON.stringify(metadata),
        relevance_score: t.relevance_score,
        screenshot_id: frame.dbId,
      },
    });
  } catch (err) {
    console.warn("[TaskAssistant] upsert_staged_task failed:", err);
    return;
  }

  // Embed the title and store the vector for future similarity search.
  if (saved) {
    const localId = saved.id;
    void embedText(t.title, "RETRIEVAL_DOCUMENT")
      .then((vec) =>
        invoke("save_staged_task_embedding", {
          id: localId,
          embedding: Array.from(vec),
        }),
      )
      .catch((err) => console.warn("[TaskAssistant] embed/save failed:", err));
  }

  // Mirror to backend (cross-device + dedup pass uses the backend list).
  try {
    const resp = await api.post<BackendStagedTask>("/v1/staged-tasks", {
      description: t.title,
      due_at: parseDueDate(t.inferred_deadline),
      source: "screenshot",
      priority: t.priority,
      category: t.tags[0] ?? null,
      metadata,
      relevance_score: t.relevance_score,
    });
    if (resp?.id && saved) {
      await invoke("set_staged_task_backend_id", {
        id: saved.id,
        backendId: resp.id,
      });
    }
  } catch (err) {
    console.warn("[TaskAssistant] backend sync failed:", err);
  }
}

/** Convert "yyyy-MM-dd" (or empty) to an ISO timestamp at end-of-day local. */
function parseDueDate(s: string | null): string | null {
  if (!s) return null;
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s);
  if (!m) return null;
  const d = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]), 23, 59, 0);
  if (d.getTime() < Date.now() - 24 * 60 * 60 * 1000) {
    // Past dates rejected — matches Swift parseDueDate behavior.
    return null;
  }
  return d.toISOString();
}
