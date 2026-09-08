import { describe, expect, it } from "vitest";

import {
  DesktopIntentRouteError,
  DesktopIntentRouter,
  type DesktopIntentRouteAuthority,
  type DesktopIntentRouteRequest,
} from "../src/runtime/desktop-intent-router.js";

const authority = (overrides: Partial<DesktopIntentRouteAuthority> = {}): DesktopIntentRouteAuthority => ({
  ownerId: "owner-1",
  callerExecutionRole: "coordinator",
  availableAdapterIds: ["pi-mono", "hermes"],
  nowMs: 10_000,
  ...overrides,
});

const request = (overrides: Partial<DesktopIntentRouteRequest> = {}): DesktopIntentRouteRequest => ({
  utterance: "structured request",
  surfaceKind: "main_chat",
  snapshotVersion: "snapshot:7",
  proposal: { intent: "answer_inline" },
  ...overrides,
});

describe("canonical desktop intent router", () => {
  it("returns the same route kind for the same proposal across desktop surfaces", () => {
    const router = new DesktopIntentRouter();
    const intents = ["main_chat", "floating_bar", "realtime"].map(
      (surfaceKind) => router.route(
        request({ surfaceKind, proposal: { intent: "spawn_agent" } }),
        authority(),
      ).intent,
    );

    expect(intents).toEqual(["spawn_agent", "spawn_agent", "spawn_agent"]);
  });

  it("lets explicit delegation negation override an untrusted spawn proposal", () => {
    const route = new DesktopIntentRouter().route(
      request({
        proposal: { intent: "spawn_agent" },
        syntaxFacts: { delegationNegated: true },
      }),
      authority(),
    );

    expect(route).toMatchObject({
      intent: "answer_inline",
      reasonCode: "explicit_delegation_negation",
    });
  });

  it("continues only an explicit handle resolved by kernel authority", () => {
    const route = new DesktopIntentRouter().route(
      request({
        proposal: { intent: "continue_run" },
        syntaxFacts: {
          explicitSessionId: "ses_1",
          explicitRunId: "run_1",
        },
      }),
      authority({
        continuationTarget: {
          sessionId: "ses_1",
          runId: "run_1",
          status: "open",
        },
      }),
    );

    expect(route).toMatchObject({
      intent: "continue_run",
      sessionId: "ses_1",
      runId: "run_1",
      reasonCode: "continue_proposal",
    });
  });

  it("rejects a continuation target not visible to the active owner", () => {
    const route = new DesktopIntentRouter().route(
      request({
        proposal: { intent: "continue_run" },
        syntaxFacts: { explicitSessionId: "ses_other_owner" },
      }),
      authority({ continuationTarget: null }),
    );

    expect(route).toMatchObject({
      intent: "reject",
      code: "continuation_target_unavailable",
    });
  });

  it("rejects spawn and continuation effects for a kernel-owned leaf role", () => {
    for (const proposal of [{ intent: "spawn_agent" }, { intent: "continue_run" }] as const) {
      const route = new DesktopIntentRouter().route(
        request({
          proposal,
          syntaxFacts: proposal.intent === "continue_run" ? { explicitSessionId: "ses_1" } : undefined,
        }),
        authority({
          callerExecutionRole: "leaf",
          continuationTarget: { sessionId: "ses_1", status: "open" },
        }),
      );

      expect(route).toMatchObject({
        intent: "reject",
        code: "caller_role_forbidden",
      });
    }
  });

  it("fails closed when an explicit provider is not registered", () => {
    const route = new DesktopIntentRouter().route(
      request({
        proposal: { intent: "spawn_agent" },
        syntaxFacts: { explicitProvider: "openclaw" },
      }),
      authority({ availableAdapterIds: ["pi-mono"] }),
    );

    expect(route).toMatchObject({
      intent: "reject",
      code: "provider_unavailable",
    });
  });

  it("binds a bounded sibling count into the single spawn decision", () => {
    const router = new DesktopIntentRouter();
    expect(router.route(request({
      proposal: { intent: "spawn_agent" },
      syntaxFacts: { requestedAgentCount: 3 },
    }), authority())).toMatchObject({
      intent: "spawn_agent",
      requestedAgentCount: 3,
    });
    expect(router.route(request({
      proposal: { intent: "spawn_agent" },
      syntaxFacts: { requestedAgentCount: 9 },
    }), authority())).toMatchObject({
      intent: "reject",
      code: "agent_count_unsupported",
    });
  });

  it("requires a structured proposal instead of applying language heuristics", () => {
    const route = new DesktopIntentRouter().route(
      request({
        utterance: "implement, audit, research, send, and fix this in the background",
        proposal: undefined,
      }),
      authority(),
    );

    expect(route).toMatchObject({
      intent: "clarify",
      reasonCode: "proposal_required",
      missing: ["proposal"],
    });
  });

  it("consumes a bound decision before its effect and prevents replayed children", async () => {
    let sequence = 0;
    let childCount = 0;
    const router = new DesktopIntentRouter({ nextDecisionId: () => `decision-${++sequence}` });
    const route = router.route(request({ proposal: { intent: "spawn_agent" } }), authority());
    expect(route.intent).toBe("spawn_agent");

    const binding = {
      decisionId: route.decisionId,
      ownerId: "owner-1",
      surfaceKind: "main_chat",
      snapshotVersion: "snapshot:7",
      expectedIntent: "spawn_agent" as const,
      nowMs: 10_001,
    };
    const first = await router.apply(binding, () => ({ childId: `child-${++childCount}` }));

    expect(first.result).toEqual({ childId: "child-1" });
    await expect(router.apply(binding, () => ({ childId: `child-${++childCount}` }))).rejects.toMatchObject({
      name: "DesktopIntentRouteError",
      reasonCode: "decision_replayed",
    });
    expect(childCount).toBe(1);
  });

  it("binds effect decisions to owner, surface, and snapshot", () => {
    const router = new DesktopIntentRouter({ nextDecisionId: () => "decision-bound" });
    const route = router.route(request({ proposal: { intent: "spawn_agent" } }), authority());

    expect(() => router.consume({
      decisionId: route.decisionId,
      ownerId: "other-owner",
      surfaceKind: "main_chat",
      snapshotVersion: "snapshot:7",
      expectedIntent: "spawn_agent",
      nowMs: 10_001,
    })).toThrowError(DesktopIntentRouteError);

    expect(router.consume({
      decisionId: route.decisionId,
      ownerId: "owner-1",
      surfaceKind: "main_chat",
      snapshotVersion: "snapshot:7",
      expectedIntent: "spawn_agent",
      nowMs: 10_002,
    }).intent).toBe("spawn_agent");
  });

  it("does not expose raw user content in route observability fields", () => {
    const secret = "private launch plan for alex@example.com";
    const route = new DesktopIntentRouter().route(
      request({ utterance: secret }),
      authority(),
    );
    const serialized = JSON.stringify(route);

    expect(serialized).not.toContain(secret);
    expect(serialized).not.toContain("alex@example.com");
    expect(route.inputHash).toMatch(/^[a-f0-9]{16}$/);
    expect(route.reasonCode).toBe("inline_proposal");
  });
});
