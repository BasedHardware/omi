// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMCORE-008)
/**
 * HTTP write door for user-asserted STM notes — `POST /v1/stm-notes/ops`.
 *
 * Memories remains a read-only ratified domain (`POST /v1/memories/ops` stays
 * 422). This is a dedicated path, not an addition to `WRITABLE_DOMAINS`. A note
 * is a ledger write: the epoch fence and `assertAuthorizedLedgerWriteContext`
 * still apply. The note is never quality-gated or dropped.
 */

import type { Hono } from "hono";

import {
  MAX_WRITE_ENVELOPE_JSON_CODE_UNITS,
  WRITE_ERRORS,
  WRITE_ID_PATTERN,
  WRITE_REFUSALS,
} from "@omi-core/ratified-contracts/write/ops";
import type { WriteFenceCounter } from "../control/fence-counter";
import { writeFenceRefusalResponse } from "../control/fence-http";
import type { AccountControlProjectionStore } from "../control/projection-store";
import type { EntitlementProjectionReader } from "../control/settings-projection";
import { applyWriteFence } from "../control/write-fence-guard";
import type { DevPrincipal } from "../auth/dev-token";
import {
  WRITE_RUN_ID_HEADER,
  type WriteOpsCounter,
  type WriteOpsWireOutcome,
} from "../observability/write-ops-counter";
import type { StragglerTable } from "../stores/straggler-table";
import { exceedsFingerprintDepth, type WriteIdRegistry } from "../stores/write-id-registry";
import { sealUserAssertedStmNote } from "../../../core/stm/note";
import type { LocalMemoryFormation } from "../composition/memory-formation";

const JSON_HEADERS = Object.freeze({
  "cache-control": "no-store",
  "content-type": "application/json",
});

export const STM_NOTES_OPS_PATH = "/v1/stm-notes/ops";
const STM_NOTES_DOMAIN = "stm-notes";
const RECORD_ID_PATTERN = /^[\x21-\x7e]{1,256}$/;
const CLIENT_WRITE_REF_PATTERN = /^[\x21-\x7e]{1,256}$/;
const INTERNAL_BODY = JSON.stringify({ error: "internal_server_error" });

export interface StmNoteWriteEnvelope {
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
}

export interface StmNotesOpsRouteDependencies {
  readonly resolvePrincipal: (token: string) => DevPrincipal | null;
  readonly registry: WriteIdRegistry;
  readonly stragglers: StragglerTable;
  readonly fence: {
    readonly store: AccountControlProjectionStore;
    readonly entitlement: EntitlementProjectionReader;
    readonly counter: WriteFenceCounter;
  };
  readonly counter: WriteOpsCounter;
  readonly now: () => number;
  readonly formation: LocalMemoryFormation | null;
}

const fixedResponse = (body: string, status: number): Response =>
  new Response(body, { status, headers: JSON_HEADERS });

const bearerToken = (header: string | undefined): string | null => {
  if (typeof header !== "string") return null;
  const prefix = "Bearer ";
  if (!header.startsWith(prefix)) return null;
  const token = header.slice(prefix.length);
  return token.length > 0 ? token : null;
};

const hasExactKeys = (value: unknown, expected: readonly string[]): value is Record<string, unknown> => {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return false;
  const actual = Object.keys(value).sort();
  return actual.length === expected.length && [...expected].sort().every((key, index) => key === actual[index]);
};

const isStmNoteWriteEnvelope = (value: unknown): value is StmNoteWriteEnvelope => {
  if (!hasExactKeys(value, ["write_id", "account_epoch", "domain", "op"])) return false;
  if (typeof value.write_id !== "string" || !WRITE_ID_PATTERN.test(value.write_id)) return false;
  if (typeof value.account_epoch !== "number" || !Number.isSafeInteger(value.account_epoch)
    || value.account_epoch < 0) return false;
  if (value.domain !== STM_NOTES_DOMAIN) return false;
  const op = value.op;
  if (!hasExactKeys(op, ["op", "record_id", "content"]) || op.op !== "create") return false;
  if (typeof op.record_id !== "string" || !RECORD_ID_PATTERN.test(op.record_id)) return false;
  const content = op.content;
  if (!hasExactKeys(content, ["text", "client_write_ref"])) return false;
  if (typeof content.text !== "string") return false;
  if (content.client_write_ref !== null
    && (typeof content.client_write_ref !== "string" || !CLIENT_WRITE_REF_PATTERN.test(content.client_write_ref))) {
    return false;
  }
  return true;
};

export const parseStmNoteWriteEnvelopeJson = (raw: string): StmNoteWriteEnvelope | null => {
  if (typeof raw !== "string" || raw.length === 0 || raw.length > MAX_WRITE_ENVELOPE_JSON_CODE_UNITS) {
    return null;
  }
  try {
    const parsed: unknown = JSON.parse(raw);
    if (JSON.stringify(parsed) !== raw) return null;
    return isStmNoteWriteEnvelope(parsed) ? parsed : null;
  } catch {
    return null;
  }
};

const opFingerprint = (envelope: StmNoteWriteEnvelope): unknown => ({
  account_epoch: envelope.account_epoch,
  domain: envelope.domain,
  op: envelope.op,
});

export const registerStmNotesOpsRoutes = (app: Hono, deps: StmNotesOpsRouteDependencies): void => {
  const handler = async (context: {
    req: {
      header: (name: string) => string | undefined;
      text: () => Promise<string>;
    };
  }): Promise<Response> => {
    const runId = context.req.header(WRITE_RUN_ID_HEADER);
    const answer = (outcome: WriteOpsWireOutcome, response: Response): Response => {
      deps.counter.record(runId, outcome);
      return response;
    };

    const token = bearerToken(context.req.header("authorization"));
    const principal = token === null ? null : deps.resolvePrincipal(token);
    if (principal === null) {
      const refusal = WRITE_REFUSALS.authentication;
      return answer("authentication", fixedResponse(refusal.body, refusal.status));
    }

    let raw: string;
    try {
      raw = await context.req.text();
    } catch {
      return answer("validation", fixedResponse(WRITE_ERRORS.validation.body, WRITE_ERRORS.validation.status));
    }
    const envelope = parseStmNoteWriteEnvelopeJson(raw);
    if (envelope === null || exceedsFingerprintDepth(envelope.op)) {
      return answer("validation", fixedResponse(WRITE_ERRORS.validation.body, WRITE_ERRORS.validation.status));
    }

    const decision = applyWriteFence(
      {
        store: deps.fence.store,
        entitlement: deps.fence.entitlement,
        counter: deps.fence.counter,
      },
      { accountId: principal.uid, requestEpoch: envelope.account_epoch, runId },
    );
    if (!decision.admitted) {
      if (decision.evidence === "preserve_envelope") {
        deps.stragglers.preserve(principal.uid, {
          envelope_json: raw,
          write_id: envelope.write_id,
          account_epoch: envelope.account_epoch,
          retained_at_epoch_seconds: deps.now(),
        });
        deps.counter.recordPreservedEnvelope(runId);
      }
      return answer(decision.outcome, writeFenceRefusalResponse(decision));
    }

    const lookup = deps.registry.lookup(principal.uid, envelope.write_id, opFingerprint(envelope));
    if (lookup.kind === "reuse") {
      return answer(
        "write_id_reuse",
        fixedResponse(WRITE_ERRORS.write_id_reuse.body, WRITE_ERRORS.write_id_reuse.status),
      );
    }
    if (lookup.kind === "replay") {
      return answer("accepted_idempotent", fixedResponse(
        JSON.stringify({ applied: lookup.outcome, idempotent: true }),
        200,
      ));
    }

    const submittedAt = new Date(deps.now() * 1_000).toISOString();
    let note;
    try {
      note = sealUserAssertedStmNote({
        owner_account_id: principal.uid,
        write_id: envelope.write_id,
        content: envelope.op.content.text,
        metadata: {
          write_door: "http",
          client_write_ref: envelope.op.content.client_write_ref,
          submitted_at: submittedAt,
        },
      });
    } catch {
      return answer("validation", fixedResponse(WRITE_ERRORS.validation.body, WRITE_ERRORS.validation.status));
    }
    if (deps.formation !== null) {
      await deps.formation.ingestUserNote({
        note,
        account_epoch: envelope.account_epoch,
        now_epoch_seconds: deps.now(),
      });
    }
    const outcome = Object.freeze({
      record_id: envelope.op.record_id,
      revision: note.note_digest,
    });
    deps.registry.record({
      accountId: principal.uid,
      writeId: envelope.write_id,
      fingerprintOf: opFingerprint(envelope),
      accountEpoch: envelope.account_epoch,
      outcome,
    });
    return answer("accepted", fixedResponse(
      JSON.stringify({ applied: outcome, idempotent: false }),
      200,
    ));
  };

  const guarded = async (context: Parameters<typeof handler>[0]): Promise<Response> => {
    try {
      return await handler(context);
    } catch {
      deps.counter.recordInternalError(context.req.header(WRITE_RUN_ID_HEADER));
      return fixedResponse(INTERNAL_BODY, 500);
    }
  };

  app.post(STM_NOTES_OPS_PATH, guarded);
};
