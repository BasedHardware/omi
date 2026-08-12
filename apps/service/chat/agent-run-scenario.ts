// domain-pending(DIV-CHAT-SOURCE-001)

import {
  createAgentRunEventSupervisor,
  createInMemoryAgentRunEventStore,
  projectAgentRunTimeline,
  type AgentRunApprovalResolution,
  type AgentRunEvent,
  type AgentRunEventStore,
  type AgentRunEventStoreSnapshot,
  type AgentRunRecoveryAction,
  type AgentRunStatus,
  type AgentRunTerminalCode,
  type AgentRunTerminalOutcome,
} from "./agent-run-events";

export interface AgentRunScenario {
  readonly runId?: string;
  readonly attemptId?: string;
  /** Strict durable state restored before the declarative continuation runs. */
  readonly initialSnapshot?: AgentRunEventStoreSnapshot;
  readonly capability?: {
    readonly capabilityId: string;
    readonly tier: "deterministic-scripted" | "real-provider" | "unknown";
    readonly adapter: string;
    readonly deterministic: boolean;
  };
  readonly context?: {
    readonly contextReceiptId: string;
    readonly sourceKind: string;
    readonly sourceRef: string;
    readonly sourceHash: string;
    readonly ownerRef: string;
    readonly expiresAt: number | null;
    readonly redactedPreview: string;
    readonly tokenEstimate: number;
    readonly inclusionReason: string;
    readonly policyDecision: "included" | "excluded" | "degraded";
  };
  readonly statuses?: readonly { readonly status: AgentRunStatus; readonly progressPct: number | null }[];
  readonly tools?: readonly ({
    readonly callId: string;
    readonly toolName: string;
    readonly timeoutMs: number;
    readonly idempotencyKey: string;
    readonly result?: { readonly summary: string; readonly durationMs: number; readonly retryable: boolean };
    readonly error?: { readonly code: string; readonly summary: string; readonly retryable: boolean };
  })[];
  readonly approval?: {
    readonly approvalId: string;
    readonly callId: string;
    readonly reason: string;
    readonly expiresAt: number;
    readonly resolution?: AgentRunApprovalResolution;
  };
  readonly usage?: {
    readonly usageId: string;
    readonly inputTokens: number;
    readonly outputTokens: number;
    readonly totalTokens: number;
    readonly durationMs: number;
  };
  readonly recovery?: {
    readonly recoveryId: string;
    readonly action: AgentRunRecoveryAction;
    readonly reason: string;
    readonly fromAttemptId: string;
    readonly toAttemptId: string;
  };
  readonly terminal: {
    readonly outcome: AgentRunTerminalOutcome;
    readonly code: AgentRunTerminalCode;
    readonly retryable: boolean;
    readonly recoveryAction: AgentRunRecoveryAction | null;
  };
}

export interface AgentRunScenarioResult {
  readonly runId: string;
  readonly events: readonly AgentRunEvent[];
  readonly timeline: ReturnType<typeof projectAgentRunTimeline>;
  readonly replayEvents: readonly AgentRunEvent[];
}

const SCENARIO_RUN = "scenario-run";
const SCENARIO_ATTEMPT = "attempt-1";
const SCENARIO_ADMISSION = "admission-1";

/** Runs a declarative agent lifecycle against the strict in-memory ledger. */
export const runAgentRunScenario = (
  scenario: AgentRunScenario,
  existingStore?: AgentRunEventStore,
): AgentRunScenarioResult => {
  const runId = scenario.runId ?? SCENARIO_RUN;
  const attemptId = scenario.attemptId ?? SCENARIO_ATTEMPT;
  if (existingStore !== undefined && scenario.initialSnapshot !== undefined) {
    throw new TypeError("agent run scenario has two durable state authorities");
  }
  const store = existingStore ?? createInMemoryAgentRunEventStore();
  if (scenario.initialSnapshot !== undefined) store.restore(scenario.initialSnapshot);
  const initialEvents = store.list(runId);
  let now = initialEvents.length === 0
    ? 0
    : Math.max(...initialEvents.map((event) => event.createdAt)) + 1;
  const supervisor = createAgentRunEventSupervisor({
    events: store,
    nowEpochMilliseconds: () => now,
    eventId: (id, sequence, kind) => `${id}:${sequence}:${kind}`,
  });
  const events: AgentRunEvent[] = [];
  const record = (event: AgentRunEvent): void => {
    events.push(event);
    now += 1;
  };
  if (initialEvents.length === 0) {
    record(supervisor.accepted({ runId, attemptId, admissionId: SCENARIO_ADMISSION }));
  }
  if (scenario.capability !== undefined) record(supervisor.capability({ runId, attemptId, ...scenario.capability }));
  if (scenario.context !== undefined) record(supervisor.context({ runId, attemptId, ...scenario.context }));
  for (const status of scenario.statuses ?? []) record(supervisor.status({ runId, attemptId, ...status }));
  for (const tool of scenario.tools ?? []) {
    record(supervisor.toolRequest({ runId, attemptId, callId: tool.callId, toolName: tool.toolName,
      timeoutMs: tool.timeoutMs, idempotencyKey: tool.idempotencyKey }));
    if (tool.result !== undefined) {
      record(supervisor.toolResult({ runId, attemptId, callId: tool.callId, toolName: tool.toolName,
        resultSummary: tool.result.summary, durationMs: tool.result.durationMs, retryable: tool.result.retryable }));
    } else if (tool.error !== undefined) {
      record(supervisor.toolError({ runId, attemptId, callId: tool.callId, toolName: tool.toolName,
        errorCode: tool.error.code, errorSummary: tool.error.summary, retryable: tool.error.retryable }));
    }
  }
  if (scenario.approval !== undefined) {
    const { approvalId, callId, reason, expiresAt, resolution } = scenario.approval;
    record(supervisor.approvalRequested({ runId, attemptId, approvalId, callId, reason, expiresAt }));
    if (resolution !== undefined) {
      record(supervisor.approvalResolved({ runId, attemptId, approvalId, callId, resolution }));
    }
  }
  if (scenario.usage !== undefined) record(supervisor.usage({ runId, attemptId, ...scenario.usage }));
  if (scenario.recovery !== undefined) record(supervisor.recovery({ runId, attemptId, ...scenario.recovery }));
  record(supervisor.terminal({ runId, attemptId, terminalOutcome: scenario.terminal.outcome,
    terminalCode: scenario.terminal.code, retryable: scenario.terminal.retryable,
    recoveryAction: scenario.terminal.recoveryAction }));
  const snapshot = store.snapshot();
  const reloaded = createInMemoryAgentRunEventStore();
  reloaded.restore(snapshot);
  return Object.freeze({
    runId,
    events: Object.freeze(store.list(runId)),
    timeline: projectAgentRunTimeline(store.list(runId)),
    replayEvents: Object.freeze(reloaded.list(runId)),
  });
};
