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

  it("filters expired pending dispatches", () => {
    const queue = buildDesktopActionQueue({
      nowMs: 10_000,
      dispatches: [
        {
          dispatchId: "expired-dispatch",
          ownerId: "owner-1",
          kind: "approval",
          status: "pending",
          title: "Expired approval",
          priority: 100,
          createdAtMs: 1_000,
          expiresAtMs: 9_999,
        },
        {
          dispatchId: "active-dispatch",
          ownerId: "owner-1",
          kind: "approval",
          status: "pending",
          title: "Active approval",
          priority: 1,
          createdAtMs: 9_000,
          expiresAtMs: 11_000,
        },
      ],
    });

    expect(queue.map((item) => item.subjectId)).toEqual(["active-dispatch"]);
  });

  it("coalesces reusable-session items to one row per session", () => {
    const queue = buildDesktopActionQueue({
      nowMs: 10_000,
      runs: [
        {
          runId: "older-run",
          sessionId: "session-1",
          ownerId: "owner-1",
          status: "succeeded",
          title: "Older run",
          createdAtMs: 1_000,
          updatedAtMs: 2_000,
          reusable: true,
        },
        {
          runId: "newer-run",
          sessionId: "session-1",
          ownerId: "owner-1",
          status: "succeeded",
          title: "Newer run",
          createdAtMs: 3_000,
          updatedAtMs: 5_000,
          reusable: true,
        },
      ],
    });

    expect(queue).toHaveLength(1);
    expect(queue[0]).toMatchObject({
      itemId: "reusable_session:session:session-1",
      sourceRunId: "newer-run",
      title: "Newer run",
    });
  });

  it("does not keep recovering an older orphaned visible goal after a newer successful sibling covers it", () => {
    const queue = buildDesktopActionQueue({
      nowMs: 10_000,
      runs: [
        {
          runId: "orphaned-story-run",
          sessionId: "session-orphaned",
          ownerId: "owner-1",
          status: "orphaned",
          title: "Create Memory Story",
          goalText: "Search my recent memories and use them to construct a short story idea.",
          createdAtMs: 1_000,
          updatedAtMs: 2_000,
          visibleUserGoal: true,
        },
        {
          runId: "successful-story-run",
          sessionId: "session-success",
          ownerId: "owner-1",
          status: "succeeded",
          title: "Analyze Memories For Storyline",
          goalText: "Get a subagent to look through recent memories and come up with a storyline.",
          createdAtMs: 3_000,
          updatedAtMs: 4_000,
          visibleUserGoal: true,
          reusable: true,
        },
      ],
    });

    expect(queue.map((item) => item.kind)).toEqual(["reusable_session"]);
    expect(queue.some((item) => item.subjectId === "orphaned-story-run")).toBe(false);
  });

  it("uses completion time instead of reconciliation update time when suppressing covered orphaned goals", () => {
    const queue = buildDesktopActionQueue({
      nowMs: 20_000,
      runs: [
        {
          runId: "orphaned-story-run",
          sessionId: "session-orphaned",
          ownerId: "owner-1",
          status: "orphaned",
          title: "Create Memory Story",
          goalText: "Search recent memories and write a short story idea.",
          createdAtMs: 1_000,
          completedAtMs: 2_000,
          updatedAtMs: 19_000,
          visibleUserGoal: true,
        },
        {
          runId: "successful-story-run",
          sessionId: "session-success",
          ownerId: "owner-1",
          status: "succeeded",
          title: "Analyze Memories For Storyline",
          goalText: "Search recent memories and write a short story idea.",
          createdAtMs: 3_000,
          completedAtMs: 4_000,
          updatedAtMs: 4_000,
          visibleUserGoal: true,
          reusable: true,
        },
      ],
    });

    expect(queue.map((item) => item.kind)).toEqual(["reusable_session"]);
    expect(queue.some((item) => item.subjectId === "orphaned-story-run")).toBe(false);
  });

  it("uses wider run context for suppression while capping visible run-derived items", () => {
    const queue = buildDesktopActionQueue({
      nowMs: 20_000,
      runs: [
        {
          runId: "hidden-success",
          sessionId: "session-hidden-success",
          ownerId: "owner-1",
          status: "succeeded",
          title: "Analyze Memories For Storyline",
          goalText: "Search recent memories and write a short story idea.",
          createdAtMs: 3_000,
          completedAtMs: 4_000,
          updatedAtMs: 4_000,
          visibleUserGoal: true,
          reusable: true,
        },
        {
          runId: "visible-failed-run",
          sessionId: "session-visible-failed",
          ownerId: "owner-1",
          status: "failed",
          title: "A visible failed task",
          goalText: "A different failed task inside the widened run window.",
          createdAtMs: 5_000,
          completedAtMs: 6_000,
          updatedAtMs: 6_000,
          visibleUserGoal: true,
        },
      ],
      runItemLimit: 1,
      runSuppressionContext: [
        {
          runId: "visible-orphan",
          sessionId: "session-visible-orphan",
          ownerId: "owner-1",
          status: "orphaned",
          title: "Create Memory Story",
          goalText: "Search recent memories and write a short story idea.",
          createdAtMs: 1_000,
          completedAtMs: 2_000,
          updatedAtMs: 19_000,
          visibleUserGoal: true,
        },
        {
          runId: "visible-failed-run",
          sessionId: "session-visible-failed",
          ownerId: "owner-1",
          status: "failed",
          title: "A visible failed task",
          goalText: "A different failed task inside the widened run window.",
          createdAtMs: 5_000,
          completedAtMs: 6_000,
          updatedAtMs: 6_000,
          visibleUserGoal: true,
        },
      ],
      artifactDeliveries: [
        {
          deliveryId: "delivery-1",
          artifactId: "artifact-1",
          ownerId: "owner-1",
          sourceSessionId: "session-delivery",
          sourceRunId: "run-delivery",
          deliveryStatus: "pending",
          createdAtMs: 7_000,
          updatedAtMs: 8_000,
          targetKind: "task_chat",
        },
      ],
    });

    expect(queue.map((item) => item.subjectId)).toEqual(["visible-failed-run", "delivery-1"]);
  });

  it("still surfaces orphaned visible goals when newer successes are unrelated", () => {
    const queue = buildDesktopActionQueue({
      nowMs: 10_000,
      runs: [
        {
          runId: "orphaned-story-run",
          sessionId: "session-orphaned",
          ownerId: "owner-1",
          status: "orphaned",
          title: "Create Memory Story",
          goalText: "Search my recent memories and use them to construct a short story idea.",
          createdAtMs: 1_000,
          updatedAtMs: 2_000,
          visibleUserGoal: true,
        },
        {
          runId: "successful-calendar-run",
          sessionId: "session-success",
          ownerId: "owner-1",
          status: "succeeded",
          title: "Calendar Summary",
          goalText: "Summarize today's calendar meetings.",
          createdAtMs: 3_000,
          updatedAtMs: 4_000,
          visibleUserGoal: true,
          reusable: true,
        },
      ],
    });

    expect(queue.map((item) => item.kind)).toEqual(["failed_run", "reusable_session"]);
    expect(queue[0]).toMatchObject({ subjectId: "orphaned-story-run" });
  });

  it("projects pending candidates into derived items", () => {
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
    });

    expect(queue.map((item) => item.kind)).toEqual(["candidate_review"]);
  });
});
