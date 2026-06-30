import type {
  DesktopArtifactDeliveryStatus,
  DesktopCandidateStatus,
  DesktopDispatchKind,
  DesktopDispatchStatus,
  RunStatus,
} from "./types.js";

export type DesktopActionQueueItemKind =
  | "dispatch"
  | "failed_run"
  | "artifact_delivery"
  | "stale_run"
  | "candidate_review"
  | "legacy_pill"
  | "reusable_session";

export interface DesktopActionQueueItem {
  itemId: string;
  kind: DesktopActionQueueItemKind;
  subjectKind: string;
  subjectId: string;
  ownerId: string;
  title: string;
  priority: number;
  rank: number;
  createdAtMs: number;
  sourceSessionId?: string | null;
  sourceRunId?: string | null;
  dispatchKind?: DesktopDispatchKind;
  reason: string;
}

export interface QueueDispatchInput {
  dispatchId: string;
  ownerId: string;
  kind: DesktopDispatchKind;
  status: DesktopDispatchStatus;
  title: string;
  priority: number;
  createdAtMs: number;
  sourceSessionId?: string | null;
  sourceRunId?: string | null;
}

export interface QueueRunInput {
  runId: string;
  sessionId: string;
  ownerId: string;
  status: RunStatus;
  title?: string | null;
  updatedAtMs: number;
  createdAtMs: number;
  visibleUserGoal?: boolean;
  reusable?: boolean;
}

export interface QueueArtifactDeliveryInput {
  deliveryId: string;
  artifactId: string;
  ownerId: string;
  sourceSessionId: string;
  sourceRunId?: string | null;
  deliveryStatus: DesktopArtifactDeliveryStatus;
  reviewStatus?: string;
  createdAtMs: number;
  updatedAtMs: number;
  targetKind: string;
}

export interface QueueCandidateInput {
  candidateId: string;
  ownerId: string;
  kind: "memory_candidate" | "task_candidate";
  status: DesktopCandidateStatus;
  createdAtMs: number;
  sourceSessionId?: string | null;
  sourceRunId?: string | null;
}

export interface QueueLegacyPillInput {
  pillId: string;
  ownerId: string;
  title: string;
  status: "running" | "failed" | "completed" | "waiting";
  createdAtMs: number;
  updatedAtMs: number;
}

export interface QueueOverrideInput {
  ownerId: string;
  subjectKind: string;
  subjectId: string;
  hiddenUntilMs?: number | null;
  dismissedAtMs?: number | null;
}

export interface BuildDesktopActionQueueInput {
  nowMs: number;
  staleAfterMs?: number;
  dispatches?: readonly QueueDispatchInput[];
  runs?: readonly QueueRunInput[];
  artifactDeliveries?: readonly QueueArtifactDeliveryInput[];
  candidates?: readonly QueueCandidateInput[];
  legacyPills?: readonly QueueLegacyPillInput[];
  overrides?: readonly QueueOverrideInput[];
}

function isSuppressed(item: DesktopActionQueueItem, overrides: readonly QueueOverrideInput[], nowMs: number): boolean {
  return overrides.some((override) => {
    if (override.ownerId !== item.ownerId || override.subjectKind !== item.subjectKind || override.subjectId !== item.subjectId) {
      return false;
    }
    if (override.dismissedAtMs != null) return true;
    return override.hiddenUntilMs != null && override.hiddenUntilMs > nowMs;
  });
}

function item(input: Omit<DesktopActionQueueItem, "itemId">): DesktopActionQueueItem {
  return { ...input, itemId: `${input.kind}:${input.subjectKind}:${input.subjectId}` };
}

export function buildDesktopActionQueue(input: BuildDesktopActionQueueInput): DesktopActionQueueItem[] {
  const nowMs = input.nowMs;
  const staleAfterMs = input.staleAfterMs ?? 30 * 60 * 1000;
  const items: DesktopActionQueueItem[] = [];

  for (const dispatch of input.dispatches ?? []) {
    if (dispatch.status !== "pending") continue;
    items.push(
      item({
        kind: "dispatch",
        subjectKind: "dispatch",
        subjectId: dispatch.dispatchId,
        ownerId: dispatch.ownerId,
        title: dispatch.title,
        priority: 100 + dispatch.priority,
        rank: 1,
        createdAtMs: dispatch.createdAtMs,
        sourceSessionId: dispatch.sourceSessionId ?? null,
        sourceRunId: dispatch.sourceRunId ?? null,
        dispatchKind: dispatch.kind,
        reason: "Pending dispatch blocks local coordinator progress.",
      }),
    );
  }

  for (const run of input.runs ?? []) {
    if ((run.status === "failed" || run.status === "orphaned") && run.visibleUserGoal !== false) {
      items.push(
        item({
          kind: "failed_run",
          subjectKind: "run",
          subjectId: run.runId,
          ownerId: run.ownerId,
          title: run.title ?? "Recover failed agent run",
          priority: 90,
          rank: 2,
          createdAtMs: run.updatedAtMs,
          sourceSessionId: run.sessionId,
          sourceRunId: run.runId,
          reason: `${run.status} run tied to a visible user goal needs recovery.`,
        }),
      );
    } else if (["queued", "starting", "running", "waiting_input", "waiting_approval"].includes(run.status) && nowMs - run.updatedAtMs >= staleAfterMs) {
      items.push(
        item({
          kind: "stale_run",
          subjectKind: "run",
          subjectId: run.runId,
          ownerId: run.ownerId,
          title: run.title ?? "Check stale agent run",
          priority: 70,
          rank: 4,
          createdAtMs: run.updatedAtMs,
          sourceSessionId: run.sessionId,
          sourceRunId: run.runId,
          reason: "Active run has not advanced within the stale threshold.",
        }),
      );
    } else if (run.reusable === true) {
      items.push(
        item({
          kind: "reusable_session",
          subjectKind: "session",
          subjectId: run.sessionId,
          ownerId: run.ownerId,
          title: run.title ?? "Reusable agent session",
          priority: 20,
          rank: 7,
          createdAtMs: run.updatedAtMs,
          sourceSessionId: run.sessionId,
          sourceRunId: run.runId,
          reason: "Existing session may be relevant to the current request.",
        }),
      );
    }
  }

  for (const delivery of input.artifactDeliveries ?? []) {
    if (!["pending", "failed", "retrying"].includes(delivery.deliveryStatus)) continue;
    items.push(
      item({
        kind: "artifact_delivery",
        subjectKind: "artifact_delivery",
        subjectId: delivery.deliveryId,
        ownerId: delivery.ownerId,
        title: `Review ${delivery.targetKind} artifact delivery`,
        priority: delivery.deliveryStatus === "failed" ? 85 : 80,
        rank: 3,
        createdAtMs: delivery.updatedAtMs,
        sourceSessionId: delivery.sourceSessionId,
        sourceRunId: delivery.sourceRunId ?? null,
        reason: "Completed run has an undelivered artifact or result.",
      }),
    );
  }

  for (const candidate of input.candidates ?? []) {
    if (candidate.status !== "pending") continue;
    items.push(
      item({
        kind: "candidate_review",
        subjectKind: candidate.kind,
        subjectId: candidate.candidateId,
        ownerId: candidate.ownerId,
        title: candidate.kind === "memory_candidate" ? "Review memory candidate" : "Review task candidate",
        priority: 60,
        rank: 5,
        createdAtMs: candidate.createdAtMs,
        sourceSessionId: candidate.sourceSessionId ?? null,
        sourceRunId: candidate.sourceRunId ?? null,
        reason: "Candidate mutation requires explicit review before canonical state changes.",
      }),
    );
  }

  for (const pill of input.legacyPills ?? []) {
    if (pill.status === "completed") continue;
    items.push(
      item({
        kind: "legacy_pill",
        subjectKind: "legacy_pill",
        subjectId: pill.pillId,
        ownerId: pill.ownerId,
        title: pill.title,
        priority: pill.status === "failed" ? 75 : 40,
        rank: pill.status === "failed" ? 2 : 6,
        createdAtMs: pill.updatedAtMs,
        reason: "Legacy floating pill is projected into the derived action queue.",
      }),
    );
  }

  return items
    .filter((queueItem) => !isSuppressed(queueItem, input.overrides ?? [], nowMs))
    .sort((left, right) => left.rank - right.rank || right.priority - left.priority || right.createdAtMs - left.createdAtMs);
}
