import { isProxy } from "node:util/types";

import { sha256CanonicalContent } from "../../../core/retrieve/content-digest";
import {
  assertAuthorizedLedgerWriteContext,
  type AuthorizedLedgerWriteContext,
} from "../auth/authorized-context";
import {
  defineMemoryEvaluationEvidenceSource,
  type MemoryEvaluationEvidenceSource,
} from "../stores/memory-evaluation-evidence-source";
import {
  formationWorkInputSnapshotDigest,
} from "../workers/formation-work-input-repository";
import {
  parseFormationInputSnapshot,
  type FormationInputSnapshot,
} from "../workers/formation-work-producer";
import {
  materializeListenAttributionBeliefInputs,
  parseListenAttributionBeliefInput,
  type ListenAttributionBeliefInput,
} from "./attribution-belief-input";

export const LISTEN_ATTRIBUTION_BELIEF_INPUT_SET_VERSION =
  "listen-attribution-belief-input-set-v1" as const;
export const STORED_LISTEN_ATTRIBUTION_BELIEF_INPUT_VERSION =
  "stored-listen-attribution-belief-input-v1" as const;

const SOURCE_PORT: unique symbol = Symbol("accepted-formation-belief-source");
const REPOSITORY_PORT: unique symbol = Symbol("listen-attribution-belief-input-repository");
const STAGER_PORT: unique symbol = Symbol("listen-attribution-belief-input-stager");
const CAPABILITY = "memories.experiments.shadow";
const TOKEN = /^[\x21-\x7e]{1,256}$/;
const DIGEST = /^[a-f0-9]{64}$/;
const INPUT_REF = /^labinput1_[a-f0-9]{64}$/;

export interface ListenAttributionBeliefInputEntry {
  readonly input_ref: string;
  readonly input: Readonly<ListenAttributionBeliefInput>;
}

export interface ListenAttributionBeliefInputSet {
  readonly version: typeof LISTEN_ATTRIBUTION_BELIEF_INPUT_SET_VERSION;
  readonly owner_account_id: string;
  readonly account_epoch: number;
  readonly formation_work_id: string;
  readonly source_snapshot_digest: string;
  readonly inputs: readonly Readonly<ListenAttributionBeliefInputEntry>[];
  readonly set_digest: string;
}

export interface StoredListenAttributionBeliefInput {
  readonly version: typeof STORED_LISTEN_ATTRIBUTION_BELIEF_INPUT_VERSION;
  readonly owner_account_id: string;
  readonly account_epoch: number;
  readonly formation_work_id: string;
  readonly source_snapshot_digest: string;
  readonly set_digest: string;
  readonly input_count: number;
  readonly input_ordinal: number;
  readonly input_ref: string;
  readonly input_digest: string;
  readonly stage_request_digest: string;
  readonly input: Readonly<ListenAttributionBeliefInput>;
}

export type ListenAttributionBeliefInputCommonOutcome =
  | Readonly<{ kind: "serialization_retryable" }>
  | Readonly<{
      kind: "stale_context";
      reason: "expired_context" | "stale_epoch" | "destination_inactive" | "lifecycle_inactive";
    }>
  | Readonly<{
      kind: "authorization_denied";
      reason: "credential_inactive" | "grant_inactive" | "capability_denied";
    }>;

export type AcceptedFormationBeliefSourceOutcome =
  | Readonly<{
      kind: "found";
      formation_work_id: string;
      source_snapshot_digest: string;
      snapshot: Readonly<FormationInputSnapshot>;
    }>
  | Readonly<{ kind: "not_found" | "ineligible" }>
  | ListenAttributionBeliefInputCommonOutcome;

export interface AcceptedFormationBeliefSource {
  readonly [SOURCE_PORT]: true;
  load(
    context: AuthorizedLedgerWriteContext,
    formationWorkId: string,
  ): Promise<AcceptedFormationBeliefSourceOutcome>;
}

export type ListenAttributionBeliefInputStageOutcome =
  | Readonly<{ kind: "staged" | "replayed"; set: Readonly<ListenAttributionBeliefInputSet> }>
  | Readonly<{ kind: "idempotency_conflict" }>
  | ListenAttributionBeliefInputCommonOutcome;

export type ListenAttributionBeliefInputLoadOutcome =
  | Readonly<{ kind: "found"; record: Readonly<StoredListenAttributionBeliefInput> }>
  | Readonly<{ kind: "not_found" }>
  | ListenAttributionBeliefInputCommonOutcome;

export interface ListenAttributionBeliefInputRepository {
  readonly [REPOSITORY_PORT]: true;
  stage(
    context: AuthorizedLedgerWriteContext,
    request: Readonly<{
      set: Readonly<ListenAttributionBeliefInputSet>;
      request_digest: string;
    }>,
  ): Promise<ListenAttributionBeliefInputStageOutcome>;
  load(
    context: AuthorizedLedgerWriteContext,
    inputRef: string,
  ): Promise<ListenAttributionBeliefInputLoadOutcome>;
}

export interface ListenAttributionBeliefInputStager {
  readonly [STAGER_PORT]: true;
  stageAcceptedFormation(
    context: AuthorizedLedgerWriteContext,
    formationWorkId: string,
  ): Promise<ListenAttributionBeliefInputStageOutcome | Readonly<{ kind: "not_found" | "ineligible" }>>;
}

const fail = (code: string): never => {
  throw new TypeError(`listen attribution belief input source ${code}`);
};

const exactRecord = (
  value: unknown,
  keys: readonly string[],
  code: string,
): Record<string, unknown> => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype) fail(code);
  const descriptors = Object.getOwnPropertyDescriptors(value);
  const actual = Reflect.ownKeys(descriptors);
  const expected = [...keys].sort();
  if (actual.some((key) => typeof key !== "string") || actual.length !== expected.length
    || (actual as string[]).sort().some((key, index) => key !== expected[index])) fail(code);
  const output: Record<string, unknown> = {};
  for (const key of expected) {
    const descriptor = descriptors[key];
    if (!descriptor || !descriptor.enumerable || !("value" in descriptor)) fail(code);
    output[key] = descriptor.value;
  }
  return output;
};

const exactArray = (value: unknown, maximum: number, code: string): readonly unknown[] => {
  if (!Array.isArray(value) || isProxy(value) || Object.getPrototypeOf(value) !== Array.prototype
    || value.length < 1 || value.length > maximum) fail(code);
  const descriptors = Object.getOwnPropertyDescriptors(value);
  if (Reflect.ownKeys(descriptors).length !== value.length + 1) fail(code);
  const output: unknown[] = [];
  for (let index = 0; index < value.length; index += 1) {
    const descriptor = descriptors[String(index)];
    if (!descriptor || !descriptor.enumerable || !("value" in descriptor)) fail(code);
    output.push(descriptor.value);
  }
  return output;
};

const token = (value: unknown, code: string): string => {
  if (typeof value !== "string" || !TOKEN.test(value)) fail(code);
  return value;
};

const digest = (value: unknown, code: string): string => {
  if (typeof value !== "string" || !DIGEST.test(value)) fail(code);
  return value;
};

const nonnegative = (value: unknown, code: string): number => {
  if (!Number.isSafeInteger(value) || (value as number) < 0) fail(code);
  return value as number;
};

const authority = (value: AuthorizedLedgerWriteContext): AuthorizedLedgerWriteContext => {
  const context = assertAuthorizedLedgerWriteContext(value);
  if (context.capability !== CAPABILITY) fail("capability_denied");
  return context;
};

const compare = (left: string, right: string): number => left < right ? -1 : left > right ? 1 : 0;

export const listenAttributionBeliefInputRef = (value: {
  readonly owner_account_id: string;
  readonly account_epoch: number;
  readonly formation_work_id: string;
  readonly about_ref: string;
}): string => `labinput1_${sha256CanonicalContent({
  contract_version: "listen-attribution-belief-input-ref-v1",
  owner_account_id: value.owner_account_id,
  account_epoch: value.account_epoch,
  formation_work_id: value.formation_work_id,
  about_ref: value.about_ref,
})}`;

const setCore = (set: Omit<ListenAttributionBeliefInputSet, "set_digest">) => ({
  version: set.version,
  owner_account_id: set.owner_account_id,
  account_epoch: set.account_epoch,
  formation_work_id: set.formation_work_id,
  source_snapshot_digest: set.source_snapshot_digest,
  inputs: set.inputs,
});

export const parseListenAttributionBeliefInputSet = (
  value: unknown,
): Readonly<ListenAttributionBeliefInputSet> => {
  const code = "invalid_set";
  const row = exactRecord(value, [
    "version", "owner_account_id", "account_epoch", "formation_work_id",
    "source_snapshot_digest", "inputs", "set_digest",
  ], code);
  if (row["version"] !== LISTEN_ATTRIBUTION_BELIEF_INPUT_SET_VERSION) fail(code);
  const owner = token(row["owner_account_id"], code);
  const epoch = nonnegative(row["account_epoch"], code);
  const workId = token(row["formation_work_id"], code);
  const entries = exactArray(row["inputs"], 2, code).map((value) => {
    const entry = exactRecord(value, ["input_ref", "input"], code);
    const input = parseListenAttributionBeliefInput(entry["input"]);
    const inputRef = token(entry["input_ref"], code);
    if (!INPUT_REF.test(inputRef) || input.owner_account_id !== owner
      || inputRef !== listenAttributionBeliefInputRef({
        owner_account_id: owner, account_epoch: epoch,
        formation_work_id: workId, about_ref: input.about_ref,
      })) fail(code);
    return Object.freeze({ input_ref: inputRef, input });
  }).sort((left, right) => compare(left.input_ref, right.input_ref));
  if (new Set(entries.map((entry) => entry.input_ref)).size !== entries.length) fail(code);
  const supplied = exactArray(row["inputs"], 2, code) as readonly Record<string, unknown>[];
  if (supplied.some((entry, index) => entry["input_ref"] !== entries[index]?.input_ref)) fail(code);
  const core = Object.freeze({
    version: LISTEN_ATTRIBUTION_BELIEF_INPUT_SET_VERSION,
    owner_account_id: owner,
    account_epoch: epoch,
    formation_work_id: workId,
    source_snapshot_digest: digest(row["source_snapshot_digest"], code),
    inputs: Object.freeze(entries),
  });
  const setDigest = digest(row["set_digest"], code);
  if (setDigest !== sha256CanonicalContent(setCore(core))) fail(code);
  return Object.freeze({ ...core, set_digest: setDigest });
};

export const materializeListenAttributionBeliefInputSet = (
  contextValue: AuthorizedLedgerWriteContext,
  sourceValue: Readonly<{
    formation_work_id: string;
    source_snapshot_digest: string;
    snapshot: Readonly<FormationInputSnapshot>;
  }>,
): Readonly<ListenAttributionBeliefInputSet> => {
  const context = authority(contextValue);
  const source = exactRecord(sourceValue, [
    "formation_work_id", "source_snapshot_digest", "snapshot",
  ], "invalid_source");
  const snapshot = parseFormationInputSnapshot(source["snapshot"]);
  const formationWorkId = token(source["formation_work_id"], "invalid_source");
  const sourceSnapshotDigest = digest(source["source_snapshot_digest"], "invalid_source");
  if (snapshot.owner_account_id !== context.account_id || snapshot.work_id !== formationWorkId
    || formationWorkInputSnapshotDigest(snapshot) !== sourceSnapshotDigest) fail("source_mismatch");
  const inputs = materializeListenAttributionBeliefInputs(snapshot)
    .map((input) => Object.freeze({
      input_ref: listenAttributionBeliefInputRef({
        owner_account_id: context.account_id,
        account_epoch: context.account_epoch,
        formation_work_id: formationWorkId,
        about_ref: input.about_ref,
      }),
      input,
    }))
    .sort((left, right) => compare(left.input_ref, right.input_ref));
  const core = Object.freeze({
    version: LISTEN_ATTRIBUTION_BELIEF_INPUT_SET_VERSION,
    owner_account_id: context.account_id,
    account_epoch: context.account_epoch,
    formation_work_id: formationWorkId,
    source_snapshot_digest: sourceSnapshotDigest,
    inputs: Object.freeze(inputs),
  });
  return Object.freeze({ ...core, set_digest: sha256CanonicalContent(setCore(core)) });
};

export const listenAttributionBeliefInputStageRequestDigest = (
  setValue: ListenAttributionBeliefInputSet,
): string => sha256CanonicalContent({
  contract_version: "listen-attribution-belief-input-stage-v1",
  set: parseListenAttributionBeliefInputSet(setValue),
});

export const materializeStoredListenAttributionBeliefInput = (
  setValue: ListenAttributionBeliefInputSet,
  inputOrdinal: number,
  stageRequestDigest: string,
): Readonly<StoredListenAttributionBeliefInput> => {
  const set = parseListenAttributionBeliefInputSet(setValue);
  if (!Number.isSafeInteger(inputOrdinal) || inputOrdinal < 0 || inputOrdinal >= set.inputs.length) {
    fail("invalid_ordinal");
  }
  const entry = set.inputs[inputOrdinal]!;
  const requestDigest = digest(stageRequestDigest, "invalid_request_digest");
  return Object.freeze({
    version: STORED_LISTEN_ATTRIBUTION_BELIEF_INPUT_VERSION,
    owner_account_id: set.owner_account_id,
    account_epoch: set.account_epoch,
    formation_work_id: set.formation_work_id,
    source_snapshot_digest: set.source_snapshot_digest,
    set_digest: set.set_digest,
    input_count: set.inputs.length,
    input_ordinal: inputOrdinal,
    input_ref: entry.input_ref,
    input_digest: sha256CanonicalContent(entry.input),
    stage_request_digest: requestDigest,
    input: entry.input,
  });
};

export const parseStoredListenAttributionBeliefInput = (
  value: unknown,
): Readonly<StoredListenAttributionBeliefInput> => {
  const code = "invalid_record";
  const row = exactRecord(value, [
    "version", "owner_account_id", "account_epoch", "formation_work_id",
    "source_snapshot_digest", "set_digest", "input_count", "input_ordinal",
    "input_ref", "input_digest", "stage_request_digest", "input",
  ], code);
  if (row["version"] !== STORED_LISTEN_ATTRIBUTION_BELIEF_INPUT_VERSION) fail(code);
  const input = parseListenAttributionBeliefInput(row["input"]);
  const record = Object.freeze({
    version: STORED_LISTEN_ATTRIBUTION_BELIEF_INPUT_VERSION,
    owner_account_id: token(row["owner_account_id"], code),
    account_epoch: nonnegative(row["account_epoch"], code),
    formation_work_id: token(row["formation_work_id"], code),
    source_snapshot_digest: digest(row["source_snapshot_digest"], code),
    set_digest: digest(row["set_digest"], code),
    input_count: nonnegative(row["input_count"], code),
    input_ordinal: nonnegative(row["input_ordinal"], code),
    input_ref: token(row["input_ref"], code),
    input_digest: digest(row["input_digest"], code),
    stage_request_digest: digest(row["stage_request_digest"], code),
    input,
  });
  if (record.input_count < 1 || record.input_count > 2
    || record.input_ordinal >= record.input_count || !INPUT_REF.test(record.input_ref)
    || record.owner_account_id !== input.owner_account_id
    || record.input_ref !== listenAttributionBeliefInputRef({
      owner_account_id: record.owner_account_id,
      account_epoch: record.account_epoch,
      formation_work_id: record.formation_work_id,
      about_ref: input.about_ref,
    })
    || record.input_digest !== sha256CanonicalContent(input)) fail(code);
  return record;
};

const parseCommon = (value: unknown): ListenAttributionBeliefInputCommonOutcome | null => {
  const kind = value !== null && typeof value === "object"
    ? Object.getOwnPropertyDescriptor(value, "kind") : undefined;
  if (!kind || !kind.enumerable || !("value" in kind)) fail("invalid_outcome");
  if (kind.value === "serialization_retryable") {
    exactRecord(value, ["kind"], "invalid_outcome");
    return Object.freeze({ kind: "serialization_retryable" as const });
  }
  if (kind.value === "stale_context" || kind.value === "authorization_denied") {
    const row = exactRecord(value, ["kind", "reason"], "invalid_outcome");
    const reasons = kind.value === "stale_context"
      ? ["expired_context", "stale_epoch", "destination_inactive", "lifecycle_inactive"]
      : ["credential_inactive", "grant_inactive", "capability_denied"];
    if (typeof row["reason"] !== "string" || !reasons.includes(row["reason"])) fail("invalid_outcome");
    return Object.freeze({
      kind: kind.value, reason: row["reason"],
    }) as ListenAttributionBeliefInputCommonOutcome;
  }
  return null;
};

export const defineAcceptedFormationBeliefSource = (
  implementation: (
    context: AuthorizedLedgerWriteContext,
    formationWorkId: string,
  ) => Promise<unknown>,
): AcceptedFormationBeliefSource => Object.freeze({
  [SOURCE_PORT]: true as const,
  async load(contextValue, formationWorkIdValue) {
    const context = authority(contextValue);
    const formationWorkId = token(formationWorkIdValue, "invalid_work_id");
    const raw = await implementation(context, formationWorkId);
    const common = parseCommon(raw);
    if (common) return common;
    const kind = Object.getOwnPropertyDescriptor(raw as object, "kind")?.value;
    if (kind === "not_found" || kind === "ineligible") {
      exactRecord(raw, ["kind"], "invalid_outcome");
      return Object.freeze({ kind });
    }
    const row = exactRecord(raw, [
      "kind", "formation_work_id", "source_snapshot_digest", "snapshot",
    ], "invalid_outcome");
    const snapshot = parseFormationInputSnapshot(row["snapshot"]);
    const sourceDigest = digest(row["source_snapshot_digest"], "invalid_outcome");
    if (row["kind"] !== "found" || row["formation_work_id"] !== formationWorkId
      || snapshot.owner_account_id !== context.account_id || snapshot.work_id !== formationWorkId
      || formationWorkInputSnapshotDigest(snapshot) !== sourceDigest) fail("source_mismatch");
    return Object.freeze({
      kind: "found" as const,
      formation_work_id: formationWorkId,
      source_snapshot_digest: sourceDigest,
      snapshot,
    });
  },
});

export const defineListenAttributionBeliefInputRepository = (implementation: {
  readonly stage: (
    context: AuthorizedLedgerWriteContext,
    request: Readonly<{ set: ListenAttributionBeliefInputSet; request_digest: string }>,
  ) => Promise<unknown>;
  readonly load: (
    context: AuthorizedLedgerWriteContext,
    inputRef: string,
  ) => Promise<unknown>;
}): ListenAttributionBeliefInputRepository => Object.freeze({
  [REPOSITORY_PORT]: true as const,
  async stage(contextValue, requestValue) {
    const context = authority(contextValue);
    const request = exactRecord(requestValue, ["set", "request_digest"], "invalid_request");
    const set = parseListenAttributionBeliefInputSet(request["set"]);
    const requestDigest = digest(request["request_digest"], "invalid_request");
    if (set.owner_account_id !== context.account_id || set.account_epoch !== context.account_epoch
      || requestDigest !== listenAttributionBeliefInputStageRequestDigest(set)) fail("request_mismatch");
    const raw = await implementation.stage(context, Object.freeze({
      set, request_digest: requestDigest,
    }));
    const common = parseCommon(raw);
    if (common) return common;
    const kind = Object.getOwnPropertyDescriptor(raw as object, "kind")?.value;
    if (kind === "idempotency_conflict") {
      exactRecord(raw, ["kind"], "invalid_outcome");
      return Object.freeze({ kind });
    }
    const row = exactRecord(raw, ["kind", "set"], "invalid_outcome");
    const returned = parseListenAttributionBeliefInputSet(row["set"]);
    if ((row["kind"] !== "staged" && row["kind"] !== "replayed")
      || returned.set_digest !== set.set_digest) fail("invalid_outcome");
    return Object.freeze({
      kind: row["kind"], set: returned,
    }) as ListenAttributionBeliefInputStageOutcome;
  },
  async load(contextValue, inputRefValue) {
    const context = authority(contextValue);
    const inputRef = token(inputRefValue, "invalid_input_ref");
    if (!INPUT_REF.test(inputRef)) fail("invalid_input_ref");
    const raw = await implementation.load(context, inputRef);
    const common = parseCommon(raw);
    if (common) return common;
    const kind = Object.getOwnPropertyDescriptor(raw as object, "kind")?.value;
    if (kind === "not_found") {
      exactRecord(raw, ["kind"], "invalid_outcome");
      return Object.freeze({ kind });
    }
    const row = exactRecord(raw, ["kind", "record"], "invalid_outcome");
    const record = parseStoredListenAttributionBeliefInput(row["record"]);
    if (row["kind"] !== "found" || record.input_ref !== inputRef
      || record.owner_account_id !== context.account_id
      || record.account_epoch !== context.account_epoch) fail("invalid_outcome");
    return Object.freeze({ kind: "found" as const, record });
  },
});

export const defineListenAttributionBeliefInputStager = (dependencies: {
  readonly source: AcceptedFormationBeliefSource;
  readonly repository: ListenAttributionBeliefInputRepository;
}): ListenAttributionBeliefInputStager => {
  const row = exactRecord(dependencies, ["source", "repository"], "invalid_dependencies");
  const source = row["source"] as AcceptedFormationBeliefSource;
  const repository = row["repository"] as ListenAttributionBeliefInputRepository;
  return Object.freeze({
    [STAGER_PORT]: true as const,
    async stageAcceptedFormation(contextValue, formationWorkIdValue) {
      const context = authority(contextValue);
      const formationWorkId = token(formationWorkIdValue, "invalid_work_id");
      const loaded = await source.load(context, formationWorkId);
      if (loaded.kind !== "found") return loaded;
      const set = materializeListenAttributionBeliefInputSet(context, {
        formation_work_id: loaded.formation_work_id,
        source_snapshot_digest: loaded.source_snapshot_digest,
        snapshot: loaded.snapshot,
      });
      return repository.stage(context, {
        set,
        request_digest: listenAttributionBeliefInputStageRequestDigest(set),
      });
    },
  });
};

export const defineListenAttributionBeliefEvaluationSource = (
  repository: ListenAttributionBeliefInputRepository,
): MemoryEvaluationEvidenceSource => defineMemoryEvaluationEvidenceSource(
  async (context, request) => {
    if (request.source_kind !== "formation_input_snapshot") fail("invalid_source_kind");
    const loaded = await repository.load(context, request.source_ref);
    if (loaded.kind === "not_found") return loaded;
    if (loaded.kind !== "found") return loaded;
    if (loaded.record.input.graph_frontier !== request.input_frontier) {
      return Object.freeze({ kind: "not_found" as const });
    }
    return Object.freeze({
      kind: "found" as const,
      owner_account_id: context.account_id,
      account_epoch: context.account_epoch,
      source_kind: request.source_kind,
      source_ref: request.source_ref,
      input_frontier: request.input_frontier,
      payload: loaded.record.input,
    });
  },
);
