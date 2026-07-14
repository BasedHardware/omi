// Desktop capability-bundle / grant policy engine — Windows port of the macOS
// agent runtime's desktop-tool-policy.ts (desktop/macos/agent/src/runtime/).
//
// This is the engine behind the `evaluate_desktop_tool_policy` control tool: a
// pure decision table over capability bundles, risk/privacy/approval tiers, and
// scoped grants. Deny-by-default. `Date.now()` is its only non-deterministic
// call and callers can override it with `nowMs`, so the whole engine is
// hermetically testable with an injected clock.
//
// It is one of THREE independent policy axes; do not conflate them:
//   1. capability bundles + grants  — this file
//   2. execution-role gating        — ./executionPolicy (leaf workers cannot
//                                     spawn or message other agents)
//   3. ACP per-action permissions   — ../codingAgent/toolPolicyStub
//      ("may I run this bash command", raised by the coding-agent adapter)
//
// The types here are the WIDE, coordinator-wide family (12 bundles, 4 approval
// policies) — they intentionally differ from the narrow control-tool-only family
// in ./controlToolManifest. See that file's header.
//
// PORT NOTE — product ("omi") tools. macOS resolves a non-control tool name
// through omi-tool-manifest.ts (~31 product tools: execute_sql, capture_screen,
// request_permission, …). That manifest is owned by other tracks and is not
// ported here, so `descriptorFromToolName` resolves control tools only. An
// unrecognized tool name therefore falls through to `descriptorFromBundles`,
// exactly as it does on macOS for a name absent from both manifests — with no
// requested bundles that is a deny ("No coordinator capability bundle was
// declared."), which is both faithful and the safe direction. The product-tool
// bundle mapping itself is ported verbatim below and exported
// (`bundlesForOmiTool` / `descriptorFromOmiTool`) so the track that lands those
// tools inherits this policy instead of re-deriving it.

import { agentControlCapabilityManifest } from './controlToolManifest'

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

export type DesktopToolPolicyDecision = 'allow' | 'deny' | 'dispatch_required'
export type DesktopToolRiskTier = 'low' | 'medium' | 'high'
export type DesktopToolPrivacyTier = 'low' | 'local_private' | 'sensitive'
export type DesktopToolApprovalPolicy = 'allow' | 'user_approval' | 'policy_grant' | 'deny'

export interface DesktopToolGrant {
  bundle: DesktopCoordinatorBundle
  operation?: string
  resourceRef?: string
  expiresAtMs: number
  effect: 'allow' | 'deny'
}

export interface DesktopToolPolicyRequest {
  toolName?: string
  operation?: string
  resourceRef?: string
  requestedBundles?: readonly DesktopCoordinatorBundle[]
  selectedBundles: readonly DesktopCoordinatorBundle[]
  surface?: string
  nowMs?: number
  isDevBundle?: boolean
  sql?: string
  includesScreenshotImageBytes?: boolean
  broadScreenHistory?: boolean
  externalSend?: boolean
  persistentGrant?: boolean
  userExplicitMutation?: boolean
  grants?: readonly DesktopToolGrant[]
}

export interface DesktopToolDescriptor {
  name: string
  bundles: readonly DesktopCoordinatorBundle[]
  riskTier: DesktopToolRiskTier
  privacyTier: DesktopToolPrivacyTier
  approvalPolicy: DesktopToolApprovalPolicy
  readOnly: boolean
  destructive: boolean
}

export interface DesktopToolPolicyResult {
  decision: DesktopToolPolicyDecision
  descriptor: DesktopToolDescriptor
  requiredBundles: readonly DesktopCoordinatorBundle[]
  reason: string
}

/**
 * Structural shape of a product-tool manifest entry, as far as the policy engine
 * needs it. Mirrors the fields `bundlesForOmiTool` reads from macOS'
 * `OmiToolManifestEntry`.
 */
export interface OmiToolPolicyEntry {
  name: string
  executor: { kind: string }
  annotations: { readOnlyHint?: boolean; destructiveHint?: boolean }
}

const EXTERNAL_SEND_TOOLS = new Set(['fill_cloud_connector_form'])
const TASK_WRITE_TOOLS = new Set([
  'complete_task',
  'delete_task',
  'create_action_item',
  'update_action_item',
  'save_knowledge_graph',
  'set_user_preferences',
  'complete_onboarding'
])
const SCREEN_IMAGE_TOOLS = new Set(['get_screenshot', 'capture_screen'])
const SCREEN_SUMMARY_TOOLS = new Set(['semantic_search', 'get_work_context'])
// Coordinator policy classifies this as a production user-approved operation;
// the chat tool executor independently enforces the current-turn consent at
// execution.
const PERMISSION_REQUEST_TOOLS = new Set(['request_permission'])
const AUTOMATION_READ_TOOLS = new Set(['check_permission_status'])
const LOCAL_READ_TOOLS = new Set([
  'execute_sql',
  'get_daily_recap',
  'search_tasks',
  'load_skill',
  'get_conversations',
  'search_conversations',
  'get_memories',
  'search_memories',
  'get_action_items',
  'get_email_insights',
  'get_local_status'
])

function isSqlWrite(sql: string): boolean {
  const stripped = sql
    .replace(/--.*$/gm, ' ')
    .replace(/\/\*[\s\S]*?\*\//g, ' ')
    .trim()
    .toLowerCase()
  if (!stripped) return false
  if (!/^(select|with|pragma)\b/.test(stripped)) return true
  return /\b(insert|update|delete|drop|alter|create|replace|truncate|attach|detach|vacuum|reindex)\b/.test(
    stripped
  )
}

function controlDescriptor(toolName: string): DesktopToolDescriptor | undefined {
  const tool = agentControlCapabilityManifest.find((entry) => entry.name === toolName)
  if (!tool) return undefined
  const bundles = [...tool.bundles] as DesktopCoordinatorBundle[]
  const riskTier = tool.riskTier as DesktopToolRiskTier
  return {
    name: tool.name,
    bundles,
    riskTier,
    privacyTier: tool.privacyTier,
    approvalPolicy: tool.approvalPolicy,
    readOnly: bundles.includes('desktop.agent_control.read'),
    destructive: riskTier === 'high'
  }
}

/** Bundle assignment for a non-control ("omi") product tool, by fixed name-set membership. */
export function bundlesForOmiTool(tool: OmiToolPolicyEntry): DesktopCoordinatorBundle[] {
  const bundles = new Set<DesktopCoordinatorBundle>()
  if (LOCAL_READ_TOOLS.has(tool.name)) bundles.add('desktop.context.local_read')
  if (SCREEN_SUMMARY_TOOLS.has(tool.name)) bundles.add('desktop.context.screen_summary')
  if (SCREEN_IMAGE_TOOLS.has(tool.name)) bundles.add('desktop.context.screenshot_image')
  if (TASK_WRITE_TOOLS.has(tool.name)) bundles.add('desktop.tasks.readwrite')
  if (AUTOMATION_READ_TOOLS.has(tool.name)) bundles.add('desktop.automation.read')
  if (PERMISSION_REQUEST_TOOLS.has(tool.name)) bundles.add('desktop.permissions.request')
  if (EXTERNAL_SEND_TOOLS.has(tool.name)) bundles.add('external.write_send')
  if (tool.executor.kind === 'runtimeControl') {
    const control = controlDescriptor(tool.name)
    for (const bundle of control?.bundles ?? []) bundles.add(bundle)
  }
  if (bundles.size === 0 && tool.annotations.readOnlyHint) bundles.add('desktop.context.local_read')
  return [...bundles]
}

/** Descriptor for a non-control ("omi") product tool. */
export function descriptorFromOmiTool(tool: OmiToolPolicyEntry): DesktopToolDescriptor {
  const bundles = bundlesForOmiTool(tool)
  const destructive = tool.annotations.destructiveHint === true
  const write = tool.annotations.readOnlyHint !== true
  const sensitive =
    bundles.includes('desktop.context.screenshot_image') ||
    bundles.includes('external.write_send') ||
    bundles.includes('desktop.automation.act_dev_only') ||
    bundles.includes('desktop.permissions.request')
  return {
    name: tool.name,
    bundles,
    riskTier: destructive || sensitive ? 'high' : write ? 'medium' : 'low',
    privacyTier: sensitive ? 'sensitive' : 'local_private',
    approvalPolicy: write || sensitive ? 'user_approval' : 'allow',
    readOnly: tool.annotations.readOnlyHint === true,
    destructive
  }
}

function descriptorFromToolName(toolName: string): DesktopToolDescriptor | undefined {
  // Control tools only — see the product-tool port note in the file header.
  return controlDescriptor(toolName)
}

function descriptorFromBundles(
  bundles: readonly DesktopCoordinatorBundle[]
): DesktopToolDescriptor {
  const sensitive = bundles.some((bundle) =>
    [
      'desktop.context.screenshot_image',
      'external.write_send',
      'desktop.automation.act_dev_only',
      'desktop.permissions.request'
    ].includes(bundle)
  )
  const write = bundles.some((bundle) =>
    [
      'desktop.agent_control.manage',
      'desktop.tasks.readwrite',
      'desktop.artifacts.manage',
      'external.write_prepare',
      'external.write_send',
      'desktop.automation.act_dev_only',
      'desktop.permissions.request'
    ].includes(bundle)
  )
  return {
    name: 'bundle_request',
    bundles,
    riskTier: sensitive ? 'high' : write ? 'medium' : 'low',
    privacyTier: sensitive ? 'sensitive' : 'local_private',
    approvalPolicy: write || sensitive ? 'user_approval' : 'allow',
    readOnly: !write,
    destructive:
      bundles.includes('desktop.tasks.readwrite') || bundles.includes('external.write_send')
  }
}

function hasAllowGrant(
  request: DesktopToolPolicyRequest,
  bundle: DesktopCoordinatorBundle
): boolean {
  const nowMs = request.nowMs ?? Date.now()
  return (request.grants ?? []).some((grant) => {
    if (grant.effect !== 'allow' || grant.bundle !== bundle || grant.expiresAtMs <= nowMs) {
      return false
    }
    if (grant.operation && grant.operation !== request.operation) return false
    if (grant.resourceRef && grant.resourceRef !== request.resourceRef) return false
    return true
  })
}

export function evaluateDesktopToolPolicy(
  request: DesktopToolPolicyRequest
): DesktopToolPolicyResult {
  const descriptor = request.toolName
    ? (descriptorFromToolName(request.toolName) ??
      descriptorFromBundles(request.requestedBundles ?? []))
    : descriptorFromBundles(request.requestedBundles ?? [])
  const requiredBundles = [
    ...new Set([...(descriptor.bundles ?? []), ...(request.requestedBundles ?? [])])
  ]
  const selected = new Set(request.selectedBundles)

  if (requiredBundles.length === 0) {
    return {
      decision: 'deny',
      descriptor,
      requiredBundles,
      reason: 'No coordinator capability bundle was declared.'
    }
  }
  const missing = requiredBundles.filter((bundle) => !selected.has(bundle))
  if (missing.length > 0) {
    return {
      decision: 'deny',
      descriptor,
      requiredBundles,
      reason: `Missing selected bundle(s): ${missing.join(', ')}`
    }
  }
  if (request.sql && isSqlWrite(request.sql)) {
    return {
      decision: 'deny',
      descriptor,
      requiredBundles,
      reason: 'SQL writes are not allowed through read context tools.'
    }
  }
  if (requiredBundles.includes('desktop.automation.act_dev_only') && request.isDevBundle !== true) {
    return {
      decision: 'deny',
      descriptor,
      requiredBundles,
      reason: 'Desktop automation actuation is only available in dev/test bundles.'
    }
  }

  const requiresDispatch =
    request.includesScreenshotImageBytes === true ||
    request.broadScreenHistory === true ||
    request.externalSend === true ||
    request.persistentGrant === true ||
    requiredBundles.includes('desktop.context.screenshot_image') ||
    requiredBundles.includes('external.write_send') ||
    requiredBundles.includes('desktop.automation.act_dev_only') ||
    requiredBundles.includes('desktop.permissions.request') ||
    descriptor.approvalPolicy === 'user_approval' ||
    descriptor.approvalPolicy === 'policy_grant'

  if (requiresDispatch) {
    const granted = requiredBundles.every((bundle) => hasAllowGrant(request, bundle))
    if (granted) {
      return {
        decision: 'allow',
        descriptor,
        requiredBundles,
        reason: 'Scoped allow grant covers the request.'
      }
    }
    if (requiredBundles.includes('desktop.tasks.readwrite') && request.userExplicitMutation === true) {
      return {
        decision: 'dispatch_required',
        descriptor,
        requiredBundles,
        reason: 'Task mutation still needs a durable approval record.'
      }
    }
    return {
      decision: 'dispatch_required',
      descriptor,
      requiredBundles,
      reason: 'Sensitive action requires dispatch or scoped grant.'
    }
  }

  if (descriptor.approvalPolicy === 'deny') {
    return {
      decision: 'deny',
      descriptor,
      requiredBundles,
      reason: 'The manifest marks this capability denied.'
    }
  }
  return {
    decision: 'allow',
    descriptor,
    requiredBundles,
    reason: 'Selected bundles allow this read-only local operation.'
  }
}

export const desktopToolPolicyInternals = {
  isSqlWrite,
  descriptorFromToolName
}
