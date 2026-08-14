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
  readonly scannerId: string;
};

const SCAN_STATES: ReadonlySet<ChatAttachmentScanState> = new Set([
  "staged",
  "scanning",
  "clean",
  "rejected",
  "timed_out",
  "error",
  "bound",
]);

const SCANNER_ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._-]{0,64}$/u;

export function isChatAttachmentScanState(value: unknown): value is ChatAttachmentScanState {
  return typeof value === "string" && SCAN_STATES.has(value as ChatAttachmentScanState);
}

export function scannerIdFromWire(value: unknown): string {
  return typeof value === "string" && SCANNER_ID_PATTERN.test(value) ? value : DEV_NOOP_SCANNER_ID;
}

/** Read platform upload/bind scan extras. Unknown states stay null (fail-closed). */
export function scanMetadataFromWire(value: unknown): {
  readonly scanState: ChatAttachmentScanState | null;
  readonly scannerId: string;
} {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return { scanState: null, scannerId: DEV_NOOP_SCANNER_ID };
  }
  const item = value as Record<string, unknown>;
  return {
    scanState: isChatAttachmentScanState(item["scanState"]) ? item["scanState"] : null,
    scannerId: scannerIdFromWire(item["scannerId"]),
  };
}

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
  scannerId: string = DEV_NOOP_SCANNER_ID,
): ChatTrayAttachment {
  return {
    id: staged.id,
    mimeType: staged.mimeType,
    sizeBytes: staged.sizeBytes,
    expiresAt: staged.expiresAt,
    state: "staged",
    scanState,
    scannerId: scannerIdFromWire(scannerId),
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
