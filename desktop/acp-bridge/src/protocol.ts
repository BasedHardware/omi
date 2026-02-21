// JSON lines protocol between Swift app and Node.js ACP bridge
// Extended from agent-bridge protocol with authentication message types

// === Swift → Bridge (stdin) ===

export interface QueryMessage {
  type: "query";
  id: string;
  prompt: string;
  systemPrompt: string;
  cwd?: string;
  mode?: "ask" | "act";
  model?: string;
}

export interface ToolResultMessage {
  type: "tool_result";
  callId: string;
  result: string;
}

export interface StopMessage {
  type: "stop";
}

export interface InterruptMessage {
  type: "interrupt";
}

/** Swift tells the bridge which auth method the user chose */
export interface AuthenticateMessage {
  type: "authenticate";
  methodId: string;
}

/** Swift tells the bridge to pre-create an ACP session in the background */
export interface WarmupMessage {
  type: "warmup";
  cwd?: string;
  model?: string;
  models?: string[];
}

export type InboundMessage =
  | QueryMessage
  | ToolResultMessage
  | StopMessage
  | InterruptMessage
  | AuthenticateMessage
  | WarmupMessage;

// === Bridge → Swift (stdout) ===

export interface InitMessage {
  type: "init";
  sessionId: string;
}

export interface TextDeltaMessage {
  type: "text_delta";
  text: string;
}

export interface ToolUseMessage {
  type: "tool_use";
  callId: string;
  name: string;
  input: Record<string, unknown>;
}

export interface ResultMessage {
  type: "result";
  text: string;
  sessionId: string;
  costUsd?: number;
}

export interface ToolActivityMessage {
  type: "tool_activity";
  name: string;
  status: "started" | "completed";
  toolUseId?: string;
  input?: Record<string, unknown>;
}

export interface ToolResultDisplayMessage {
  type: "tool_result_display";
  toolUseId: string;
  name: string;
  output: string;
}

export interface ThinkingDeltaMessage {
  type: "thinking_delta";
  text: string;
}

export interface ErrorMessage {
  type: "error";
  message: string;
}

/** Sent when ACP requires user authentication (OAuth) */
export interface AuthRequiredMessage {
  type: "auth_required";
  methods: AuthMethod[];
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
  | AuthSuccessMessage;
