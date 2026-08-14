import type { StagedChatAttachment } from "@omi-core/contracts";

/** Explicit development scanner identity. Never present this as a real product scanner. */
export const DEV_NOOP_SCANNER_ID = "dev-noop-scanner" as const;

/** Fail-closed scan budget. Callers inject a clock; this module never reads the wall clock. */
export const ATTACHMENT_SCAN_TIMEOUT_MS = 5_000;

export type ChatAttachmentScanState =
  | "staged"
  | "scanning"
  | "clean"
  | "rejected"
  | "timed_out"
  | "error"
  | "bound";

export type ChatAttachmentScanTerminal = "clean" | "rejected" | "timed_out" | "error";

export type ChatAttachmentScanClock = {
  now(): number;
};

export type ChatTrayAttachment = StagedChatAttachment & {
  readonly scanState: ChatAttachmentScanState;
  readonly scannerId: typeof DEV_NOOP_SCANNER_ID;
};

export type ChatAttachmentScanner = {
  readonly identity: typeof DEV_NOOP_SCANNER_ID;
  scan(attachment: StagedChatAttachment): Promise<ChatAttachmentScanTerminal>;
};

export function isAdmissibleForBind(state: ChatAttachmentScanState): boolean {
  return state === "clean";
}

export function canRetryAttachmentScan(state: ChatAttachmentScanState): boolean {
  return state === "rejected" || state === "timed_out" || state === "error";
}

export function canRemoveTrayAttachment(state: ChatAttachmentScanState): boolean {
  return state !== "bound";
}

export function asScanTerminal(value: unknown): ChatAttachmentScanTerminal | null {
  if (
    value === "clean" ||
    value === "rejected" ||
    value === "timed_out" ||
    value === "error"
  ) {
    return value;
  }
  return null;
}

export function toTrayAttachment(
  staged: StagedChatAttachment,
  scanState: ChatAttachmentScanState,
): ChatTrayAttachment {
  return {
    id: staged.id,
    mimeType: staged.mimeType,
    sizeBytes: staged.sizeBytes,
    expiresAt: staged.expiresAt,
    state: "staged",
    scanState,
    scannerId: DEV_NOOP_SCANNER_ID,
  };
}

export function attachmentsAreAdmissibleForSend(
  attachments: readonly ChatTrayAttachment[],
): boolean {
  return attachments.every((attachment) => isAdmissibleForBind(attachment.scanState));
}

/**
 * Development scanner. The default outcome is `clean` without claiming any
 * real file-checking product. A caller-supplied clock can force `timed_out`
 * after ATTACHMENT_SCAN_TIMEOUT_MS.
 */
export function createDevNoopAttachmentScanner(options?: {
  clock?: ChatAttachmentScanClock;
  startedAt?: number;
  outcome?: ChatAttachmentScanTerminal;
}): ChatAttachmentScanner {
  return {
    identity: DEV_NOOP_SCANNER_ID,
    async scan() {
      const clock = options?.clock;
      const startedAt = options?.startedAt;
      if (clock !== undefined && startedAt !== undefined) {
        if (clock.now() - startedAt >= ATTACHMENT_SCAN_TIMEOUT_MS) {
          return "timed_out";
        }
      }
      return options?.outcome ?? "clean";
    },
  };
}
