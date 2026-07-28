/**
 * Elicitation normalization.
 *
 * Two wire protocols ask the user a question mid-run:
 *
 *   - ACP `session/request_permission` (external adapters and pi): a fixed
 *     option list keyed by `optionId`. The response may only echo an option
 *     the agent offered, so free text is protocol-invalid here.
 *   - The Omi `ask_user` tool: an Omi-defined question with optional choices.
 *
 * They normalize into one `ElicitationRequest` so a single desktop surface can
 * render both, and so the answer can be routed back in each protocol's own
 * shape without the UI knowing which protocol it came from.
 *
 * This module is deliberately free of kernel and adapter imports: it is pure
 * translation plus the ACP auto-resolution rule, which keeps it directly
 * testable without a store or a subprocess.
 */

export type ElicitationChannel = "acp_permission" | "omi_ask_user";

/**
 * `permission` renders an approval card with no free-text field; `question`
 * renders choices plus an optional custom answer. The distinction is a protocol
 * fact, not a presentation preference: ACP permission responses cannot carry
 * arbitrary text.
 */
export type ElicitationMode = "permission" | "question";

export type ElicitationOptionEffect =
  | "allow_once"
  | "allow_always"
  | "reject_once"
  | "reject_always"
  | "choice";

export interface ElicitationOption {
  optionId: string;
  label: string;
  effect: ElicitationOptionEffect;
}

export interface ElicitationRequest {
  channel: ElicitationChannel;
  mode: ElicitationMode;
  adapterId: string;
  /** Session the request belongs to, as reported by the source protocol. */
  externalSessionId: string | null;
  /** Short dispatch title, e.g. "Claude Code wants to run a command". */
  title: string;
  /** The dispatch decision prompt: the question, or the action being approved. */
  prompt: string;
  /** Verbatim subject rendered monospace, e.g. the command or the file path. */
  subject: string | null;
  /** Where the action applies: working directory or affected file locations. */
  context: string | null;
  options: readonly ElicitationOption[];
  allowsFreeText: boolean;
  /**
   * Whether several options may be chosen at once. Always false for a
   * permission: an ACP response names exactly one `optionId`, so offering more
   * would build an answer the protocol cannot carry.
   */
  allowsMultiple: boolean;
  recommendedDefault: string | null;
}

/**
 * ACP tool kinds that neither mutate local state nor move data off the machine.
 * `fetch` is deliberately excluded: retrieving external data is network egress,
 * not a local read.
 */
const READ_SHAPED_TOOL_KINDS: ReadonlySet<string> = new Set(["read", "search", "think"]);

const PERMISSION_OPTION_EFFECTS: ReadonlySet<string> = new Set([
  "allow_once",
  "allow_always",
  "reject_once",
  "reject_always",
]);

function asRecord(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function asNonEmptyString(value: unknown): string | null {
  return typeof value === "string" && value.trim().length > 0 ? value : null;
}

function optionEffect(kind: unknown): ElicitationOptionEffect {
  return typeof kind === "string" && PERMISSION_OPTION_EFFECTS.has(kind)
    ? (kind as ElicitationOptionEffect)
    : "choice";
}

/**
 * Render `rawInput` as the verbatim subject line. Agents put the meaningful
 * payload under varying keys (`command`, `file_path`, `path`), so prefer those
 * and fall back to compact JSON rather than dropping the detail entirely — an
 * approval card that cannot say what it is approving is worse than a dense one.
 */
function subjectFromRawInput(rawInput: unknown): string | null {
  const record = asRecord(rawInput);
  if (!record) return asNonEmptyString(rawInput);
  for (const key of ["command", "cmd", "file_path", "filePath", "path", "query", "url"]) {
    const direct = asNonEmptyString(record[key]);
    if (direct) return direct;
  }
  const serialized = JSON.stringify(record);
  return serialized && serialized !== "{}" ? serialized : null;
}

function contextFromLocations(locations: unknown): string | null {
  if (!Array.isArray(locations)) return null;
  const paths = locations
    .map((entry) => asNonEmptyString(asRecord(entry)?.path))
    .filter((path): path is string => path !== null);
  return paths.length > 0 ? paths.join(", ") : null;
}

export interface AcpPermissionParams {
  adapterId: string;
  agentLabel: string;
  params: unknown;
}

/**
 * Normalize an ACP `session/request_permission` payload.
 *
 * Returns null when the payload carries no usable option, which is the one case
 * the caller cannot resolve: an ACP permission response may only name an
 * `optionId` the agent itself offered.
 */
export function normalizeAcpPermission(input: AcpPermissionParams): ElicitationRequest | null {
  const params = asRecord(input.params);
  const rawOptions = Array.isArray(params?.options) ? params.options : [];
  const options: ElicitationOption[] = [];
  for (const entry of rawOptions) {
    const record = asRecord(entry);
    const optionId = asNonEmptyString(record?.optionId);
    if (!optionId) continue;
    options.push({
      optionId,
      label: asNonEmptyString(record?.name) ?? optionId,
      effect: optionEffect(record?.kind),
    });
  }
  if (options.length === 0) return null;

  const toolCall = asRecord(params?.toolCall);
  const title = asNonEmptyString(toolCall?.title);
  const recommended = options.find((option) => option.effect === "allow_once");
  const subject = subjectFromRawInput(toolCall?.rawInput);
  const locations = contextFromLocations(toolCall?.locations);

  return {
    channel: "acp_permission",
    mode: "permission",
    adapterId: input.adapterId,
    externalSessionId: asNonEmptyString(params?.sessionId),
    title: `${input.agentLabel} needs permission`,
    prompt: title ?? `${input.agentLabel} wants to run a tool`,
    subject,
    // A file-write tool reports the same path as both its raw input and its
    // location. Rendering it twice adds nothing and reads as a bug, so the
    // location is kept only when it says something the subject does not.
    context: locations === subject ? null : locations,
    options,
    allowsFreeText: false,
    allowsMultiple: false,
    recommendedDefault: recommended?.optionId ?? null,
  };
}

export type AcpPermissionClassification =
  | { decision: "auto"; optionId: string; reason: string }
  | { decision: "dispatch"; reason: string };

/**
 * Tools whose entire effect is to put a question to the user.
 *
 * These are never gated. Asking the user is the consent mechanism, so routing
 * it through consent produces a permission card asking whether the agent may
 * ask a question — two cards for one question, and the first one is noise the
 * user cannot act on meaningfully.
 */
const USER_INTERACTION_TOOLS: ReadonlySet<string> = new Set(["ask_user"]);

/** Strip any MCP server prefix: `mcp__omi-tools__ask_user` → `ask_user`. */
function bareToolName(toolName: unknown): string | null {
  if (typeof toolName !== "string" || toolName.length === 0) return null;
  const segments = toolName.split("__").filter((segment) => segment.length > 0);
  return segments[segments.length - 1] ?? null;
}

export function isUserInteractionTool(toolName: unknown): boolean {
  const bare = bareToolName(toolName);
  return bare !== null && USER_INTERACTION_TOOLS.has(bare);
}

/** How long the tool relay waits for an executor before giving up on it. */
export const RELAY_TOOL_TIMEOUT_MS = 120_000;

/**
 * The relay deadline for one tool, or null when it must not have one.
 *
 * A tool whose whole job is to wait for a person has no deadline the relay can
 * choose. Two minutes is an ordinary pause for someone reading a question and
 * deciding, and expiring it throws away the answer they were in the middle of
 * giving: the card stays on screen, the user picks, and nothing is listening.
 *
 * Untimed is not unbounded. These end when the user answers or cancels, when
 * the turn is cancelled, or when the runtime restarts and terminalizes pending
 * dispatches — the contract elicitation already documents.
 */
export function relayToolTimeoutMs(toolName: unknown): number | null {
  return isUserInteractionTool(toolName) ? null : RELAY_TOOL_TIMEOUT_MS;
}

/**
 * Decide whether an ACP permission request may resolve without the user.
 *
 * Two branches stay automatic: putting a question to the user, which is the
 * consent mechanism and cannot itself sit behind consent, and a one-time grant
 * on a read-shaped tool. Anything that mutates state, executes, fetches, or
 * asks to be remembered goes to the user, because a remembered grant outlives
 * the turn that requested it.
 *
 * This replaces two prior behaviors that never reached a human — a blind
 * `allow_always` selection for the pi adapter, and a `-32001` rejection for
 * external adapters offering only permanent options.
 */
export function classifyAcpPermission(
  request: ElicitationRequest,
  toolKind: unknown,
  toolName?: unknown,
): AcpPermissionClassification {
  const kind = typeof toolKind === "string" ? toolKind : "other";

  if (isUserInteractionTool(toolName)) {
    // Prefer a one-time grant so the tool never accumulates a remembered one,
    // but any allow works: the effect being authorized is the question itself.
    const allow =
      request.options.find((option) => option.effect === "allow_once")
      ?? request.options.find((option) => option.effect === "allow_always");
    if (allow) {
      return {
        decision: "auto",
        optionId: allow.optionId,
        reason: "asking the user needs no permission to ask",
      };
    }
  }

  if (!READ_SHAPED_TOOL_KINDS.has(kind)) {
    return { decision: "dispatch", reason: `tool kind ${kind} is not read-shaped` };
  }
  const allowOnce = request.options.find((option) => option.effect === "allow_once");
  if (!allowOnce) {
    return { decision: "dispatch", reason: "read-shaped tool offered no one-time allow" };
  }
  return {
    decision: "auto",
    optionId: allowOnce.optionId,
    reason: `one-time allow on read-shaped tool kind ${kind}`,
  };
}

export interface AskUserArgs {
  adapterId: string;
  agentLabel: string;
  args: unknown;
}

/** Keys that hold a label when the model sends an object. Tried in order. */
const OPTION_LABEL_KEYS = ["label", "description", "title", "name", "text", "value"] as const;

/** Trailing markup a model leaves on a label, e.g. `"Other</item>"`. */
const TRAILING_MARKUP = /<\/[A-Za-z][\w-]*>\s*$/;

/**
 * Find the human-readable label inside whatever one option turned out to be.
 *
 * Models send options as plain strings, as objects keyed half a dozen
 * different ways, as JSON encoded into a string, and wrapped in arrays --
 * sometimes several of those at once. Enumerating shapes grew a special case
 * per bug report, so this looks for the first usable string anywhere inside
 * the value instead, and handles the next shape nobody has sent yet.
 */
function labelFrom(value: unknown, depth = 0): string | null {
  if (depth > 8) return null;

  if (typeof value === "string") {
    const trimmed = value.trim();
    if (!trimmed) return null;
    // A string that is really an encoded object; a label that merely starts
    // with a brace falls through to itself when the parse fails.
    if (trimmed.startsWith("{") || trimmed.startsWith("[")) {
      try {
        return labelFrom(JSON.parse(trimmed), depth + 1);
      } catch {
        return trimmed;
      }
    }
    return trimmed;
  }

  if (Array.isArray(value)) {
    for (const entry of value) {
      const label = labelFrom(entry, depth + 1);
      if (label) return label;
    }
    return null;
  }

  if (value && typeof value === "object") {
    const record = value as Record<string, unknown>;
    for (const key of OPTION_LABEL_KEYS) {
      const label = labelFrom(record[key], depth + 1);
      if (label) return label;
    }
    // Unknown key: any string the object carries beats dropping the option.
    for (const entry of Object.values(record)) {
      if (typeof entry !== "string") continue;
      const label = labelFrom(entry, depth + 1);
      if (label) return label;
    }
  }

  return null;
}

/**
 * One entry per option, however deeply the list was wrapped.
 *
 * Distinct from `labelFrom`: an array *of* options must become several
 * options, while an array *inside* one option is just where its label is
 * hiding.
 */
function optionEntries(value: unknown, depth = 0): unknown[] {
  if (!Array.isArray(value) || depth >= 8) return [value];
  return value.flatMap((entry) => optionEntries(entry, depth + 1));
}

/**
 * Runaway-payload guard, not a product limit. How many answers to offer is the
 * model's call; this only stops a malformed or looping call turning one
 * question into a list nobody can read. Enforced here rather than only in the
 * tool schema because flattening a nested list can produce more entries than
 * the call sent.
 */
export const ASK_USER_MAX_OPTIONS_PER_QUESTION = 32;

function normalizeAskUserOptions(rawOptions: unknown): ElicitationOption[] {
  if (!Array.isArray(rawOptions)) return [];
  const options: ElicitationOption[] = [];
  const seen = new Set<string>();
  for (const entry of optionEntries(rawOptions)) {
    if (options.length >= ASK_USER_MAX_OPTIONS_PER_QUESTION) break;
    const label = labelFrom(entry)?.replace(TRAILING_MARKUP, "").trim();
    if (!label) continue;
    const optionId = asNonEmptyString(asRecord(entry)?.id) ?? label;
    // Two identical ids would make the answer ambiguous, and a duplicate row is
    // not a choice the user can meaningfully make.
    if (seen.has(optionId)) continue;
    seen.add(optionId);
    options.push({ optionId, label, effect: "choice" });
  }
  return options;
}

/**
 * Normalize the Omi `ask_user` tool call into one request per question.
 *
 * One call carries the whole set of decisions, because a decision that needs
 * three answers is one moment for the user, not three round trips through the
 * model. Each question still becomes its own request, so the surface presents
 * them as a queue and each answer routes back independently.
 *
 * Omi defines this shape, so the only defensive work is dropping an entry with
 * no question rather than putting up a card that asks nothing.
 */
export function normalizeAskUser(input: AskUserArgs): ElicitationRequest[] {
  const args = asRecord(input.args);
  const rawQuestions = Array.isArray(args?.questions) ? args.questions : [];
  const requests: ElicitationRequest[] = [];

  for (const entry of rawQuestions) {
    const record = asRecord(entry);
    const question = asNonEmptyString(record?.question);
    if (!question) continue;
    requests.push({
      channel: "omi_ask_user",
      mode: "question",
      adapterId: input.adapterId,
      externalSessionId: null,
      title: `${input.agentLabel} is asking`,
      prompt: question,
      subject: null,
      context: null,
      options: normalizeAskUserOptions(record?.options),
      allowsFreeText: record?.allow_free_text !== false,
      // Only meaningful when there is a list to pick from; a multi-select with
      // no options is just a free-text question.
      allowsMultiple: record?.allow_multiple === true,
      recommendedDefault: null,
    });
  }

  return requests;
}

/**
 * The kernel dispatch kind an elicitation records as. Both kinds already exist
 * in `desktop_dispatches`, so no schema migration is required: an approval is
 * an `approval`, and a question with choices is a `routing_choice`.
 */
export function dispatchKindFor(request: ElicitationRequest): "approval" | "routing_choice" {
  return request.mode === "permission" ? "approval" : "routing_choice";
}

export type ElicitationOutcome =
  /**
   * One or more options the user chose. A permission always carries exactly
   * one, because that is all its protocol can answer with; a multi-select
   * question may carry several, in the order they appear on the card.
   */
  | { kind: "selected"; optionIds: readonly string[]; text?: string }
  | { kind: "answered"; text: string }
  | { kind: "cancelled"; reason: string };

/**
 * Asks a human and resolves when they answer.
 *
 * Deliberately has no timeout: the run stays in `waiting_approval` until the
 * user acts or the turn is cancelled. The one bound is process death — the
 * blocked protocol request does not survive a runtime restart, so the kernel
 * terminalizes pending dispatches at startup rather than leaving a card that
 * answers nothing.
 *
 * Injected rather than imported so adapters stay free of kernel dependencies.
 */
export type ElicitationResolver = (request: ElicitationRequest) => Promise<ElicitationOutcome>;

/**
 * The outcome to use when a request needs a human but none can be reached —
 * no resolver is installed, or the resolver itself failed.
 *
 * Fails closed. Choosing a rejection the agent offered is preferred over a bare
 * cancellation because it tells the agent the operation was refused rather than
 * that the turn went away. Never selects an allow: an unreachable user has not
 * consented to anything.
 */
export function failClosedOutcome(request: ElicitationRequest, reason: string): ElicitationOutcome {
  const rejection =
    request.options.find((option) => option.effect === "reject_once")
    ?? request.options.find((option) => option.effect === "reject_always");
  return rejection
    ? { kind: "selected", optionIds: [rejection.optionId] }
    : { kind: "cancelled", reason };
}
