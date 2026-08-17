import { isProxy } from "node:util/types";

import {
  isWellFormedAccountId,
  type AccountControlConflict,
  type AccountControlProjection,
  type AccountControlRejection,
  type AccountGeneration,
  type AccountLifecycleState,
  type DestinationActivation,
} from "../../../core/control/account-control";
import {
  evaluateAccountControlAdmission,
  type AccountControlAdmissionReason,
} from "../../../core/control/application-admission";

export interface ApplicationAccountControlSource {
  /**
   * Returns an untrusted source envelope for exactly one opaque account key.
   * Production implementations are asynchronous; no caller may infer current
   * authority from a thrown read or a stale/unavailable envelope.
   */
  load(accountId: string): Promise<unknown>;
}

export type ApplicationControlSourceReason =
  | AccountControlAdmissionReason
  | "control_source_stale"
  | "control_source_unavailable"
  | "control_source_invalid";

export type ApplicationControlInspection =
  | Readonly<{
      admitted: true;
      account_epoch: number;
      control_revision: number;
      destination_activation_revision: number;
    }>
  | Readonly<{ admitted: false; reason: ApplicationControlSourceReason }>;

type DescriptorRecord = Record<PropertyKey, PropertyDescriptor>;

const fail = (): never => {
  throw new TypeError("invalid account control source result");
};

const descriptorsFor = (value: unknown): DescriptorRecord => {
  if (value === null || typeof value !== "object" || Array.isArray(value)
    || isProxy(value) || Object.getPrototypeOf(value) !== Object.prototype) fail();
  const objectValue = value as object;
  const keys = Reflect.ownKeys(objectValue);
  if (keys.some((key) => typeof key !== "string")) fail();
  const descriptors = Object.getOwnPropertyDescriptors(objectValue);
  for (const key of keys as string[]) {
    const descriptor = descriptors[key];
    if (descriptor === undefined || !("value" in descriptor) || descriptor.enumerable !== true) fail();
  }
  return descriptors;
};

const exactRecord = (value: unknown, keys: readonly string[]): Record<string, unknown> => {
  const descriptors = descriptorsFor(value);
  const actual = Object.keys(descriptors).sort();
  const expected = [...keys].sort();
  if (actual.length !== expected.length
    || actual.some((key, index) => key !== expected[index])) fail();
  return Object.fromEntries(keys.map((key) => [key, descriptors[key]!.value]));
};

const safeCounter = (value: unknown): value is number =>
  typeof value === "number" && Number.isSafeInteger(value) && value >= 0;

const nullableCounter = (value: unknown): value is number | null =>
  value === null || safeCounter(value);

const GENERATIONS: ReadonlySet<string> = new Set<AccountGeneration>([
  "legacy",
  "migrating",
  "new",
  "rolled_back_stranded",
]);

const LIFECYCLES: ReadonlySet<string> = new Set<AccountLifecycleState>([
  "active",
  "deletion_pending",
  "deleted",
]);

const CONFLICT_REASONS: ReadonlySet<string> = new Set<AccountControlRejection>([
  "malformed_observation",
  "account_id_mismatch",
  "stale_observation",
  "conflicting_observation",
  "unordered_generation_transition",
  "unordered_epoch",
  "withdrawn_epoch",
  "unordered_lifecycle",
  "mutated_deletion_epoch",
  "projection_conflicted",
]);

const parseActivation = (
  value: unknown,
  projection: {
    readonly account_generation: AccountGeneration;
    readonly account_epoch: number | null;
    readonly control_revision: number;
  },
): DestinationActivation | null => {
  if (value === null) return null;
  const row = exactRecord(value, ["activated_epoch", "at_control_revision"]);
  const activatedEpoch = row.activated_epoch;
  const atControlRevision = row.at_control_revision;
  if (!safeCounter(activatedEpoch) || !safeCounter(atControlRevision)
    || projection.account_generation !== "new"
    || activatedEpoch !== projection.account_epoch
    || atControlRevision > projection.control_revision) fail();
  return Object.freeze({
    activated_epoch: activatedEpoch as number,
    at_control_revision: atControlRevision as number,
  });
};

const parseConflict = (value: unknown): AccountControlConflict | null => {
  if (value === null) return null;
  const row = exactRecord(value, ["at_control_revision", "detail"]);
  const atControlRevision = row.at_control_revision;
  const detail = row.detail;
  if (typeof atControlRevision !== "number"
    || !Number.isSafeInteger(atControlRevision)
    || atControlRevision < -1
    || typeof detail !== "string"
    || !CONFLICT_REASONS.has(detail)) fail();
  return Object.freeze({
    at_control_revision: atControlRevision as number,
    detail: detail as AccountControlRejection,
  });
};

const parseProjection = (value: unknown, requestedAccountId: string): AccountControlProjection => {
  const row = exactRecord(value, [
    "account_id",
    "control_revision",
    "account_generation",
    "account_epoch",
    "lifecycle_state",
    "deletion_epoch",
    "activation",
    "conflict",
  ]);
  const accountId = row.account_id;
  const controlRevision = row.control_revision;
  const accountGeneration = row.account_generation;
  const accountEpoch = row.account_epoch;
  const lifecycleState = row.lifecycle_state;
  const deletionEpoch = row.deletion_epoch;
  if (!isWellFormedAccountId(accountId) || accountId !== requestedAccountId
    || !safeCounter(controlRevision)
    || typeof accountGeneration !== "string" || !GENERATIONS.has(accountGeneration)
    || !nullableCounter(accountEpoch)
    || typeof lifecycleState !== "string" || !LIFECYCLES.has(lifecycleState)
    || !nullableCounter(deletionEpoch)
    || (lifecycleState === "active") !== (deletionEpoch === null)) fail();

  const base = {
    account_generation: accountGeneration as AccountGeneration,
    account_epoch: accountEpoch as number | null,
    control_revision: controlRevision as number,
  };
  const activation = parseActivation(row.activation, base);
  const conflict = parseConflict(row.conflict);
  return Object.freeze({
    account_id: accountId as string,
    control_revision: controlRevision as number,
    account_generation: base.account_generation,
    account_epoch: base.account_epoch,
    lifecycle_state: lifecycleState as AccountLifecycleState,
    deletion_epoch: deletionEpoch as number | null,
    activation,
    conflict,
  });
};

const deny = (reason: ApplicationControlSourceReason): ApplicationControlInspection =>
  Object.freeze({ admitted: false, reason });

const inspectEnvelope = (
  raw: unknown,
  requestedAccountId: string,
): ApplicationControlInspection => {
  try {
    const descriptors = descriptorsFor(raw);
    const statusDescriptor = descriptors.status;
    if (statusDescriptor === undefined) return deny("control_source_invalid");
    const status = statusDescriptor.value;

    if (status === "absent" || status === "stale" || status === "unavailable") {
      exactRecord(raw, ["status"]);
      if (status === "absent") return deny("control_state_absent");
      return deny(status === "stale" ? "control_source_stale" : "control_source_unavailable");
    }
    if (status !== "current") return deny("control_source_invalid");

    const envelope = exactRecord(raw, ["status", "projection"]);
    const projection = parseProjection(envelope.projection, requestedAccountId);
    const decision = evaluateAccountControlAdmission(projection);
    if (!decision.admitted) return deny(decision.reason);
    if (projection.activation === null) return deny("control_source_invalid");
    return Object.freeze({
      admitted: true,
      account_epoch: decision.account_epoch,
      control_revision: projection.control_revision,
      destination_activation_revision: projection.activation.at_control_revision,
    });
  } catch {
    return deny("control_source_invalid");
  }
};

/**
 * Reads and inspects one coherent account-control source observation.
 *
 * This is not authentication, authorization, or a durable capability. A later
 * positive emission/effect must perform its own final inspection.
 */
export const inspectApplicationAccountControl = async (
  source: ApplicationAccountControlSource,
  accountId: string,
): Promise<ApplicationControlInspection> => {
  if (!isWellFormedAccountId(accountId) || source === null || typeof source !== "object"
    || isProxy(source)) return deny("control_source_invalid");

  let load: ApplicationAccountControlSource["load"];
  try {
    load = source.load;
  } catch {
    return deny("control_source_invalid");
  }
  if (typeof load !== "function" || isProxy(load)) return deny("control_source_invalid");

  let raw: unknown;
  try {
    raw = await load.call(source, accountId);
  } catch {
    return deny("control_source_unavailable");
  }
  return inspectEnvelope(raw, accountId);
};
