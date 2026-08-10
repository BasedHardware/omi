import type { ChatGenerationEvent } from "../stores/chat-generation-events-store";
import type { StoredChatMessage } from "../stores/chat-messages-store";

export interface AdmittedChatGeneration {
  readonly accountId: string;
  readonly stored: StoredChatMessage;
  readonly acceptedEvent: ChatGenerationEvent;
}

/** The next lane replaces this seam with the real streaming supervisor. */
export interface ChatGenerationSupervisor {
  onAdmitted(input: AdmittedChatGeneration): void;
}

/**
 * Deliberately emits no snapshot, delta, answer, or terminal frame. This lane
 * persists admission and then stops at the supervisor boundary.
 */
export const createStubChatGenerationSupervisor = (): ChatGenerationSupervisor =>
  Object.freeze({ onAdmitted: (_input: AdmittedChatGeneration): void => {} });
