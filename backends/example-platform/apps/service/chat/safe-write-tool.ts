// domain-pending(DIV-CHAT-TOOL-001)

import type { AgentApprovalCoordinator } from "./agent-approval-coordinator";
import type { AgentRunEventStore } from "./agent-run-events";
import {
  createAgentToolRegistry,
  type AgentToolDefinition,
  type AgentToolRegistry,
} from "./agent-tools";
import type { GatewayReadOnlyToolLoopOptions } from "./gateway-tool-loop";

/** Canned product seam promoted to approval-required; not a live write path. */
export const SAFE_WRITE_TOOL_NAME = "safe_write" as const;

export const SAFE_WRITE_TOOL_SCHEMA = Object.freeze({
  name: SAFE_WRITE_TOOL_NAME,
  description: "Record a scoped write intent after explicit approval.",
  parameters: Object.freeze({
    type: "object" as const,
    additionalProperties: false as const,
    properties: Object.freeze({
      note: Object.freeze({ type: "string" as const, description: "A short scoped note." }),
    }),
    required: Object.freeze([] as readonly string[]),
  }),
});

const emptyOrNote = (input: unknown): boolean => {
  if (input === null || typeof input !== "object" || Array.isArray(input)) return false;
  const record = input as Record<string, unknown>;
  const keys = Object.keys(record);
  if (keys.length === 0) return true;
  return keys.length === 1 && keys[0] === "note"
    && typeof record.note === "string" && record.note.length <= 240
    && !/[\u0000-\u001f\u007f]/u.test(record.note);
};

export const createSafeWriteTool = (): AgentToolDefinition => Object.freeze({
  schemaVersion: 1,
  name: SAFE_WRITE_TOOL_NAME,
  risk: "approval-required",
  timeoutMs: 5_000,
  retryable: false,
  displaySummary: "Scoped write",
  validateInput: emptyOrNote,
  execute: async (_input, control) => {
    if (control.cancelled) throw new Error("tool cancelled");
    return Object.freeze({
      summary: "Scoped write recorded.",
      durationMs: 1,
      retryable: false,
    });
  },
});

export const createSafeWriteToolRegistry = (): AgentToolRegistry =>
  createAgentToolRegistry([createSafeWriteTool()]);

export const createSafeWriteToolLoop = (runtime: {
  readonly agentRunEvents: AgentRunEventStore;
  readonly approvalCoordinator: AgentApprovalCoordinator;
  readonly nowEpochMilliseconds: () => number;
}): GatewayReadOnlyToolLoopOptions => Object.freeze({
  registry: createSafeWriteToolRegistry(),
  tool: SAFE_WRITE_TOOL_SCHEMA,
  agentRunEvents: runtime.agentRunEvents,
  approvalCoordinator: runtime.approvalCoordinator,
  nowEpochMilliseconds: runtime.nowEpochMilliseconds,
});
