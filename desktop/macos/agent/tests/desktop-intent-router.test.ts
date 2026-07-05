import { describe, expect, it } from "vitest";
import { routeDesktopIntent } from "../src/runtime/desktop-intent-router.js";

describe("desktop intent router", () => {
  it("resumes a healthy same-task session", () => {
    const route = routeDesktopIntent({
      utterance: "finish this",
      surfaceKind: "task_chat",
      taskId: "task-1",
      nowMs: 10_000,
      sessionCandidates: [
        {
          sessionId: "session-1",
          runId: "run-1",
          surfaceKind: "task_chat",
          taskId: "task-1",
          status: "healthy",
          relevance: 0.9,
          lastActivityAtMs: 9_000,
        },
      ],
    });

    expect(route).toMatchObject({
      intent: "resume",
      sessionId: "session-1",
      runId: "run-1",
    });
    expect(route.explanation).toContain("healthy recent session");
  });

  it("forks stale same-task sessions instead of resuming them", () => {
    const route = routeDesktopIntent({
      utterance: "continue the same task",
      surfaceKind: "task_chat",
      taskId: "task-1",
      nowMs: 10_000,
      sessionCandidates: [
        {
          sessionId: "session-stale",
          runId: "run-stale",
          surfaceKind: "task_chat",
          taskId: "task-1",
          status: "stale",
          relevance: 0.95,
          lastActivityAtMs: 1_000,
        },
      ],
    });

    expect(route.intent).toBe("fork");
    expect(route.sessionId).toBe("session-stale");
  });

  it("creates dispatches for ambiguous external sends", () => {
    const route = routeDesktopIntent({
      utterance: "send that to Alex",
      surfaceKind: "main_chat",
      nowMs: 10_000,
    });

    expect(route.intent).toBe("dispatch");
    expect(route.explanation).toContain("External send/share");
  });

  it("routes to any pending dispatch before other intent paths", () => {
    const route = routeDesktopIntent({
      utterance: "what's running right now?",
      surfaceKind: "main_chat",
      nowMs: 10_000,
      actionQueue: [
        {
          itemId: "dispatch:dispatch:approval-1",
          kind: "dispatch",
          subjectKind: "dispatch",
          subjectId: "approval-1",
          ownerId: "owner-1",
          title: "Approve screen access",
          priority: 100,
          rank: 1,
          createdAtMs: 9_000,
          dispatchKind: "screen_context",
          reason: "screen approval",
        },
      ],
    });

    expect(route).toMatchObject({
      intent: "dispatch",
      dispatchId: "approval-1",
      queueItemId: "dispatch:dispatch:approval-1",
    });
  });

  it("does not resume untasked surface candidates for explicit task intents", () => {
    const route = routeDesktopIntent({
      utterance: "continue this task",
      surfaceKind: "task_chat",
      taskId: "task-1",
      nowMs: 10_000,
      sessionCandidates: [
        {
          sessionId: "wrong-task-surface-session",
          runId: "run-1",
          surfaceKind: "task_chat",
          taskId: null,
          status: "healthy",
          relevance: 0.95,
          lastActivityAtMs: 9_000,
        },
      ],
    });

    expect(route.intent).toBe("new_run");
  });

  it("routes unrelated implementation work to delegation", () => {
    const route = routeDesktopIntent({
      utterance: "please implement and test the desktop coordinator policy",
      surfaceKind: "main_chat",
      nowMs: 10_000,
      sessionCandidates: [
        {
          sessionId: "low-relevance",
          surfaceKind: "task_chat",
          taskId: "other-task",
          status: "healthy",
          relevance: 0.2,
          lastActivityAtMs: 9_000,
        },
      ],
    });

    expect(route.intent).toBe("delegate");
  });

  it("does not resume same-surface chat sessions for explicit new delegated work", () => {
    const route = routeDesktopIntent({
      utterance: "ask an agent to build me a single page html iphone facts page",
      surfaceKind: "main_chat",
      nowMs: 10_000,
      sessionCandidates: [
        {
          sessionId: "main-chat-session",
          runId: "previous-run",
          surfaceKind: "main_chat",
          taskId: null,
          status: "healthy",
          relevance: 0.7,
          lastActivityAtMs: 9_000,
        },
      ],
    });

    expect(route.intent).toBe("delegate");
    expect(route.sessionId).toBeUndefined();
    expect(route.runId).toBeUndefined();
  });

  it("quick-answers status requests from coordinator state", () => {
    const route = routeDesktopIntent({
      utterance: "what's running right now?",
      surfaceKind: "main_chat",
      nowMs: 10_000,
    });

    expect(route.intent).toBe("quick_answer");
  });

  it("prioritizes a pending external dispatch from the action queue", () => {
    const route = routeDesktopIntent({
      utterance: "send it now",
      surfaceKind: "main_chat",
      nowMs: 10_000,
      actionQueue: [
        {
          itemId: "dispatch:dispatch:dispatch-1",
          kind: "dispatch",
          subjectKind: "dispatch",
          subjectId: "dispatch-1",
          ownerId: "owner-1",
          title: "Review external draft",
          priority: 100,
          rank: 1,
          createdAtMs: 9_000,
          dispatchKind: "external_draft",
          reason: "external draft",
        },
      ],
    });

    expect(route).toMatchObject({
      intent: "dispatch",
      dispatchId: "dispatch-1",
      queueItemId: "dispatch:dispatch:dispatch-1",
    });
  });
});
