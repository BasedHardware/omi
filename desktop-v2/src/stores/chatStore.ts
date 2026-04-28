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
import { api, sendChatViaBackend, type ToolResultFrame } from "@/services/api";
import {
  buildChatSystemPrompt,
  buildClaudeChatSystemPrompt,
  getContextSnapshotCounts,
  invalidateChatContext,
} from "@/services/chatContext";
import { createClient, sendMessageStreaming } from "@/services/chat";
import { useAppStore } from "@/stores/appStore";
import { useAuthStore } from "@/stores/authStore";
import { useClaudeStore } from "@/stores/claudeStore";
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

export type ToolPartStatus = "running" | "completed" | "error";

export interface ToolPartInput {
  summary: string;
  details?: string;
}

/** Compact ticket shape for in-chat cards. Subset of the unified
 *  `IntegrationTask` schema — keeps the bytes-on-the-wire small per chat. */
export interface ChatTaskCard {
  external_id: string;
  title: string;
  /** Short plain-text snippet of the source body (Jira ADF flattened, etc.).
   *  Plugins truncate to ~240 chars before sending. */
  description?: string;
  status?: string;
  status_type?: "todo" | "in_progress" | "done" | "canceled";
  url?: string;
  project?: string;
  due_at?: string | null;
  assignee?: string;
  priority?: string;
}

export type ChatMessagePart =
  | { type: "text"; id: string; text: string }
  | {
      type: "tool";
      id: string;
      name: string;
      status: ToolPartStatus;
      input?: ToolPartInput;
      output?: string;
      errorMessage?: string;
    }
  | { type: "reasoning"; id: string; text: string; isStreaming?: boolean }
  | {
      type: "task_cards";
      id: string;
      appId: string | null;
      appName: string;
      appImage?: string;
      tasks: ChatTaskCard[];
    };

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
  /**
   * Structured parts (tool calls, reasoning, text). When present, renderers
   * should walk `parts` in order; `content` is kept as a concatenation of
   * text parts for markdown/persistence/search.
   */
  parts?: ChatMessagePart[];
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
// Parts helpers
// ---------------------------------------------------------------------------

function withMessage(
  messages: ChatMessage[],
  id: string,
  updater: (m: ChatMessage) => ChatMessage,
): ChatMessage[] {
  return messages.map((m) => (m.id === id ? updater(m) : m));
}

function appendPart(msg: ChatMessage, part: ChatMessagePart): ChatMessage {
  return { ...msg, parts: [...(msg.parts ?? []), part] };
}

function mutatePart(
  msg: ChatMessage,
  partId: string,
  updater: (p: ChatMessagePart) => ChatMessagePart,
): ChatMessage {
  if (!msg.parts) return msg;
  return { ...msg, parts: msg.parts.map((p) => (p.id === partId ? updater(p) : p)) };
}

function appendTextDelta(msg: ChatMessage, delta: string): ChatMessage {
  const parts = msg.parts ?? [];
  const last = parts[parts.length - 1];
  if (last && last.type === "text") {
    const next = [...parts];
    next[next.length - 1] = { ...last, text: last.text + delta };
    return { ...msg, parts: next, content: msg.content + delta };
  }
  const textPart: ChatMessagePart = {
    type: "text",
    id: nanoid(),
    text: delta,
  };
  return { ...msg, parts: [...parts, textPart], content: msg.content + delta };
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

/** Which LLM the chat should route through.
 *  - "auto": when signed-in to Nooto → backend agent (plugin tools available);
 *    else Claude when its token is connected; else Gemini local fallback.
 *  - "backend": always use the Nooto backend agent (Claude with full tool access
 *    + plugin chat tools like Jira/Linear). Requires sign-in.
 *  - "claude": always use the user's local Claude account (no plugin tools).
 *  - "gemini": always use Gemini direct (no plugin tools, no Nooto backend). */
export type ChatModelPreference = "auto" | "backend" | "claude" | "gemini";

interface ChatState {
  /** Only the messages for the currently selected session. */
  messages: ChatMessage[];
  isStreaming: boolean;

  sessions: ChatSession[];
  currentSessionId: string | null;
  /** Keyed index: sessionId -> its messages. Kept alongside `messages` so we
   *  can swap sessions without re-fetching anything. */
  sessionMessages: Record<string, ChatMessage[]>;

  /** User-selected model preference (persisted). */
  model: ChatModelPreference;
  setModel: (model: ChatModelPreference) => void;

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

/** Sessions that have already shown the "Loaded context" preamble card.
 *  Module-level so it resets on app reload (mirrors the chatContext cache). */
const contextCardShown = new Set<string>();

export const useChatStore = create<ChatState>()(
  persist(
    (set, get) => ({
      messages: [],
      isStreaming: false,
      sessions: [],
      currentSessionId: null,
      sessionMessages: {},
      model: "auto",

      setModel: (model: ChatModelPreference) => set({ model }),

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

        const claudeToken = useClaudeStore.getState().accessToken;
        const idToken = useAuthStore.getState().idToken;
        const modelPref = get().model;

        // Routing: "auto" prefers the backend (plugin tools) when signed in,
        // then Claude, then Gemini. Explicit choices fall back to the next
        // available path on missing credentials so the user is never stuck.
        type Route = "backend" | "claude" | "gemini";
        const route: Route =
          modelPref === "backend"
            ? "backend"
            : modelPref === "claude"
              ? "claude"
              : modelPref === "gemini"
                ? "gemini"
                : idToken
                  ? "backend"
                  : claudeToken
                    ? "claude"
                    : "gemini";

        try {
          if (modelPref === "backend" && !idToken) {
            throw new Error(
              "The Nooto agent is selected but you're signed out. Sign in to use plugin tools.",
            );
          }
          if (modelPref === "claude" && !claudeToken) {
            throw new Error(
              "Claude is selected but not connected. Open the model picker and connect your Claude account.",
            );
          }

          // The backend agent builds its own context (memories, goals,
          // conversations) and emits its own `think:` cards via SSE — skip
          // the local "Loaded context" preamble for that path.
          if (route !== "backend" && !contextCardShown.has(sessionId)) {
            try {
              const counts = await getContextSnapshotCounts(sessionId);
              const total = counts.memories + counts.goals + counts.tasks;
              if (total > 0) {
                const parts: string[] = [];
                if (counts.goals) parts.push(`${counts.goals} goal${counts.goals === 1 ? "" : "s"}`);
                if (counts.tasks) parts.push(`${counts.tasks} task${counts.tasks === 1 ? "" : "s"}`);
                if (counts.memories)
                  parts.push(`${counts.memories} memor${counts.memories === 1 ? "y" : "ies"}`);
                const summary = parts.join(", ");
                const cardId = nanoid();
                set((state) => {
                  const updated = withMessage(state.messages, assistantId, (m) =>
                    appendPart(m, {
                      type: "tool",
                      id: cardId,
                      name: "loaded_context",
                      status: "completed",
                      input: { summary },
                      output: summary,
                    }),
                  );
                  return {
                    messages: updated,
                    sessionMessages: sessionId
                      ? { ...state.sessionMessages, [sessionId]: updated }
                      : state.sessionMessages,
                  };
                });
              }
              contextCardShown.add(sessionId);
            } catch (e) {
              console.warn("[chatStore] context card prelude failed", e);
            }
          }

          const textToSend = content;

          // Build conversation history for context (last 20 messages from current session)
          const history = get()
            .messages.filter((m) => m.id !== assistantId && m.content.trim() !== "")
            .slice(-20)
            .map((m) => ({ role: m.role, content: m.content }));

          const appendDelta = (delta: string) => {
            set((state) => {
              const updated = withMessage(state.messages, assistantId, (m) =>
                appendTextDelta(m, delta),
              );
              return {
                messages: updated,
                sessionMessages: sessionId
                  ? { ...state.sessionMessages, [sessionId]: updated }
                  : state.sessionMessages,
              };
            });
          };

          const onToolCall = (toolUseId: string, name: string, input: unknown) => {
            const summary = (() => {
              try {
                return JSON.stringify(input).slice(0, 200);
              } catch {
                return "";
              }
            })();
            set((state) => {
              const updated = withMessage(state.messages, assistantId, (m) =>
                appendPart(m, {
                  type: "tool",
                  id: toolUseId,
                  name,
                  status: "running",
                  input: { summary },
                }),
              );
              return {
                messages: updated,
                sessionMessages: sessionId
                  ? { ...state.sessionMessages, [sessionId]: updated }
                  : state.sessionMessages,
              };
            });
          };

          const onToolResult = (toolUseId: string, _name: string, output: string) => {
            set((state) => {
              const updated = withMessage(state.messages, assistantId, (m) =>
                mutatePart(m, toolUseId, (p) =>
                  p.type === "tool"
                    ? { ...p, status: "completed", output: output.slice(0, 1500) }
                    : p,
                ),
              );
              return {
                messages: updated,
                sessionMessages: sessionId
                  ? { ...state.sessionMessages, [sessionId]: updated }
                  : state.sessionMessages,
              };
            });
          };

          if (route === "backend") {
            // ----- Nooto backend agent: plugin tools (Jira, Linear, …) + Claude -----
            // The backend dispatches tool calls automatically and streams
            // `think:` lines for status cards (e.g. "Listing Jira projects…").
            // Each `think: <text>|app_id:<id>` becomes a tool card here so
            // the UI matches the mobile app's "Loaded context" affordance.
            const thinkCardIds = new Map<string, string>();
            // Resolve the app's friendly name from appStore so the tool card
            // shows "Jira" instead of the raw ULID. Fall back to "Plugin" when
            // the app hasn't been loaded yet (rare — apps load on dashboard mount).
            const appNameFor = (appId: string | null): string => {
              if (!appId) return "agent";
              const app = useAppStore.getState().apps.find((a) => a.id === appId);
              return app?.name ?? "Plugin";
            };
            await sendChatViaBackend(textToSend, {
              onDelta: appendDelta,
              onThink: (text, appId) => {
                const key = appId ?? "_agent";
                let cardId = thinkCardIds.get(key);
                if (!cardId) {
                  cardId = nanoid();
                  thinkCardIds.set(key, cardId);
                  set((state) => {
                    const updated = withMessage(state.messages, assistantId, (m) =>
                      appendPart(m, {
                        type: "tool",
                        id: cardId!,
                        name: appNameFor(appId),
                        status: "running",
                        input: { summary: text },
                      }),
                    );
                    return {
                      messages: updated,
                      sessionMessages: sessionId
                        ? { ...state.sessionMessages, [sessionId]: updated }
                        : state.sessionMessages,
                    };
                  });
                } else {
                  // Subsequent think lines for the same app: refine the summary.
                  set((state) => {
                    const updated = withMessage(state.messages, assistantId, (m) =>
                      mutatePart(m, cardId!, (p) =>
                        p.type === "tool" ? { ...p, input: { summary: text } } : p,
                      ),
                    );
                    return {
                      messages: updated,
                      sessionMessages: sessionId
                        ? { ...state.sessionMessages, [sessionId]: updated }
                        : state.sessionMessages,
                    };
                  });
                }
              },
              onToolResult: (frame: ToolResultFrame) => {
                // Plugins sending `data.tasks[]` (Jira / Linear / …) get
                // rendered as inline cards. Other shapes (data.foo, etc.) are
                // ignored for now — we'll add card types per surface as we
                // wire them up.
                const rawTasks = (frame.data as { tasks?: unknown }).tasks;
                if (!Array.isArray(rawTasks) || rawTasks.length === 0) return;
                const tasks: ChatTaskCard[] = rawTasks
                  .filter((t): t is Record<string, unknown> => !!t && typeof t === "object")
                  .map((t) => ({
                    external_id: String(t.external_id ?? ""),
                    title: String(t.title ?? ""),
                    description: typeof t.description === "string" ? t.description : undefined,
                    status: typeof t.status === "string" ? t.status : undefined,
                    status_type: t.status_type as ChatTaskCard["status_type"],
                    url: typeof t.url === "string" ? t.url : undefined,
                    project: typeof t.project === "string" ? t.project : undefined,
                    due_at: typeof t.due_at === "string" ? t.due_at : null,
                    assignee: typeof t.assignee === "string" ? t.assignee : undefined,
                    priority: typeof t.priority === "string" ? t.priority : undefined,
                  }))
                  .filter((t) => t.external_id || t.title);
                if (tasks.length === 0) return;
                const cardId = nanoid();
                const appName = appNameFor(frame.app_id);
                const app = frame.app_id
                  ? useAppStore.getState().apps.find((a) => a.id === frame.app_id)
                  : null;
                set((state) => {
                  const updated = withMessage(state.messages, assistantId, (m) =>
                    appendPart(m, {
                      type: "task_cards",
                      id: cardId,
                      appId: frame.app_id,
                      appName,
                      appImage: app?.image,
                      tasks,
                    }),
                  );
                  return {
                    messages: updated,
                    sessionMessages: sessionId
                      ? { ...state.sessionMessages, [sessionId]: updated }
                      : state.sessionMessages,
                  };
                });
              },
              onDone: () => {
                // Mark all running tool cards as completed once the final
                // ResponseMessage arrives.
                set((state) => {
                  const updated = withMessage(state.messages, assistantId, (m) => {
                    if (!m.parts) return m;
                    const parts = m.parts.map((p) =>
                      p.type === "tool" && p.status === "running"
                        ? { ...p, status: "completed" as const }
                        : p,
                    );
                    return { ...m, parts };
                  });
                  return {
                    messages: updated,
                    sessionMessages: sessionId
                      ? { ...state.sessionMessages, [sessionId]: updated }
                      : state.sessionMessages,
                  };
                });
              },
            });
          } else if (route === "claude" && claudeToken) {
            // ----- Claude path: tool-use enabled -----
            const systemPrompt = await buildClaudeChatSystemPrompt(sessionId);
            const client = createClient(claudeToken);
            const claudeMessages = [
              ...history.map((h) => ({
                role: h.role as "user" | "assistant",
                content: h.content,
              })),
              { role: "user" as const, content: textToSend },
            ];

            await sendMessageStreaming(
              client,
              claudeMessages,
              systemPrompt,
              appendDelta,
              onToolCall,
              onToolResult,
            );
          } else {
            // ----- Gemini path: tool-use enabled (function calling) -----
            const systemPrompt = await buildChatSystemPrompt(sessionId);
            await api.sendChatViaGemini(
              textToSend,
              { onDelta: appendDelta, onToolCall, onToolResult },
              history,
              systemPrompt,
            );
          }

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
          const updated = state.messages.map((m) => {
            if (!m.isStreaming) return m;
            const parts = m.parts?.map((p) =>
              p.type === "tool" && p.status === "running"
                ? { ...p, status: "error" as const, errorMessage: "Cancelled" }
                : p,
            );
            return { ...m, isStreaming: false, ...(parts ? { parts } : {}) };
          });
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
        const sid = get().currentSessionId;
        if (sid) {
          invalidateChatContext(sid);
          contextCardShown.delete(sid);
        }
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
        invalidateChatContext(session.id);
        contextCardShown.delete(session.id);
        set((state) => ({
          sessions: [session, ...state.sessions],
          sessionMessages: { ...state.sessionMessages, [session.id]: [] },
          currentSessionId: session.id,
          messages: [],
        }));
        return session.id;
      },

      deleteSession: (id: string) => {
        invalidateChatContext(id);
        contextCardShown.delete(id);
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
        model: state.model,
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
