/**
 * Chat store — Zustand store for AI chat via Gemini.
 *
 * Calls Gemini directly (no backend proxy needed).
 * Messages are persisted locally via Zustand persist + tauri-plugin-store.
 * Screen capture data from the local Rewind database is automatically
 * injected as context when the user asks about their activity.
 */

import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";
import { nanoid } from "nanoid";
import { api } from "@/services/api";
import { getRecentScreenshots } from "@/services/rewind";
import type { ScreenshotRow } from "@/services/rewind";
import { LazyStore } from "@tauri-apps/plugin-store";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: string;
  isStreaming?: boolean;
}

// ---------------------------------------------------------------------------
// Tauri store adapter for Zustand persist
// ---------------------------------------------------------------------------

const tauriStore = new LazyStore("chat-history.json");

const tauriStorage = createJSONStorage(() => ({
  getItem: async (name: string) => {
    const val = await tauriStore.get<string>(name);
    return val ?? null;
  },
  setItem: async (name: string, value: string) => {
    await tauriStore.set(name, value);
    await tauriStore.save();
  },
  removeItem: async (name: string) => {
    await tauriStore.delete(name);
    await tauriStore.save();
  },
}));

// ---------------------------------------------------------------------------
// Screen context helpers
// ---------------------------------------------------------------------------

function formatScreenRows(rows: ScreenshotRow[]): string {
  if (rows.length === 0) return "";
  return rows
    .map((r) => {
      const ts = new Date(r.timestamp).toLocaleString();
      const ocr = r.ocr_text ? ` | Text: ${r.ocr_text.slice(0, 200)}` : "";
      return `[${ts}] ${r.app_name} — ${r.window_title}${ocr}`;
    })
    .join("\n");
}

const SCREEN_KEYWORDS = [
  "screen", "activity", "working on", "work on", "apps", "app usage",
  "screen time", "recent", "today", "doing", "been using", "browsing",
  "visited", "open", "window", "tab",
];

function isScreenQuery(text: string): boolean {
  const lower = text.toLowerCase();
  return SCREEN_KEYWORDS.some((kw) => lower.includes(kw));
}

async function buildScreenContext(userText: string): Promise<string> {
  if (!isScreenQuery(userText)) return "";

  try {
    const recent = await getRecentScreenshots(30, 0);
    if (recent.length === 0) return "";

    const formatted = formatScreenRows(recent);
    return [
      "[The user has a desktop screen capture tool running. Here is their recent screen activity from the local database:]",
      formatted,
      "[End of screen activity. Use this data to answer the user's question. Summarize by app and provide time estimates based on timestamps.]",
      "\n",
    ].join("\n");
  } catch {
    return "";
  }
}

// ---------------------------------------------------------------------------
// State shape
// ---------------------------------------------------------------------------

interface ChatState {
  messages: ChatMessage[];
  isStreaming: boolean;

  sendMessage: (content: string) => Promise<void>;
  stopStreaming: () => void;
  clearMessages: () => void;
}

// ---------------------------------------------------------------------------
// Store
// ---------------------------------------------------------------------------

let abortController: AbortController | null = null;

export const useChatStore = create<ChatState>()(
  persist(
    (set, get) => ({
      messages: [],
      isStreaming: false,

      // -----------------------------------------------------------------------
      // sendMessage
      // -----------------------------------------------------------------------
      sendMessage: async (content: string) => {
        if (get().isStreaming) return;

        const now = new Date().toISOString();

        const userMsg: ChatMessage = {
          id: nanoid(),
          role: "user",
          content,
          timestamp: now,
        };

        const assistantId = nanoid();
        const assistantMsg: ChatMessage = {
          id: assistantId,
          role: "assistant",
          content: "",
          timestamp: now,
          isStreaming: true,
        };

        set((state) => ({
          messages: [...state.messages, userMsg, assistantMsg],
          isStreaming: true,
        }));

        abortController = new AbortController();

        try {
          // Inject local screen context if the query is about activity
          const screenContext = await buildScreenContext(content);
          const textToSend = screenContext ? screenContext + content : content;

          // Build conversation history for context (last 20 messages)
          const history = get()
            .messages.filter((m) => m.id !== assistantId && m.content.trim() !== "")
            .slice(-20)
            .map((m) => ({ role: m.role, content: m.content }));

          await api.sendChatViaGemini(
            textToSend,
            (delta) => {
              set((state) => ({
                messages: state.messages.map((m) =>
                  m.id === assistantId
                    ? { ...m, content: m.content + delta }
                    : m,
                ),
              }));
            },
            history,
          );

          set((state) => ({
            messages: state.messages.map((m) =>
              m.id === assistantId ? { ...m, isStreaming: false } : m,
            ),
            isStreaming: false,
          }));
        } catch (err: unknown) {
          const message = err instanceof Error ? err.message : String(err);
          const isAbort = message.includes("abort") || message.includes("AbortError");

          set((state) => ({
            messages: state.messages.map((m) => {
              if (m.id !== assistantId) return m;
              const errorSuffix = !isAbort && m.content === "" ? `\n\n*Error: ${message}*` : "";
              return { ...m, content: m.content + errorSuffix, isStreaming: false };
            }),
            isStreaming: false,
          }));

          if (!isAbort) {
            console.error("[Chat] sendMessage failed:", err);
          }
        } finally {
          abortController = null;
        }
      },

      // -----------------------------------------------------------------------
      // stopStreaming
      // -----------------------------------------------------------------------
      stopStreaming: () => {
        if (abortController) {
          abortController.abort();
          abortController = null;
        }
        set((state) => ({
          messages: state.messages.map((m) =>
            m.isStreaming ? { ...m, isStreaming: false } : m,
          ),
          isStreaming: false,
        }));
      },

      // -----------------------------------------------------------------------
      // clearMessages
      // -----------------------------------------------------------------------
      clearMessages: () => {
        set({ messages: [], isStreaming: false });
      },
    }),
    {
      name: "chat-messages",
      storage: tauriStorage,
      partialize: (state) => ({
        // Only persist messages, not transient streaming state
        messages: state.messages.filter((m) => !m.isStreaming),
      }),
    },
  ),
);
