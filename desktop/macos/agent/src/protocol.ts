// JSON lines protocol between Swift app and Node.js agent runtime
// Extended from agent protocol with authentication message types

// === Swift → Bridge (stdin) ===

export const PROTOCOL_VERSION = 2 as const;
export type ProtocolVersion = typeof PROTOCOL_VERSION;

export interface ProtocolEnvelope {
  protocolVersion: ProtocolVersion;
  requestId: string;
  clientId: string;
  /** Signed-in Omi/Firebase uid used to scope persisted runtime state. */
  ownerId?: string;
}

export interface CanonicalCorrelation {
  sessionId?: string;
  runId?: string;
  attemptId?: string;
  eventId?: string;
}

export interface QueryMessage extends ProtocolEnvelope, CanonicalCorrelation {
  type: "query";
  prompt: string;
  systemPrompt: string;
  adapterId?: string;
  surfaceKind: string;
  externalRefKind: string;
  externalRefId: string;
  cwd?: string;
  mode?: "ask" | "act";
  model?: string;
  imageBase64?: string;
  attachmentMetadataJson?: string;
  surfaceContextJson?: string;
}

export interface ToolResultMessage {
  type: "tool_result";
  callId: string;
  result: string;
  protocolVersion: ProtocolVersion;
  requestId: string;
  clientId: string;
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
  surfaceKind: string;
  externalRefKind: string;
  externalRefId: string;
}

export interface ClearOwnerStateMessage extends ProtocolEnvelope {
  type: "clear_owner_state";
}

export interface ImportLegacyMainChatSessionsMessage extends ProtocolEnvelope {
  type: "import_legacy_main_chat_sessions";
  entries: Array<{ chatId: string; agentSessionId: string }>;
}

export interface ImportConversationTurnsMessage extends ProtocolEnvelope {
  type: "import_conversation_turns";
  surfaceKind: string;
  externalRefKind: string;
  externalRefId: string;
  turns: Array<{
    role?: string;
    content?: string;
    surfaceKind?: string;
    createdAtMs?: number;
    metadataJson?: string;
  }>;
}

export interface MergeFloatingChatIntoMainChatMessage extends ProtocolEnvelope {
  type: "merge_floating_chat_into_main_chat";
  chatId?: string;
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
  model?: string;
  models?: string[];
  sessions?: WarmupSessionConfig[];
}

/** Swift pushes a refreshed Firebase ID token to the bridge (piMono mode) */
export interface RefreshTokenMessage {
  type: "refresh_token";
  token: string;
  ownerId?: string;
}

export interface RecordSurfaceTurnMessage extends ProtocolEnvelope {
  type: "record_surface_turn";
  surfaceKind: string;
  externalRefKind: string;
  externalRefId: string;
  userText: string;
  assistantText: string;
  origin: string;
  interrupted?: boolean;
  idempotencyKey?: string;
}

export interface GetVoiceSeedContextMessage extends ProtocolEnvelope {
  type: "get_voice_seed_context";
  conversationId?: string;
  surfaceKind?: string;
  externalRefKind?: string;
  externalRefId?: string;
}

export interface ClearOwnerSurfaceStateMessage extends ProtocolEnvelope {
  type: "clear_owner_surface_state";
  chatId?: string;
}

export interface GetKernelTurnTailMessage extends ProtocolEnvelope {
  type: "get_kernel_turn_tail";
  limit?: number;
  chatId?: string;
}

export interface ProjectCrossSurfaceTurnMessage extends ProtocolEnvelope {
  type: "project_cross_surface_turn";
  surfaceKind: string;
  externalRefKind: string;
  externalRefId: string;
  userText: string;
  assistantText: string;
  origin: string;
  idempotencyKey?: string;
}

export type InboundMessage =
  | QueryMessage
  | ToolResultMessage
  | ControlToolRequestMessage
  | DirectControlToolRequestMessage
  | StopMessage
  | InterruptMessage
  | InvalidateSessionMessage
  | ClearOwnerStateMessage
  | ImportLegacyMainChatSessionsMessage
  | ImportConversationTurnsMessage
  | MergeFloatingChatIntoMainChatMessage
  | RecordSurfaceTurnMessage
  | GetVoiceSeedContextMessage
  | ClearOwnerSurfaceStateMessage
  | GetKernelTurnTailMessage
  | ProjectCrossSurfaceTurnMessage
  | AuthenticateMessage
  | WarmupMessage
  | RefreshTokenMessage;

// === Bridge → Swift (stdout) ===

export interface OutboundEnvelope {
  protocolVersion: ProtocolVersion;
  requestId?: string;
  clientId?: string;
}

export interface QueryScopedOutbound extends OutboundEnvelope, CanonicalCorrelation {
  adapterSessionId?: string;
}

export interface InitMessage {
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

export interface ToolCancelMessage extends QueryScopedOutbound {
  type: "tool_cancel";
  callId: string;
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
  artifacts?: SerializedArtifact[];
  completionDeltaArtifacts?: SerializedArtifact[];
}

export interface SerializedArtifact {
  artifactId: string;
  sessionId: string;
  runId: string | null;
  attemptId: string | null;
  kind: string;
  role: string;
  uri: string;
  displayName: string | null;
  mimeType: string | null;
  contentHash: string | null;
  sizeBytes: number | null;
  lifecycleState: string;
  lifecycleUpdatedAtMs: number | null;
  metadata: Record<string, unknown>;
  createdAtMs: number;
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

export interface TurnRecordedMessage extends OutboundEnvelope {
  type: "turn_recorded";
  conversationId: string;
  surfaceKind: string;
  externalRefKind: string;
  externalRefId: string;
  userText: string;
  assistantText: string;
  origin: string;
  interrupted: boolean;
  idempotencyKey?: string;
  userTurnId?: string;
  assistantTurnId?: string;
}

export interface VoiceSeedContextMessage extends OutboundEnvelope {
  type: "voice_seed_context";
  conversationId: string;
  context: string;
}

export interface KernelTurnTailMessage extends OutboundEnvelope {
  type: "kernel_turn_tail";
  conversationId: string;
  turns: Array<{
    role: string;
    content: string;
    surfaceKind: string;
    createdAtMs: number;
    metadataJson: string;
    origin?: string;
  }>;
}

export type OutboundMessage =
  | InitMessage
  | TextDeltaMessage
  | ToolUseMessage
  | ToolCancelMessage
  | ToolActivityMessage
  | ToolResultDisplayMessage
  | ThinkingDeltaMessage
  | ResultMessage
  | ErrorMessage
  | AuthRequiredMessage
  | AuthSuccessMessage
  | CancelAckMessage
  | ControlToolResultMessage
  | TurnRecordedMessage
  | VoiceSeedContextMessage
  | KernelTurnTailMessage;

type OutboundWithEnvelope = Exclude<OutboundMessage, InitMessage | AuthRequiredMessage | AuthSuccessMessage>;

type DraftEnvelope<T extends OutboundWithEnvelope> = Omit<T, "protocolVersion"> & Partial<Pick<T, "protocolVersion">>;

/** Outbound payload before correlation / envelope enrichment (adapters, transport internals). */
export type OutboundMessageDraft =
  | InitMessage
  | AuthRequiredMessage
  | AuthSuccessMessage
  | DraftEnvelope<TextDeltaMessage>
  | DraftEnvelope<ToolUseMessage>
  | DraftEnvelope<ToolCancelMessage>
  | DraftEnvelope<ToolActivityMessage>
  | DraftEnvelope<ToolResultDisplayMessage>
  | DraftEnvelope<ThinkingDeltaMessage>
  | DraftEnvelope<ResultMessage>
  | DraftEnvelope<ErrorMessage>
  | DraftEnvelope<CancelAckMessage>
  | DraftEnvelope<ControlToolResultMessage>
  | DraftEnvelope<TurnRecordedMessage>
  | DraftEnvelope<VoiceSeedContextMessage>
  | DraftEnvelope<KernelTurnTailMessage>;

export function ensureOutboundProtocolVersion(message: OutboundMessageDraft): OutboundMessage {
  if (message.type === "init" || message.type === "auth_required" || message.type === "auth_success") {
    return message;
  }
  if ("protocolVersion" in message && message.protocolVersion === PROTOCOL_VERSION) {
    return message as OutboundMessage;
  }
  return { ...message, protocolVersion: PROTOCOL_VERSION } as OutboundMessage;
}
