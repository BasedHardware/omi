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
