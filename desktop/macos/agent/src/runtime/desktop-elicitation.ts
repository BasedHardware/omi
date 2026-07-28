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

  return {
    channel: "acp_permission",
    mode: "permission",
    adapterId: input.adapterId,
    externalSessionId: asNonEmptyString(params?.sessionId),
    title: `${input.agentLabel} needs permission`,
    prompt: title ?? `${input.agentLabel} wants to run a tool`,
    subject: subjectFromRawInput(toolCall?.rawInput),
    context: contextFromLocations(toolCall?.locations),
    options,
    allowsFreeText: false,
    recommendedDefault: recommended?.optionId ?? null,
  };
}

export type AcpPermissionClassification =
  | { decision: "auto"; optionId: string; reason: string }
  | { decision: "dispatch"; reason: string };

/**
 * Decide whether an ACP permission request may resolve without the user.
 *
 * Exactly one branch stays automatic: a one-time grant on a read-shaped tool.
 * Anything that mutates state, executes, fetches, or asks to be remembered goes
 * to the user, because a remembered grant outlives the turn that requested it.
 *
 * This replaces two prior behaviors that never reached a human — a blind
 * `allow_always` selection for the pi adapter, and a `-32001` rejection for
 * external adapters offering only permanent options.
 */
export function classifyAcpPermission(
  request: ElicitationRequest,
  toolKind: unknown,
): AcpPermissionClassification {
  const kind = typeof toolKind === "string" ? toolKind : "other";
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

/**
 * Normalize the Omi `ask_user` tool call. Omi defines this shape, so the only
 * defensive work is rejecting a call with no question.
 */
export function normalizeAskUser(input: AskUserArgs): ElicitationRequest | null {
  const args = asRecord(input.args);
  const question = asNonEmptyString(args?.question);
  if (!question) return null;

  const rawOptions = Array.isArray(args?.options) ? args.options : [];
  const options: ElicitationOption[] = [];
  for (const entry of rawOptions) {
    const label = typeof entry === "string" ? entry : asNonEmptyString(asRecord(entry)?.label);
    if (!label) continue;
    const optionId = asNonEmptyString(asRecord(entry)?.id) ?? label;
    options.push({ optionId, label, effect: "choice" });
  }

  return {
    channel: "omi_ask_user",
    mode: "question",
    adapterId: input.adapterId,
    externalSessionId: null,
    title: `${input.agentLabel} is asking`,
    prompt: question,
    subject: null,
    context: null,
    options,
    allowsFreeText: args?.allow_free_text !== false,
    recommendedDefault: null,
  };
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
  | { kind: "selected"; optionId: string }
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
    ? { kind: "selected", optionId: rejection.optionId }
    : { kind: "cancelled", reason };
}
