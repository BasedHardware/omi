/**
 * MemoryAssistant — TypeScript port of
 * `desktop/Desktop/Sources/ProactiveAssistants/Assistants/MemoryExtraction/MemoryAssistant.swift`.
 *
 * Hooks into the proactive frame stream from `proactiveAssistant.ts`. For each
 * frame that clears the exclusion + interval checks, we build a dedup-aware
 * prompt (last 20 extractions) and ask Gemini for a structured JSON response.
 * Accepted memories land in local SQLite first, then sync to the backend.
 *
 * Simpler than TaskAssistant — no tool-calling loop. Matches Swift.
 */

import { invoke } from "@tauri-apps/api/core";
import { api } from "@/services/api";
import { notify } from "@/services/notifications";
import {
  CapturedFrame,
  addFrameListener,
  startMonitoring,
  stopMonitoring,
} from "@/services/proactiveAssistant";
import {
  isAppAllowed,
  useMemoryAssistantSettings,
} from "@/services/memoryAssistantSettings";
import { useMemoryStore } from "@/stores/memoryStore";

export type MemoryCategory = "system" | "interesting";

export interface ExtractedMemory {
  content: string;
  category: MemoryCategory;
  source_app: string;
  confidence: number;
}

export interface MemoryExtractionResult {
  hasNewMemory: boolean;
  memories: ExtractedMemory[];
  contextSummary: string;
  currentActivity: string;
}

interface GeminiPart {
  text?: string;
  inlineData?: { mimeType: string; data: string };
}

interface GeminiResponse {
  candidates?: Array<{
    content?: { parts?: GeminiPart[] };
    finishReason?: string;
  }>;
}

const GEMINI_MODEL = "gemini-pro-latest";
const GEMINI_PATH = `/v1/proxy/gemini/models/${GEMINI_MODEL}:generateContent`;

const MAX_PREVIOUS_MEMORIES = 20;
const previousMemories: ExtractedMemory[] = [];

let lastAnalysisTime = 0;
let inflight = false;
let unsubscribeFrame: (() => void) | null = null;

const RESPONSE_SCHEMA = {
  type: "object",
  properties: {
    has_new_memory: {
      type: "boolean",
      description: "True if new memories were found",
    },
    memories: {
      type: "array",
      description: "Array of extracted memories (0-1 max)",
      items: {
        type: "object",
        properties: {
          content: { type: "string", description: "The memory content (max 15 words)" },
          category: {
            type: "string",
            enum: ["system", "interesting"],
            description: "Memory category",
          },
          source_app: { type: "string", description: "App where memory was found" },
          confidence: { type: "number", description: "Confidence score 0.0-1.0" },
        },
        required: ["content", "category", "source_app", "confidence"],
      },
    },
    context_summary: {
      type: "string",
      description: "Brief summary of what user is looking at",
    },
    current_activity: {
      type: "string",
      description: "High-level description of user's activity",
    },
  },
  required: ["has_new_memory", "memories", "context_summary", "current_activity"],
};

function buildPrompt(appName: string): string {
  let prompt = `Analyze this screenshot from ${appName}.\n\n`;
  if (previousMemories.length > 0) {
    prompt +=
      "RECENTLY EXTRACTED MEMORIES (do not re-extract these or semantically similar ones):\n";
    previousMemories.forEach((m, i) => {
      prompt += `${i + 1}. [${m.category}] ${m.content}\n`;
    });
    prompt += "\nLook for NEW memories that are NOT already in the list above.";
  } else {
    prompt +=
      "Look for memories to extract (system facts about the user, or interesting wisdom from others).";
  }
  return prompt;
}

async function callGemini(
  systemPrompt: string,
  prompt: string,
  imageBase64: string,
): Promise<string | null> {
  const body = {
    system_instruction: { parts: [{ text: systemPrompt }] },
    contents: [
      {
        role: "user",
        parts: [
          { text: prompt },
          { inlineData: { mimeType: "image/jpeg", data: imageBase64 } },
        ],
      },
    ],
    generationConfig: {
      maxOutputTokens: 2048,
      temperature: 0.2,
      response_mime_type: "application/json",
      response_schema: RESPONSE_SCHEMA,
    },
  };
  const resp = await api.post<GeminiResponse>(GEMINI_PATH, body);
  const text = resp?.candidates?.[0]?.content?.parts?.[0]?.text;
  return text ?? null;
}

function parseResult(raw: string): MemoryExtractionResult | null {
  try {
    const parsed = JSON.parse(raw) as {
      has_new_memory?: boolean;
      memories?: Array<Partial<ExtractedMemory>>;
      context_summary?: string;
      current_activity?: string;
    };
    const memories: ExtractedMemory[] = Array.isArray(parsed.memories)
      ? parsed.memories
          .filter(
            (m): m is ExtractedMemory =>
              typeof m?.content === "string" &&
              (m.category === "system" || m.category === "interesting") &&
              typeof m.source_app === "string" &&
              typeof m.confidence === "number",
          )
          .map((m) => ({
            content: m.content,
            category: m.category,
            source_app: m.source_app,
            confidence: m.confidence,
          }))
      : [];
    return {
      hasNewMemory: Boolean(parsed.has_new_memory),
      memories,
      contextSummary: String(parsed.context_summary ?? ""),
      currentActivity: String(parsed.current_activity ?? ""),
    };
  } catch (err) {
    console.warn("[MemoryAssistant] malformed JSON from Gemini:", err);
    return null;
  }
}

export async function extractMemories(
  frame: CapturedFrame,
): Promise<MemoryExtractionResult | null> {
  const settings = useMemoryAssistantSettings.getState();
  const prompt = buildPrompt(frame.appName);

  let raw: string | null;
  try {
    raw = await callGemini(settings.analysisPrompt, prompt, frame.imageBase64);
  } catch (err) {
    console.warn("[MemoryAssistant] Gemini call failed:", err);
    return null;
  }
  if (!raw) return null;
  return parseResult(raw);
}

interface BackendMemoryResponse {
  id: string;
  message?: string;
}

async function persistMemory(
  memory: ExtractedMemory,
  frame: CapturedFrame,
  result: MemoryExtractionResult,
): Promise<void> {
  const id =
    typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
      ? crypto.randomUUID()
      : `mem_${Date.now()}_${Math.floor(Math.random() * 1e9)}`;

  try {
    await invoke<string>("insert_memory", {
      input: {
        id,
        content: memory.content,
        category: memory.category,
        visibility: "private",
        confidence: memory.confidence,
        source_app: memory.source_app,
        window_title: frame.windowTitle,
        context_summary: result.contextSummary,
        current_activity: result.currentActivity,
        headline: null,
        reasoning: null,
        tags_json: null,
        screenshot_id: frame.dbId,
      },
    });
  } catch (err) {
    console.warn("[MemoryAssistant] local insert failed:", err);
    return;
  }

  const payload = {
    content: memory.content,
    visibility: "private",
    category: memory.category,
    confidence: memory.confidence,
    source_app: memory.source_app,
    context_summary: result.contextSummary,
    tags: [] as string[],
    reasoning: "",
    current_activity: result.currentActivity,
    source: "desktop",
    window_title: frame.windowTitle,
    headline: "",
  };

  try {
    const resp = await api.post<BackendMemoryResponse>("/v3/memories", payload);
    if (resp?.id) {
      try {
        await invoke("set_memory_backend_id", { id, backendId: resp.id });
      } catch (err) {
        console.warn("[MemoryAssistant] set_memory_backend_id failed:", err);
      }
    }
  } catch (err) {
    console.warn("[MemoryAssistant] backend sync failed:", err);
  }

  try {
    await useMemoryStore.getState().loadMemories();
  } catch (err) {
    console.warn("[MemoryAssistant] loadMemories refresh failed:", err);
  }
}

async function handleFrame(frame: CapturedFrame): Promise<void> {
  if (inflight) return;
  const settings = useMemoryAssistantSettings.getState();
  if (!settings.enabled) return;
  if (!isAppAllowed(frame.appName)) {
    return;
  }

  const intervalMs = settings.extractionIntervalSeconds * 1000;
  if (Date.now() - lastAnalysisTime < intervalMs) return;

  inflight = true;
  lastAnalysisTime = Date.now();
  try {
    console.info(
      `[MemoryAssistant] analyzing frame app=${frame.appName}`,
    );
    const result = await extractMemories(frame);
    if (!result || !result.hasNewMemory || result.memories.length === 0) {
      return;
    }

    const memory = result.memories[0];
    if (!memory) return;

    if (memory.confidence < settings.minConfidence) {
      console.info(
        `[MemoryAssistant] filtered ${(memory.confidence * 100).toFixed(0)}% < ${(settings.minConfidence * 100).toFixed(0)}%: "${memory.content}"`,
      );
      return;
    }

    console.info(
      `[MemoryAssistant] extracted [${memory.category}] "${memory.content}" conf=${memory.confidence.toFixed(2)}`,
    );

    previousMemories.unshift(memory);
    if (previousMemories.length > MAX_PREVIOUS_MEMORIES) {
      previousMemories.pop();
    }

    await persistMemory(memory, frame, result);

    if (settings.notificationsEnabled) {
      const title = memory.category === "interesting" ? "Wisdom captured" : "Memory saved";
      void notify(title, memory.content);
    }
  } catch (err) {
    console.warn("[MemoryAssistant] handleFrame error:", err);
  } finally {
    inflight = false;
  }
}

/** Start listening for proactive frames. Idempotent. */
export function initMemoryAssistant(): void {
  if (unsubscribeFrame) return;
  const off = addFrameListener((frame) => {
    void handleFrame(frame);
  });
  startMonitoring();
  unsubscribeFrame = () => {
    off();
    stopMonitoring();
  };
  console.info("[MemoryAssistant] started");
}

/** Stop listening and reset state. */
export function stopMemoryAssistant(): void {
  if (unsubscribeFrame) {
    unsubscribeFrame();
    unsubscribeFrame = null;
  }
  lastAnalysisTime = 0;
  inflight = false;
  previousMemories.length = 0;
  console.info("[MemoryAssistant] stopped");
}
