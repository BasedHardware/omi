import type { StoredChatMessage } from "../stores/chat-messages-store";

export interface ChatGenerationContextSource {
  load(input: {
    readonly accountId: string;
    readonly admitted: StoredChatMessage;
  }): Promise<readonly string[]>;
}

/**
 * Deliberately empty adapter. The memory lane can later implement this port;
 * generation does not read or model memory storage itself.
 */
export const createEmptyChatGenerationContextSource = (): ChatGenerationContextSource =>
  Object.freeze({ load: async (): Promise<readonly string[]> => Object.freeze([]) });
