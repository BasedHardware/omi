// domain-pending(DIV-CHAT-TOOL-001)

import type { AgentApprovalCoordinator } from "./agent-approval-coordinator";
import type { AgentRunEventStore } from "./agent-run-events";
import {
  createGetActionItemsTool,
  createGetActionItemsToolLoop,
  GET_ACTION_ITEMS_TOOL_NAME,
  GET_ACTION_ITEMS_TOOL_SCHEMA,
  type GetActionItemsToolRuntime,
} from "./action-items-tool";
import { createAgentToolRegistry } from "./agent-tools";
import type { GatewayReadOnlyToolLoopOptions } from "./gateway-tool-loop";
import {
  createSafeWriteTool,
  SAFE_WRITE_TOOL_NAME,
  SAFE_WRITE_TOOL_SCHEMA,
} from "./safe-write-tool";

export interface ProductionGatewayToolLoopRuntime extends GetActionItemsToolRuntime {
  readonly approvalCoordinator: AgentApprovalCoordinator;
}

/** Production-shaped gateway lane: safe read-only tasks plus approval-required safe.write. */
export const createProductionGatewayToolLoop = (
  runtime: ProductionGatewayToolLoopRuntime,
): GatewayReadOnlyToolLoopOptions => Object.freeze({
  registry: createAgentToolRegistry([
    createGetActionItemsTool(runtime),
    createSafeWriteTool(),
  ]),
  tools: Object.freeze([GET_ACTION_ITEMS_TOOL_SCHEMA, SAFE_WRITE_TOOL_SCHEMA]),
  agentRunEvents: runtime.agentRunEvents,
  approvalCoordinator: runtime.approvalCoordinator,
  nowEpochMilliseconds: runtime.nowEpochMilliseconds,
});

export const PRODUCTION_GATEWAY_TOOL_NAMES = Object.freeze([
  GET_ACTION_ITEMS_TOOL_NAME,
  SAFE_WRITE_TOOL_NAME,
] as const);

/** Back-compat helper for tests that only exercise get_action_items. */
export const createGetActionItemsOnlyToolLoop = (
  runtime: GetActionItemsToolRuntime,
): GatewayReadOnlyToolLoopOptions => createGetActionItemsToolLoop(runtime);
