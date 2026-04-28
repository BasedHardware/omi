/**
 * Nooto Apps (a.k.a. Plugins / Integrations).
 *
 * Apps are backend-managed extensions users can enable to re-summarize
 * conversations with a custom prompt, expose chat personas, or trigger
 * external integrations. The desktop client only needs to browse, toggle,
 * and render the server-computed results — nothing runs locally.
 *
 * Field names mirror the backend JSON (snake_case).
 */

export interface ExternalIntegration {
  /**
   * Where to send users to start the OAuth / setup flow when the backend's
   * /v1/apps/enable rejects with "App setup is not completed". The plugin's
   * own auth route appends ?uid=<caller-uid> and 302s to the IdP.
   */
  app_home_url?: string | null;
  setup_completed_url?: string | null;
  chat_tools_manifest_url?: string | null;
  webhook_url?: string | null;
  triggers_on?: string | null;
  auth_steps?: Array<{ name: string; url: string }> | null;
}

export interface ChatTool {
  /** Plugin-prefixed name (e.g. `jira_update_issue_status`). When picking a
   *  writeback target we match by suffix so this stays generic across plugins. */
  name: string;
  description: string;
  /** Full URL to POST tool input to (plugin origin + `/tools/...`). */
  endpoint: string;
  method?: string;
  parameters?: unknown;
  auth_required?: boolean;
  status_message?: string | null;
}

export interface OmiApp {
  id: string;
  name: string;
  author: string;
  description: string;
  image: string;
  category: string;
  capabilities: string[];
  approved: boolean;
  enabled: boolean;
  private?: boolean;
  deleted?: boolean;
  is_paid?: boolean;
  price?: number | null;
  installs?: number;
  rating_avg?: number | null;
  rating_count?: number;
  status?: string;
  external_integration?: ExternalIntegration | null;
  chat_tools?: ChatTool[] | null;
}

export interface AppResponse {
  id: number;
  app_id?: string | null;
  content: string;
}

export const CAPABILITY = {
  chat: "chat",
  persona: "persona",
  memories: "memories",
  external: "external_integration",
  proactive: "proactive_notification",
} as const;

export function worksWithMemories(app: OmiApp): boolean {
  return app.capabilities?.includes(CAPABILITY.memories) ?? false;
}

export function worksWithChat(app: OmiApp): boolean {
  return (
    app.capabilities?.includes(CAPABILITY.chat) ||
    app.capabilities?.includes(CAPABILITY.persona)
  );
}

export function worksExternally(app: OmiApp): boolean {
  return app.capabilities?.includes(CAPABILITY.external) ?? false;
}

export const CAPABILITY_LABELS: Record<string, string> = {
  [CAPABILITY.chat]: "Chat",
  [CAPABILITY.persona]: "Persona",
  [CAPABILITY.memories]: "Memories",
  [CAPABILITY.external]: "Integration",
  [CAPABILITY.proactive]: "Notifications",
};
