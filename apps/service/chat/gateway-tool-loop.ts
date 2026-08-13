// domain-pending(DIV-CHAT-TOOL-001)

import { createHash } from "node:crypto";

import {
  createAgentRunEventSupervisor,
  type AgentRunEventStore,
  type AgentRunEventSupervisor,
} from "./agent-run-events";
import {
  createAgentToolRunner,
  type AgentToolOutcome,
  type AgentToolRegistry,
  type AgentToolScheduler,
  type AgentToolTraceEvent,
} from "./agent-tools";
import type { ChatGenerationSourceInput } from "./generation-source";

const SAFE_TOKEN = /^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,127}$/u;
const SAFE_TEXT = /^[^\u0000-\u001f\u007f]{1,240}$/u;
const MAX_GATEWAY_EVENT_BYTES = 1_048_576;
const MAX_TOOL_ARGUMENT_BYTES = 16_384;

export interface GatewayReadOnlyToolSchema {
  readonly name: string;
  readonly description: string;
  readonly parameters: {
    readonly type: "object";
    readonly additionalProperties: false;
    readonly properties: Readonly<Record<string, {
      readonly type: "string";
      readonly description?: string;
      readonly enum?: readonly string[];
    }>>;
    readonly required: readonly string[];
  };
}

export interface GatewayReadOnlyToolLoopOptions {
  /** A closed registry. The single advertised definition must be risk=safe. */
  readonly registry: AgentToolRegistry;
  readonly tool: GatewayReadOnlyToolSchema;
  /** The same append-only ledger used by the generation supervisor. */
  readonly agentRunEvents: AgentRunEventStore;
  readonly nowEpochMilliseconds: () => number;
  readonly scheduler?: AgentToolScheduler;
}

export interface GatewayToolLoopStartOptions {
  readonly endpoint: string;
  readonly laneId: string;
  readonly serviceToken: string;
  readonly serviceCaller: string;
  readonly usageFeature: string;
  readonly fetch: typeof fetch;
  readonly baseMessages: readonly Readonly<{ readonly role: "system" | "user" | "assistant"; readonly content: string }>[];
  readonly loop: GatewayReadOnlyToolLoopOptions;
  readonly input: ChatGenerationSourceInput;
  readonly fail: (error: unknown) => void;
  readonly complete: () => void;
  readonly isCancelled: () => boolean;
}

export interface GatewayToolLoopRun {
  cancel(): void;
}

type ProviderToolCall = {
  readonly id: string;
  readonly name: string;
  readonly argumentsJson: string;
};

const ownPlainObject = (value: unknown): Record<string, unknown> | null => {
  if (value === null || typeof value !== "object" || Array.isArray(value)
    || Object.getPrototypeOf(value) !== Object.prototype) return null;
  return value as Record<string, unknown>;
};

const exactKeys = (value: Record<string, unknown>, expected: readonly string[]): boolean => {
  const actual = Object.keys(value).sort();
  const wanted = [...expected].sort();
  return actual.length === wanted.length && actual.every((key, index) => key === wanted[index]);
};

const validateToolSchema = (
  loop: GatewayReadOnlyToolLoopOptions,
): Readonly<{ type: "function"; function: GatewayReadOnlyToolSchema }> => {
  const tool = ownPlainObject(loop.tool);
  const parameters = ownPlainObject(loop.tool.parameters);
  const properties = ownPlainObject(loop.tool.parameters.properties);
  if (tool === null || parameters === null || properties === null
    || !exactKeys(tool, ["description", "name", "parameters"])
    || !exactKeys(parameters, ["additionalProperties", "properties", "required", "type"])
    || !SAFE_TOKEN.test(loop.tool.name) || !SAFE_TEXT.test(loop.tool.description)
    || loop.tool.parameters.type !== "object" || loop.tool.parameters.additionalProperties !== false
    || !Array.isArray(loop.tool.parameters.required)
    || loop.registry.names().length !== 1 || loop.registry.names()[0] !== loop.tool.name) {
    throw new TypeError("invalid gateway read-only tool configuration");
  }
  const definition = loop.registry.resolve(loop.tool.name);
  if (definition === null || definition.risk !== "safe") {
    throw new TypeError("invalid gateway read-only tool configuration");
  }
  const required = new Set(loop.tool.parameters.required);
  if (required.size !== loop.tool.parameters.required.length
    || [...required].some((name) => !SAFE_TOKEN.test(name) || !(name in properties))) {
    throw new TypeError("invalid gateway read-only tool configuration");
  }
  for (const [name, rawProperty] of Object.entries(properties)) {
    const property = ownPlainObject(rawProperty);
    if (!SAFE_TOKEN.test(name) || property === null
      || !exactKeys(property, property.description === undefined
        ? (property.enum === undefined ? ["type"] : ["enum", "type"])
        : (property.enum === undefined ? ["description", "type"] : ["description", "enum", "type"]))
      || property.type !== "string"
      || (property.description !== undefined
        && (typeof property.description !== "string" || !SAFE_TEXT.test(property.description)))
      || (property.enum !== undefined && (!Array.isArray(property.enum) || property.enum.length === 0
        || property.enum.some((entry) => typeof entry !== "string" || !SAFE_TOKEN.test(entry))))) {
      throw new TypeError("invalid gateway read-only tool configuration");
    }
  }
  return Object.freeze({ type: "function", function: loop.tool });
};

const validatesAgainstToolSchema = (
  schema: GatewayReadOnlyToolSchema,
  input: unknown,
): boolean => {
  const record = ownPlainObject(input);
  if (record === null) return false;
  const propertyNames = Object.keys(schema.parameters.properties);
  if (Object.keys(record).some((name) => !propertyNames.includes(name))) return false;
  if (schema.parameters.required.some((name) => !Object.hasOwn(record, name))) return false;
  return Object.entries(record).every(([name, value]) => {
    const property = schema.parameters.properties[name];
    return property !== undefined && typeof value === "string"
      && (property.enum === undefined || property.enum.includes(value));
  });
};

export const validateGatewayReadOnlyToolLoop = (
  loop: GatewayReadOnlyToolLoopOptions,
): Readonly<{ type: "function"; function: GatewayReadOnlyToolSchema }> => validateToolSchema(loop);

const canonicalJson = (value: unknown): string => {
  if (value === null || typeof value !== "object") return JSON.stringify(value) ?? "null";
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  return `{${Object.keys(value as Record<string, unknown>).sort().map((key) =>
    `${JSON.stringify(key)}:${canonicalJson((value as Record<string, unknown>)[key])}`).join(",")}}`;
};

const inputKey = (toolName: string, input: unknown): string =>
  `sha256:${createHash("sha256").update(`${toolName}\n${canonicalJson(input)}`, "utf8").digest("hex")}`;

const stableCallId = (input: ChatGenerationSourceInput): string => {
  const seed = `${input.generationId}\n${input.attemptId ?? input.generationId}`;
  return `toolcall:${createHash("sha256").update(seed, "utf8").digest("hex").slice(0, 32)}`;
};

const sseDataPayloads = (event: string): readonly string[] => event
  .split(/\r?\n/u)
  .filter((line) => line.startsWith("data:"))
  .map((line) => line.slice(5).trimStart());

const gatewayFailure = (code: "generation_provider_failed" | "generation_timeout") =>
  Object.freeze({ code, retryable: true });

const appendSyntheticFailure = (
  events: AgentRunEventSupervisor,
  input: ChatGenerationSourceInput,
  callId: string,
  toolName: string,
  idempotencyKey: string,
  code: string,
  summary: string,
): AgentToolOutcome => {
  const attemptId = input.attemptId ?? `${input.generationId}:attempt:unknown`;
  events.toolRequest({ runId: input.generationId, attemptId, callId, toolName,
    timeoutMs: 1, idempotencyKey });
  events.toolError({ runId: input.generationId, attemptId, callId, toolName,
    errorCode: code, errorSummary: summary, retryable: false });
  return Object.freeze({ kind: "failed", callId, code, summary, retryable: false });
};

const priorOutcome = (
  store: AgentRunEventStore,
  runId: string,
  callId: string,
  toolName: string,
  idempotencyKey: string,
): AgentToolOutcome | null => {
  const events = store.list(runId);
  const request = events.find((event) => event.kind === "tool_request" && event.callId === callId);
  if (request === undefined) return null;
  if (request.kind !== "tool_request" || request.toolName !== toolName
    || request.idempotencyKey !== idempotencyKey) {
    return Object.freeze({ kind: "failed", callId, code: "tool_idempotency_conflict",
      summary: "The tool replay conflicts with the durable request.", retryable: false });
  }
  const terminal = events.find((event) =>
    (event.kind === "tool_result" || event.kind === "tool_error") && event.callId === callId);
  if (terminal !== undefined && (terminal.toolName !== request.toolName
    || terminal.attemptId !== request.attemptId)) {
    return Object.freeze({ kind: "failed", callId, code: "tool_idempotency_conflict",
      summary: "The tool replay conflicts with the durable result.", retryable: false });
  }
  if (terminal?.kind === "tool_result") return Object.freeze({
    kind: "completed", callId, summary: terminal.resultSummary,
    durationMs: terminal.durationMs, retryable: terminal.retryable,
  });
  if (terminal?.kind === "tool_error") return Object.freeze({
    kind: "failed", callId, code: terminal.errorCode,
    summary: terminal.errorSummary, retryable: terminal.retryable,
  });
  return Object.freeze({ kind: "failed", callId, code: "tool_in_progress",
    summary: "The durable tool request has no terminal result.", retryable: false });
};

const toolHistory = (
  call: ProviderToolCall,
  outcome: AgentToolOutcome,
): readonly Readonly<Record<string, unknown>>[] => Object.freeze([
  Object.freeze({
    role: "assistant",
    content: null,
    tool_calls: [Object.freeze({
      id: call.id,
      type: "function",
      function: Object.freeze({ name: call.name, arguments: call.argumentsJson }),
    })],
  }),
  Object.freeze({
    role: "tool",
    tool_call_id: call.id,
    content: outcome.kind === "completed" ? outcome.summary
      : outcome.kind === "failed" ? outcome.summary
        : "The tool call did not complete.",
  }),
]);

export const startGatewayReadOnlyToolLoop = (
  options: GatewayToolLoopStartOptions,
): GatewayToolLoopRun => {
  const providerTool = validateToolSchema(options.loop);
  const controller = new AbortController();
  let activeRunner: ReturnType<typeof createAgentToolRunner> | null = null;
  let activeCallId: string | null = null;

  void (async (): Promise<void> => {
    const input = options.input;
    const attemptId = input.attemptId ?? `${input.generationId}:attempt:unknown`;
    const ledger = createAgentRunEventSupervisor({
      events: options.loop.agentRunEvents,
      nowEpochMilliseconds: options.loop.nowEpochMilliseconds,
      eventId: (runId, sequence, kind) => `${runId}:event:${sequence}:${kind}`,
    });
    let messages: readonly Readonly<Record<string, unknown>>[] = options.baseMessages;
    for (let round = 0; round < 2 && !options.isCancelled(); round += 1) {
      let response: Response;
      try {
        response = await options.fetch(options.endpoint, {
          method: "POST",
          headers: {
            "authorization": `Bearer ${options.serviceToken}`,
            "content-type": "application/json",
            "x-omi-service-caller": options.serviceCaller,
            "x-omi-user-uid": input.context.ownerAccountId,
            "x-omi-llm-feature": options.usageFeature,
          },
          body: JSON.stringify({
            model: options.laneId,
            messages,
            tools: [providerTool],
            tool_choice: round === 0 ? "auto" : "none",
            stream: true,
            stream_options: { include_usage: true },
          }),
          signal: controller.signal,
        });
      } catch {
        if (!options.isCancelled()) options.fail(gatewayFailure("generation_provider_failed"));
        return;
      }
      if (!response.ok || response.body === null) {
        options.fail(gatewayFailure(response.status === 408 || response.status === 504
          ? "generation_timeout" : "generation_provider_failed"));
        return;
      }
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let sawDone = false;
      let callId = "";
      let toolName = "";
      let argumentsJson = "";
      let sawToolCallFragment = false;
      try {
        while (!options.isCancelled()) {
          const next = await reader.read();
          buffer += decoder.decode(next.value, { stream: !next.done });
          if (buffer.length > MAX_GATEWAY_EVENT_BYTES) throw new TypeError("gateway event too large");
          const events = buffer.split(/\r?\n\r?\n/u);
          buffer = events.pop() ?? "";
          for (const event of events) {
            const data = sseDataPayloads(event).join("\n");
            if (data.length === 0) continue;
            if (sawDone) throw new TypeError("gateway data followed terminal marker");
            if (data === "[DONE]") { sawDone = true; continue; }
            const record = ownPlainObject(JSON.parse(data));
            if (record === null) throw new TypeError("invalid gateway SSE payload");
            const choices = record.choices;
            if (Array.isArray(choices) && choices.length > 0) {
              const choice = ownPlainObject(choices[0]);
              const delta = ownPlainObject(choice?.delta);
              const content = delta?.content;
              if (typeof content === "string" && content.length > 0) input.onDelta(content);
              const calls = delta?.tool_calls;
              if (calls !== undefined) {
                sawToolCallFragment = true;
                if (!Array.isArray(calls) || calls.length !== 1 || round !== 0) {
                  throw new TypeError("invalid bounded gateway tool call");
                }
                const fragment = ownPlainObject(calls[0]);
                const fn = ownPlainObject(fragment?.function);
                if (fragment === null || fn === null
                  || (fragment.index !== undefined && fragment.index !== 0)
                  || (fragment.id !== undefined && typeof fragment.id !== "string")
                  || (fn.name !== undefined && typeof fn.name !== "string")
                  || (fn.arguments !== undefined && typeof fn.arguments !== "string")) {
                  throw new TypeError("invalid bounded gateway tool call");
                }
                if (typeof fragment.id === "string") callId += fragment.id;
                if (typeof fn.name === "string") toolName += fn.name;
                if (typeof fn.arguments === "string") argumentsJson += fn.arguments;
                if (argumentsJson.length > MAX_TOOL_ARGUMENT_BYTES) throw new TypeError("tool arguments too large");
              }
            }
            const usage = ownPlainObject(record.usage);
            const promptTokens = usage?.prompt_tokens;
            const completionTokens = usage?.completion_tokens;
            const totalTokens = usage?.total_tokens;
            if (Number.isSafeInteger(promptTokens) && (promptTokens as number) >= 0
              && Number.isSafeInteger(completionTokens) && (completionTokens as number) >= 0
              && Number.isSafeInteger(totalTokens)
              && totalTokens === (promptTokens as number) + (completionTokens as number)) {
              input.onUsage?.(Object.freeze({
                usageId: `${attemptId}:usage:${round + 1}`,
                provider: "omi-llm-gateway",
                model: "semantic-lane",
                inputTokens: promptTokens as number,
                outputTokens: completionTokens as number,
                totalTokens: totalTokens as number,
              }));
            }
          }
          if (next.done) break;
        }
      } catch {
        if (!options.isCancelled()) options.fail(gatewayFailure("generation_provider_failed"));
        return;
      }
      if (options.isCancelled()) return;
      if (!sawDone || buffer.trim().length > 0) {
        options.fail(gatewayFailure("generation_provider_failed"));
        return;
      }
      if (sawToolCallFragment && callId.length === 0 && toolName.length === 0 && argumentsJson.length === 0) {
        options.fail(gatewayFailure("generation_provider_failed"));
        return;
      }
      if (callId.length === 0 && toolName.length === 0 && argumentsJson.length === 0) {
        options.complete();
        return;
      }
      if (round !== 0 || !SAFE_TOKEN.test(callId) || !SAFE_TOKEN.test(toolName)) {
        options.fail(gatewayFailure("generation_provider_failed"));
        return;
      }
      const canonicalCallId = stableCallId(input);
      activeCallId = canonicalCallId;
      let parsedInput: unknown;
      let outcome: AgentToolOutcome;
      try {
        parsedInput = JSON.parse(argumentsJson);
      } catch {
        const idem = inputKey(toolName, { malformed: true });
        try {
          outcome = appendSyntheticFailure(ledger, input, canonicalCallId, toolName, idem,
            "tool_invalid_input", "The tool request is invalid.");
        } catch {
          options.fail(gatewayFailure("generation_provider_failed"));
          return;
        }
        messages = Object.freeze([...messages, ...toolHistory({ id: callId, name: toolName, argumentsJson }, outcome)]);
        continue;
      }
      const idem = inputKey(toolName, parsedInput);
      const replay = priorOutcome(options.loop.agentRunEvents, input.generationId,
        canonicalCallId, toolName, idem);
      if (replay !== null) {
        outcome = replay;
      } else if (options.loop.registry.resolve(toolName) === null) {
        try {
          outcome = appendSyntheticFailure(ledger, input, canonicalCallId, toolName, idem,
            "tool_unknown", "The requested tool is unavailable.");
        } catch {
          options.fail(gatewayFailure("generation_provider_failed"));
          return;
        }
      } else if (!validatesAgainstToolSchema(options.loop.tool, parsedInput)) {
        try {
          outcome = appendSyntheticFailure(ledger, input, canonicalCallId, toolName, idem,
            "tool_invalid_input", "The tool request is invalid.");
        } catch {
          options.fail(gatewayFailure("generation_provider_failed"));
          return;
        }
      } else {
        const definition = options.loop.registry.resolve(toolName)!;
        try {
          ledger.toolRequest({
            runId: input.generationId, attemptId, callId: canonicalCallId,
            toolName, timeoutMs: definition.timeoutMs, idempotencyKey: idem,
          });
        } catch {
          options.fail(gatewayFailure("generation_provider_failed"));
          return;
        }
        let ledgerError = false;
        let terminalRecorded = false;
        const runner = createAgentToolRunner({
          registry: options.loop.registry,
          nowEpochMilliseconds: options.loop.nowEpochMilliseconds,
          scheduler: options.loop.scheduler,
          onEvent: (event: AgentToolTraceEvent): void => {
            try {
              if (event.kind === "tool_result") {
                ledger.toolResult({
                runId: input.generationId, attemptId, callId: event.callId,
                toolName: event.toolName, resultSummary: event.summary,
                durationMs: event.durationMs, retryable: event.retryable,
                });
                terminalRecorded = true;
              }
              if (event.kind === "tool_error") {
                ledger.toolError({
                runId: input.generationId, attemptId, callId: event.callId,
                toolName: event.toolName, errorCode: event.code,
                errorSummary: event.summary, retryable: event.retryable,
                });
                terminalRecorded = true;
              }
            } catch { ledgerError = true; }
          },
        });
        activeRunner = runner;
        outcome = await runner.request({
          callId: canonicalCallId,
          toolName,
          idempotencyKey: idem,
          input: parsedInput,
        });
        activeRunner = null;
        if (options.isCancelled()) return;
        if (!ledgerError && !terminalRecorded && outcome.kind === "failed") {
          try {
            ledger.toolError({
              runId: input.generationId, attemptId, callId: outcome.callId,
              toolName, errorCode: outcome.code, errorSummary: outcome.summary,
              retryable: outcome.retryable,
            });
            terminalRecorded = true;
          } catch { ledgerError = true; }
        }
        if (ledgerError || outcome.kind === "pending_approval" || outcome.kind === "cancelled") {
          options.fail(gatewayFailure("generation_provider_failed"));
          return;
        }
      }
      messages = Object.freeze([...messages, ...toolHistory({ id: callId, name: toolName, argumentsJson }, outcome)]);
    }
    if (!options.isCancelled()) options.fail(gatewayFailure("generation_provider_failed"));
  })();

  return Object.freeze({
    cancel(): void {
      controller.abort();
      if (activeRunner !== null && activeCallId !== null) activeRunner.cancel(activeCallId);
    },
  });
};
