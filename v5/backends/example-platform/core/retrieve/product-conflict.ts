import { createHash } from "node:crypto";
import { isProxy } from "node:util/types";

import {
  parseProductPropositionRedirect,
  parseProductPropositionIdentity,
  resolveTerminalPropositionIds,
  type ProductPropositionIdentity,
  type ProductPropositionRedirect,
} from "./product-projection";

export const PRODUCT_CONFLICT_CONTRACT_VERSION = "product-conflict-reference-v1" as const;

export type ProductConflictContractErrorCode =
  | "invalid_conflict_occurrence"
  | "invalid_conflict_resolution_input";

export class ProductConflictContractError extends Error {
  constructor(readonly code: ProductConflictContractErrorCode) {
    super(code);
    this.name = "ProductConflictContractError";
  }
}

export interface ProductConflictOccurrence {
  readonly version: typeof PRODUCT_CONFLICT_CONTRACT_VERSION;
  readonly owner_account_id: string;
  readonly occurrence_id: string;
  readonly original_proposition_ids: readonly string[];
  readonly graph_frontier: string;
  readonly reference_snapshot_digest: string;
  readonly detector_contract_digest: string;
  readonly conflict_basis_digest: string;
  readonly created_at_event_time: number;
}

export interface ProductConflictResolutionInput {
  readonly version: typeof PRODUCT_CONFLICT_CONTRACT_VERSION;
  readonly owner_account_id: string;
  readonly resolution_input_id: string;
  readonly occurrence_id: string;
  readonly original_proposition_ids: readonly string[];
  readonly resolved_proposition_ids: readonly string[];
  readonly graph_frontier: string;
  readonly reference_snapshot_digest: string;
  readonly operation_ref: string;
  readonly resolution_contract_digest: string;
  readonly created_at_event_time: number;
}

export interface BuildProductConflictOccurrenceInput {
  readonly owner_account_id: string;
  readonly original_proposition_ids: readonly string[];
  readonly propositions: readonly ProductPropositionIdentity[];
  readonly graph_frontier: string;
  readonly detector_contract_digest: string;
  readonly conflict_basis_digest: string;
  readonly created_at_event_time: number;
}

export interface BuildProductConflictResolutionInput {
  readonly occurrence: ProductConflictOccurrence;
  readonly proposed_resolved_proposition_ids: readonly string[];
  readonly propositions: readonly ProductPropositionIdentity[];
  readonly redirects: readonly ProductPropositionRedirect[];
  readonly graph_frontier: string;
  readonly operation_ref: string;
  readonly resolution_contract_digest: string;
  readonly created_at_event_time: number;
}

const TOKEN = /^[\x21-\x7e]{1,256}$/;
const DIGEST = /^[a-f0-9]{64}$/;
const GROUP_ID = /^grp1_[a-f0-9]{64}$/;
const OPAQUE_OPERATION_REF = /^opref1_[a-f0-9]{64}$/;
const ARRAY_INDEX = /^(0|[1-9]\d*)$/;
const MAX_PROPOSITIONS = 10_000;

const fail = (code: ProductConflictContractErrorCode): never => {
  throw new ProductConflictContractError(code);
};

const exactRecord = (
  value: unknown,
  expected: readonly string[],
  code: ProductConflictContractErrorCode,
): Record<string, unknown> => {
  if (value === null || typeof value !== "object" || Array.isArray(value)
    || isProxy(value) || Object.getPrototypeOf(value) !== Object.prototype) fail(code);
  const descriptors = Object.getOwnPropertyDescriptors(value);
  const keys = Reflect.ownKeys(descriptors);
  if (keys.some((key) => typeof key !== "string")) fail(code);
  const actual = (keys as string[]).sort();
  const wanted = [...expected].sort();
  if (actual.length !== wanted.length
    || actual.some((key, index) => key !== wanted[index])) fail(code);
  for (const key of actual) {
    const descriptor = descriptors[key];
    if (!descriptor || !descriptor.enumerable || !("value" in descriptor)) fail(code);
  }
  return value as Record<string, unknown>;
};

const exactArray = (
  value: unknown,
  code: ProductConflictContractErrorCode,
): readonly unknown[] => {
  if (!Array.isArray(value) || isProxy(value) || Object.getPrototypeOf(value) !== Array.prototype
    || value.length > MAX_PROPOSITIONS) fail(code);
  const arrayValue = value as unknown[];
  const descriptors = Object.getOwnPropertyDescriptors(arrayValue);
  const keys = Reflect.ownKeys(descriptors);
  if (keys.some((key) => typeof key !== "string") || keys.length !== arrayValue.length + 1) fail(code);
  for (const key of keys as string[]) {
    if (key === "length") continue;
    if (!ARRAY_INDEX.test(key) || Number(key) >= arrayValue.length) fail(code);
    const descriptor = descriptors[key];
    if (!descriptor || !descriptor.enumerable || !("value" in descriptor)) fail(code);
  }
  const output: unknown[] = [];
  for (let index = 0; index < arrayValue.length; index += 1) {
    const descriptor = descriptors[String(index)];
    if (!descriptor || !descriptor.enumerable || !("value" in descriptor)) fail(code);
    output.push(descriptor!.value);
  }
  return output;
};

const token = (value: unknown, code: ProductConflictContractErrorCode): string => {
  if (typeof value !== "string" || !TOKEN.test(value)) fail(code);
  return value as string;
};

const propositionId = (value: unknown, code: ProductConflictContractErrorCode): string => {
  const parsed = token(value, code);
  if (GROUP_ID.test(parsed)) fail(code);
  return parsed;
};

const digest = (value: unknown, code: ProductConflictContractErrorCode): string => {
  if (typeof value !== "string" || !DIGEST.test(value)) fail(code);
  return value as string;
};

const opaqueOperationRef = (
  value: unknown,
  code: ProductConflictContractErrorCode,
): string => {
  if (typeof value !== "string" || !OPAQUE_OPERATION_REF.test(value)) fail(code);
  return value as string;
};

const eventTime = (value: unknown, code: ProductConflictContractErrorCode): number => {
  if (!Number.isSafeInteger(value) || (value as number) < 0) fail(code);
  return value as number;
};

const sortedUniquePropositionIds = (
  value: unknown,
  minimum: number,
  code: ProductConflictContractErrorCode,
): readonly string[] => {
  const ids = exactArray(value, code).map((entry) => propositionId(entry, code));
  if (ids.length < minimum) fail(code);
  for (let index = 1; index < ids.length; index += 1) {
    if (ids[index - 1]!.localeCompare(ids[index]!) >= 0) fail(code);
  }
  return Object.freeze(ids);
};

const propositionCatalog = (
  value: unknown,
  owner: string,
  code: ProductConflictContractErrorCode,
): ReadonlyMap<string, ProductPropositionIdentity> => {
  const catalog = new Map<string, ProductPropositionIdentity>();
  for (const entry of exactArray(value, code)) {
    let identity: ProductPropositionIdentity;
    try {
      identity = parseProductPropositionIdentity(entry);
    } catch {
      return fail(code);
    }
    if (identity.owner_account_id !== owner || catalog.has(identity.proposition_id)) fail(code);
    catalog.set(identity.proposition_id, identity);
  }
  return catalog;
};

const requireKnown = (
  ids: readonly string[],
  catalog: ReadonlyMap<string, ProductPropositionIdentity>,
  code: ProductConflictContractErrorCode,
): void => {
  if (ids.some((id) => !catalog.has(id))) fail(code);
};

const contentAddress = (domain: string, value: unknown): string => createHash("sha256")
  .update(domain, "ascii")
  .update("\0", "ascii")
  .update(JSON.stringify(value), "utf8")
  .digest("hex");

const referenceSnapshotDigest = (
  owner: string,
  frontier: string,
  propositions: readonly ProductPropositionIdentity[],
  redirects: readonly ProductPropositionRedirect[],
): string => contentAddress("omi.product-conflict-reference-snapshot.v1", {
  owner_account_id: owner,
  graph_frontier: frontier,
  propositions: [...propositions].sort((left, right) =>
    left.proposition_id.localeCompare(right.proposition_id)),
  redirects: [...redirects].sort((left, right) =>
    left.redirect_id.localeCompare(right.redirect_id)),
});

const redirectRows = (
  value: unknown,
  owner: string,
  catalog: ReadonlyMap<string, ProductPropositionIdentity>,
  code: ProductConflictContractErrorCode,
): readonly ProductPropositionRedirect[] => {
  const redirects: ProductPropositionRedirect[] = [];
  for (const entry of exactArray(value, code)) {
    const redirect = parseProductPropositionRedirect(entry);
    if (redirect.owner_account_id !== owner
      || !catalog.has(redirect.source_proposition_id)
      || redirect.successor_proposition_ids.some((id) => !catalog.has(id))) fail(code);
    redirects.push(redirect);
  }
  return Object.freeze(redirects);
};

const occurrenceId = (value: Omit<ProductConflictOccurrence, "occurrence_id">): string =>
  `pco1_${contentAddress("omi.product-conflict-occurrence.v1", value)}`;

const resolutionInputId = (value: Omit<ProductConflictResolutionInput, "resolution_input_id">): string =>
  `pcr1_${contentAddress("omi.product-conflict-resolution-input.v1", value)}`;

const occurrenceFields = (
  value: unknown,
  propositionsValue: unknown,
): ProductConflictOccurrence => {
  const code = "invalid_conflict_occurrence" as const;
  const input = exactRecord(value, [
    "version", "owner_account_id", "occurrence_id", "original_proposition_ids",
    "graph_frontier", "reference_snapshot_digest", "detector_contract_digest", "conflict_basis_digest",
    "created_at_event_time",
  ], code);
  if (input["version"] !== PRODUCT_CONFLICT_CONTRACT_VERSION) fail(code);
  const owner = token(input["owner_account_id"], code);
  const alternatives = sortedUniquePropositionIds(input["original_proposition_ids"], 2, code);
  const catalog = propositionCatalog(propositionsValue, owner, code);
  requireKnown(alternatives, catalog, code);
  const frontier = token(input["graph_frontier"], code);
  const snapshotDigest = referenceSnapshotDigest(
    owner,
    frontier,
    alternatives.map((id) => catalog.get(id)!),
    [],
  );
  if (input["reference_snapshot_digest"] !== snapshotDigest) fail(code);
  const withoutId = {
    version: PRODUCT_CONFLICT_CONTRACT_VERSION,
    owner_account_id: owner,
    original_proposition_ids: alternatives,
    graph_frontier: frontier,
    reference_snapshot_digest: snapshotDigest,
    detector_contract_digest: digest(input["detector_contract_digest"], code),
    conflict_basis_digest: digest(input["conflict_basis_digest"], code),
    created_at_event_time: eventTime(input["created_at_event_time"], code),
  };
  const expected = occurrenceId(withoutId);
  if (input["occurrence_id"] !== expected) fail(code);
  return Object.freeze({ ...withoutId, occurrence_id: expected });
};

export const parseProductConflictOccurrence = (
  value: unknown,
  propositions: readonly ProductPropositionIdentity[],
): ProductConflictOccurrence => occurrenceFields(value, propositions);

export const buildProductConflictOccurrence = (
  inputValue: BuildProductConflictOccurrenceInput,
): ProductConflictOccurrence => {
  const code = "invalid_conflict_occurrence" as const;
  const input = exactRecord(inputValue, [
    "owner_account_id", "original_proposition_ids", "propositions", "graph_frontier",
    "detector_contract_digest", "conflict_basis_digest", "created_at_event_time",
  ], code);
  const owner = token(input["owner_account_id"], code);
  const alternatives = sortedUniquePropositionIds(input["original_proposition_ids"], 2, code);
  const propositions = exactArray(input["propositions"], code) as readonly ProductPropositionIdentity[];
  const catalog = propositionCatalog(propositions, owner, code);
  requireKnown(alternatives, catalog, code);
  const frontier = token(input["graph_frontier"], code);
  const withoutId = {
    version: PRODUCT_CONFLICT_CONTRACT_VERSION,
    owner_account_id: owner,
    original_proposition_ids: alternatives,
    graph_frontier: frontier,
    reference_snapshot_digest: referenceSnapshotDigest(
      owner,
      frontier,
      alternatives.map((id) => catalog.get(id)!),
      [],
    ),
    detector_contract_digest: digest(input["detector_contract_digest"], code),
    conflict_basis_digest: digest(input["conflict_basis_digest"], code),
    created_at_event_time: eventTime(input["created_at_event_time"], code),
  };
  return occurrenceFields({ ...withoutId, occurrence_id: occurrenceId(withoutId) }, propositions);
};

const resolutionFields = (
  value: unknown,
  occurrenceValue: unknown,
  propositionsValue: unknown,
  redirectsValue: unknown,
): ProductConflictResolutionInput => {
  const code = "invalid_conflict_resolution_input" as const;
  const input = exactRecord(value, [
    "version", "owner_account_id", "resolution_input_id", "occurrence_id",
    "original_proposition_ids", "resolved_proposition_ids", "graph_frontier", "reference_snapshot_digest",
    "operation_ref", "resolution_contract_digest", "created_at_event_time",
  ], code);
  if (input["version"] !== PRODUCT_CONFLICT_CONTRACT_VERSION) fail(code);
  const owner = token(input["owner_account_id"], code);
  const propositions = exactArray(propositionsValue, code) as readonly ProductPropositionIdentity[];
  const occurrence = occurrenceFields(occurrenceValue, propositions);
  if (occurrence.owner_account_id !== owner || input["occurrence_id"] !== occurrence.occurrence_id) fail(code);
  const originals = sortedUniquePropositionIds(input["original_proposition_ids"], 2, code);
  if (originals.length !== occurrence.original_proposition_ids.length
    || originals.some((id, index) => id !== occurrence.original_proposition_ids[index])) fail(code);
  const resolved = sortedUniquePropositionIds(input["resolved_proposition_ids"], 1, code);
  const catalog = propositionCatalog(propositions, owner, code);
  requireKnown(resolved, catalog, code);
  const redirects = redirectRows(redirectsValue, owner, catalog, code);
  const terminals = resolveTerminalPropositionIds({
    owner_account_id: owner,
    start_proposition_ids: resolved,
    propositions,
    redirects,
  });
  if (terminals.length !== resolved.length
    || terminals.some((id, index) => id !== resolved[index])) fail(code);
  const frontier = token(input["graph_frontier"], code);
  const snapshotDigest = referenceSnapshotDigest(owner, frontier, [...catalog.values()], redirects);
  if (input["reference_snapshot_digest"] !== snapshotDigest) fail(code);
  const createdAt = eventTime(input["created_at_event_time"], code);
  if (createdAt < occurrence.created_at_event_time) fail(code);
  const withoutId = {
    version: PRODUCT_CONFLICT_CONTRACT_VERSION,
    owner_account_id: owner,
    occurrence_id: occurrence.occurrence_id,
    original_proposition_ids: originals,
    resolved_proposition_ids: resolved,
    graph_frontier: frontier,
    reference_snapshot_digest: snapshotDigest,
    operation_ref: opaqueOperationRef(input["operation_ref"], code),
    resolution_contract_digest: digest(input["resolution_contract_digest"], code),
    created_at_event_time: createdAt,
  };
  const expected = resolutionInputId(withoutId);
  if (input["resolution_input_id"] !== expected) fail(code);
  return Object.freeze({ ...withoutId, resolution_input_id: expected });
};

export const parseProductConflictResolutionInput = (
  value: unknown,
  occurrence: ProductConflictOccurrence,
  propositions: readonly ProductPropositionIdentity[],
  redirects: readonly ProductPropositionRedirect[],
): ProductConflictResolutionInput =>
  resolutionFields(value, occurrence, propositions, redirects);

export const buildProductConflictResolutionInput = (
  inputValue: BuildProductConflictResolutionInput,
): ProductConflictResolutionInput => {
  const code = "invalid_conflict_resolution_input" as const;
  const input = exactRecord(inputValue, [
    "occurrence", "proposed_resolved_proposition_ids", "propositions", "redirects",
    "graph_frontier", "operation_ref", "resolution_contract_digest",
    "created_at_event_time",
  ], code);
  const propositions = exactArray(input["propositions"], code) as readonly ProductPropositionIdentity[];
  const occurrence = occurrenceFields(input["occurrence"], propositions);
  const catalog = propositionCatalog(propositions, occurrence.owner_account_id, code);
  const redirects = redirectRows(input["redirects"], occurrence.owner_account_id, catalog, code);
  const proposed = sortedUniquePropositionIds(input["proposed_resolved_proposition_ids"], 1, code);
  const resolved = resolveTerminalPropositionIds({
    owner_account_id: occurrence.owner_account_id,
    start_proposition_ids: proposed,
    propositions,
    redirects,
  });
  const frontier = token(input["graph_frontier"], code);
  const withoutId = {
    version: PRODUCT_CONFLICT_CONTRACT_VERSION,
    owner_account_id: occurrence.owner_account_id,
    occurrence_id: occurrence.occurrence_id,
    original_proposition_ids: occurrence.original_proposition_ids,
    resolved_proposition_ids: resolved,
    graph_frontier: frontier,
    reference_snapshot_digest: referenceSnapshotDigest(
      occurrence.owner_account_id,
      frontier,
      [...catalog.values()],
      redirects,
    ),
    operation_ref: opaqueOperationRef(input["operation_ref"], code),
    resolution_contract_digest: digest(input["resolution_contract_digest"], code),
    created_at_event_time: eventTime(input["created_at_event_time"], code),
  };
  return resolutionFields(
    { ...withoutId, resolution_input_id: resolutionInputId(withoutId) },
    occurrence,
    propositions,
    redirects,
  );
};
