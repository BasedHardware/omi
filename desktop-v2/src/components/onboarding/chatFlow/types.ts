/**
 * Shared types for the chat-driven onboarding flow. The conversation is a
 * heterogeneous list of turns — assistant text, user text, and interactive
 * "widget" bubbles that each step emits to capture whatever input it needs.
 */
import type {
  OnboardingStepId,
  PermissionStatus,
} from "@/stores/onboardingStore";
import type { DesktopPlatform } from "@/lib/platform";
import type { CompanionSignals } from "@/stores/onboardingCompanionStore";

export type StepId = OnboardingStepId;

// ---------------------------------------------------------------------------
// Turns
// ---------------------------------------------------------------------------

export interface AssistantTextTurn {
  kind: "assistant_text";
  id: string;
  content: string;
  streaming: boolean;
  /** Which step produced this turn. `null` for ad-hoc side-chat replies that
   *  aren't tied to the active step's opener. */
  stepId: StepId | null;
}

export interface UserTextTurn {
  kind: "user_text";
  id: string;
  content: string;
}

export interface AssistantWidgetTurn {
  kind: "assistant_widget";
  id: string;
  stepId: StepId;
  widget: StepWidget;
  /** Flipped to true once the widget has been interacted with. The widget
   *  renders read-only afterwards so the user can see what they answered
   *  without being able to mutate it after moving on. */
  captured: boolean;
  /** The captured result — rendered inline (e.g. "Matheus" under the input
   *  widget, "Granted" under the permission widget) once captured. */
  capturedSummary?: string;
}

export type CompanionTurn =
  | AssistantTextTurn
  | UserTextTurn
  | AssistantWidgetTurn;

// ---------------------------------------------------------------------------
// Widgets — the interactive payload the assistant drops into the chat
// ---------------------------------------------------------------------------

export interface ChipOption {
  id: string;
  label: string;
  sublabel?: string;
}

export type StepWidget =
  | {
      /** No interactive bubble; the step expects input from the main
       *  PromptInput at the bottom of the screen. Used by text-only steps
       *  like name/goal where a redundant inline input would duplicate
       *  the prompt bar. */
      type: "none";
    }
  | {
      type: "chips";
      options: ChipOption[];
      /** When true, the widget also renders a free-text input; commits on
       *  Enter just like picking a chip. */
      allowFreeText: boolean;
      placeholder?: string;
    }
  | {
      type: "text_prompt";
      placeholder: string;
      initialValue?: string;
    }
  | {
      type: "permission_grant";
      kind: string;
      label: string;
      skippable: boolean;
      /** Short descriptor shown next to the status badge for context. */
      helper?: string;
    }
  | {
      type: "file_scan_progress";
    }
  | {
      type: "shortcut_capture";
      kind: "floating_bar" | "voice";
      allowModifierOnly: boolean;
    }
  | {
      type: "research_panel";
    }
  | {
      type: "acknowledge";
      label: string;
      skippable?: boolean;
    };

export type WidgetResult =
  | { chip: string }
  | { text: string }
  | { granted: boolean; skipped?: boolean }
  | { scanDone: true }
  | { chord: string }
  | { ack: true };

// ---------------------------------------------------------------------------
// Step handler — one per onboarding step
// ---------------------------------------------------------------------------

export interface HandlerCtx {
  signals: CompanionSignals;
  platform: DesktopPlatform;
  /** Call onto the main onboarding store to persist step outputs. */
  onboarding: {
    setPreferredName(name: string): void;
    setLanguage(lang: string | null): void;
    setGoal(goal: string | null): void;
    setFloatingBarShortcut(s: string): void;
    setVoiceShortcut(s: string): void;
    setPermission(kind: string, status: PermissionStatus): void;
    advance(): void;
    markCompleted(): Promise<void>;
  };
  companion: {
    updateSignals(patch: Partial<CompanionSignals>): void;
    addNote(note: string): void;
  };
  /** Called by the final step's handler to exit onboarding. */
  finishOnboarding(): void;
}

export interface ChatStepHandler {
  stepId: StepId;
  /** When omitted the step runs on every platform. */
  includeForPlatform?: (platform: DesktopPlatform) => boolean;
  /** Gemini system-prompt appendix describing what the opener should say
   *  for this step. Called per-step so the signals-at-time-of-step are used. */
  buildOpenerInstruction: (signals: CompanionSignals) => string;
  /** Static copy used if the Gemini stream fails or the API key is missing.
   *  Chat flow must NEVER block on the LLM — the fallback copy is always
   *  good enough to advance without it. */
  fallbackOpener: (signals: CompanionSignals) => string;
  /** The interactive widget that shows beneath the opener. */
  widget: (signals: CompanionSignals, platform: DesktopPlatform) => StepWidget;
  /** When true, a typed message in the main PromptInput is routed to this
   *  step's `onCapture` instead of the side-chat. */
  acceptsTypedAnswer: boolean;
  onCapture: (result: WidgetResult, ctx: HandlerCtx) => Promise<void>;
  /** Marks the step as safely skippable — appears as a muted affordance on
   *  supported widgets. */
  skippable?: boolean;
  /** Short summary rendered under the widget once captured (e.g. "Matheus",
   *  "English", "Granted"). Returning null suppresses the summary row. */
  summarize?: (result: WidgetResult) => string | null;
}
