// JSON lines protocol between Swift app and Node.js agent runtime
// Extended from agent protocol with authentication message types

// === Swift → Bridge (stdin) ===

export type ProtocolVersion = 1 | 2;

export interface ProtocolEnvelope {
  /** v1 omits this field; v2 sends 2. */
  protocolVersion?: ProtocolVersion;
  /** v1 `id` maps to requestId during the compatibility window. */
  requestId?: string;
  clientId?: string;
  /** Signed-in Omi/Firebase uid used to scope persisted runtime state. */
  ownerId?: string;
}

export interface CanonicalCorrelation {
  /** Canonical Omi IDs are optional until the Phase 1 kernel owns them. */
  sessionId?: string;
  runId?: string;
  attemptId?: string;
  eventId?: string;
}

export interface QueryMessage extends ProtocolEnvelope, CanonicalCorrelation {
  type: "query";
  id?: string;
  prompt: string;
  systemPrompt: string;
  adapterId?: string;
  surfaceKind?: string;
  externalRefKind?: string;
  externalRefId?: string;
  legacyClientScope?: string;
  legacySessionKey?: string;
  legacyAdapterSessionId?: string;
  sessionKey?: string;
  cwd?: string;
  mode?: "ask" | "act";
  model?: string;
  resume?: string;
  imageBase64?: string;
}

export interface ToolResultMessage {
  type: "tool_result";
  callId: string;
  result: string;
  requestId?: string;
  clientId?: string;
  protocolVersion?: ProtocolVersion;
}

export interface ControlToolRequestMessage extends ProtocolEnvelope {
  type: "control_tool";
  name: string;
  input: Record<string, unknown>;
}

export interface DirectControlToolRequestMessage extends ProtocolEnvelope {
  type: "direct_control_tool";
  name: string;
  input: Record<string, unknown>;
}

export interface StopMessage {
  type: "stop";
}

export interface InterruptMessage extends ProtocolEnvelope, CanonicalCorrelation {
  type: "interrupt";
}

export interface InvalidateSessionMessage extends ProtocolEnvelope {
  type: "invalidate_session";
  sessionKey: string;
}

/** Swift tells the bridge which auth method the user chose */
export interface AuthenticateMessage {
  type: "authenticate";
  methodId: string;
}

export interface WarmupSessionConfig {
  key: string;
  model?: string;
  systemPrompt?: string;
}

/** Swift tells the bridge to pre-create an ACP session in the background */
export interface WarmupMessage extends ProtocolEnvelope {
  type: "warmup";
  cwd?: string;
  model?: string;       // backward compat
  models?: string[];    // backward compat
  sessions?: WarmupSessionConfig[];  // new: per-session config with system prompts
}

/** Swift pushes a refreshed Firebase ID token to the bridge (piMono mode) */
export interface RefreshTokenMessage {
  type: "refresh_token";
  token: string;
  ownerId?: string;
}

export type InboundMessage =
  | QueryMessage
  | ToolResultMessage
  | ControlToolRequestMessage
  | DirectControlToolRequestMessage
  | StopMessage
  | InterruptMessage
  | InvalidateSessionMessage
  | AuthenticateMessage
  | WarmupMessage
  | RefreshTokenMessage;

// === Bridge → Swift (stdout) ===

export interface OutboundEnvelope {
  protocolVersion?: ProtocolVersion;
  requestId?: string;
  clientId?: string;
}

export interface QueryScopedOutbound extends OutboundEnvelope, CanonicalCorrelation {
  adapterSessionId?: string;
  legacyAdapterSessionId?: string;
}

export interface InitMessage extends OutboundEnvelope {
  type: "init";
  sessionId: string;
  agentControlTools: string[];
}

export interface TextDeltaMessage extends QueryScopedOutbound {
  type: "text_delta";
  text: string;
}

export interface ToolUseMessage extends QueryScopedOutbound {
  type: "tool_use";
  callId: string;
  name: string;
  input: Record<string, unknown>;
}

export interface ResultMessage extends QueryScopedOutbound {
  type: "result";
  text: string;
  sessionId: string;
  terminalStatus?: "succeeded" | "failed" | "cancelled";
  failure?: RuntimeFailurePayload;
  costUsd?: number;
  inputTokens?: number;
  outputTokens?: number;
  cacheReadTokens?: number;
  cacheWriteTokens?: number;
}

export interface RuntimeFailurePayload {
  code: string;
  userMessage: string;
  technicalMessage?: string;
  source?: string;
  adapterId?: string;
  provider?: string;
  retryable?: boolean;
}

export interface ToolActivityMessage extends QueryScopedOutbound {
  type: "tool_activity";
  name: string;
  status: "started" | "completed" | "failed";
  toolUseId?: string;
  input?: Record<string, unknown>;
}

export interface ToolResultDisplayMessage extends QueryScopedOutbound {
  type: "tool_result_display";
  toolUseId: string;
  name: string;
  output: string;
}

export interface ThinkingDeltaMessage extends QueryScopedOutbound {
  type: "thinking_delta";
  text: string;
}

export interface ErrorMessage extends QueryScopedOutbound {
  type: "error";
  message: string;
  failure?: RuntimeFailurePayload;
}

/** Sent when ACP requires user authentication (OAuth) */
export interface AuthRequiredMessage {
  type: "auth_required";
  methods: AuthMethod[];
  authUrl?: string;
}

export interface AuthMethod {
  id: string;
  type: "agent_auth" | "env_var" | "terminal";
  displayName?: string;
  args?: string[];
  env?: Record<string, string>;
}

/** Sent after successful authentication */
export interface AuthSuccessMessage {
  type: "auth_success";
}

export interface CancelAckMessage extends QueryScopedOutbound {
  type: "cancel_ack";
  accepted: boolean;
  dispatchAttempted: boolean;
  adapterAcknowledged: boolean;
}

export interface ControlToolResultMessage extends OutboundEnvelope {
  type: "control_tool_result";
  name: string;
  result: string;
}

export type OutboundMessage =
  | InitMessage
  | TextDeltaMessage
  | ToolUseMessage
  | ToolActivityMessage
  | ToolResultDisplayMessage
  | ThinkingDeltaMessage
  | ResultMessage
  | ErrorMessage
  | AuthRequiredMessage
  | AuthSuccessMessage
  | CancelAckMessage
  | ControlToolResultMessage;

export function requestIdFor(message: ProtocolEnvelope & { id?: string }): string | undefined {
  return message.requestId ?? message.id;
}
