/**
 * Chat store — Zustand store for AI chat via Gemini.
 *
 * Calls Gemini directly (no backend proxy needed).
 * Messages are persisted locally via Zustand persist + tauri-plugin-store.
 * Screen capture data from the local Rewind database is automatically
 * injected as context when the user asks about their activity.
 *
 * This store also tracks chat *sessions* — each session groups a list of
 * messages under a shared id, title, and createdAt/updatedAt. Sessions are
 * persisted alongside messages so the sidebar can list them across app
 * launches.
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

export type CitationSourceType = "conversation" | "memory" | "web" | "note";

export interface Citation {
  id: string;
  sourceType: CitationSourceType;
  title: string;
  preview: string;
  /** Optional URL or internal id the UI can navigate to on click. */
  target?: string;
  createdAt?: string;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: string;
  isStreaming?: boolean;
  /** Parsed from backend response when present — otherwise undefined. */
  citations?: Citation[];
  /** Session this message belongs to. Legacy messages may be undefined. */
  sessionId?: string;
}

export interface ChatSession {
  id: string;
  title: string;
  createdAt: string;
  updatedAt: string;
  /** Short preview taken from the first user message. */
  preview?: string;
  messageCount: number;
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
// Session helpers
// ---------------------------------------------------------------------------

function deriveSessionTitle(text: string): string {
  const trimmed = text.trim().replace(/\s+/g, " ");
  if (!trimmed) return "New Chat";
  return trimmed.length > 48 ? `${trimmed.slice(0, 48)}…` : trimmed;
}

function makeSession(initialMessageText?: string): ChatSession {
  const now = new Date().toISOString();
  return {
    id: nanoid(),
    title: initialMessageText ? deriveSessionTitle(initialMessageText) : "New Chat",
    createdAt: now,
    updatedAt: now,
    preview: initialMessageText?.slice(0, 120),
    messageCount: 0,
  };
}

// ---------------------------------------------------------------------------
// State shape
// ---------------------------------------------------------------------------

interface ChatState {
  /** Only the messages for the currently selected session. */
  messages: ChatMessage[];
  isStreaming: boolean;

  sessions: ChatSession[];
  currentSessionId: string | null;
  /** Keyed index: sessionId -> its messages. Kept alongside `messages` so we
   *  can swap sessions without re-fetching anything. */
  sessionMessages: Record<string, ChatMessage[]>;

  sendMessage: (content: string) => Promise<void>;
  stopStreaming: () => void;
  clearMessages: () => void;

  // Session API
  loadSessions: () => void;
  selectSession: (id: string) => void;
  newSession: () => string;
  deleteSession: (id: string) => void;
  renameSession: (id: string, title: string) => void;
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
      sessions: [],
      currentSessionId: null,
      sessionMessages: {},

      // -----------------------------------------------------------------------
      // sendMessage
      // -----------------------------------------------------------------------
      sendMessage: async (content: string) => {
        if (get().isStreaming) return;

        const now = new Date().toISOString();

        // Ensure a session exists. Create one on the fly when needed.
        let sessionId = get().currentSessionId;
        if (!sessionId) {
          sessionId = get().newSession();
        }

        const userMsg: ChatMessage = {
          id: nanoid(),
          role: "user",
          content,
          timestamp: now,
          sessionId,
        };

        const assistantId = nanoid();
        const assistantMsg: ChatMessage = {
          id: assistantId,
          role: "assistant",
          content: "",
          timestamp: now,
          isStreaming: true,
          sessionId,
        };

        set((state) => {
          const nextMessages = [...state.messages, userMsg, assistantMsg];
          const nextSessionMessages = {
            ...state.sessionMessages,
            [sessionId!]: nextMessages,
          };
          // If this is the first message, stamp the session title from it.
          const nextSessions = state.sessions.map((s) => {
            if (s.id !== sessionId) return s;
            const isFirstUserMsg = s.messageCount === 0;
            return {
              ...s,
              title: isFirstUserMsg ? deriveSessionTitle(content) : s.title,
              preview: isFirstUserMsg ? content.slice(0, 120) : s.preview,
              messageCount: s.messageCount + 2,
              updatedAt: now,
            };
          });
          return {
            messages: nextMessages,
            sessionMessages: nextSessionMessages,
            sessions: nextSessions,
            isStreaming: true,
          };
        });

        abortController = new AbortController();

        try {
          // Inject local screen context if the query is about activity
          const screenContext = await buildScreenContext(content);
          const textToSend = screenContext ? screenContext + content : content;

          // Build conversation history for context (last 20 messages from current session)
          const history = get()
            .messages.filter((m) => m.id !== assistantId && m.content.trim() !== "")
            .slice(-20)
            .map((m) => ({ role: m.role, content: m.content }));

          await api.sendChatViaGemini(
            textToSend,
            (delta) => {
              set((state) => {
                const updated = state.messages.map((m) =>
                  m.id === assistantId
                    ? { ...m, content: m.content + delta }
                    : m,
                );
                return {
                  messages: updated,
                  sessionMessages: sessionId
                    ? { ...state.sessionMessages, [sessionId]: updated }
                    : state.sessionMessages,
                };
              });
            },
            history,
          );

          set((state) => {
            const updated = state.messages.map((m) =>
              m.id === assistantId ? { ...m, isStreaming: false } : m,
            );
            return {
              messages: updated,
              sessionMessages: sessionId
                ? { ...state.sessionMessages, [sessionId]: updated }
                : state.sessionMessages,
              isStreaming: false,
            };
          });
        } catch (err: unknown) {
          const message = err instanceof Error ? err.message : String(err);
          const isAbort = message.includes("abort") || message.includes("AbortError");

          set((state) => {
            const updated = state.messages.map((m) => {
              if (m.id !== assistantId) return m;
              const errorSuffix = !isAbort && m.content === "" ? `\n\n*Error: ${message}*` : "";
              return { ...m, content: m.content + errorSuffix, isStreaming: false };
            });
            return {
              messages: updated,
              sessionMessages: sessionId
                ? { ...state.sessionMessages, [sessionId]: updated }
                : state.sessionMessages,
              isStreaming: false,
            };
          });

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
        set((state) => {
          const updated = state.messages.map((m) =>
            m.isStreaming ? { ...m, isStreaming: false } : m,
          );
          return {
            messages: updated,
            sessionMessages: state.currentSessionId
              ? { ...state.sessionMessages, [state.currentSessionId]: updated }
              : state.sessionMessages,
            isStreaming: false,
          };
        });
      },

      // -----------------------------------------------------------------------
      // clearMessages — clears the current session's messages
      // -----------------------------------------------------------------------
      clearMessages: () => {
        set((state) => {
          const sid = state.currentSessionId;
          const nextSessions = sid
            ? state.sessions.map((s) =>
                s.id === sid ? { ...s, messageCount: 0, preview: undefined } : s,
              )
            : state.sessions;
          return {
            messages: [],
            sessionMessages: sid
              ? { ...state.sessionMessages, [sid]: [] }
              : state.sessionMessages,
            sessions: nextSessions,
            isStreaming: false,
          };
        });
      },

      // -----------------------------------------------------------------------
      // Sessions
      // -----------------------------------------------------------------------
      loadSessions: () => {
        // Sessions are already restored from persist storage. This method
        // exists so callers can trigger any future remote refresh; for now
        // it is a no-op but makes the API symmetrical with other stores.
      },

      selectSession: (id: string) => {
        const state = get();
        if (state.currentSessionId === id) return;
        const messages = state.sessionMessages[id] ?? [];
        set({ currentSessionId: id, messages });
      },

      newSession: () => {
        const session = makeSession();
        set((state) => ({
          sessions: [session, ...state.sessions],
          sessionMessages: { ...state.sessionMessages, [session.id]: [] },
          currentSessionId: session.id,
          messages: [],
        }));
        return session.id;
      },

      deleteSession: (id: string) => {
        set((state) => {
          const nextSessions = state.sessions.filter((s) => s.id !== id);
          const { [id]: _, ...rest } = state.sessionMessages;
          const wasCurrent = state.currentSessionId === id;
          const nextCurrent = wasCurrent
            ? nextSessions[0]?.id ?? null
            : state.currentSessionId;
          const nextMessages = wasCurrent
            ? nextCurrent
              ? rest[nextCurrent] ?? []
              : []
            : state.messages;
          return {
            sessions: nextSessions,
            sessionMessages: rest,
            currentSessionId: nextCurrent,
            messages: nextMessages,
          };
        });
      },

      renameSession: (id: string, title: string) => {
        const trimmed = title.trim();
        if (!trimmed) return;
        set((state) => ({
          sessions: state.sessions.map((s) =>
            s.id === id ? { ...s, title: trimmed } : s,
          ),
        }));
      },
    }),
    {
      name: "chat-messages",
      version: 2,
      storage: tauriStorage,
      partialize: (state) => ({
        // Persist sessions + session message map. Strip transient streaming flags.
        sessions: state.sessions,
        currentSessionId: state.currentSessionId,
        sessionMessages: Object.fromEntries(
          Object.entries(state.sessionMessages).map(([sid, msgs]) => [
            sid,
            (msgs as ChatMessage[]).filter((m) => !m.isStreaming),
          ]),
        ),
      }),
      migrate: (persisted: unknown, version: number) => {
        // v1 only persisted a flat `messages` array. Wrap those into a
        // single session so existing users keep their history.
        if (version < 2 && persisted && typeof persisted === "object") {
          const legacy = persisted as { messages?: ChatMessage[] };
          if (Array.isArray(legacy.messages) && legacy.messages.length > 0) {
            const session = makeSession(
              legacy.messages.find((m) => m.role === "user")?.content,
            );
            session.messageCount = legacy.messages.length;
            const tagged = legacy.messages.map((m) => ({ ...m, sessionId: session.id }));
            return {
              sessions: [session],
              currentSessionId: session.id,
              sessionMessages: { [session.id]: tagged },
            };
          }
        }
        return persisted as Partial<ChatState>;
      },
      onRehydrateStorage: () => (state) => {
        // After rehydrate, materialize `messages` from the current session.
        if (!state) return;
        const sid = state.currentSessionId;
        if (sid && state.sessionMessages[sid]) {
          state.messages = state.sessionMessages[sid];
        }
      },
    },
  ),
);
