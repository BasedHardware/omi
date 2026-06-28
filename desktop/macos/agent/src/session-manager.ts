/**
 * Session management logic extracted for testability.
 * The main index.ts module calls these functions to manage
 * the pre-warmed ACP session map.
 */

export interface SessionEntry {
  sessionId: string;
  cwd: string;
  model?: string;
}

export interface SessionMap {
  get(key: string): SessionEntry | undefined;
  set(key: string, entry: SessionEntry): void;
  delete(key: string): boolean;
  has(key: string): boolean;
  clear(): void;
}

/**
 * Determine which session to use for a query.
 * Returns the sessionId if a valid session exists, or null if a new one is needed.
 */
export function resolveSession(
  sessions: SessionMap,
  sessionKey: string,
  requestedCwd: string
): { sessionId: string; existing: SessionEntry } | null {
  const existing = sessions.get(sessionKey);
  if (!existing) return null;

  // If cwd changed, invalidate this specific session
  if (existing.cwd !== requestedCwd) {
    sessions.delete(sessionKey);
    return null;
  }

  return { sessionId: existing.sessionId, existing };
}

/**
 * Check if model needs updating on a reused session.
 */
export function needsModelUpdate(
  existing: SessionEntry | undefined,
  requestedModel: string | undefined
): boolean {
  if (!existing || !requestedModel) return false;
  return requestedModel !== existing.model;
}

/**
 * Determine which sessions need warming from a list of configs.
 * Returns only configs whose keys are not already in the session map.
 */
export function filterSessionsToWarm(
  sessions: SessionMap,
  configs: Array<{ key: string; model: string; systemPrompt?: string }>
): Array<{ key: string; model: string; systemPrompt?: string }> {
  return configs.filter((cfg) => !sessions.has(cfg.key));
}

/**
 * Get the correct session key for retry deletion.
 * This must be the sessionKey (map key), NOT the requestedModel.
 */
export function getRetryDeleteKey(sessionKey: string): string {
  return sessionKey;
}
