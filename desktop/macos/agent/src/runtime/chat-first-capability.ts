/**
 * The chat-first rollout is sampled by Swift once per app session from the
 * server-owned workflow-control response.  This module deliberately contains
 * no persistence: process restart, owner replacement, an absent projection,
 * and every non-main surface are all capability-off.
 */
export interface ChatFirstCapabilityProjection {
  chatFirstUi: boolean;
  controlGeneration: number;
}

export interface ChatFirstProjectionContext {
  surfaceKind?: string;
  chatFirstUi?: boolean;
  controlGeneration?: number | null;
}

export interface EffectiveChatFirstCapability {
  chatFirstUi: boolean;
  controlGeneration: number | null;
}

export function effectiveChatFirstCapability(
  projection: ChatFirstProjectionContext | undefined,
): EffectiveChatFirstCapability {
  const generation = projection?.controlGeneration;
  const enabled = projection?.chatFirstUi === true
    && projection?.surfaceKind === "main_chat"
    && Number.isSafeInteger(generation)
    && (generation ?? -1) >= 0;
  return {
    chatFirstUi: enabled,
    controlGeneration: enabled ? generation! : null,
  };
}

/** One predicate shared by snapshots, run admission, and the MCP child. */
export function isChatFirstMainChat(projection: ChatFirstProjectionContext | undefined): boolean {
  return effectiveChatFirstCapability(projection).chatFirstUi;
}
