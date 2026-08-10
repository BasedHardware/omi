import type { ChatAttachmentMetadata } from "../stores/chat-messages-store";

export interface ChatGenerationAttachmentDescriptor extends ChatAttachmentMetadata {
  /** Detached retained bytes, or null after the content-retention boundary. */
  readonly content: Uint8Array | null;
}

/** Generation consults attachment content without knowing its storage adapter. */
export interface ChatAttachmentContentPort {
  loadForGeneration(input: {
    readonly accountId: string;
    readonly messageId: string;
    readonly attachments: readonly ChatAttachmentMetadata[];
    readonly nowEpochMilliseconds: number;
  }): readonly ChatGenerationAttachmentDescriptor[];
}
