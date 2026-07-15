// Published "tool surface" contract for the Windows port's agent control plane.
// Track 2's in-session voice tool-calling codes against these names + taxonomy.
// Const + types only — no handler logic in this PR.
//
// Tool names mirror macOS `agent/src/runtime/control-tool-manifest.ts`
// (agentControlCapabilityManifest). The policy taxonomy mirrors
// `agent/src/runtime/desktop-tool-policy.ts`.

/**
 * The 17 LLM-callable agent-control tool names, in manifest order.
 *
 * EXCLUDED (host-only, never advertised to agent-facing surfaces):
 *  - `spawn_background_agent` — internal Swift coordinator entrypoint
 *    (manifest `surfaces: []`).
 *  - the five `*_workstream_continuity` tools — host-only, not in this manifest.
 */
export const AGENT_CONTROL_TOOL_NAMES = [
  'list_agent_sessions',
  'get_agent_run',
  'build_desktop_awareness_snapshot',
  'list_desktop_action_queue',
  'get_desktop_open_loops',
  'build_desktop_context_packet',
  'route_desktop_intent',
  'evaluate_desktop_tool_policy',
  'create_desktop_dispatch',
  'resolve_desktop_dispatch',
  'cancel_agent_run',
  'inspect_agent_artifacts',
  'update_agent_artifact_lifecycle',
  'send_agent_message',
  'spawn_agent',
  'run_agent_and_wait',
  'set_desktop_attention_override'
] as const

/** Union of the 17 LLM-callable agent-control tool names. */
export type AgentControlToolName = (typeof AGENT_CONTROL_TOOL_NAMES)[number]

/**
 * The 12 capability bundles the desktop coordinator gates tools on. Mirrors
 * `desktop-tool-policy.ts` `DesktopCoordinatorBundle`.
 */
export type DesktopCoordinatorBundle =
  | 'desktop.agent_control.read'
  | 'desktop.agent_control.manage'
  | 'desktop.context.local_read'
  | 'desktop.context.screen_summary'
  | 'desktop.context.screenshot_image'
  | 'desktop.tasks.readwrite'
  | 'desktop.artifacts.manage'
  | 'desktop.automation.read'
  | 'desktop.automation.act_dev_only'
  | 'desktop.permissions.request'
  | 'external.write_prepare'
  | 'external.write_send'

/** Tool risk tier. Mirrors `desktop-tool-policy.ts` `DesktopToolRiskTier`. */
export type RiskTier = 'low' | 'medium' | 'high'

/** Tool privacy tier. Mirrors `desktop-tool-policy.ts` `DesktopToolPrivacyTier`. */
export type PrivacyTier = 'low' | 'local_private' | 'sensitive'

/** Per-tool approval policy. Mirrors `desktop-tool-policy.ts`
 *  `DesktopToolApprovalPolicy`. */
export type ApprovalPolicy = 'allow' | 'user_approval' | 'policy_grant' | 'deny'

/** Coordinator policy outcome for a tool/capability request. Mirrors
 *  `desktop-tool-policy.ts` `DesktopToolPolicyDecision`. */
export type ToolPolicyDecision = 'allow' | 'deny' | 'dispatch_required'
