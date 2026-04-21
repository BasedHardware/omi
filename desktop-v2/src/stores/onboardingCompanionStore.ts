/**
 * Onboarding Companion store — drives the chat-driven onboarding flow.
 *
 * The conversation is a heterogeneous list of turns: assistant text (streamed
 * from Gemini), user text, and interactive widget bubbles that each step
 * emits to capture its required input. Widget captures run through the
 * step's handler (see chatFlow/types.ts → ChatStepHandler) which applies
 * side-effects (persistence, store writes) and triggers auto-advance.
 *
 * The store also tracks what Nooto has learned about the user so each
 * step's opener is grounded in real signals rather than boilerplate.
 */
import { create } from "zustand";
import {
  streamCompanionReply,
  type GeminiHistoryTurn,
} from "@/services/onboardingCompanion";
import type {
  AssistantTextTurn,
  AssistantWidgetTurn,
  ChatStepHandler,
  CompanionTurn,
  StepId,
  StepWidget,
  UserTextTurn,
  WidgetResult,
} from "@/components/onboarding/chatFlow/types";
import type { DesktopPlatform } from "@/lib/platform";

export interface CompanionSignals {
  preferredName: string;
  email: string | null;
  language: string | null;
  orgHint: string | null;
  projectNames: string[];
  applications: string[];
  technologies: string[];
  webSummary: string;
  /** Free-form notes dropped by individual steps ("mic granted", "skipped
   *  notifications") so the agent can weave them into follow-ups. */
  notes: string[];
}

interface StepOpenerState {
  fired: boolean;
  abort: AbortController | null;
}

interface CompanionState {
  conversation: CompanionTurn[];
  isStreaming: boolean;
  signals: CompanionSignals;
  stepOpeners: Record<string, StepOpenerState>;
  activeStepId: StepId | null;
  handlers: Record<string, ChatStepHandler>;
  /** Platform gets set once the shell knows it. Default `macos` is a safe
   *  placeholder that matches the "most features enabled" branch — handlers
   *  that care about platform will re-render when this becomes accurate. */
  platform: DesktopPlatform;

  registerHandlers: (handlers: ChatStepHandler[]) => void;
  setPlatform: (platform: DesktopPlatform) => void;
  setActiveStep: (stepId: StepId) => void;
  updateSignals: (patch: Partial<CompanionSignals>) => void;
  addNote: (note: string) => void;
  ensureOpenerFor: (stepId: StepId) => void;
  /** Called when the user types into the main PromptInput and the active
   *  step does NOT accept typed answers — behaves as side-chat. */
  sendSideChatMessage: (text: string) => Promise<void>;
  /** Called when the user types into the main PromptInput and the active
   *  step DOES accept typed answers. Adds the user turn and reports the
   *  capture to the active step's handler. */
  submitTypedAnswer: (text: string, onCapture: (result: WidgetResult) => Promise<void> | void) => void;
  reportWidgetCapture: (
    turnId: string,
    result: WidgetResult,
    summary: string | null,
    onCapture: (result: WidgetResult) => Promise<void> | void,
  ) => void;
  reset: () => void;
}

const INITIAL_SIGNALS: CompanionSignals = {
  preferredName: "",
  email: null,
  language: null,
  orgHint: null,
  projectNames: [],
  applications: [],
  technologies: [],
  webSummary: "",
  notes: [],
};

const SYSTEM_PROMPT = `You are Nooto, a warm but quiet AI companion guiding \
a new user through onboarding of the Nooto desktop app. Keep every message \
short — 1 to 3 sentences, plain prose, second-person ("you"), no lists or \
markdown, no sign-offs. Ground every factual claim in the SIGNALS block \
the runtime provides; never invent biographical details. When signals are \
sparse, speak to what you know and stay forward-looking. The user answers \
by tapping chips or typing inline under each of your messages — do NOT \
tell them which buttons to press. Never pressure; the flow auto-advances \
when the user provides their answer.`;

function buildSignalsBlock(signals: CompanionSignals): string {
  const lines: string[] = [];
  if (signals.preferredName) lines.push(`Name: ${signals.preferredName}`);
  if (signals.email) lines.push(`Email: ${signals.email}`);
  if (signals.orgHint) lines.push(`Likely org: ${signals.orgHint}`);
  if (signals.language) lines.push(`Language: ${signals.language}`);
  if (signals.projectNames.length > 0)
    lines.push(
      `Local projects: ${signals.projectNames.slice(0, 8).join(", ")}`,
    );
  if (signals.technologies.length > 0)
    lines.push(`Tech stack: ${signals.technologies.join(", ")}`);
  if (signals.applications.length > 0)
    lines.push(
      `Installed apps: ${signals.applications.slice(0, 12).join(", ")}`,
    );
  if (signals.webSummary) lines.push(`Web summary: ${signals.webSummary}`);
  if (signals.notes.length > 0)
    lines.push(`Runtime notes: ${signals.notes.join(" | ")}`);
  return lines.length > 0 ? lines.join("\n") : "No signals yet.";
}

/** Short stable id for each turn — scroll anchor + React key. */
let turnCounter = 0;
function nextId(prefix: string): string {
  turnCounter += 1;
  return `${prefix}-${Date.now()}-${turnCounter}`;
}

/** Flatten the rich conversation into the simple role/content pairs that
 *  Gemini's API expects. Widget turns contribute nothing to the LLM context;
 *  user answers are synthesized from the captured_summary. */
function flattenForGemini(turns: CompanionTurn[]): GeminiHistoryTurn[] {
  const out: GeminiHistoryTurn[] = [];
  for (const turn of turns) {
    if (turn.kind === "assistant_text") {
      if (turn.content.trim().length > 0) {
        out.push({ role: "assistant", content: turn.content });
      }
    } else if (turn.kind === "user_text") {
      out.push({ role: "user", content: turn.content });
    } else if (turn.kind === "assistant_widget" && turn.capturedSummary) {
      // A captured widget reads as a user turn in LLM context ("the user
      // chose English" / "granted microphone").
      out.push({
        role: "user",
        content: `(${turn.capturedSummary})`,
      });
    }
  }
  return out;
}

export const useOnboardingCompanionStore = create<CompanionState>(
  (set, get) => ({
    conversation: [],
    isStreaming: false,
    signals: { ...INITIAL_SIGNALS },
    stepOpeners: {},
    activeStepId: null,
    handlers: {},
    platform: "macos",

    registerHandlers: (handlers) => {
      const map: Record<string, ChatStepHandler> = {};
      for (const h of handlers) map[h.stepId] = h;
      set({ handlers: map });
    },

    setPlatform: (platform) => set({ platform }),

    setActiveStep: (stepId) => {
      if (get().activeStepId === stepId) {
        // Same step — might be a remount. ensureOpenerFor's guard handles
        // idempotency.
        get().ensureOpenerFor(stepId);
        return;
      }
      set({ activeStepId: stepId });
      get().ensureOpenerFor(stepId);
    },

    updateSignals: (patch) => {
      set((state) => ({
        signals: { ...state.signals, ...patch },
      }));
    },

    addNote: (note) => {
      set((state) => ({
        signals: {
          ...state.signals,
          notes: [...state.signals.notes, note].slice(-12),
        },
      }));
    },

    ensureOpenerFor: (stepId) => {
      const state = get();
      const existing = state.stepOpeners[stepId];
      if (existing?.fired) return;

      const handler = state.handlers[stepId];
      if (!handler) {
        // Handlers not registered yet — bail; the shell will retry once
        // registration completes.
        return;
      }

      const abort = new AbortController();
      set((s) => ({
        stepOpeners: {
          ...s.stepOpeners,
          [stepId]: { fired: true, abort },
        },
      }));

      void runOpener(stepId, handler, abort.signal);
    },

    sendSideChatMessage: async (text) => {
      const trimmed = text.trim();
      if (!trimmed) return;
      const state = get();
      if (state.isStreaming) return;

      const userTurn: UserTextTurn = {
        kind: "user_text",
        id: nextId("u"),
        content: trimmed,
      };
      const assistantTurn: AssistantTextTurn = {
        kind: "assistant_text",
        id: nextId("a"),
        content: "",
        streaming: true,
        stepId: state.activeStepId,
      };

      const historyForReply = flattenForGemini(state.conversation);
      set((s) => ({
        conversation: [...s.conversation, userTurn, assistantTurn],
        isStreaming: true,
      }));

      const stepId = state.activeStepId ?? "unknown";
      const contextMessage = [
        trimmed,
        ``,
        `[Runtime context — not user-authored]`,
        `Current step: ${stepId}`,
        `SIGNALS:`,
        buildSignalsBlock(state.signals),
      ].join("\n");

      try {
        await streamCompanionReply({
          systemPrompt: SYSTEM_PROMPT,
          history: historyForReply,
          userMessage: contextMessage,
          onDelta: (chunk) => {
            set((curr) => {
              const convo = [...curr.conversation];
              // Find the assistant turn we just seeded (by id, in case the
              // list has grown meanwhile).
              const idx = convo.findIndex(
                (t) => t.kind === "assistant_text" && t.id === assistantTurn.id,
              );
              if (idx === -1) return {};
              const t = convo[idx] as AssistantTextTurn;
              convo[idx] = { ...t, content: t.content + chunk };
              return { conversation: convo };
            });
          },
        });
      } catch (err) {
        console.warn("[companion] side-chat failed:", err);
        set((curr) => {
          const convo = [...curr.conversation];
          const idx = convo.findIndex(
            (t) => t.kind === "assistant_text" && t.id === assistantTurn.id,
          );
          if (idx !== -1) {
            const t = convo[idx] as AssistantTextTurn;
            if (t.content === "") {
              convo[idx] = {
                ...t,
                content:
                  "Hmm, I lost that reply — mind asking again?",
              };
            }
          }
          return { conversation: convo };
        });
      } finally {
        set((curr) => {
          const convo = [...curr.conversation];
          const idx = convo.findIndex(
            (t) => t.kind === "assistant_text" && t.id === assistantTurn.id,
          );
          if (idx !== -1) {
            const t = convo[idx] as AssistantTextTurn;
            convo[idx] = { ...t, streaming: false };
          }
          return { conversation: convo, isStreaming: false };
        });
      }
    },

    submitTypedAnswer: (text, onCapture) => {
      const trimmed = text.trim();
      if (!trimmed) return;
      const state = get();
      // Append the user turn so it shows up in the chat.
      set((s) => ({
        conversation: [
          ...s.conversation,
          { kind: "user_text", id: nextId("u"), content: trimmed },
        ],
      }));
      // Mark any pending widget for the active step as captured, since the
      // typed answer supersedes it.
      if (state.activeStepId) {
        const stepId = state.activeStepId;
        set((s) => {
          const convo = s.conversation.map((t) => {
            if (
              t.kind === "assistant_widget" &&
              t.stepId === stepId &&
              !t.captured
            ) {
              return {
                ...t,
                captured: true,
                capturedSummary: trimmed,
              };
            }
            return t;
          });
          return { conversation: convo };
        });
      }
      void Promise.resolve(onCapture({ text: trimmed }));
    },

    reportWidgetCapture: (turnId, result, summary, onCapture) => {
      set((s) => {
        const convo = s.conversation.map((t) => {
          if (t.kind === "assistant_widget" && t.id === turnId) {
            return {
              ...t,
              captured: true,
              capturedSummary: summary ?? undefined,
            };
          }
          return t;
        });
        return { conversation: convo };
      });
      void Promise.resolve(onCapture(result));
    },

    reset: () => {
      // Abort any in-flight openers so their deltas don't land after reset.
      const state = get();
      Object.values(state.stepOpeners).forEach((opener) =>
        opener.abort?.abort(),
      );
      turnCounter = 0;
      set({
        conversation: [],
        isStreaming: false,
        signals: { ...INITIAL_SIGNALS },
        stepOpeners: {},
        activeStepId: null,
        // Keep handlers registered across resets — they're defined once.
      });
    },
  }),
);

/** Runs the opener flow for a step: streams Gemini greeting, then emits the
 *  widget turn. Failure modes fall back to the handler's static copy so the
 *  flow never blocks on the LLM being up. */
async function runOpener(
  stepId: StepId,
  handler: ChatStepHandler,
  signal: AbortSignal,
): Promise<void> {
  const api = useOnboardingCompanionStore;
  const initial = api.getState();

  // Seed an empty assistant turn we can stream into.
  const textTurn: AssistantTextTurn = {
    kind: "assistant_text",
    id: nextId("a"),
    content: "",
    streaming: true,
    stepId,
  };
  const historyForReply = flattenForGemini(initial.conversation);
  api.setState((s) => ({
    conversation: [...s.conversation, textTurn],
    isStreaming: true,
  }));

  const instruction = handler.buildOpenerInstruction(initial.signals);
  const userMessage = [
    `[Runtime context]`,
    `Current step: ${stepId}`,
    `Instruction: ${instruction}`,
    ``,
    `SIGNALS:`,
    buildSignalsBlock(initial.signals),
    ``,
    `Respond with only the message the user should see — no meta-commentary.`,
  ].join("\n");

  let usedFallback = false;

  try {
    await streamCompanionReply({
      systemPrompt: SYSTEM_PROMPT,
      history: historyForReply,
      userMessage,
      signal,
      onDelta: (chunk) => {
        api.setState((curr) => {
          const convo = [...curr.conversation];
          const idx = convo.findIndex(
            (t) => t.kind === "assistant_text" && t.id === textTurn.id,
          );
          if (idx === -1) return {};
          const t = convo[idx] as AssistantTextTurn;
          convo[idx] = { ...t, content: t.content + chunk };
          return { conversation: convo };
        });
      },
    });
  } catch (err) {
    if ((err as Error).name === "AbortError") {
      return;
    }
    console.warn(`[companion] opener for ${stepId} failed:`, err);
    usedFallback = true;
    const fallback = handler.fallbackOpener(initial.signals);
    api.setState((curr) => {
      const convo = [...curr.conversation];
      const idx = convo.findIndex(
        (t) => t.kind === "assistant_text" && t.id === textTurn.id,
      );
      if (idx === -1) return {};
      const t = convo[idx] as AssistantTextTurn;
      convo[idx] = { ...t, content: fallback };
      return { conversation: convo };
    });
  } finally {
    // Flip streaming flag off for this turn.
    api.setState((curr) => {
      const convo = [...curr.conversation];
      const idx = convo.findIndex(
        (t) => t.kind === "assistant_text" && t.id === textTurn.id,
      );
      if (idx !== -1) {
        const t = convo[idx] as AssistantTextTurn;
        // If the stream returned zero tokens and we didn't already fallback,
        // inject the fallback now.
        const content =
          t.content.trim().length === 0 && !usedFallback
            ? handler.fallbackOpener(initial.signals)
            : t.content;
        convo[idx] = { ...t, content, streaming: false };
      }
      return { conversation: convo, isStreaming: false };
    });
  }

  // Emit the interactive widget turn now that the opener text is in place.
  // Steps that want typed input from the main PromptInput (name, goal free
  // text) can return { type: "none" } to skip the widget — no duplicate
  // input affordance.
  const stateNow = api.getState();
  const widget: StepWidget = handler.widget(stateNow.signals, stateNow.platform);
  if (widget.type === "none") return;
  const widgetTurn: AssistantWidgetTurn = {
    kind: "assistant_widget",
    id: nextId("w"),
    stepId,
    widget,
    captured: false,
  };
  api.setState((s) => ({
    conversation: [...s.conversation, widgetTurn],
  }));
}
