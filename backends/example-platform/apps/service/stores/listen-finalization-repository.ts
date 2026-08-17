import { isProxy } from "node:util/types";

import type { AuthorizedLedgerWriteContext } from "../auth/authorized-context";
import type { ListenTranscriptSegment } from "./listen-store";

export const LISTEN_CAPTURE_OPEN_VERSION = "listen-capture-open-v1" as const;
export const LISTEN_CAPTURE_APPEND_VERSION = "listen-capture-append-v1" as const;
export const LISTEN_CAPTURE_INTERRUPT_VERSION = "listen-capture-interrupt-v1" as const;
export const LISTEN_CAPTURE_RESUME_VERSION = "listen-capture-resume-v1" as const;
export const LISTEN_CAPTURE_FINALIZE_VERSION = "listen-capture-finalize-v1" as const;

export interface ListenCaptureOpenRequest {
  readonly version: typeof LISTEN_CAPTURE_OPEN_VERSION;
  readonly session_id: string;
  readonly conversation_id: string;
  readonly client_conversation_id: string | null;
  readonly started_at: string;
  readonly source: string | null;
  readonly codec: string;
  readonly sample_rate: number;
  readonly channels: number;
}

export interface ListenCaptureAppendRequest {
  readonly version: typeof LISTEN_CAPTURE_APPEND_VERSION;
  readonly session_id: string;
  readonly segment: ListenTranscriptSegment;
  readonly appended_at: string;
}

export interface ListenCaptureFinalizeRequest {
  readonly version: typeof LISTEN_CAPTURE_FINALIZE_VERSION;
  readonly session_id: string;
  readonly terminal_status: "completed" | "entitlement_exhausted";
  readonly ended_at: string;
}

export interface ListenCaptureInterruptRequest {
  readonly version: typeof LISTEN_CAPTURE_INTERRUPT_VERSION;
  readonly session_id: string;
  readonly interrupted_at: string;
}

export interface ListenCaptureResumeRequest {
  readonly version: typeof LISTEN_CAPTURE_RESUME_VERSION;
  readonly session_id: string;
  readonly resumed_at: string;
}

export type ListenCaptureOpenOutcome = Readonly<{
  kind: "opened" | "replayed";
  session_id: string;
  conversation_id: string;
}>;

export type ListenCaptureAppendOutcome = Readonly<{
  kind: "appended" | "replayed";
  session_id: string;
  segment_id: string;
  ordinal: number;
}>;

export type ListenCaptureStateOutcome = Readonly<{
  kind: "interrupted" | "resumed" | "replayed";
  session_id: string;
  state_sequence: number;
}>;

export type ListenCaptureFinalizeOutcome = Readonly<{
  kind: "sealed" | "replayed";
  finalization_id: string;
  formation_work_id: string;
  transcript_digest: string;
  finalization_digest: string;
  segment_count: number;
}>;

export interface ListenFinalizationRepository {
  open(
    context: AuthorizedLedgerWriteContext,
    request: ListenCaptureOpenRequest,
  ): Promise<ListenCaptureOpenOutcome>;
  append(
    context: AuthorizedLedgerWriteContext,
    request: ListenCaptureAppendRequest,
  ): Promise<ListenCaptureAppendOutcome>;
  interrupt(
    context: AuthorizedLedgerWriteContext,
    request: ListenCaptureInterruptRequest,
  ): Promise<ListenCaptureStateOutcome>;
  resume(
    context: AuthorizedLedgerWriteContext,
    request: ListenCaptureResumeRequest,
  ): Promise<ListenCaptureStateOutcome>;
  finalize(
    context: AuthorizedLedgerWriteContext,
    request: ListenCaptureFinalizeRequest,
  ): Promise<ListenCaptureFinalizeOutcome>;
}

const TOKEN = /^[\x21-\x7e]{1,256}$/;
const SOURCE = /^[\x20-\x7e]{0,256}$/;
const MAX_SEGMENT_TEXT = 1_500;
const MAX_SEGMENT_OFFSET_SECONDS = 31 * 24 * 60 * 60;

const fail = (code: string): never => {
  throw new TypeError(`listen finalization repository ${code}`);
};

const exact = (value: unknown, keys: readonly string[], code: string): Record<string, unknown> => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype) fail(code);
  const actual = Reflect.ownKeys(value);
  const expected = [...keys].sort();
  if (actual.some((key) => typeof key !== "string") || actual.length !== expected.length
    || (actual as string[]).sort().some((key, index) => key !== expected[index])) fail(code);
  const output: Record<string, unknown> = {};
  for (const key of keys) {
    const descriptor = Object.getOwnPropertyDescriptor(value, key);
    if (!descriptor || !("value" in descriptor) || !descriptor.enumerable) fail(code);
    output[key] = descriptor.value;
  }
  return output;
};

const token = (value: unknown, code: string): string => {
  if (typeof value !== "string" || !TOKEN.test(value)) fail(code);
  return value;
};

const timestamp = (value: unknown, code: string): string => {
  const result = token(value, code);
  const millis = Date.parse(result);
  if (!Number.isFinite(millis)) fail(code);
  return new Date(millis).toISOString();
};

export const parseListenCaptureOpenRequest = (
  value: unknown,
): Readonly<ListenCaptureOpenRequest> => {
  const input = exact(value, [
    "version", "session_id", "conversation_id", "client_conversation_id", "started_at",
    "source", "codec", "sample_rate", "channels",
  ], "invalid_open");
  if (input["version"] !== LISTEN_CAPTURE_OPEN_VERSION) fail("invalid_open");
  const client = input["client_conversation_id"];
  const source = input["source"];
  if (client !== null) token(client, "invalid_open");
  if (source !== null && (typeof source !== "string" || !SOURCE.test(source))) fail("invalid_open");
  if (!Number.isSafeInteger(input["sample_rate"]) || (input["sample_rate"] as number) < 1
    || !Number.isSafeInteger(input["channels"]) || (input["channels"] as number) < 1) {
    fail("invalid_open");
  }
  return Object.freeze({
    version: LISTEN_CAPTURE_OPEN_VERSION,
    session_id: token(input["session_id"], "invalid_open"),
    conversation_id: token(input["conversation_id"], "invalid_open"),
    client_conversation_id: client as string | null,
    started_at: timestamp(input["started_at"], "invalid_open"),
    source: source as string | null,
    codec: token(input["codec"], "invalid_open"),
    sample_rate: input["sample_rate"] as number,
    channels: input["channels"] as number,
  });
};

export const parseListenCaptureAppendRequest = (
  value: unknown,
): Readonly<ListenCaptureAppendRequest> => {
  const input = exact(value, ["version", "session_id", "segment", "appended_at"], "invalid_append");
  if (input["version"] !== LISTEN_CAPTURE_APPEND_VERSION) fail("invalid_append");
  const segment = exact(input["segment"], ["id", "text", "is_user", "start", "end"], "invalid_segment");
  const text = segment["text"];
  if (typeof text !== "string" || text.length === 0 || text.length > MAX_SEGMENT_TEXT
    || typeof segment["is_user"] !== "boolean"
    || typeof segment["start"] !== "number" || !Number.isFinite(segment["start"])
    || typeof segment["end"] !== "number" || !Number.isFinite(segment["end"])
    || (segment["start"] as number) < 0
    || (segment["end"] as number) < (segment["start"] as number)
    || (segment["end"] as number) > MAX_SEGMENT_OFFSET_SECONDS) fail("invalid_segment");
  return Object.freeze({
    version: LISTEN_CAPTURE_APPEND_VERSION,
    session_id: token(input["session_id"], "invalid_append"),
    segment: Object.freeze({
      id: token(segment["id"], "invalid_segment"),
      text,
      is_user: segment["is_user"] as boolean,
      start: segment["start"] as number,
      end: segment["end"] as number,
    }),
    appended_at: timestamp(input["appended_at"], "invalid_append"),
  });
};

export const parseListenCaptureFinalizeRequest = (
  value: unknown,
): Readonly<ListenCaptureFinalizeRequest> => {
  const input = exact(value, ["version", "session_id", "terminal_status", "ended_at"], "invalid_finalize");
  if (input["version"] !== LISTEN_CAPTURE_FINALIZE_VERSION
    || (input["terminal_status"] !== "completed"
      && input["terminal_status"] !== "entitlement_exhausted")) fail("invalid_finalize");
  return Object.freeze({
    version: LISTEN_CAPTURE_FINALIZE_VERSION,
    session_id: token(input["session_id"], "invalid_finalize"),
    terminal_status: input["terminal_status"],
    ended_at: timestamp(input["ended_at"], "invalid_finalize"),
  });
};

export const parseListenCaptureInterruptRequest = (
  value: unknown,
): Readonly<ListenCaptureInterruptRequest> => {
  const input = exact(value, ["version", "session_id", "interrupted_at"], "invalid_interrupt");
  if (input["version"] !== LISTEN_CAPTURE_INTERRUPT_VERSION) fail("invalid_interrupt");
  return Object.freeze({
    version: LISTEN_CAPTURE_INTERRUPT_VERSION,
    session_id: token(input["session_id"], "invalid_interrupt"),
    interrupted_at: timestamp(input["interrupted_at"], "invalid_interrupt"),
  });
};

export const parseListenCaptureResumeRequest = (
  value: unknown,
): Readonly<ListenCaptureResumeRequest> => {
  const input = exact(value, ["version", "session_id", "resumed_at"], "invalid_resume");
  if (input["version"] !== LISTEN_CAPTURE_RESUME_VERSION) fail("invalid_resume");
  return Object.freeze({
    version: LISTEN_CAPTURE_RESUME_VERSION,
    session_id: token(input["session_id"], "invalid_resume"),
    resumed_at: timestamp(input["resumed_at"], "invalid_resume"),
  });
};
