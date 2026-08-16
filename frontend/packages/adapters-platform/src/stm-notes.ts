/**
 * The client half of `POST /v1/stm-notes/ops` — the HTTP write door for a
 * user-asserted fact.
 *
 * This is a dedicated path. Memories stays read-only (`POST /v1/memories/ops`
 * remains 422) and `stm-notes` is not a `WRITABLE_DOMAINS` member, so the
 * generic `buildWriteOpEnvelope` / `writeOpsPath` pair cannot carry it. The
 * envelope grammar matches the server's `parseStmNoteWriteEnvelopeJson`:
 * compact JSON, exact keys, `write_door` stamped server-side as `"http"`.
 *
 * A note is never quality-gated here. Empty or control-character content
 * fails on the server seal and comes back as validation — that is well-formed
 * refusal, not a filter on the user's words.
 */

import type { HttpClient, HttpResponse, WriteFailure } from "@omi-core/contracts";
import {
  isTrustedWriteAccepted,
  mintWriteId,
} from "@omi-core/ratified-contracts/write/ops";

import type { AccountEpochProvider, MutableAccountEpochProvider } from "./account-epoch.js";
import { PLATFORM_TASKS_READ_PATH } from "./tasks.js";
import { classifyWriteOpsResponse, isControlUnavailable } from "./write-ops.js";

export const STM_NOTES_OPS_PATH = "/v1/stm-notes/ops";
export const STM_NOTES_DOMAIN = "stm-notes";

const RECORD_ID_PATTERN = /^[\x21-\x7e]{1,256}$/;
const CLIENT_WRITE_REF_PATTERN = /^[\x21-\x7e]{1,256}$/;

export type StmNoteWriteEnvelope = {
  readonly write_id: string;
  readonly account_epoch: number;
  readonly domain: typeof STM_NOTES_DOMAIN;
  readonly op: {
    readonly op: "create";
    readonly record_id: string;
    readonly content: {
      readonly text: string;
      readonly client_write_ref: string | null;
    };
  };
};

export type StmNoteSendResult =
  | { readonly ok: true; readonly recordId: string; readonly revision: string | null }
  | { readonly ok: false; readonly failure: WriteFailure };

const unclassified = (detail: string): StmNoteSendResult => ({
  ok: false,
  failure: { kind: "retryable", unclassified: true, detail },
});

/**
 * D3 rides the account epoch on the tasks READ body as `accountEpoch`. The
 * synthesized memories contract has no such field, and adding one would be a
 * ratified bump this lane is not authorized to make. This observes the value
 * that already exists rather than inventing a second epoch wire.
 *
 * Returns the provider's current epoch after the observation attempt. `null`
 * stays `null` — this never stamps zero.
 */
export async function observeAccountEpochFromTasksRead(
  http: HttpClient,
  epochs: MutableAccountEpochProvider,
): Promise<number | null> {
  const response = await http.request("GET", `${PLATFORM_TASKS_READ_PATH}?limit=1`);
  if (response.status === 200 && response.json !== null && typeof response.json === "object") {
    const epoch = (response.json as { accountEpoch?: unknown }).accountEpoch;
    epochs.observeAccountEpoch(epoch);
  }
  return epochs.currentAccountEpoch();
}

export function buildStmNoteCreateEnvelope(input: {
  readonly writeId: string;
  readonly accountEpoch: number;
  readonly recordId: string;
  readonly text: string;
  readonly clientWriteRef: string | null;
}): StmNoteWriteEnvelope | null {
  if (typeof input.writeId !== "string" || input.writeId.length !== 64) return null;
  if (!/^[0-9a-f]{64}$/.test(input.writeId)) return null;
  if (!Number.isSafeInteger(input.accountEpoch) || input.accountEpoch < 0) return null;
  if (!RECORD_ID_PATTERN.test(input.recordId)) return null;
  if (typeof input.text !== "string" || input.text.length === 0) return null;
  if (input.clientWriteRef !== null && !CLIENT_WRITE_REF_PATTERN.test(input.clientWriteRef)) {
    return null;
  }
  return {
    write_id: input.writeId,
    account_epoch: input.accountEpoch,
    domain: STM_NOTES_DOMAIN,
    op: {
      op: "create",
      record_id: input.recordId,
      content: {
        text: input.text,
        client_write_ref: input.clientWriteRef,
      },
    },
  };
}

export async function sendUserAssertedStmNote(
  http: HttpClient,
  input: {
    readonly text: string;
    readonly accountEpoch: number;
    readonly entropy: Uint8Array;
    readonly clientWriteRef?: string | null;
  },
): Promise<StmNoteSendResult> {
  const writeId = mintWriteId(input.entropy);
  if (writeId === null) {
    return unclassified("stm note write id could not be minted from the supplied entropy");
  }
  const envelope = buildStmNoteCreateEnvelope({
    writeId,
    accountEpoch: input.accountEpoch,
    recordId: writeId,
    text: input.text,
    clientWriteRef: input.clientWriteRef ?? null,
  });
  if (envelope === null) {
    return unclassified("stm note envelope is unsendable");
  }

  let response: HttpResponse;
  try {
    response = await http.request("POST", STM_NOTES_OPS_PATH, envelope);
  } catch (error) {
    return { ok: false, failure: { kind: "retryable", detail: `stm note transport: ${String(error)}` } };
  }

  if (response.status === 200) {
    if (!isTrustedWriteAccepted(response.json)) {
      return unclassified("stm note accepted an op with an unreadable body");
    }
    return {
      ok: true,
      recordId: response.json.applied.record_id,
      revision: response.json.applied.revision,
    };
  }

  if (response.text === undefined) {
    return unclassified(`stm note response ${response.status} carried no raw body`);
  }

  if (isControlUnavailable(response)) {
    return { ok: false, failure: { kind: "retryable", detail: "control unavailable" } };
  }

  const failure = classifyWriteOpsResponse(response, "stm-notes");
  if (failure === null) {
    return unclassified(`stm note status ${response.status} classified as success`);
  }
  return { ok: false, failure };
}
