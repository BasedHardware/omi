import { describe, expect, it } from "vitest";
import { buildDesktopActionQueue } from "../src/runtime/desktop-action-queue.js";

describe("desktop action queue", () => {
  it("ranks pending dispatches before failed runs, artifact deliveries, and stale work", () => {
    const queue = buildDesktopActionQueue({
      nowMs: 10_000,
      staleAfterMs: 1_000,
      dispatches: [
        {
          dispatchId: "dispatch-1",
          ownerId: "owner-1",
          kind: "approval",
          status: "pending",
          title: "Approve send",
          priority: 1,
          createdAtMs: 9_000,
        },
      ],
      runs: [
        {
          runId: "failed-run",
          sessionId: "session-1",
          ownerId: "owner-1",
          status: "failed",
          createdAtMs: 1_000,
          updatedAtMs: 8_000,
        },
        {
          runId: "stale-run",
          sessionId: "session-2",
          ownerId: "owner-1",
          status: "running",
          createdAtMs: 1_000,
          updatedAtMs: 2_000,
        },
      ],
      artifactDeliveries: [
        {
          deliveryId: "delivery-1",
          artifactId: "artifact-1",
          ownerId: "owner-1",
          sourceSessionId: "session-1",
          sourceRunId: "run-1",
          deliveryStatus: "pending",
          createdAtMs: 4_000,
          updatedAtMs: 7_000,
          targetKind: "task_chat",
        },
      ],
    });

    expect(queue.map((item) => item.subjectId)).toEqual(["dispatch-1", "failed-run", "delivery-1", "stale-run"]);
    expect(queue.map((item) => item.rank)).toEqual([1, 2, 3, 4]);
  });

  it("suppresses dismissed and snoozed subjects without persisting queue items", () => {
    const queue = buildDesktopActionQueue({
      nowMs: 10_000,
      dispatches: [
        {
          dispatchId: "dispatch-hidden",
          ownerId: "owner-1",
          kind: "approval",
          status: "pending",
          title: "Hidden",
          priority: 10,
          createdAtMs: 8_000,
        },
        {
          dispatchId: "dispatch-visible",
          ownerId: "owner-1",
          kind: "approval",
          status: "pending",
          title: "Visible",
          priority: 1,
          createdAtMs: 7_000,
        },
      ],
      overrides: [
        {
          ownerId: "owner-1",
          subjectKind: "dispatch",
          subjectId: "dispatch-hidden",
          hiddenUntilMs: 20_000,
        },
      ],
    });

    expect(queue).toHaveLength(1);
    expect(queue[0]).toMatchObject({
      itemId: "dispatch:dispatch:dispatch-visible",
      subjectId: "dispatch-visible",
    });
  });

  it("projects pending candidates and legacy pills into derived items", () => {
    const queue = buildDesktopActionQueue({
      nowMs: 10_000,
      candidates: [
        {
          candidateId: "task-candidate-1",
          ownerId: "owner-1",
          kind: "task_candidate",
          status: "pending",
          createdAtMs: 5_000,
        },
      ],
      legacyPills: [
        {
          pillId: "pill-1",
          ownerId: "owner-1",
          title: "Legacy Agent",
          status: "running",
          createdAtMs: 4_000,
          updatedAtMs: 6_000,
        },
      ],
    });

    expect(queue.map((item) => item.kind)).toEqual(["candidate_review", "legacy_pill"]);
  });
});
