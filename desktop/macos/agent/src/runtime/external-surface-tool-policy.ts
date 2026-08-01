export interface ExternalSurfaceToolPolicyInput {
  toolName: string;
  toolInput: Record<string, unknown>;
  originatingPrompt: string;
  precedingAssistantText?: string | null;
}

export type ExternalSurfaceToolPolicyDecision =
  | {
    action: "execute";
    toolName: string;
    toolInput: Record<string, unknown>;
    recoveredFromDelegation: boolean;
  }
  | {
    action: "reject";
    code:
      | "permission_target_rejected"
      | "permission_route_rejected"
      | "permission_request_not_authorized"
      | "pill_management_intent_required"
      | "sql_write_rejected";
    message: string;
  };

const PERMISSION_TYPES: ReadonlyArray<{ type: string; phrases: readonly string[] }> = [
  {
    type: "screen_recording",
    phrases: [
      "screen recording",
      "screen-recording",
      "screen share",
      "screen-share",
      "screen sharing",
      "screen-sharing",
    ],
  },
  { type: "microphone", phrases: ["microphone", "mic permission", "microphone access"] },
  { type: "notifications", phrases: ["notification permission", "notifications permission", "omi notifications"] },
  { type: "accessibility", phrases: ["accessibility permission", "accessibility access"] },
  { type: "automation", phrases: ["automation permission", "automation access"] },
  { type: "full_disk_access", phrases: ["full disk access"] },
];

const PERMISSION_CAPABILITY_SUBJECTS = new Set([
  "screen recording",
  "screen recording permission",
  "screen recording access",
  "screen share",
  "screen-share",
  "screen sharing",
  "screen-sharing",
  "screen share permission",
  "screen sharing permission",
  "screen share access",
  "screen sharing access",
  "microphone",
  "microphone permission",
  "microphone access",
  "mic",
  "mic permission",
  "notifications",
  "notification permission",
  "notifications permission",
  "accessibility",
  "accessibility permission",
  "accessibility access",
  "automation",
  "automation permission",
  "automation access",
  "full disk access",
  "full disk access permission",
]);

const DIRECTED_PROVIDER_TARGETS = [
  { provider: "openclaw" as const, pattern: "(?:open\\s*claw|open\\s*cloud)" },
  { provider: "hermes" as const, pattern: "hermes" },
  { provider: "codex" as const, pattern: "codex" },
] as const;
const DIRECTED_PROVIDER_ACTION = "(?:ask|tell|ping|message|use|run|try|start|spawn|delegate(?:\\s+to)?|have|let|send|make)";

/**
 * External surfaces propose tools; this policy owns the semantic safety rewrite
 * before any capability or invocation ledger row is minted.
 */
export function routeExternalSurfaceTool(
  input: ExternalSurfaceToolPolicyInput,
): ExternalSurfaceToolPolicyDecision {
  if (input.toolName === "execute_sql") {
    const query = textField(input.toolInput, "query");
    if (query && !isReadOnlySqlStatement(query)) {
      return {
        action: "reject",
        code: "sql_write_rejected",
        message: "The agent SQL capability is read-only; mutations require a separately authorized structured tool",
      };
    }
    return {
      action: "execute",
      toolName: input.toolName,
      toolInput: { ...input.toolInput, read_only: true },
      recoveredFromDelegation: false,
    };
  }
  if (input.toolName === "check_permission_status" || input.toolName === "request_permission") {
    const rawType = textField(input.toolInput, "type");
    const type = normalizedPermissionType(rawType);
    if (!type && !(input.toolName === "check_permission_status" && !rawType)) {
      return {
        action: "reject",
        code: "permission_route_rejected",
        message: "Permission tools require one supported Omi permission type",
      };
    }
    if (
      hasExplicitExternalPermissionTarget("", input.originatingPrompt, input.toolInput)
      || hasExplicitExternalPermissionTarget("", input.precedingAssistantText ?? "", {})
    ) {
      return {
        action: "reject",
        code: "permission_target_rejected",
        message: "Omi can only check or request permissions for the Omi app itself",
      };
    }
    if (
      input.toolName === "request_permission"
      && !hasPermissionRequestAuthority(type ?? "", input.originatingPrompt, input.precedingAssistantText ?? "")
    ) {
      return {
        action: "reject",
        code: "permission_request_not_authorized",
        message: "Opening a macOS permission prompt requires an explicit current user request or affirmation",
      };
    }
    return {
      action: "execute",
      toolName: input.toolName,
      toolInput: type ? { type } : {},
      recoveredFromDelegation: false,
    };
  }
  if (input.toolName === "set_desktop_attention_override" && !hasExplicitPillManagementIntent(input.originatingPrompt)) {
    return {
      action: "reject",
      code: "pill_management_intent_required",
      message: "Dismissing or restoring a desktop agent pill requires explicit current-turn pill-management intent",
    };
  }
  if (input.toolName !== "spawn_agent") {
    return { action: "execute", toolName: input.toolName, toolInput: input.toolInput, recoveredFromDelegation: false };
  }

  const toolInput = constrainSpawnProviderToCurrentUserIntent(input.toolInput, input.originatingPrompt);
  const objective = textField(toolInput, "objective") || textField(toolInput, "brief");
  const permission = permissionRequest(objective);
  if (!permission) {
    if (mentionsPermissionCapability(objective)) {
      return {
        action: "reject",
        code: "permission_route_rejected",
        message: "Permission work must use a direct native permission tool with an explicit check or request action",
      };
    }
    return { action: "execute", toolName: input.toolName, toolInput, recoveredFromDelegation: false };
  }
  if (
    hasExplicitExternalPermissionTarget(objective, input.originatingPrompt, toolInput)
    || hasExplicitExternalPermissionTarget("", input.precedingAssistantText ?? "", {})
  ) {
    return {
      action: "reject",
      code: "permission_target_rejected",
      message: "Omi can only check or request permissions for the Omi app itself",
    };
  }
  if (
    permission.toolName === "request_permission"
    && !hasPermissionRequestAuthority(permission.type, input.originatingPrompt, input.precedingAssistantText ?? "")
  ) {
    return {
      action: "reject",
      code: "permission_request_not_authorized",
      message: "Opening a macOS permission prompt requires an explicit current user request or affirmation",
    };
  }
  return {
    action: "execute",
    toolName: permission.toolName,
    toolInput: { type: permission.type },
    recoveredFromDelegation: true,
  };
}

/**
 * A realtime model may propose a local provider, but choosing a user's local
 * Hermes/OpenClaw credential boundary is not model authority. Only the current
 * user utterance may select it. Everything else stays on the regular Omi
 * managed-agent path, including a model-invented or stale provider field.
 */
function constrainSpawnProviderToCurrentUserIntent(
  toolInput: Record<string, unknown>,
  originatingPrompt: string,
): Record<string, unknown> {
  const selectedProvider = directedProviderSelectedByUser(originatingPrompt);
  if (selectedProvider) return { ...toolInput, provider: selectedProvider };

  const suppliedProvider = textField(toolInput, "provider");
  if (suppliedProvider !== "openclaw" && suppliedProvider !== "hermes" && suppliedProvider !== "codex") return toolInput;

  const { provider: _, ...defaultOmiInput } = toolInput;
  return defaultOmiInput;
}

function directedProviderSelectedByUser(prompt: string): "openclaw" | "hermes" | "codex" | null {
  const normalized = prompt.toLowerCase();
  const selected = DIRECTED_PROVIDER_TARGETS.flatMap(({ provider, pattern }) => {
    const target = `(?:the\\s+)?${pattern}(?:\\s+agent)?`;
    const positive = new RegExp(
      `(?:\\b${DIRECTED_PROVIDER_ACTION}\\s+${target}\\b|\\b(?:with|via|using|in)\\s+${target}\\b|^\\s*${pattern}\\s*(?::|,|—|-))`,
    );
    const negated = new RegExp(`\\b(?:don't|do not|never)\\s+${DIRECTED_PROVIDER_ACTION}\\s+${target}\\b`);
    return positive.test(normalized) && !negated.test(normalized) ? [provider] : [];
  });
  return selected.length === 1 ? selected[0]! : null;
}

function normalizedPermissionType(value: string): string | null {
  const normalized = value.toLowerCase().replaceAll("-", "_").replaceAll(" ", "_");
  if (PERMISSION_TYPES.some(({ type }) => type === normalized)) return normalized;
  if (normalized === "screen_share" || normalized === "screen_sharing") return "screen_recording";
  return null;
}

function hasPermissionRequestAuthority(
  type: string,
  originatingPrompt: string,
  precedingAssistantText: string,
): boolean {
  const permission = PERMISSION_TYPES.find((candidate) => candidate.type === type);
  if (!permission) return false;
  const prompt = originatingPrompt.toLowerCase().trim();
  const namesPermission = permission.phrases.some((phrase) => prompt.includes(phrase))
    || prompt.includes(type.replaceAll("_", " "));
  const explicitAction = /\b(?:request|grant|allow|enable|give|open|turn on)\b/.test(prompt);
  if (namesPermission && explicitAction) return true;

  const affirmative = /^(?:yes|yeah|yep|sure|ok|okay|please do|do it|go ahead|grant it|allow it)\b/.test(prompt);
  const preceding = precedingAssistantText.toLowerCase();
  const precedingPermissionTypes = PERMISSION_TYPES.filter((candidate) =>
    candidate.phrases.some((phrase) => preceding.includes(phrase))
      || preceding.includes(candidate.type.replaceAll("_", " ")),
  ).map((candidate) => candidate.type);
  const precedingIsPermissionRequest = precedingPermissionTypes.length === 1
    && precedingPermissionTypes[0] === type
    && !hasExplicitExternalPermissionTarget("", preceding, {})
    && /\b(?:request|grant|allow|enable|open|permission|access)\b/.test(preceding);
  if (!precedingIsPermissionRequest) return false;
  if (affirmative) return true;

  // A direct anaphoric imperative is meaningful only when the immediately
  // preceding assistant turn identified one concrete permission. This accepts
  // natural replies such as "request it" without broadening generic requests.
  return /\b(?:request|grant|allow|enable|open)\b/.test(prompt)
    && /\b(?:it|that|the (?:permission|access)|permissions?)\b/.test(prompt);
}

/**
 * Agent SQL is a read-only manifest capability. Strip strings, quoted
 * identifiers, and comments before looking for mutating CTEs so harmless
 * narrative values such as `SELECT 'DELETE'` do not become false positives.
 */
export function isReadOnlySqlStatement(query: string): boolean {
  const normalized = sqlForKeywordScan(query).trim().toUpperCase();
  if (!/^(?:SELECT|WITH)\b/.test(normalized)) return false;
  return !/\b(?:INSERT|UPDATE|DELETE|REPLACE)\b/.test(normalized);
}

function sqlForKeywordScan(query: string): string {
  let result = "";
  for (let index = 0; index < query.length;) {
    const character = query[index];
    const next = query[index + 1];
    if (character === "-" && next === "-") {
      index += 2;
      while (index < query.length && query[index] !== "\n") index += 1;
      result += " ";
      continue;
    }
    if (character === "/" && next === "*") {
      index += 2;
      while (index < query.length && !(query[index] === "*" && query[index + 1] === "/")) index += 1;
      index = Math.min(query.length, index + 2);
      result += " ";
      continue;
    }
    const closing = character === "[" ? "]"
      : character === "'" || character === "\"" || character === "`" ? character
        : null;
    if (closing) {
      index += 1;
      while (index < query.length) {
        if (query[index] === closing) {
          if (query[index + 1] === closing) {
            index += 2;
            continue;
          }
          index += 1;
          break;
        }
        index += 1;
      }
      result += " ";
      continue;
    }
    result += character;
    index += 1;
  }
  return result;
}

export function hasExplicitPillManagementIntent(prompt: string): boolean {
  const normalized = prompt.toLowerCase();
  const target = /\b(?:pill|agent pill|background agent|floating agent|agent card)\b/.test(normalized);
  const action = /\b(?:dismiss|hide|clear|remove|close|unhide|restore|show|reopen)\b/.test(normalized);
  return target && action;
}

function permissionRequest(text: string): { toolName: "check_permission_status" | "request_permission"; type: string } | null {
  const normalized = text.toLowerCase();
  const permission = PERMISSION_TYPES.find(({ phrases }) => phrases.some((phrase) => normalized.includes(phrase)));
  if (!permission) return null;
  const words = new Set(normalized.split(/[^a-z0-9]+/).filter(Boolean));
  if (["check", "status", "granted"].some((word) => words.has(word))) {
    return { toolName: "check_permission_status", type: permission.type };
  }
  if (["request", "grant", "allow", "enable", "give"].some((word) => words.has(word))) {
    return { toolName: "request_permission", type: permission.type };
  }
  return null;
}

function mentionsPermissionCapability(text: string): boolean {
  const normalized = text.toLowerCase();
  return PERMISSION_TYPES.some(({ phrases }) => phrases.some((phrase) => normalized.includes(phrase)));
}

function hasExplicitExternalPermissionTarget(
  objective: string,
  originatingPrompt: string,
  toolInput: Record<string, unknown>,
): boolean {
  for (const key of ["target", "target_app", "app", "application", "bundle_id", "bundleId"]) {
    const target = textField(toolInput, key);
    if (target) return !isLocalPermissionTarget(target);
  }
  for (const narrative of [originatingPrompt, objective]) {
    const normalized = narrative.toLowerCase();
    const candidates = [
      ...captures(normalized, /\b([a-z0-9._-]+(?:\s+[a-z0-9._-]+)?)['’]s\s+(?:screen recording|screen[- ]share(?:ing)?|microphone|mic|notifications?|accessibility|automation|full disk access)\b/g),
      ...captures(normalized, /\b([a-z0-9._-]+(?:\s+[a-z0-9._-]+)?)\s+needs\s+(?:screen recording|screen[- ]share(?:ing)?|microphone|mic|notifications?|accessibility|automation|full disk access)\b/g),
      ...captures(normalized, /\b(?:screen recording|screen[- ]share(?:ing)?|microphone|mic|notifications?|accessibility|automation|full disk access)(?:\s+permissions?|\s+access)?\s+for\s+([a-z0-9._ -]+?)(?:[?.!,]|$)/g),
      ...captures(normalized, /\b(?:grant|allow|enable|give|check)\s+([a-z0-9._-]+(?:\s+[a-z0-9._-]+)?)\s+(?:screen recording|screen[- ]share(?:ing)?|microphone|mic|notifications?|accessibility|automation|full disk access)\b/g),
    ];
    for (const candidate of candidates) {
      const cleaned = normalizeTarget(candidate);
      if (!cleaned || PERMISSION_CAPABILITY_SUBJECTS.has(cleaned)) continue;
      if (!isLocalPermissionTarget(cleaned)) return true;
    }
  }
  return false;
}

function captures(text: string, pattern: RegExp): string[] {
  return [...text.matchAll(pattern)].map((match) => match[1] ?? "");
}

function isLocalPermissionTarget(value: string): boolean {
  const normalized = normalizeTarget(value);
  const words = new Set(normalized.split(/[^a-z0-9]+/).filter(Boolean));
  return words.has("omi") || normalized.startsWith("com.omi.")
    || normalized === "this app" || normalized === "this application";
}

function normalizeTarget(value: string): string {
  return value.toLowerCase().trim().replace(/^[^a-z0-9]+|[^a-z0-9.]+$/g, "");
}

function textField(input: Record<string, unknown>, key: string): string {
  const value = input[key];
  return typeof value === "string" ? value.trim() : "";
}
