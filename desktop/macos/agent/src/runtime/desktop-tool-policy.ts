import { basename } from "node:path";

import { agentControlCapabilityManifest } from "./control-tool-manifest.js";
import { toolManifestEntry, type OmiToolManifestEntry } from "./omi-tool-manifest.js";
import { utf8Excerpt } from "./tool-result-projector.js";

export type DesktopCoordinatorBundle =
  | "desktop.agent_control.read"
  | "desktop.agent_control.manage"
  | "desktop.context.local_read"
  | "desktop.context.screen_summary"
  | "desktop.context.screenshot_image"
  | "desktop.tasks.readwrite"
  | "desktop.memories.write"
  | "desktop.artifacts.manage"
  | "desktop.automation.read"
  | "desktop.automation.act_dev_only"
  | "desktop.automation.act"
  | "desktop.contacts.read"
  | "desktop.messaging.read"
  | "desktop.mail.read"
  | "desktop.messaging.send"
  | "desktop.permissions.request"
  | "external.write_prepare"
  | "external.write_send";

export type DesktopToolPolicyDecision = "allow" | "deny" | "dispatch_required";
export type DesktopToolRiskTier = "low" | "medium" | "high";
export type DesktopToolPrivacyTier = "low" | "local_private" | "sensitive";
export type DesktopToolApprovalPolicy = "allow" | "user_approval" | "policy_grant" | "deny";

export interface DesktopToolGrant {
  bundle: DesktopCoordinatorBundle;
  operation?: string;
  resourceRef?: string;
  expiresAtMs: number;
  effect: "allow" | "deny";
}

export interface DesktopToolPolicyRequest {
  toolName?: string;
  operation?: string;
  resourceRef?: string;
  requestedBundles?: readonly DesktopCoordinatorBundle[];
  selectedBundles: readonly DesktopCoordinatorBundle[];
  surface?: string;
  nowMs?: number;
  isDevBundle?: boolean;
  sql?: string;
  includesScreenshotImageBytes?: boolean;
  broadScreenHistory?: boolean;
  externalSend?: boolean;
  persistentGrant?: boolean;
  userExplicitMutation?: boolean;
  grants?: readonly DesktopToolGrant[];
}

export interface DesktopToolDescriptor {
  name: string;
  bundles: readonly DesktopCoordinatorBundle[];
  riskTier: DesktopToolRiskTier;
  privacyTier: DesktopToolPrivacyTier;
  approvalPolicy: DesktopToolApprovalPolicy;
  readOnly: boolean;
  destructive: boolean;
}

export interface DesktopToolPolicyResult {
  decision: DesktopToolPolicyDecision;
  descriptor: DesktopToolDescriptor;
  requiredBundles: readonly DesktopCoordinatorBundle[];
  reason: string;
}

const EXTERNAL_SEND_TOOLS = new Set(["fill_cloud_connector_form"]);
const TASK_WRITE_TOOLS = new Set([
  "create_canonical_goal",
  "complete_task",
  "delete_task",
  "create_action_item",
  "create_context_reminder",
  "update_action_item",
  "save_knowledge_graph",
  "set_user_preferences",
  "complete_onboarding",
]);
const MEMORY_WRITE_TOOLS = new Set(["create_memory"]);
// JIT knowledge-ledger write verbs (save_playbook, create_standing_trigger,
// close_fact) mutate the same backend memory/knowledge store as create_memory,
// so they share its bundle rather than inventing a new one.
const LEDGER_WRITE_TOOLS = new Set(["save_playbook", "create_standing_trigger", "close_fact"]);
// `screenshot` is the realtime voice capture; it is offered only to realtime
// voice runs, never to a chat relay.
const SCREEN_IMAGE_TOOLS = new Set(["get_screenshot", "look_at_frame", "capture_screen", "screenshot"]);
// show_rewind_evidence returns the model only the stored frame's title, app
// and OCR excerpt (the same text a screen-history search already returned for
// that screenshot_id); the pixels go to the person's own Chat turn as
// evidence, behind the screenshot-sharing setting, and never to the model.
const SCREEN_SUMMARY_TOOLS = new Set(["semantic_search", "get_work_context", "show_rewind_evidence"]);
// A live screenshot holds whatever is on screen at that moment, including
// windows the person keeps out of capture elsewhere, so each one is asked for
// on its own: the card never offers a session grant and no grant covers one.
const ALLOW_ONCE_ONLY_TOOLS = new Set(["capture_screen"]);
// Coordinator policy classifies this as a production user-approved operation;
// ChatToolExecutor independently enforces the current-turn consent at execution.
const PERMISSION_REQUEST_TOOLS = new Set(["request_permission"]);
const AUTOMATION_READ_TOOLS = new Set(["check_permission_status"]);
const CONTACTS_READ_TOOLS = new Set(["search_contacts"]);
const MESSAGING_READ_TOOLS = new Set(["list_message_chats", "read_message_history"]);
// Mail headers name who is writing to the user and about what. That is the
// same class of disclosure as a message thread, so it takes the same durable
// approval rather than riding along as an ordinary local read.
const MAIL_READ_TOOLS = new Set(["list_mail_messages"]);
const MESSAGING_SEND_TOOLS = new Set(["send_message"]);
// Production actuation, unlike `act_dev_only`: allowed in release bundles but
// never without a dispatch or an unexpired scoped grant.
const AUTOMATION_ACT_TOOLS = new Set(["run_applescript"]);
const LOCAL_READ_TOOLS = new Set([
  "execute_sql",
  "get_daily_recap",
  "search_tasks",
  "load_skill",
  "search_skills",
  "get_conversations",
  "search_conversations",
  "get_memories",
  "search_memories",
  "get_action_items",
  "get_email_insights",
  "get_local_status",
  "get_product_kb",
  "search_knowledge",
  "read_playbook",
  "search_historical_facts",
  "get_entity_timeline_tool",
  "read_conversation_evidence",
  "search_conversation_evidence",
  "search_chat_history",
  "get_canonical_goals",
  "scan_files",
]);
/**
 * Relay tools declared to need no capability bundle: they read or touch none
 * of the person's local data. Declaring them keeps every relay-callable tool
 * explicitly classified (a test enforces it); an undeclared tool no longer
 * slides into `local_read` by default unnoticed.
 */
const UNBUNDLED_TOOLS: Readonly<Record<string, string>> = {
  web_search: "a public web search; only the query leaves the Mac",
  render_chat_blocks: "renders the model's own reply as blocks in the current turn",
  ask_followup: "shows the person an onboarding question with quick replies",
};

function isSqlWrite(sql: string): boolean {
  const stripped = sql
    .replace(/--.*$/gm, " ")
    .replace(/\/\*[\s\S]*?\*\//g, " ")
    .trim()
    .toLowerCase();
  if (!stripped) return false;
  if (!/^(select|with|pragma)\b/.test(stripped)) return true;
  return /\b(insert|update|delete|drop|alter|create|replace|truncate|attach|detach|vacuum|reindex)\b/.test(stripped);
}

function controlDescriptor(toolName: string): DesktopToolDescriptor | undefined {
  const tool = agentControlCapabilityManifest.find((entry) => entry.name === toolName);
  if (!tool) return undefined;
  const bundles = [...tool.bundles] as DesktopCoordinatorBundle[];
  const riskTier = tool.riskTier as DesktopToolRiskTier;
  return {
    name: tool.name,
    bundles,
    riskTier,
    privacyTier: tool.privacyTier,
    approvalPolicy: tool.approvalPolicy,
    readOnly: bundles.includes("desktop.agent_control.read"),
    destructive: riskTier === "high",
  };
}

function bundlesForOmiTool(tool: OmiToolManifestEntry): DesktopCoordinatorBundle[] {
  const bundles = new Set<DesktopCoordinatorBundle>();
  if (LOCAL_READ_TOOLS.has(tool.name)) bundles.add("desktop.context.local_read");
  if (SCREEN_SUMMARY_TOOLS.has(tool.name)) bundles.add("desktop.context.screen_summary");
  if (SCREEN_IMAGE_TOOLS.has(tool.name)) bundles.add("desktop.context.screenshot_image");
  if (TASK_WRITE_TOOLS.has(tool.name)) bundles.add("desktop.tasks.readwrite");
  if (MEMORY_WRITE_TOOLS.has(tool.name) || LEDGER_WRITE_TOOLS.has(tool.name)) bundles.add("desktop.memories.write");
  if (AUTOMATION_READ_TOOLS.has(tool.name)) bundles.add("desktop.automation.read");
  if (CONTACTS_READ_TOOLS.has(tool.name)) bundles.add("desktop.contacts.read");
  if (MESSAGING_READ_TOOLS.has(tool.name)) bundles.add("desktop.messaging.read");
  if (MAIL_READ_TOOLS.has(tool.name)) bundles.add("desktop.mail.read");
  if (MESSAGING_SEND_TOOLS.has(tool.name)) bundles.add("desktop.messaging.send");
  if (AUTOMATION_ACT_TOOLS.has(tool.name)) bundles.add("desktop.automation.act");
  if (PERMISSION_REQUEST_TOOLS.has(tool.name)) bundles.add("desktop.permissions.request");
  if (EXTERNAL_SEND_TOOLS.has(tool.name)) bundles.add("external.write_send");
  if (tool.executor.kind === "runtimeControl") {
    const control = controlDescriptor(tool.name);
    for (const bundle of control?.bundles ?? []) bundles.add(bundle);
  }
  if (bundles.size === 0 && tool.annotations.readOnlyHint) bundles.add("desktop.context.local_read");
  return [...bundles];
}

/// Whether a tool is classified on purpose: named in one of the sets above,
/// a runtime-control tool with declared bundles, or declared unbundled. The
/// read-only fallback in `bundlesForOmiTool` does not count.
function isExplicitlyClassified(toolName: string): boolean {
  if (Object.hasOwn(UNBUNDLED_TOOLS, toolName)) return true;
  if ((controlDescriptor(toolName)?.bundles.length ?? 0) > 0) return true;
  return [
    LOCAL_READ_TOOLS, SCREEN_SUMMARY_TOOLS, SCREEN_IMAGE_TOOLS, TASK_WRITE_TOOLS, MEMORY_WRITE_TOOLS,
    LEDGER_WRITE_TOOLS, AUTOMATION_READ_TOOLS, CONTACTS_READ_TOOLS, MESSAGING_READ_TOOLS, MAIL_READ_TOOLS,
    MESSAGING_SEND_TOOLS, AUTOMATION_ACT_TOOLS, PERMISSION_REQUEST_TOOLS, EXTERNAL_SEND_TOOLS,
  ].some((set) => set.has(toolName));
}

/// Bundles whose data or effects are sensitive enough that the request is
/// classified high-risk and can never resolve without a dispatch or grant.
const SENSITIVE_BUNDLES: readonly DesktopCoordinatorBundle[] = [
  "desktop.context.screenshot_image",
  "external.write_send",
  "desktop.automation.act_dev_only",
  "desktop.automation.act",
  "desktop.messaging.read",
  "desktop.mail.read",
  "desktop.messaging.send",
  "desktop.permissions.request",
];

/// Bundles that carry a write or actuation effect rather than a local read.
const WRITE_BUNDLES: readonly DesktopCoordinatorBundle[] = [
  "desktop.agent_control.manage",
  "desktop.tasks.readwrite",
  "desktop.memories.write",
  "desktop.artifacts.manage",
  "external.write_prepare",
  "external.write_send",
  "desktop.automation.act_dev_only",
  "desktop.automation.act",
  "desktop.messaging.send",
  "desktop.permissions.request",
];

function isSensitiveBundle(bundle: DesktopCoordinatorBundle): boolean {
  return SENSITIVE_BUNDLES.includes(bundle);
}

function descriptorFromToolName(toolName: string): DesktopToolDescriptor | undefined {
  const control = controlDescriptor(toolName);
  if (control) return control;
  const tool = toolManifestEntry(toolName);
  if (!tool) return undefined;
  const bundles = bundlesForOmiTool(tool);
  const destructive = tool.annotations.destructiveHint === true;
  const write = tool.annotations.readOnlyHint !== true;
  const sensitive = bundles.some(isSensitiveBundle);
  return {
    name: tool.name,
    bundles,
    riskTier: destructive || sensitive ? "high" : write ? "medium" : "low",
    privacyTier: sensitive ? "sensitive" : "local_private",
    approvalPolicy: write || sensitive ? "user_approval" : "allow",
    readOnly: tool.annotations.readOnlyHint === true,
    destructive,
  };
}

function descriptorFromBundles(bundles: readonly DesktopCoordinatorBundle[]): DesktopToolDescriptor {
  const sensitive = bundles.some(isSensitiveBundle);
  const write = bundles.some((bundle) => WRITE_BUNDLES.includes(bundle));
  return {
    name: "bundle_request",
    bundles,
    riskTier: sensitive ? "high" : write ? "medium" : "low",
    privacyTier: sensitive ? "sensitive" : "local_private",
    approvalPolicy: write || sensitive ? "user_approval" : "allow",
    readOnly: !write,
    destructive: bundles.includes("desktop.tasks.readwrite") || bundles.includes("external.write_send"),
  };
}

/// Bundles whose grants must name the exact resource they cover; an unscoped
/// or `*` row never authorizes them.
const RESOURCE_SCOPED_GRANT_BUNDLES: ReadonlySet<DesktopCoordinatorBundle> = new Set([
  "desktop.messaging.send",
  "desktop.automation.act",
  "desktop.context.screenshot_image",
]);

function hasAllowGrant(request: DesktopToolPolicyRequest, bundle: DesktopCoordinatorBundle): boolean {
  const nowMs = request.nowMs ?? Date.now();
  return (request.grants ?? []).some((grant) => {
    if (grant.effect !== "allow" || grant.bundle !== bundle || grant.expiresAtMs <= nowMs) return false;
    if (RESOURCE_SCOPED_GRANT_BUNDLES.has(bundle) && !grant.resourceRef) return false;
    if (ALLOW_ONCE_ONLY_TOOLS.has(request.toolName ?? request.operation ?? "")) return false;
    if (grant.operation && grant.operation !== request.operation) return false;
    if (grant.resourceRef && grant.resourceRef !== request.resourceRef) return false;
    return true;
  });
}

export function evaluateDesktopToolPolicy(request: DesktopToolPolicyRequest): DesktopToolPolicyResult {
  const descriptor = request.toolName
    ? descriptorFromToolName(request.toolName) ?? descriptorFromBundles(request.requestedBundles ?? [])
    : descriptorFromBundles(request.requestedBundles ?? []);
  const requiredBundles = [...new Set([...(descriptor.bundles ?? []), ...(request.requestedBundles ?? [])])];
  const selected = new Set(request.selectedBundles);

  if (requiredBundles.length === 0) {
    return { decision: "deny", descriptor, requiredBundles, reason: "No coordinator capability bundle was declared." };
  }
  const missing = requiredBundles.filter((bundle) => !selected.has(bundle));
  if (missing.length > 0) {
    return {
      decision: "deny",
      descriptor,
      requiredBundles,
      reason: `Missing selected bundle(s): ${missing.join(", ")}`,
    };
  }
  if (request.sql && isSqlWrite(request.sql)) {
    return { decision: "deny", descriptor, requiredBundles, reason: "SQL writes are not allowed through read context tools." };
  }
  if (requiredBundles.includes("desktop.automation.act_dev_only") && request.isDevBundle !== true) {
    return {
      decision: "deny",
      descriptor,
      requiredBundles,
      reason: "Desktop automation actuation is only available in dev/test bundles.",
    };
  }

  const requiresDispatch =
    request.includesScreenshotImageBytes === true ||
    request.broadScreenHistory === true ||
    request.externalSend === true ||
    request.persistentGrant === true ||
    requiredBundles.some(isSensitiveBundle) ||
    descriptor.approvalPolicy === "user_approval" ||
    descriptor.approvalPolicy === "policy_grant";

  if (requiresDispatch) {
    const granted = requiredBundles.every((bundle) => hasAllowGrant(request, bundle));
    if (granted) return { decision: "allow", descriptor, requiredBundles, reason: "Scoped allow grant covers the request." };
    if (
      (requiredBundles.includes("desktop.tasks.readwrite") || requiredBundles.includes("desktop.memories.write"))
      && request.userExplicitMutation === true
    ) {
      return {
        decision: "dispatch_required",
        descriptor,
        requiredBundles,
        reason: requiredBundles.includes("desktop.memories.write")
          ? "Memory mutation still needs a durable approval record."
          : "Task mutation still needs a durable approval record.",
      };
    }
    return { decision: "dispatch_required", descriptor, requiredBundles, reason: "Sensitive action requires dispatch or scoped grant." };
  }

  if (descriptor.approvalPolicy === "deny") {
    return { decision: "deny", descriptor, requiredBundles, reason: "The manifest marks this capability denied." };
  }
  return { decision: "allow", descriptor, requiredBundles, reason: "Selected bundles allow this read-only local operation." };
}

export const desktopToolPolicyInternals = {
  isSqlWrite,
  descriptorFromToolName,
  isSensitiveBundle,
  isExplicitlyClassified,
};

// --- Per-invocation user approval -------------------------------------------
//
// A `dispatch_required` decision for a sensitive device tool becomes an
// `approval` dispatch bound to one prepared invocation. The user resolves it
// through signed direct control; the model never chooses allow or deny. Only
// this module decides what the user is asked and which answers exist.

export const DESKTOP_APPROVAL_POLICY = "default_user_approval" as const;

/**
 * How long a parked invocation waits for the user before it fails closed as
 * denied. Matches the mobile device-tool transport's 180s: roughly how long a
 * person plausibly takes to read a card and answer it. It must stay below the
 * pi-mono `long` tool wait (10 min) minus the Swift executor timeout (120s),
 * or a late approval could run an effect the model already reported as failed.
 */
export const DESKTOP_APPROVAL_TTL_MS = 180_000;

export type DesktopApprovalOptionId = "allow_once" | "allow_session" | "deny";
export type DesktopApprovalDecision = "allow" | "deny" | "expired" | "cancelled";

export interface DesktopApprovalOption {
  id: DesktopApprovalOptionId;
  effect: "allow" | "deny";
  scope: "run" | "session" | "request";
  /** For `allow_session`: plain words for what the grant would cover, so the card never over-promises. */
  covers?: string;
}

export const DESKTOP_APPROVAL_ALLOW_ONCE_OPTION: DesktopApprovalOption = Object.freeze({ id: "allow_once", effect: "allow", scope: "run" });
export const DESKTOP_APPROVAL_DENY_OPTION: DesktopApprovalOption = Object.freeze({ id: "deny", effect: "deny", scope: "request" });

export const DESKTOP_APPROVAL_DEFAULT_OPTION_ID: DesktopApprovalOptionId = "deny";

/**
 * What an `allow_session` grant would actually cover, per tool. The grant is
 * matched on the exact resource ref, so for a script it covers only that
 * identical script, never "AppleScript in general".
 */
const APPROVAL_SESSION_GRANT_COVERS: Record<string, string> = {
  send_message: "any message or attachment to this recipient",
  run_applescript: "only this exact script",
  read_message_history: "this conversation",
  list_message_chats: "your recent Messages conversations",
  list_mail_messages: "your Mail inbox headers",
};

/**
 * `allow_session` is the only answer that mints a grant, and a grant needs the
 * exact resource it covers. Without one (a thread read with neither chat_id
 * nor handle), and for a live screenshot, the card offers only allow once and
 * deny.
 */
export function desktopApprovalOptions(toolName: string, resourceRef: string | null): readonly DesktopApprovalOption[] {
  if (resourceRef === null || ALLOW_ONCE_ONLY_TOOLS.has(toolName)) {
    return Object.freeze([DESKTOP_APPROVAL_ALLOW_ONCE_OPTION, DESKTOP_APPROVAL_DENY_OPTION]);
  }
  return Object.freeze([
    DESKTOP_APPROVAL_ALLOW_ONCE_OPTION,
    {
      id: "allow_session",
      effect: "allow",
      scope: "session",
      covers: APPROVAL_SESSION_GRANT_COVERS[toolName] ?? "only this exact request",
    },
    DESKTOP_APPROVAL_DENY_OPTION,
  ]);
}

export type DesktopApprovalPreviewValue = string | number | boolean;

export interface DesktopToolApprovalRequest {
  policy: typeof DESKTOP_APPROVAL_POLICY;
  capability: DesktopCoordinatorBundle;
  operation: string;
  resourceRef: string | null;
  title: string;
  decisionPrompt: string;
  /** Bounded, display-safe projection of the tool input; never the raw input. */
  preview: Record<string, DesktopApprovalPreviewValue>;
  previewTruncated: boolean;
  options: readonly DesktopApprovalOption[];
  defaultOptionId: DesktopApprovalOptionId;
  reason: string;
  requestedAtMs: number;
  expiresAtMs: number;
}

/** Fields each tool may show on its card. Anything else in the input stays out of the preview. */
const APPROVAL_PREVIEW_FIELDS: Record<string, readonly string[]> = {
  send_message: ["to", "text", "service", "file_path"],
  run_applescript: ["script", "timeout_seconds"],
  read_message_history: ["chat_id", "handle", "limit"],
  list_message_chats: ["limit"],
  list_mail_messages: ["limit"],
  // Takes no input: the card's question says everything the capture does.
  capture_screen: [],
};
/** Paths are redacted to their final component: the card needs the file name, not the user's directory layout. */
const APPROVAL_PREVIEW_PATH_FIELDS = new Set(["file_path"]);
/** The card shows message text and scripts verbatim, so the bound is generous; the input hash binds the exact content. */
const APPROVAL_PREVIEW_FIELD_BYTES = 4_096;

function approvalCopy(toolName: string, preview: Record<string, DesktopApprovalPreviewValue>): { title: string; decisionPrompt: string } {
  switch (toolName) {
    case "send_message":
      return { title: "Send a message", decisionPrompt: `Send this message to ${preview.to ?? "the recipient"}?` };
    case "run_applescript":
      return { title: "Run an AppleScript", decisionPrompt: "Run this AppleScript on your Mac?" };
    case "read_message_history":
      return {
        title: "Read a Messages conversation",
        decisionPrompt: preview.handle !== undefined
          ? `Read recent messages with ${preview.handle}?`
          : preview.chat_id !== undefined
            ? `Read recent messages in chat ${preview.chat_id}?`
            : "Read recent messages from this conversation?",
      };
    case "list_message_chats":
      return { title: "List Messages conversations", decisionPrompt: "List your recent Messages conversations?" };
    case "list_mail_messages":
      return { title: "List Mail messages", decisionPrompt: "List recent Mail messages (headers only, no bodies)?" };
    case "capture_screen":
      return { title: "Take a screenshot", decisionPrompt: "Let Omi take a screenshot of your whole screen?" };
    default:
      return { title: `Allow ${toolName}`, decisionPrompt: `Allow the agent to run ${toolName}?` };
  }
}

export function buildDesktopToolApprovalRequest(input: {
  toolName: string;
  toolInput: Record<string, unknown>;
  policy: DesktopToolPolicyResult;
  resourceRef: string | undefined;
  nowMs: number;
  ttlMs?: number;
}): DesktopToolApprovalRequest {
  if (input.policy.decision !== "dispatch_required") {
    throw new Error("Approval requests are built only for dispatch_required policy decisions");
  }
  const capability = input.policy.requiredBundles.find(isSensitiveBundle) ?? input.policy.requiredBundles[0];
  if (!capability) throw new Error("Approval requests require at least one capability bundle");
  const ttlMs = input.ttlMs ?? DESKTOP_APPROVAL_TTL_MS;
  if (!Number.isSafeInteger(ttlMs) || ttlMs <= 0) throw new Error("Approval TTL must be a positive integer");

  const preview: Record<string, DesktopApprovalPreviewValue> = {};
  let previewTruncated = false;
  for (const field of APPROVAL_PREVIEW_FIELDS[input.toolName] ?? []) {
    const value = input.toolInput[field];
    if (typeof value === "number" || typeof value === "boolean") {
      preview[field] = value;
    } else if (typeof value === "string" && value.trim()) {
      const shown = APPROVAL_PREVIEW_PATH_FIELDS.has(field) ? basename(value) : value;
      const bounded = utf8Excerpt(shown, APPROVAL_PREVIEW_FIELD_BYTES);
      if (bounded !== shown) previewTruncated = true;
      preview[field] = bounded;
    }
  }
  const copy = approvalCopy(input.toolName, preview);
  const resourceRef = input.resourceRef ?? null;
  return {
    policy: DESKTOP_APPROVAL_POLICY,
    capability,
    operation: input.toolName,
    resourceRef,
    title: copy.title,
    decisionPrompt: copy.decisionPrompt,
    preview,
    previewTruncated,
    options: desktopApprovalOptions(input.toolName, resourceRef),
    defaultOptionId: DESKTOP_APPROVAL_DEFAULT_OPTION_ID,
    reason: input.policy.reason,
    requestedAtMs: input.nowMs,
    expiresAtMs: input.nowMs + ttlMs,
  };
}

export interface AcpPermissionOption {
  kind: string;
  optionId: string;
}

export interface AcpPermissionDecision {
  optionId: string;
  optionKind: string;
  acpResult: {
    outcome: {
      outcome: "selected";
      optionId: string;
    };
  };
  auditEvent: {
    type: "approval.resolved";
    policy: "desktop_high_trust" | "external_constrained";
    adapterId: string;
    requestId?: number | string;
    optionId: string;
    optionKind: string;
    automatic: true;
  };
}

export interface AcpPermissionRejection {
  acpError: {
    code: number;
    message: string;
  };
  auditEvent: {
    type: "approval.rejected";
    policy: "external_constrained";
    adapterId: string;
    requestId?: number | string;
    automatic: true;
    reason: string;
  };
}

export function resolveAcpPermission(input: {
  requestId?: number | string;
  options: AcpPermissionOption[];
}): AcpPermissionDecision {
  const selected =
    input.options.find((option) => option.kind === "allow_always") ??
    input.options.find((option) => option.kind === "allow_once") ??
    input.options[0] ??
    { kind: "fallback", optionId: "allow" };

  return {
    optionId: selected.optionId,
    optionKind: selected.kind,
    acpResult: {
      outcome: {
        outcome: "selected",
        optionId: selected.optionId,
      },
    },
    auditEvent: {
      type: "approval.resolved",
      policy: "desktop_high_trust",
      adapterId: "acp",
      requestId: input.requestId,
      optionId: selected.optionId,
      optionKind: selected.kind,
      automatic: true,
    },
  };
}

export function resolveExternalAcpPermission(input: {
  adapterId: string;
  requestId?: number | string;
  options: AcpPermissionOption[];
}): AcpPermissionDecision | AcpPermissionRejection {
  const selected =
    input.options.find((option) => option.kind === "allow_once") ??
    input.options.find((option) => /deny|reject|disallow/i.test(option.kind)) ??
    input.options.find((option) => option.kind !== "allow_always");

  if (!selected) {
    return {
      acpError: {
        code: -32001,
        message: "External adapter permission requires explicit user approval",
      },
      auditEvent: {
        type: "approval.rejected",
        policy: "external_constrained",
        adapterId: input.adapterId,
        requestId: input.requestId,
        automatic: true,
        reason: "no_non_permanent_option",
      },
    };
  }

  return {
    optionId: selected.optionId,
    optionKind: selected.kind,
    acpResult: {
      outcome: {
        outcome: "selected",
        optionId: selected.optionId,
      },
    },
    auditEvent: {
      type: "approval.resolved",
      policy: "external_constrained",
      adapterId: input.adapterId,
      requestId: input.requestId,
      optionId: selected.optionId,
      optionKind: selected.kind,
      automatic: true,
    },
  };
}
