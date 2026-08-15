// domain-pending(DIV-CHAT-SOURCE-001)

import {
  createAgentRunEventSupervisor,
  createInMemoryAgentRunEventStore,
  type AgentRunApprovalResolution,
  type AgentRunEventKind,
  type AgentRunEventStoreSnapshot,
} from "./agent-run-events";
import {
  createAgentToolRegistry,
  type AgentToolDefinition,
} from "./agent-tools";
import {
  createChatGenerationContextPacket,
  type ChatGenerationContextCandidate,
} from "./generation-context";
import {
  createGatewayChatGenerationSource,
  type ChatGenerationSourceInput,
} from "./generation-source";
import type { GatewayReadOnlyToolSchema } from "./gateway-tool-loop";
import type { ChatMessageRecord } from "../stores/chat-messages-store";
import { isProxy } from "node:util/types";
import { createHash } from "node:crypto";

const ACCOUNT_ID = "gateway-scenario-account";
const SAFE_TOKEN = /^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,127}$/u;

export interface GatewayAgentScenarioTool {
  readonly schema: GatewayReadOnlyToolSchema;
  readonly timeoutMs: number;
  readonly result: {
    readonly summary: string;
    readonly durationMs: number;
    readonly retryable: boolean;
  };
}

export type GatewayAgentScenarioProviderStep =
  | {
      readonly kind: "tool_call";
      readonly providerCallId: string;
      readonly toolName: string;
      readonly arguments: Readonly<Record<string, string>>;
    }
  | {
      readonly kind: "answer";
      readonly deltas: readonly string[];
      readonly usage?: {
        readonly inputTokens: number;
        readonly outputTokens: number;
      };
    };

export interface GatewayAgentScenarioFault {
  /** One-based gateway request index across every user turn. */
  readonly exchange: number;
  readonly kind: "throw" | "http_503" | "unterminated";
}

export interface GatewayAgentScenarioApproval {
  /**
   * Declarative lifecycle input for approval UI/replay assertions. It does not
   * authorize the scenario's safe tool; approval-required execution remains
   * owned by the policy/approval harness in agent-tools.
   */
  readonly approvalId: string;
  readonly callId: string;
  readonly reason: string;
  readonly expiresAt: number;
  readonly resolution?: AgentRunApprovalResolution;
}

export interface GatewayAgentScenarioTurn {
  readonly generationId: string;
  readonly attemptId: string;
  readonly prompt: string;
  readonly contextSources: readonly ChatGenerationContextCandidate[];
  readonly approvals?: readonly GatewayAgentScenarioApproval[];
}

export interface GatewayAgentScenarioObservation {
  readonly generationId: string;
  readonly text: string;
  readonly terminal: "completed" | "failed";
  readonly errorCode: string | null;
}

export interface GatewayAgentScenarioDurableRow {
  readonly runId: string;
  readonly eventCount: number;
  readonly kinds: readonly AgentRunEventKind[];
  readonly terminalKind: "completed" | "failed" | null;
}

export interface GatewayAgentScenarioExpected {
  readonly eventTrace: readonly string[];
  readonly durableRows: readonly GatewayAgentScenarioDurableRow[];
  readonly renderedObservations: readonly GatewayAgentScenarioObservation[];
  readonly gatewayRequests: GatewayAgentScenarioResult["gatewayRequests"];
}

export interface GatewayAgentScenario {
  /** Strict append-only state restored before any new user turn is admitted. */
  readonly initialDurableState?: AgentRunEventStoreSnapshot;
  readonly userTurns: readonly GatewayAgentScenarioTurn[];
  /** Closed and bounded: the current production gateway loop admits at most one safe tool. */
  readonly availableTools: readonly GatewayAgentScenarioTool[];
  /** Deterministic gateway replies. They are never invoked as a product model directly. */
  readonly providerScript: readonly GatewayAgentScenarioProviderStep[];
  readonly scheduledFaults?: readonly GatewayAgentScenarioFault[];
  /** Optional executable assertions; a mismatch makes the scenario fail closed. */
  readonly expected?: GatewayAgentScenarioExpected;
}

export interface GatewayAgentScenarioResult {
  readonly eventTrace: readonly string[];
  readonly durableRows: readonly GatewayAgentScenarioDurableRow[];
  readonly renderedObservations: readonly GatewayAgentScenarioObservation[];
  readonly gatewayRequests: readonly {
    readonly model: string;
    readonly toolChoice: string | null;
    readonly messageRoles: readonly string[];
    /** Hashes of bounded message content prove traversal without exporting it. */
    readonly messageContentHashes: readonly string[];
  }[];
  readonly durableState: AgentRunEventStoreSnapshot;
  readonly replayStable: true;
  readonly toolExecutions: number;
}

const canonicalJson = (value: unknown): string => {
  if (value === null || typeof value !== "object") return JSON.stringify(value) ?? "null";
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  return `{${Object.keys(value as Record<string, unknown>).sort().map((key) =>
    `${JSON.stringify(key)}:${canonicalJson((value as Record<string, unknown>)[key])}`).join(",")}}`;
};

const exact = (left: unknown, right: unknown): boolean => canonicalJson(left) === canonicalJson(right);

const hasOnlyKeys = (value: object, allowed: readonly string[]): boolean =>
  Object.keys(value).every((key) => allowed.includes(key));

const hashMessageContent = (message: unknown): string => {
  const content = message !== null && typeof message === "object"
    ? (message as { readonly content?: unknown }).content
    : null;
  return `sha256:${createHash("sha256").update(canonicalJson(content), "utf8").digest("hex")}`;
};

const detachPlainData = <T>(value: T, seen = new WeakSet<object>()): T => {
  if (value === null || typeof value === "string" || typeof value === "boolean") return value;
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value !== "object") throw new TypeError("gateway agent scenario must be JSON-like plain data");
  if (isProxy(value)) throw new TypeError("gateway agent scenario must be plain data");
  if (seen.has(value)) throw new TypeError("gateway agent scenario must be acyclic");
  seen.add(value);
  try {
    if (Array.isArray(value)) {
      const descriptors = Object.getOwnPropertyDescriptors(value);
      const expected = new Set([...value.keys()].map(String).concat("length"));
      if (Array.from({ length: value.length }, (_unused, index) => index)
        .some((index) => !Object.hasOwn(value, index))
        || Reflect.ownKeys(descriptors).some((key) => typeof key !== "string" || !expected.has(key))) {
        throw new TypeError("gateway agent scenario must be dense plain data");
      }
      const entries = value.map((entry) => detachPlainData(entry, seen));
      return Object.freeze(entries) as T;
    }
    const prototype = Object.getPrototypeOf(value);
    if (prototype !== Object.prototype && prototype !== null) {
      throw new TypeError("gateway agent scenario must be plain data");
    }
    const descriptors = Object.getOwnPropertyDescriptors(value);
    if (Reflect.ownKeys(descriptors).some((key) => typeof key !== "string")
      || Object.values(descriptors).some((descriptor) => !("value" in descriptor)
        || descriptor.enumerable !== true)) {
      throw new TypeError("gateway agent scenario must be plain data");
    }
    const detached: Record<string, unknown> = {};
    for (const [key, descriptor] of Object.entries(descriptors)) {
      detached[key] = detachPlainData(descriptor.value, seen);
    }
    return Object.freeze(detached) as T;
  } finally {
    seen.delete(value);
  }
};

const sse = (...payloads: readonly string[]): Response => new Response(
  payloads.map((payload) => `data: ${payload}\n\n`).join(""),
  { status: 200, headers: { "content-type": "text/event-stream" } },
);

const validatesSchema = (schema: GatewayReadOnlyToolSchema, input: unknown): boolean => {
  if (input === null || typeof input !== "object" || Array.isArray(input)
    || Object.getPrototypeOf(input) !== Object.prototype) return false;
  const record = input as Record<string, unknown>;
  const known = Object.keys(schema.parameters.properties);
  if (Object.keys(record).some((name) => !known.includes(name))) return false;
  if (schema.parameters.required.some((name) => !Object.hasOwn(record, name))) return false;
  return Object.entries(record).every(([name, value]) => {
    const property = schema.parameters.properties[name];
    return property !== undefined && typeof value === "string"
      && (property.enum === undefined || property.enum.includes(value));
  });
};

const toolDefinition = (
  tool: GatewayAgentScenarioTool,
  onExecute: () => void,
): AgentToolDefinition => Object.freeze({
  schemaVersion: 1,
  name: tool.schema.name,
  risk: "safe",
  timeoutMs: tool.timeoutMs,
  retryable: tool.result.retryable,
  displaySummary: tool.schema.description,
  validateInput: (input) => validatesSchema(tool.schema, input),
  execute: async (_input, control) => {
    if (control.cancelled) throw new Error("scenario tool cancelled");
    onExecute();
    return Object.freeze({ ...tool.result });
  },
});

const failureCode = (value: unknown): string => {
  if (value !== null && typeof value === "object") {
    const code = (value as { readonly code?: unknown }).code;
    if (typeof code === "string" && SAFE_TOKEN.test(code)) return code;
  }
  return "generation_provider_failed";
};

const eventTrace = (snapshot: AgentRunEventStoreSnapshot): readonly string[] => Object.freeze(
  snapshot.runs.flatMap((run) => run.events.map((event) =>
    `${event.runId}:${event.sequence}:${event.kind}`)),
);

const durableRows = (snapshot: AgentRunEventStoreSnapshot): readonly GatewayAgentScenarioDurableRow[] =>
  Object.freeze(snapshot.runs.map((run) => {
    const terminal = run.events.at(-1);
    return Object.freeze({
      runId: run.runId,
      eventCount: run.events.length,
      kinds: Object.freeze(run.events.map((event) => event.kind)),
      terminalKind: terminal?.kind === "terminal" ? terminal.terminalOutcome : null,
    });
  }));

const validateScenario = (scenario: GatewayAgentScenario): void => {
  if (!hasOnlyKeys(scenario, ["availableTools", "expected", "initialDurableState", "providerScript", "scheduledFaults", "userTurns"])
    || !Array.isArray(scenario.userTurns) || scenario.userTurns.length === 0
    || scenario.userTurns.length > 16 || !Array.isArray(scenario.availableTools)
    || scenario.availableTools.length > 1 || !Array.isArray(scenario.providerScript)
    || scenario.providerScript.length === 0 || scenario.providerScript.length > 64) {
    throw new TypeError("invalid gateway agent scenario");
  }
  const runIds = new Set<string>();
  for (const turn of scenario.userTurns) {
    if (!hasOnlyKeys(turn, ["approvals", "attemptId", "contextSources", "generationId", "prompt"])
      || !SAFE_TOKEN.test(turn.generationId) || !SAFE_TOKEN.test(turn.attemptId)
      || runIds.has(turn.generationId) || typeof turn.prompt !== "string"
      || turn.prompt.trim().length === 0 || turn.prompt.length > 16_384
      || !Array.isArray(turn.contextSources)
      || turn.contextSources.some((candidate) => candidate.ownerAccountId !== ACCOUNT_ID)) {
      throw new TypeError("invalid gateway agent scenario turn");
    }
    for (const candidate of turn.contextSources) {
      if (!hasOnlyKeys(candidate, ["capturedAt", "claimId", "conflictKey", "evidenceId", "expiresAt",
        "inclusionReason", "ownerAccountId", "policyDecision", "priority", "redactedPreview", "sourceHash",
        "sourceId", "sourceKind", "tokenEstimate"])) {
        throw new TypeError("invalid gateway agent context source");
      }
    }
    for (const approval of turn.approvals ?? []) {
      if (!hasOnlyKeys(approval, ["approvalId", "callId", "expiresAt", "reason", "resolution"])) {
        throw new TypeError("invalid gateway agent approval");
      }
    }
    runIds.add(turn.generationId);
  }
  const toolName = scenario.availableTools[0]?.schema.name;
  for (const candidate of scenario.availableTools) {
    if (!hasOnlyKeys(candidate, ["result", "schema", "timeoutMs"])
      || !hasOnlyKeys(candidate.result, ["durationMs", "retryable", "summary"])) {
      throw new TypeError("invalid gateway agent scenario tool");
    }
  }
  for (const step of scenario.providerScript) {
    if (step.kind === "tool_call") {
      if (!hasOnlyKeys(step, ["arguments", "kind", "providerCallId", "toolName"])
        || toolName === undefined || step.toolName !== toolName
        || !SAFE_TOKEN.test(step.providerCallId)
        || Object.values(step.arguments).some((value) => typeof value !== "string")) {
        throw new TypeError("invalid gateway agent provider script");
      }
    } else if (!hasOnlyKeys(step, ["deltas", "kind", "usage"])
      || (step.usage !== undefined && !hasOnlyKeys(step.usage, ["inputTokens", "outputTokens"]))
      || !Array.isArray(step.deltas) || step.deltas.length === 0
      || step.deltas.some((delta) => typeof delta !== "string" || delta.length === 0
        || delta.length > 16_384 || /[\u0000-\u001f\u007f]/u.test(delta))
      || (step.usage !== undefined && (!Number.isSafeInteger(step.usage.inputTokens)
        || step.usage.inputTokens < 0 || !Number.isSafeInteger(step.usage.outputTokens)
        || step.usage.outputTokens < 0))) {
      throw new TypeError("invalid gateway agent provider script");
    }
  }
  const faults = scenario.scheduledFaults ?? [];
  const exchanges = new Set<number>();
  for (const fault of faults) {
    if (!hasOnlyKeys(fault, ["exchange", "kind"])
      || !Number.isSafeInteger(fault.exchange) || fault.exchange <= 0
      || exchanges.has(fault.exchange)
      || !["throw", "http_503", "unterminated"].includes(fault.kind)) {
      throw new TypeError("invalid gateway agent scenario fault");
    }
    exchanges.add(fault.exchange);
  }
  if (scenario.expected !== undefined
    && !hasOnlyKeys(scenario.expected, ["durableRows", "eventTrace", "gatewayRequests", "renderedObservations"])) {
    throw new TypeError("invalid gateway agent scenario expectation");
  }
};

const historyRow = (
  id: string,
  text: string,
  sender: "human" | "ai",
  createdAt: number,
): ChatMessageRecord => Object.freeze({
  id,
  text,
  sender,
  type: "text",
  createdAt,
  updatedAt: createdAt,
  chatSessionId: null,
  appId: null,
  journalRevision: 1,
  payloadHash: `sha256:${"0".repeat(64)}`,
  messageSource: "gateway_agent_scenario",
  rating: null,
  reported: false,
  revision: `revision:${id}`,
  attachments: Object.freeze([]),
});

/**
 * Runs a deterministic multi-turn agent scenario through the production
 * semantic-lane gateway adapter. The scripted producer exists only behind the
 * gateway fetch boundary; no provider or model identifier enters the product.
 */
export const runGatewayAgentScenario = async (
  rawScenario: GatewayAgentScenario,
): Promise<GatewayAgentScenarioResult> => {
  const scenario = detachPlainData(rawScenario);
  validateScenario(scenario);
  const store = createInMemoryAgentRunEventStore();
  if (scenario.initialDurableState !== undefined) store.restore(scenario.initialDurableState);
  let now = store.snapshot().runs.reduce((maximum, run) => Math.max(maximum,
    ...run.events.map((event) => event.createdAt)), 0) + 1;
  const ledger = createAgentRunEventSupervisor({
    events: store,
    nowEpochMilliseconds: () => now++,
    eventId: (runId, sequence, kind) => `${runId}:event:${sequence}:${kind}`,
  });
  let toolExecutions = 0;
  const tool = scenario.availableTools[0];
  const loop = tool === undefined ? undefined : Object.freeze({
    registry: createAgentToolRegistry([toolDefinition(tool, () => { toolExecutions += 1; })]),
    tool: tool.schema,
    agentRunEvents: store,
    nowEpochMilliseconds: () => now++,
  });
  let scriptIndex = 0;
  let exchange = 0;
  const gatewayRequests: Array<GatewayAgentScenarioResult["gatewayRequests"][number]> = [];
  const fetchScript = async (_url: string | URL | Request, init?: RequestInit): Promise<Response> => {
    exchange += 1;
    const request = JSON.parse(String(init?.body)) as Record<string, unknown>;
    const messages = Array.isArray(request.messages) ? request.messages : [];
    gatewayRequests.push(Object.freeze({
      model: String(request.model),
      toolChoice: typeof request.tool_choice === "string" ? request.tool_choice : null,
      messageRoles: Object.freeze(messages.map((message) =>
        String((message as { readonly role?: unknown }).role))),
      messageContentHashes: Object.freeze(messages.map(hashMessageContent)),
    }));
    const step = scenario.providerScript[scriptIndex++];
    if (step === undefined) throw new Error("provider script exhausted");
    const fault = (scenario.scheduledFaults ?? []).find((candidate) => candidate.exchange === exchange);
    if (fault?.kind === "throw") throw new Error("scheduled gateway fault");
    if (fault?.kind === "http_503") return new Response("unavailable", { status: 503 });
    if (fault?.kind === "unterminated") {
      return sse(JSON.stringify({ choices: [{ delta: { content: "partial" } }] }));
    }
    if (step.kind === "tool_call") {
      return sse(JSON.stringify({ choices: [{ delta: { tool_calls: [{
        index: 0,
        id: step.providerCallId,
        function: { name: step.toolName, arguments: canonicalJson(step.arguments) },
      }] } }] }), "[DONE]");
    }
    const payloads = step.deltas.map((content) => JSON.stringify({ choices: [{ delta: { content } }] }));
    if (step.usage !== undefined) payloads.push(JSON.stringify({
      choices: [{ delta: {} }],
      usage: {
        prompt_tokens: step.usage.inputTokens,
        completion_tokens: step.usage.outputTokens,
        total_tokens: step.usage.inputTokens + step.usage.outputTokens,
      },
    }));
    return sse(...payloads, "[DONE]");
  };

  const source = createGatewayChatGenerationSource({
    gatewayUrl: "http://127.0.0.1:1",
    laneId: "omi:auto:chat-agent-scenario",
    serviceToken: "scenario-only-token",
    fetch: fetchScript as typeof fetch,
    retrySleep: async () => {},
    ...(loop === undefined ? {} : { readOnlyToolLoop: loop }),
  });
  const observations: GatewayAgentScenarioObservation[] = [];
  const history: ChatMessageRecord[] = [];
  for (const turn of scenario.userTurns) {
    if (store.list(turn.generationId).length > 0) throw new TypeError("scenario turn run already exists");
    ledger.accepted({ runId: turn.generationId, attemptId: turn.attemptId,
      admissionId: `${turn.generationId}:admission` });
    ledger.capability({ runId: turn.generationId, attemptId: turn.attemptId,
      capabilityId: `${turn.generationId}:gateway-scenario`, tier: "unknown",
      adapter: "omi-llm-gateway-scenario", deterministic: false });
    const packet = createChatGenerationContextPacket({
      accountId: ACCOUNT_ID,
      generationId: turn.generationId,
      nowEpochMilliseconds: now,
      candidates: turn.contextSources,
      history,
    });
    for (const item of packet.items) {
      ledger.context({
        runId: turn.generationId,
        attemptId: turn.attemptId,
        contextReceiptId: `${turn.generationId}:context:${item.sourceId}`,
        sourceKind: item.sourceKind,
        sourceRef: item.sourceId,
        sourceHash: item.sourceHash,
        ownerRef: `owner:${ACCOUNT_ID}`,
        expiresAt: item.expiresAt,
        redactedPreview: item.redactedPreview,
        tokenEstimate: item.tokenEstimate,
        inclusionReason: item.inclusionReason,
        policyDecision: item.policyDecision,
      });
    }
    for (const approval of turn.approvals ?? []) {
      ledger.approvalRequested({ runId: turn.generationId, attemptId: turn.attemptId,
        approvalId: approval.approvalId, callId: approval.callId,
        reason: approval.reason, expiresAt: approval.expiresAt });
      if (approval.resolution !== undefined) {
        ledger.approvalResolved({ runId: turn.generationId, attemptId: turn.attemptId,
          approvalId: approval.approvalId, callId: approval.callId, resolution: approval.resolution });
      }
    }
    const text: string[] = [];
    let completed = false;
    let errorCode: string | null = null;
    await new Promise<void>((resolve) => {
      const input: ChatGenerationSourceInput = {
        generationId: turn.generationId,
        attemptId: turn.attemptId,
        prompt: turn.prompt,
        context: packet,
        attachments: [],
        onDelta: (delta) => { text.push(delta); },
        onUsage: (usage) => {
          ledger.usage({ runId: turn.generationId, attemptId: turn.attemptId,
            usageId: usage.usageId, inputTokens: usage.inputTokens,
            outputTokens: usage.outputTokens, totalTokens: usage.totalTokens, durationMs: 0 });
        },
        onComplete: () => { completed = true; resolve(); },
        onError: (error) => { errorCode = failureCode(error); resolve(); },
      };
      source.start(input);
    });
    const terminal: GatewayAgentScenarioObservation["terminal"] = completed ? "completed" : "failed";
    ledger.terminal({ runId: turn.generationId, attemptId: turn.attemptId,
      terminalOutcome: terminal, terminalCode: terminal === "completed" ? "completed" : "generation_provider_failed",
      retryable: terminal === "failed", recoveryAction: terminal === "failed" ? "retry" : null });
    observations.push(Object.freeze({ generationId: turn.generationId, text: text.join(""), terminal, errorCode }));
    history.push(historyRow(`${turn.generationId}:human`, turn.prompt, "human", history.length + 1));
    if (text.length > 0) {
      history.push(historyRow(`${turn.generationId}:assistant`, text.join(""), "ai", history.length + 1));
    }
  }
  if (scriptIndex !== scenario.providerScript.length) throw new TypeError("provider script has unused steps");
  if ((scenario.scheduledFaults ?? []).some((fault) => fault.exchange > exchange)) {
    throw new TypeError("scheduled gateway fault was not reached");
  }
  const durableState = store.snapshot();
  const reloaded = createInMemoryAgentRunEventStore();
  reloaded.restore(durableState);
  if (!exact(reloaded.snapshot(), durableState)) throw new TypeError("scenario durable replay mismatch");
  const result: GatewayAgentScenarioResult = Object.freeze({
    eventTrace: eventTrace(durableState),
    durableRows: durableRows(durableState),
    renderedObservations: Object.freeze(observations),
    gatewayRequests: Object.freeze(gatewayRequests),
    durableState,
    replayStable: true,
    toolExecutions,
  });
  if (scenario.expected !== undefined) {
    if (!exact(result.eventTrace, scenario.expected.eventTrace)
      || !exact(result.durableRows, scenario.expected.durableRows)
      || !exact(result.renderedObservations, scenario.expected.renderedObservations)
      || !exact(result.gatewayRequests, scenario.expected.gatewayRequests)) {
      throw new TypeError("gateway agent scenario expectation mismatch");
    }
  }
  return result;
};
