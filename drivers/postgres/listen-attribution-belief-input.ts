import { isProxy } from "node:util/types";

import { sha256CanonicalContent } from "../../core/retrieve/content-digest";
import type { AuthorizedLedgerWriteContext } from "../../apps/service/auth/authorized-context";
import {
  defineAcceptedFormationBeliefSource,
  defineListenAttributionBeliefInputRepository,
  materializeStoredListenAttributionBeliefInput,
  parseListenAttributionBeliefInputSet,
  parseStoredListenAttributionBeliefInput,
  type AcceptedFormationBeliefSource,
  type ListenAttributionBeliefInputRepository,
  type ListenAttributionBeliefInputSet,
  type StoredListenAttributionBeliefInput,
} from "../../apps/service/listen/attribution-belief-input-source";
import {
  parseStagedFormationWorkInput,
  type StagedFormationWorkInput,
} from "../../apps/service/workers/formation-work-input-repository";
import type { CheckedOutPostgresConnection, PostgresTransactionPool } from "./connection";
import {
  PostgresRepositoryError,
  withAuthorizedSerializableConnectionTransaction,
  type PostgresTransactionObservability,
} from "./transaction";

interface FormationInputRow extends Record<string, unknown> {
  readonly input_version: string;
  readonly staged_input_id: string;
  readonly account_id: string;
  readonly job_id: string;
  readonly account_epoch: number | string | bigint;
  readonly accepted_work_digest: string;
  readonly input_frontier: string;
  readonly input_digest: string;
  readonly execution_contract_digest: string;
  readonly snapshot_digest: string;
  readonly snapshot_json: unknown;
  readonly stage_request_digest: string;
  readonly content_hash: string;
}

interface BeliefInputRow extends Record<string, unknown> {
  readonly input_version: string;
  readonly account_id: string;
  readonly account_epoch: number | string | bigint;
  readonly formation_work_id: string;
  readonly source_snapshot_digest: string;
  readonly set_digest: string;
  readonly input_count: number | string | bigint;
  readonly input_ordinal: number | string | bigint;
  readonly input_ref: string;
  readonly input_digest: string;
  readonly graph_frontier: string;
  readonly stage_request_digest: string;
  readonly input_json: unknown;
  readonly content_hash: string;
}

const FORMATION_KEYS = [
  "input_version", "staged_input_id", "account_id", "job_id", "account_epoch",
  "accepted_work_digest", "input_frontier", "input_digest", "execution_contract_digest",
  "snapshot_digest", "snapshot_json", "stage_request_digest", "content_hash",
] as const;
const BELIEF_KEYS = [
  "input_version", "account_id", "account_epoch", "formation_work_id",
  "source_snapshot_digest", "set_digest", "input_count", "input_ordinal",
  "input_ref", "input_digest", "graph_frontier", "stage_request_digest",
  "input_json", "content_hash",
] as const;

const exactRow = (value: unknown, expected: readonly string[]): Record<string, unknown> => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype) {
    throw new PostgresRepositoryError("persistence_failed");
  }
  const actual = Reflect.ownKeys(value);
  const wanted = [...expected].sort();
  if (actual.some((key) => typeof key !== "string") || actual.length !== wanted.length
    || (actual as string[]).sort().some((key, index) => key !== wanted[index])) {
    throw new PostgresRepositoryError("persistence_failed");
  }
  const output: Record<string, unknown> = {};
  for (const key of wanted) {
    const descriptor = Object.getOwnPropertyDescriptor(value, key);
    if (!descriptor || !descriptor.enumerable || !("value" in descriptor)) {
      throw new PostgresRepositoryError("persistence_failed");
    }
    output[key] = descriptor.value;
  }
  return output;
};

const integer = (value: unknown): number => {
  if (typeof value !== "number" && typeof value !== "string" && typeof value !== "bigint") {
    throw new PostgresRepositoryError("persistence_failed");
  }
  if (typeof value === "string" && !/^(?:0|[1-9][0-9]*)$/.test(value)) {
    throw new PostgresRepositoryError("persistence_failed");
  }
  const result = Number(value);
  if (!Number.isSafeInteger(result) || result < 0) {
    throw new PostgresRepositoryError("persistence_failed");
  }
  return result;
};

const formationContentHash = (input: StagedFormationWorkInput): string => sha256CanonicalContent({
  contract_version: "formation-work-staged-input-content-v1",
  staged_input: input,
});

const parseFormationRow = (row: FormationInputRow): StagedFormationWorkInput => {
  const values = exactRow(row, FORMATION_KEYS);
  let input: StagedFormationWorkInput;
  try {
    input = parseStagedFormationWorkInput({
      version: values["input_version"],
      staged_input_id: values["staged_input_id"],
      owner_account_id: values["account_id"],
      job_id: values["job_id"],
      account_epoch: integer(values["account_epoch"]),
      accepted_work_digest: values["accepted_work_digest"],
      input_frontier: values["input_frontier"],
      input_digest: values["input_digest"],
      execution_contract_digest: values["execution_contract_digest"],
      snapshot_digest: values["snapshot_digest"],
      snapshot: values["snapshot_json"],
      stage_request_digest: values["stage_request_digest"],
    });
  } catch {
    throw new PostgresRepositoryError("persistence_failed");
  }
  if (values["content_hash"] !== formationContentHash(input)) {
    throw new PostgresRepositoryError("persistence_failed");
  }
  return input;
};

const recordContentHash = (record: StoredListenAttributionBeliefInput): string =>
  sha256CanonicalContent({
    contract_version: "stored-listen-attribution-belief-input-content-v1",
    record,
  });

const parseBeliefRow = (row: BeliefInputRow): StoredListenAttributionBeliefInput => {
  const values = exactRow(row, BELIEF_KEYS);
  let record: StoredListenAttributionBeliefInput;
  try {
    record = parseStoredListenAttributionBeliefInput({
      version: values["input_version"],
      owner_account_id: values["account_id"],
      account_epoch: integer(values["account_epoch"]),
      formation_work_id: values["formation_work_id"],
      source_snapshot_digest: values["source_snapshot_digest"],
      set_digest: values["set_digest"],
      input_count: integer(values["input_count"]),
      input_ordinal: integer(values["input_ordinal"]),
      input_ref: values["input_ref"],
      input_digest: values["input_digest"],
      stage_request_digest: values["stage_request_digest"],
      input: values["input_json"],
    });
  } catch {
    throw new PostgresRepositoryError("persistence_failed");
  }
  if (record.input.graph_frontier !== values["graph_frontier"]
    || values["content_hash"] !== recordContentHash(record)) {
    throw new PostgresRepositoryError("persistence_failed");
  }
  return record;
};

const setFromRows = (
  rows: readonly BeliefInputRow[],
): Readonly<{ set: ListenAttributionBeliefInputSet; records: readonly StoredListenAttributionBeliefInput[] }> | null => {
  if (rows.length === 0) return null;
  if (rows.length > 2) throw new PostgresRepositoryError("persistence_failed");
  const records = rows.map(parseBeliefRow);
  const first = records[0]!;
  if (records.length !== first.input_count
    || records.some((record, ordinal) => record.owner_account_id !== first.owner_account_id
      || record.account_epoch !== first.account_epoch
      || record.formation_work_id !== first.formation_work_id
      || record.source_snapshot_digest !== first.source_snapshot_digest
      || record.set_digest !== first.set_digest
      || record.input_count !== first.input_count
      || record.input_ordinal !== ordinal
      || record.stage_request_digest !== first.stage_request_digest)) {
    throw new PostgresRepositoryError("persistence_failed");
  }
  let set: ListenAttributionBeliefInputSet;
  try {
    set = parseListenAttributionBeliefInputSet({
      version: "listen-attribution-belief-input-set-v1",
      owner_account_id: first.owner_account_id,
      account_epoch: first.account_epoch,
      formation_work_id: first.formation_work_id,
      source_snapshot_digest: first.source_snapshot_digest,
      inputs: records.map((record) => ({ input_ref: record.input_ref, input: record.input })),
      set_digest: first.set_digest,
    });
  } catch {
    throw new PostgresRepositoryError("persistence_failed");
  }
  return Object.freeze({ set, records: Object.freeze(records) });
};

const commonFailure = (error: unknown): unknown => {
  if (!(error instanceof PostgresRepositoryError)) throw error;
  switch (error.code) {
    case "expired_context":
    case "stale_epoch":
    case "destination_inactive":
    case "lifecycle_inactive":
      return Object.freeze({ kind: "stale_context" as const, reason: error.code });
    case "credential_inactive":
    case "grant_inactive":
    case "capability_denied":
      return Object.freeze({ kind: "authorization_denied" as const, reason: error.code });
    case "retryable_serialization":
      return Object.freeze({ kind: "serialization_retryable" as const });
    case "idempotency_conflict":
      return Object.freeze({ kind: "idempotency_conflict" as const });
    default:
      throw error;
  }
};

const providerCode = (error: unknown): string | undefined => {
  if (error === null || typeof error !== "object") return undefined;
  const descriptor = Object.getOwnPropertyDescriptor(error, "code");
  return descriptor && "value" in descriptor && typeof descriptor.value === "string"
    ? descriptor.value : undefined;
};

export interface PostgresListenAttributionBeliefInputOptions {
  readonly pool: PostgresTransactionPool;
  readonly observability?: PostgresTransactionObservability;
}

const transact = async <Result>(
  options: PostgresListenAttributionBeliefInputOptions,
  context: AuthorizedLedgerWriteContext,
  callback: (connection: CheckedOutPostgresConnection) => Promise<Result>,
): Promise<Result | unknown> => {
  try {
    return await withAuthorizedSerializableConnectionTransaction(
      options.pool,
      context,
      async ({ connection }) => {
        try { return await callback(connection); }
        catch (error) {
          if (providerCode(error) === "23505") {
            throw new PostgresRepositoryError("idempotency_conflict");
          }
          throw error;
        }
      },
      options.observability ?? {},
    );
  } catch (error) {
    return commonFailure(error);
  }
};

const readSet = async (
  connection: CheckedOutPostgresConnection,
  inputRef: string,
): Promise<ReturnType<typeof setFromRows>> => setFromRows(
  await connection.query<BeliefInputRow>({
    name: "belief.listen_input_set.read",
    text: "SELECT * FROM omi_memory.read_listen_attribution_belief_input_set($1)",
    values: [inputRef],
  }),
);

export const createPostgresAcceptedFormationBeliefSource = (
  options: PostgresListenAttributionBeliefInputOptions,
): AcceptedFormationBeliefSource => defineAcceptedFormationBeliefSource(
  async (context, formationWorkId) => transact(options, context, async (connection) => {
    const rows = await connection.query<FormationInputRow>({
      name: "belief.accepted_formation_input.read",
      text: "SELECT * FROM omi_memory.read_accepted_formation_work_input_for_shadow($1)",
      values: [formationWorkId],
    });
    if (rows.length === 0) return Object.freeze({ kind: "not_found" as const });
    if (rows.length !== 1 || !rows[0]) throw new PostgresRepositoryError("persistence_failed");
    const input = parseFormationRow(rows[0]);
    if (input.account_epoch !== context.account_epoch) {
      return Object.freeze({ kind: "ineligible" as const });
    }
    return Object.freeze({
      kind: "found" as const,
      formation_work_id: input.job_id,
      source_snapshot_digest: input.snapshot_digest,
      snapshot: input.snapshot,
    });
  }),
);

export const createPostgresListenAttributionBeliefInputRepository = (
  options: PostgresListenAttributionBeliefInputOptions,
): ListenAttributionBeliefInputRepository => defineListenAttributionBeliefInputRepository({
  stage: (context, request) => transact(options, context, async (connection) => {
    await connection.query({
      name: "belief.listen_input_set.lock",
      text: "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
      values: [`listen-belief-input:${context.account_id}:${request.set.formation_work_id}`],
    });
    const prior = await readSet(connection, request.set.inputs[0]!.input_ref);
    if (prior) {
      return prior.set.set_digest === request.set.set_digest
        && prior.records.every((record) => record.stage_request_digest === request.request_digest)
        ? Object.freeze({ kind: "replayed" as const, set: prior.set })
        : Object.freeze({ kind: "idempotency_conflict" as const });
    }
    for (let ordinal = 0; ordinal < request.set.inputs.length; ordinal += 1) {
      const record = materializeStoredListenAttributionBeliefInput(
        request.set, ordinal, request.request_digest,
      );
      const rows = await connection.query<{ inserted: boolean }>({
        name: "belief.listen_input.insert",
        text: `SELECT omi_memory.insert_listen_attribution_belief_input(
          $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11,
          ($12::text)::jsonb, $13
        ) AS inserted`,
        values: [
          record.input_ref, record.version, record.account_epoch, record.formation_work_id,
          record.source_snapshot_digest, record.set_digest, record.input_count,
          record.input_ordinal, record.input_digest, record.input.graph_frontier,
          record.stage_request_digest, JSON.stringify(record.input), recordContentHash(record),
        ],
      });
      if (rows.length !== 1 || rows[0]?.inserted !== true || Object.keys(rows[0]).length !== 1) {
        throw new PostgresRepositoryError("persistence_failed");
      }
    }
    return Object.freeze({ kind: "staged" as const, set: request.set });
  }),
  load: (context, inputRef) => transact(options, context, async (connection) => {
    const loaded = await readSet(connection, inputRef);
    if (!loaded || loaded.set.account_epoch !== context.account_epoch) {
      return Object.freeze({ kind: "not_found" as const });
    }
    const record = loaded.records.find((item) => item.input_ref === inputRef);
    if (!record) throw new PostgresRepositoryError("persistence_failed");
    return Object.freeze({ kind: "found" as const, record });
  }),
});
