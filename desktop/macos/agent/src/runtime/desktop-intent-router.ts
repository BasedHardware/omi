import type { DesktopActionQueueItem } from "./desktop-action-queue.js";

export type DesktopIntentRouteKind = "quick_answer" | "resume" | "fork" | "delegate" | "dispatch" | "new_run";

export interface DesktopIntentSessionCandidate {
  sessionId: string;
  runId?: string | null;
  surfaceKind: string;
  taskId?: string | null;
  title?: string | null;
  status: "healthy" | "stale" | "failed" | "orphaned" | "closed";
  relevance: number;
  lastActivityAtMs: number;
}

export interface DesktopIntentRouteInput {
  utterance: string;
  surfaceKind: string;
  taskId?: string | null;
  nowMs: number;
  actionQueue?: readonly DesktopActionQueueItem[];
  sessionCandidates?: readonly DesktopIntentSessionCandidate[];
}

export interface DesktopIntentRoute {
  intent: DesktopIntentRouteKind;
  explanation: string;
  sessionId?: string;
  runId?: string | null;
  dispatchId?: string;
  queueItemId?: string;
}

function isExternalSendAmbiguous(utterance: string): boolean {
  return /\b(send|email|post|share|submit)\b/i.test(utterance) && !/\b(draft|prepare|do not send|don't send)\b/i.test(utterance);
}

function isQuickAnswer(utterance: string): boolean {
  return /\b(status|what'?s running|list agents|open loops|what happened)\b/i.test(utterance);
}

function isLongRunning(utterance: string): boolean {
  return /\b(research|implement|build|fix|test|audit|review|refactor|investigate|long[- ]running|background)\b/i.test(utterance);
}

function chooseCandidate(input: DesktopIntentRouteInput): DesktopIntentSessionCandidate | undefined {
  const candidates = [...(input.sessionCandidates ?? [])].sort(
    (left, right) => right.relevance - left.relevance || right.lastActivityAtMs - left.lastActivityAtMs,
  );
  return candidates.find((candidate) => {
    if (candidate.relevance < 0.55) return false;
    if (input.taskId) return candidate.taskId === input.taskId;
    return candidate.surfaceKind === input.surfaceKind || candidate.taskId === input.taskId;
  });
}

export function routeDesktopIntent(input: DesktopIntentRouteInput): DesktopIntentRoute {
  const dispatchItem = (input.actionQueue ?? []).find((item) => item.kind === "dispatch");
  if (dispatchItem) {
    return {
      intent: "dispatch",
      dispatchId: dispatchItem.subjectId,
      queueItemId: dispatchItem.itemId,
      explanation: "A pending dispatch must be resolved before routing additional local agent work.",
    };
  }
  if (isExternalSendAmbiguous(input.utterance)) {
    return {
      intent: "dispatch",
      explanation: "External send/share intent is ambiguous and requires a durable dispatch.",
    };
  }

  const candidate = chooseCandidate(input);
  if (candidate) {
    if (candidate.status === "healthy") {
      return {
        intent: "resume",
        sessionId: candidate.sessionId,
        runId: candidate.runId ?? null,
        explanation: "The request matches a healthy recent session on the same task or surface.",
      };
    }
    if (candidate.status === "stale" || candidate.status === "failed" || candidate.status === "orphaned") {
      return {
        intent: "fork",
        sessionId: candidate.sessionId,
        runId: candidate.runId ?? null,
        explanation: "Related prior context is useful, but the existing run is stale or failed, so isolate follow-up work.",
      };
    }
  }

  if (isQuickAnswer(input.utterance)) {
    return { intent: "quick_answer", explanation: "The request can be answered from local coordinator state." };
  }
  if (isLongRunning(input.utterance)) {
    return { intent: "delegate", explanation: "The request appears to require long-running or specialist work." };
  }
  return { intent: "new_run", explanation: "No reusable session or blocking dispatch matched the request." };
}

export const desktopIntentRouterInternals = {
  isExternalSendAmbiguous,
  isQuickAnswer,
  isLongRunning,
};
