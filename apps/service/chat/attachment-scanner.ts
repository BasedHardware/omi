// domain-pending(DIV-CHAT-ATTACH-001)

/** Explicit dev scanner identity; never claims antivirus coverage. */
export const DEV_NOOP_SCANNER_ID = "dev-noop-scanner" as const;

export const ATTACHMENT_SCAN_TIMEOUT_MS = 5_000 as const;

export type AttachmentScanState =
  | "staged"
  | "scanning"
  | "clean"
  | "rejected"
  | "timed_out"
  | "error"
  | "bound";

export type AttachmentScanTerminalState = "clean" | "rejected" | "timed_out" | "error";

export interface AttachmentScanClock {
  readonly now: () => number;
}

export interface AttachmentScanInput {
  readonly scannerId: typeof DEV_NOOP_SCANNER_ID;
  readonly state: AttachmentScanState;
  readonly scanningStartedAt: number | null;
  readonly stagedAt: number;
}

export interface AttachmentScanTransition {
  readonly state: AttachmentScanState;
  readonly scanningStartedAt: number | null;
}

export interface AttachmentScanOptions {
  readonly clock: AttachmentScanClock;
  readonly timeoutMs?: number;
  /** Test-only fault injection; production noop scanner never rejects. */
  readonly forceOutcome?: AttachmentScanTerminalState;
}

const isFailedTerminal = (state: AttachmentScanState): state is Exclude<AttachmentScanTerminalState, "clean"> =>
  state === "rejected" || state === "timed_out" || state === "error";

/** Begin or resume scanning from staged or a failed terminal state. */
export const beginAttachmentScan = (
  input: AttachmentScanInput,
  options: AttachmentScanOptions,
): AttachmentScanTransition => {
  if (input.scannerId !== DEV_NOOP_SCANNER_ID) {
    throw new TypeError("unsupported attachment scanner");
  }
  if (input.state === "bound") {
    throw new TypeError("bound attachments are not scannable");
  }
  if (input.state !== "staged" && !isFailedTerminal(input.state) && input.state !== "clean") {
    throw new TypeError("attachment is not scannable");
  }
  const now = options.clock.now();
  return Object.freeze({ state: "scanning", scanningStartedAt: now });
};

/** Advance an in-flight scan; idempotent for terminal states. */
export const advanceAttachmentScan = (
  input: AttachmentScanInput,
  options: AttachmentScanOptions,
): AttachmentScanTransition => {
  if (input.scannerId !== DEV_NOOP_SCANNER_ID) {
    throw new TypeError("unsupported attachment scanner");
  }
  if (input.state === "bound") {
    throw new TypeError("bound attachments are not scannable");
  }
  if (input.state === "clean" || isFailedTerminal(input.state)) {
    return Object.freeze({
      state: input.state,
      scanningStartedAt: input.scanningStartedAt,
    });
  }
  if (input.state === "staged") return beginAttachmentScan(input, options);
  const startedAt = input.scanningStartedAt;
  if (startedAt === null || !Number.isSafeInteger(startedAt)) {
    return Object.freeze({ state: "error", scanningStartedAt: null });
  }
  const timeoutMs = options.timeoutMs ?? ATTACHMENT_SCAN_TIMEOUT_MS;
  const now = options.clock.now();
  if (now - startedAt >= timeoutMs) {
    return Object.freeze({ state: "timed_out", scanningStartedAt: startedAt });
  }
  if (options.forceOutcome !== undefined) {
    return Object.freeze({ state: options.forceOutcome, scanningStartedAt: startedAt });
  }
  return Object.freeze({ state: "clean", scanningStartedAt: startedAt });
};

export const attachmentScanAdmissible = (state: AttachmentScanState): boolean => state === "clean";

export const attachmentScanVisibleState = (
  state: AttachmentScanState,
): AttachmentScanState => state;
