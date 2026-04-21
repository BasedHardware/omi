import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Conversation,
  ConversationContent,
  ConversationScrollButton,
} from "@/components/ai-elements/conversation";
import {
  Message,
  MessageContent,
  MessageResponse,
} from "@/components/ai-elements/message";
import {
  PromptInput,
  PromptInputBody,
  PromptInputFooter,
  PromptInputSubmit,
  PromptInputTextarea,
  PromptInputTools,
  type PromptInputMessage,
} from "@/components/ai-elements/prompt-input";
import { Shimmer } from "@/components/ai-elements/shimmer";
import { getPlatform, type DesktopPlatform } from "@/lib/platform";
import { useAuthStore } from "@/stores/authStore";
import { useOnboardingStore } from "@/stores/onboardingStore";
import {
  useOnboardingCompanionStore,
  type CompanionSignals,
} from "@/stores/onboardingCompanionStore";
import {
  ALL_HANDLERS,
  getHandler,
  stepIdsForPlatform,
} from "./ChatStepRegistry";
import { WidgetMount } from "./widgets";
import type {
  AssistantTextTurn,
  AssistantWidgetTurn,
  CompanionTurn,
  HandlerCtx,
  StepId,
  UserTextTurn,
  WidgetResult,
} from "./types";

interface Props {
  onComplete: () => void;
}

/** Fullscreen chat-driven onboarding. Replaces the legacy split/centered
 *  layout entirely. No header, no footer, no progress bar — the chat scroll
 *  itself is the flow. */
export function OnboardingChat({ onComplete }: Props) {
  const [platform, setPlatform] = useState<DesktopPlatform | null>(null);

  // Stable reference to Zustand stores via getState() inside handler ctx.
  const onboardingStore = useOnboardingStore;
  const companionStore = useOnboardingCompanionStore;

  const conversation = useOnboardingCompanionStore((s) => s.conversation);
  const isStreaming = useOnboardingCompanionStore((s) => s.isStreaming);
  const currentStepIndex = useOnboardingStore((s) => s.currentStepIndex);
  const hasCompletedOnboarding = useOnboardingStore(
    (s) => s.hasCompletedOnboarding,
  );
  const preferredName = useOnboardingStore((s) => s.preferredName);
  const language = useOnboardingStore((s) => s.language);
  const userEmail = useAuthStore((s) => s.userEmail);

  // ------------------------------------------------------------------
  // Platform detection + registration (once)
  // ------------------------------------------------------------------
  useEffect(() => {
    let cancelled = false;
    getPlatform().then((p) => {
      if (cancelled) return;
      setPlatform(p);
      companionStore.getState().setPlatform(p);
    });
    return () => {
      cancelled = true;
    };
  }, [companionStore]);

  useEffect(() => {
    companionStore.getState().registerHandlers(ALL_HANDLERS);
  }, [companionStore]);

  // ------------------------------------------------------------------
  // Feed shell-known signals into the companion
  // ------------------------------------------------------------------
  useEffect(() => {
    companionStore.getState().updateSignals({
      preferredName: preferredName || "",
      email: userEmail ?? null,
      language: language ?? null,
    });
  }, [preferredName, userEmail, language, companionStore]);

  // ------------------------------------------------------------------
  // Resolve the active step and drive openers
  // ------------------------------------------------------------------
  const stepIds = useMemo<StepId[]>(() => {
    if (!platform) return [];
    return stepIdsForPlatform(platform);
  }, [platform]);

  const activeStepId: StepId | null = useMemo(() => {
    if (stepIds.length === 0) return null;
    const clamped = Math.min(
      Math.max(0, currentStepIndex),
      stepIds.length - 1,
    );
    return stepIds[clamped];
  }, [stepIds, currentStepIndex]);

  useEffect(() => {
    if (!activeStepId) return;
    companionStore.getState().setActiveStep(activeStepId);
  }, [activeStepId, companionStore]);

  // ------------------------------------------------------------------
  // Finish detection
  // ------------------------------------------------------------------
  useEffect(() => {
    if (hasCompletedOnboarding) onComplete();
  }, [hasCompletedOnboarding, onComplete]);

  // ------------------------------------------------------------------
  // Handler context builder (re-created on each capture so side-effects see
  // fresh store state)
  // ------------------------------------------------------------------
  const buildHandlerCtx = useCallback(
    (stepId: StepId): HandlerCtx => {
      const signals: CompanionSignals = companionStore.getState().signals;
      const onboarding = onboardingStore.getState();
      return {
        signals,
        platform: platform ?? "macos",
        onboarding: {
          setPreferredName: onboarding.setPreferredName,
          setLanguage: onboarding.setLanguage,
          setGoal: onboarding.setGoal,
          setFloatingBarShortcut: onboarding.setFloatingBarShortcut,
          setVoiceShortcut: onboarding.setVoiceShortcut,
          setPermission: onboarding.setPermission,
          advance: onboarding.advance,
          markCompleted: onboarding.markCompleted,
        },
        companion: {
          updateSignals: (patch) =>
            companionStore.getState().updateSignals(patch),
          addNote: (note) => companionStore.getState().addNote(note),
        },
        finishOnboarding: onComplete,
      };
      // stepId is here so future per-step context (e.g. active turn id) is easy
      // to thread in. Intentionally unused right now.
      void stepId;
    },
    [companionStore, onboardingStore, platform, onComplete],
  );

  // ------------------------------------------------------------------
  // Widget capture dispatcher
  // ------------------------------------------------------------------
  const handleWidgetCapture = useCallback(
    (turn: AssistantWidgetTurn, result: WidgetResult, summary: string | null) => {
      const handler = getHandler(turn.stepId);
      if (!handler) return;
      const resolvedSummary =
        summary ?? (handler.summarize ? handler.summarize(result) : null);
      companionStore.getState().reportWidgetCapture(
        turn.id,
        result,
        resolvedSummary,
        async (r) => {
          try {
            await handler.onCapture(r, buildHandlerCtx(turn.stepId));
          } catch (err) {
            console.warn(
              `[onboarding] handler ${turn.stepId} failed:`,
              err,
            );
          }
        },
      );
    },
    [companionStore, buildHandlerCtx],
  );

  // ------------------------------------------------------------------
  // Main PromptInput submission — routes to the active step's handler if
  // it accepts typed answers, otherwise side-chats the companion.
  // ------------------------------------------------------------------
  const [inputText, setInputText] = useState("");

  const handleSubmit = useCallback(
    (message: PromptInputMessage) => {
      const text = (message?.text ?? "").trim();
      if (!text) return;
      setInputText("");
      const step = activeStepId;
      if (!step) return;
      const handler = getHandler(step);
      if (handler?.acceptsTypedAnswer) {
        companionStore
          .getState()
          .submitTypedAnswer(text, async (r) => {
            try {
              await handler.onCapture(r, buildHandlerCtx(step));
            } catch (err) {
              console.warn(
                `[onboarding] typed capture for ${step} failed:`,
                err,
              );
            }
          });
      } else {
        void companionStore.getState().sendSideChatMessage(text);
      }
    },
    [activeStepId, companionStore, buildHandlerCtx],
  );

  // ------------------------------------------------------------------
  // Render
  // ------------------------------------------------------------------
  if (!platform) {
    return (
      <div className="w-screen h-screen bg-background flex items-center justify-center">
        <Shimmer>Loading…</Shimmer>
      </div>
    );
  }

  const chatStatus = isStreaming ? ("streaming" as const) : ("ready" as const);

  return (
    <div className="flex flex-col w-screen h-screen bg-background text-foreground">
      <Conversation className="flex-1">
        <ConversationContent className="max-w-[760px] mx-auto">
          {conversation.length === 0 ? (
            <div className="flex items-center justify-center py-12">
              <Shimmer>Nooto is getting up to speed…</Shimmer>
            </div>
          ) : null}
          {conversation.map((turn) => (
            <TurnView
              key={turn.id}
              turn={turn}
              onWidgetCapture={handleWidgetCapture}
            />
          ))}
        </ConversationContent>
        <ConversationScrollButton />
      </Conversation>

      <div className="shrink-0 px-5 pb-5 pt-3 max-w-[760px] w-full mx-auto">
        <PromptInput onSubmit={handleSubmit} className="w-full">
          <PromptInputBody>
            <PromptInputTextarea
              value={inputText}
              onChange={(e) => setInputText(e.target.value)}
              placeholder={promptPlaceholder(activeStepId)}
              autoFocus
            />
          </PromptInputBody>
          <PromptInputFooter>
            <PromptInputTools />
            <PromptInputSubmit
              status={chatStatus}
              disabled={chatStatus === "ready" && !inputText.trim()}
            />
          </PromptInputFooter>
        </PromptInput>
      </div>
    </div>
  );
}

function promptPlaceholder(activeStepId: StepId | null): string {
  if (!activeStepId) return "Say hi";
  const handler = getHandler(activeStepId);
  if (handler?.acceptsTypedAnswer) return "Type your answer…";
  return "Ask Nooto anything";
}

// ---------------------------------------------------------------------------
// Turn rendering
// ---------------------------------------------------------------------------

interface TurnViewProps {
  turn: CompanionTurn;
  onWidgetCapture: (
    turn: AssistantWidgetTurn,
    result: WidgetResult,
    summary: string | null,
  ) => void;
}

function TurnView({ turn, onWidgetCapture }: TurnViewProps) {
  if (turn.kind === "user_text") {
    return <UserTurnView turn={turn} />;
  }
  if (turn.kind === "assistant_text") {
    return <AssistantTextView turn={turn} />;
  }
  return (
    <AssistantWidgetView turn={turn} onWidgetCapture={onWidgetCapture} />
  );
}

function UserTurnView({ turn }: { turn: UserTextTurn }) {
  return (
    <Message from="user">
      <MessageContent>{turn.content}</MessageContent>
    </Message>
  );
}

function AssistantTextView({ turn }: { turn: AssistantTextTurn }) {
  if (!turn.content && turn.streaming) {
    return (
      <Message from="assistant">
        <MessageContent>
          <Shimmer>Thinking…</Shimmer>
        </MessageContent>
      </Message>
    );
  }
  return (
    <Message from="assistant">
      <MessageContent>
        <MessageResponse>{turn.content}</MessageResponse>
      </MessageContent>
    </Message>
  );
}

function AssistantWidgetView({
  turn,
  onWidgetCapture,
}: {
  turn: AssistantWidgetTurn;
  onWidgetCapture: TurnViewProps["onWidgetCapture"];
}) {
  const handleCapture = useCallback(
    (result: WidgetResult, summary: string | null) => {
      onWidgetCapture(turn, result, summary);
    },
    [turn, onWidgetCapture],
  );
  return (
    <Message from="assistant">
      <MessageContent>
        <WidgetMount
          widget={turn.widget}
          disabled={turn.captured}
          onCapture={handleCapture}
        />
        {turn.captured && turn.capturedSummary ? (
          <div className="text-[12px] text-muted-foreground mt-2">
            You said: {turn.capturedSummary}
          </div>
        ) : null}
      </MessageContent>
    </Message>
  );
}
