import { isProxy } from "node:util/types";

import type { ApplicationAccountControlSource } from
  "../../apps/service/control/application-control-source";
import { isWellFormedAccountId } from "../../core/control/account-control";
import type { SqlStatement } from "./connection";

const MAX_COUNTER = Number.MAX_SAFE_INTEGER;
const GENERATIONS = new Set(["legacy", "migrating", "new", "rolled_back_stranded"]);
const LIFECYCLES = new Set(["active", "deletion_pending", "deleted"]);
const CONFLICTS = new Set([
  "malformed_observation", "account_id_mismatch", "stale_observation",
  "conflicting_observation", "unordered_generation_transition", "unordered_epoch",
  "withdrawn_epoch", "unordered_lifecycle", "mutated_deletion_epoch",
  "projection_conflicted",
]);

export const LOAD_APPLICATION_ACCOUNT_CONTROL: SqlStatement["text"] = `
SELECT
  h.account_id,
  h.control_revision,
  r.account_generation,
  r.account_epoch,
  r.lifecycle_state,
  r.deletion_epoch,
  h.activated_epoch,
  h.activation_control_revision,
  h.conflict_reason,
  h.conflict_at_control_revision AS conflict_at_revision
FROM omi_memory.account_control_heads AS h
JOIN omi_memory.account_control_revisions AS r
  ON r.account_id = h.account_id
 AND r.control_revision = h.control_revision
WHERE h.account_id = $1
`;

export interface ApplicationAccountControlQueryPort {
  query(statement: SqlStatement): Promise<readonly Record<string, unknown>[]>;
}

type QueryMethod = ApplicationAccountControlQueryPort["query"];
const unavailable = Object.freeze({ status: "unavailable" as const });
const absent = Object.freeze({ status: "absent" as const });

const exactRecord = (value: unknown, expected: readonly string[]): Record<string, unknown> | null => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype) return null;
  const keys = Reflect.ownKeys(value);
  if (keys.some((key) => typeof key !== "string")) return null;
  const actual = (keys as string[]).sort();
  const wanted = [...expected].sort();
  if (actual.length !== wanted.length
    || actual.some((key, index) => key !== wanted[index])) return null;
  const output: Record<string, unknown> = {};
  for (const key of actual) {
    const descriptor = Object.getOwnPropertyDescriptor(value, key);
    if (!descriptor || !("value" in descriptor) || !descriptor.enumerable) return null;
    output[key] = descriptor.value;
  }
  return output;
};

const rows = (value: unknown): readonly unknown[] | null => {
  if (!Array.isArray(value) || isProxy(value) || Object.getPrototypeOf(value) !== Array.prototype) {
    return null;
  }
  const keys = Reflect.ownKeys(value);
  if (keys.some((key) => key !== "length"
    && (typeof key !== "string" || !/^(0|[1-9][0-9]*)$/.test(key)))) return null;
  for (let index = 0; index < value.length; index += 1) {
    const descriptor = Object.getOwnPropertyDescriptor(value, String(index));
    if (!descriptor || !("value" in descriptor) || !descriptor.enumerable) return null;
  }
  return value;
};

const counter = (value: unknown): number | null => {
  if (typeof value === "number" && Number.isSafeInteger(value) && value >= 0) return value;
  if (typeof value !== "string" || !/^(0|[1-9][0-9]*)$/.test(value)) return null;
  const parsed = Number(value);
  return Number.isSafeInteger(parsed) && parsed >= 0 && parsed <= MAX_COUNTER ? parsed : null;
};

const nullableCounter = (value: unknown): number | null | undefined =>
  value === null ? null : counter(value) ?? undefined;

const snapshotQuery = (value: unknown): Readonly<{ receiver: object; method: QueryMethod }> | null => {
  const record = exactRecord(value, ["query"]);
  const method = record?.query;
  if (record === null || typeof method !== "function" || isProxy(method)) return null;
  return Object.freeze({ receiver: value as object, method: method as QueryMethod });
};

const ROW_KEYS = Object.freeze([
  "account_id", "control_revision", "account_generation", "account_epoch",
  "lifecycle_state", "deletion_epoch", "activated_epoch",
  "activation_control_revision", "conflict_reason", "conflict_at_revision",
] as const);

const parseCurrent = (value: unknown, accountId: string): unknown | null => {
  const row = exactRecord(value, ROW_KEYS);
  if (row === null || row.account_id !== accountId) return null;
  const controlRevision = counter(row.control_revision);
  const accountEpoch = nullableCounter(row.account_epoch);
  const deletionEpoch = nullableCounter(row.deletion_epoch);
  const activatedEpoch = nullableCounter(row.activated_epoch);
  const activationRevision = nullableCounter(row.activation_control_revision);
  const conflictRevision = nullableCounter(row.conflict_at_revision);
  if (controlRevision === null || accountEpoch === undefined || deletionEpoch === undefined
    || activatedEpoch === undefined || activationRevision === undefined
    || conflictRevision === undefined
    || typeof row.account_generation !== "string" || !GENERATIONS.has(row.account_generation)
    || typeof row.lifecycle_state !== "string" || !LIFECYCLES.has(row.lifecycle_state)
    || (row.lifecycle_state === "active") !== (deletionEpoch === null)
    || (activatedEpoch === null) !== (activationRevision === null)
    || (row.conflict_reason === null) !== (conflictRevision === null)
    || (row.conflict_reason !== null
      && (typeof row.conflict_reason !== "string" || !CONFLICTS.has(row.conflict_reason)))) return null;
  return Object.freeze({
    status: "current" as const,
    projection: Object.freeze({
      account_id: accountId,
      control_revision: controlRevision,
      account_generation: row.account_generation,
      account_epoch: accountEpoch,
      lifecycle_state: row.lifecycle_state,
      deletion_epoch: deletionEpoch,
      activation: activatedEpoch === null ? null : Object.freeze({
        activated_epoch: activatedEpoch,
        at_control_revision: activationRevision,
      }),
      conflict: row.conflict_reason === null ? null : Object.freeze({
        at_control_revision: conflictRevision,
        detail: row.conflict_reason,
      }),
    }),
  });
};

/** Fixed-query PostgreSQL source for the coherent application control inspection. */
export const createPostgresApplicationAccountControlSource = (
  queryPort: ApplicationAccountControlQueryPort,
): ApplicationAccountControlSource => {
  const query = snapshotQuery(queryPort);
  if (query === null) throw new TypeError("invalid PostgreSQL account control query port");
  return Object.freeze({
    async load(accountId: string): Promise<unknown> {
      if (!isWellFormedAccountId(accountId)) return unavailable;
      let raw: unknown;
      try {
        raw = await query.method.call(query.receiver, Object.freeze({
          name: "application_control.load_current",
          text: LOAD_APPLICATION_ACCOUNT_CONTROL,
          values: Object.freeze([accountId]),
        }));
      } catch {
        return unavailable;
      }
      const resultRows = rows(raw);
      if (resultRows === null || resultRows.length > 1) return unavailable;
      if (resultRows.length === 0) return absent;
      return parseCurrent(resultRows[0], accountId) ?? unavailable;
    },
  });
};
