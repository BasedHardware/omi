import { isProxy } from "node:util/types";

import {
  planLegacyPropositionMapping,
  type LegacyPropositionMapping,
} from "../../../core/retrieve/product-projection";
import { sha256CanonicalContent } from "../../../core/retrieve/content-digest";
import {
  assertAuthorizedLedgerWriteContext,
  type AuthorizedLedgerWriteContext,
} from "../auth/authorized-context";

const PORT: unique symbol = Symbol("legacy-proposition-migration-repository");
const CAPABILITY = "memories.project";
const TOKEN = /^[\x21-\x7e]{1,256}$/;
const DIGEST = /^[a-f0-9]{64}$/;

export interface LegacyPropositionMappingResumeBody {
  readonly legacy_source_id: string;
  readonly proposed_random_opaque_proposition_id: string | null;
}

export interface LegacyPropositionMappingResumeRequest extends LegacyPropositionMappingResumeBody {
  readonly request_digest: string;
}

export interface LegacyMigrationTombstoneBody {
  readonly legacy_source_id: string;
  readonly tombstone_sequence: number;
  readonly tombstone_operation_id: string;
  readonly tombstoned_at_event_time: number;
}

export interface LegacyMigrationTombstoneRequest extends LegacyMigrationTombstoneBody {
  readonly request_digest: string;
}

type CommonOutcome =
  | Readonly<{ kind: "serialization_retryable" }>
  | Readonly<{ kind: "stale_context"; reason: "expired_context" | "stale_epoch" | "destination_inactive" | "lifecycle_inactive" }>
  | Readonly<{ kind: "authorization_denied"; reason: "credential_inactive" | "grant_inactive" | "capability_denied" }>;

export type LegacyPropositionMappingResumeOutcome =
  | Readonly<{ kind: "allocation_required" | "tombstoned" }>
  | Readonly<{ kind: "inserted" | "reused"; mapping: LegacyPropositionMapping }>
  | Readonly<{ kind: "idempotency_conflict" }>
  | CommonOutcome;

export type LegacyMigrationTombstoneOutcome =
  | Readonly<{ kind: "recorded" | "replayed" }>
  | Readonly<{ kind: "idempotency_conflict" }>
  | CommonOutcome;

export interface LegacyPropositionMigrationRepository {
  readonly [PORT]: true;
  resumeMapping(
    context: AuthorizedLedgerWriteContext,
    request: LegacyPropositionMappingResumeRequest,
  ): Promise<LegacyPropositionMappingResumeOutcome>;
  recordTombstone(
    context: AuthorizedLedgerWriteContext,
    request: LegacyMigrationTombstoneRequest,
  ): Promise<LegacyMigrationTombstoneOutcome>;
}

export interface LegacyPropositionMigrationImplementation {
  resumeMapping(
    context: AuthorizedLedgerWriteContext,
    request: LegacyPropositionMappingResumeRequest,
  ): Promise<unknown>;
  recordTombstone(
    context: AuthorizedLedgerWriteContext,
    request: LegacyMigrationTombstoneRequest,
  ): Promise<unknown>;
}

const fail = (code: string): never => {
  throw new TypeError(`legacy proposition migration repository ${code}`);
};

const exactRecord = (value: unknown, keys: readonly string[], code: string): Record<string, unknown> => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype) fail(code);
  const descriptors = Object.getOwnPropertyDescriptors(value);
  const actual = Reflect.ownKeys(descriptors);
  if (actual.length !== keys.length || actual.some((key) => typeof key !== "string" || !keys.includes(key))) fail(code);
  const output: Record<string, unknown> = {};
  for (const key of keys) {
    const descriptor = descriptors[key];
    if (!descriptor || !descriptor.enumerable || !("value" in descriptor)) fail(code);
    output[key] = descriptor.value;
  }
  return output;
};

const token = (value: unknown, code: string): string => {
  if (typeof value !== "string" || !TOKEN.test(value)) fail(code);
  return value;
};

const safeInteger = (value: unknown, minimum: number, code: string): number => {
  if (!Number.isSafeInteger(value) || (value as number) < minimum) fail(code);
  return value as number;
};

export const legacyPropositionMappingResumeRequestDigest = (
  ownerAccountId: string,
  body: LegacyPropositionMappingResumeBody,
): string => sha256CanonicalContent({
  contract_version: "legacy-proposition-mapping-resume-v1",
  owner_account_id: ownerAccountId,
  ...body,
});

export const legacyMigrationTombstoneRequestDigest = (
  ownerAccountId: string,
  body: LegacyMigrationTombstoneBody,
): string => sha256CanonicalContent({
  contract_version: "legacy-migration-item-tombstone-v1",
  owner_account_id: ownerAccountId,
  ...body,
});

const resumeRequest = (
  context: AuthorizedLedgerWriteContext,
  value: unknown,
): Readonly<LegacyPropositionMappingResumeRequest> => {
  const row = exactRecord(value, [
    "legacy_source_id", "proposed_random_opaque_proposition_id", "request_digest",
  ], "invalid_resume_request");
  const legacySourceId = token(row["legacy_source_id"], "invalid_resume_request");
  const proposed = row["proposed_random_opaque_proposition_id"] === null
    ? null : token(row["proposed_random_opaque_proposition_id"], "invalid_resume_request");
  planLegacyPropositionMapping({
    owner_account_id: context.account_id,
    legacy_source_id: legacySourceId,
    item_tombstoned: false,
    existing_mapping: null,
    proposed_random_opaque_proposition_id: proposed,
  });
  const body = Object.freeze({
    legacy_source_id: legacySourceId,
    proposed_random_opaque_proposition_id: proposed,
  });
  if (typeof row["request_digest"] !== "string" || !DIGEST.test(row["request_digest"])
    || row["request_digest"] !== legacyPropositionMappingResumeRequestDigest(context.account_id, body)) {
    fail("invalid_resume_request");
  }
  return Object.freeze({ ...body, request_digest: row["request_digest"] });
};

const tombstoneRequest = (
  context: AuthorizedLedgerWriteContext,
  value: unknown,
): Readonly<LegacyMigrationTombstoneRequest> => {
  const row = exactRecord(value, [
    "legacy_source_id", "tombstone_sequence", "tombstone_operation_id",
    "tombstoned_at_event_time", "request_digest",
  ], "invalid_tombstone_request");
  const body = Object.freeze({
    legacy_source_id: token(row["legacy_source_id"], "invalid_tombstone_request"),
    tombstone_sequence: safeInteger(row["tombstone_sequence"], 1, "invalid_tombstone_request"),
    tombstone_operation_id: token(row["tombstone_operation_id"], "invalid_tombstone_request"),
    tombstoned_at_event_time: safeInteger(row["tombstoned_at_event_time"], 0, "invalid_tombstone_request"),
  });
  if (typeof row["request_digest"] !== "string" || !DIGEST.test(row["request_digest"])
    || row["request_digest"] !== legacyMigrationTombstoneRequestDigest(context.account_id, body)) {
    fail("invalid_tombstone_request");
  }
  return Object.freeze({ ...body, request_digest: row["request_digest"] });
};

const commonOutcome = (value: unknown): CommonOutcome | Readonly<{ kind: "idempotency_conflict" }> | null => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype) return null;
  const descriptors = Object.getOwnPropertyDescriptors(value);
  const kindDescriptor = descriptors["kind"];
  if (!kindDescriptor || !kindDescriptor.enumerable || !("value" in kindDescriptor)
    || typeof kindDescriptor.value !== "string") return null;
  const commonKinds = [
    "serialization_retryable", "idempotency_conflict", "stale_context", "authorization_denied",
  ];
  if (!commonKinds.includes(kindDescriptor.value)) return null;
  const row = exactRecord(value,
    kindDescriptor.value === "stale_context" || kindDescriptor.value === "authorization_denied"
      ? ["kind", "reason"] : ["kind"], "invalid_outcome");
  if (row["kind"] === "serialization_retryable" || row["kind"] === "idempotency_conflict") {
    if (Reflect.ownKeys(row).length !== 1) fail("invalid_outcome");
    return Object.freeze({ kind: row["kind"] });
  }
  if (row["kind"] === "stale_context"
    && ["expired_context", "stale_epoch", "destination_inactive", "lifecycle_inactive"]
      .includes(row["reason"] as string)) {
    return Object.freeze({ kind: row["kind"], reason: row["reason"] }) as CommonOutcome;
  }
  if (row["kind"] === "authorization_denied"
    && ["credential_inactive", "grant_inactive", "capability_denied"]
      .includes(row["reason"] as string)) {
    return Object.freeze({ kind: row["kind"], reason: row["reason"] }) as CommonOutcome;
  }
  return null;
};

const resumeOutcome = (
  context: AuthorizedLedgerWriteContext,
  request: LegacyPropositionMappingResumeRequest,
  value: unknown,
): LegacyPropositionMappingResumeOutcome => {
  const common = commonOutcome(value);
  if (common) return common;
  const hasMapping = value !== null && typeof value === "object" && !isProxy(value)
    && Object.prototype.hasOwnProperty.call(value, "mapping");
  const row = exactRecord(value, hasMapping ? ["kind", "mapping"] : ["kind"], "invalid_resume_outcome");
  if (row["kind"] === "allocation_required" || row["kind"] === "tombstoned") {
    if (hasMapping) fail("invalid_resume_outcome");
    return Object.freeze({ kind: row["kind"] });
  }
  if (row["kind"] !== "inserted" && row["kind"] !== "reused") fail("invalid_resume_outcome");
  const mapping = exactRecord(row["mapping"], [
    "version", "owner_account_id", "legacy_source_id", "proposition_id",
  ], "invalid_resume_outcome") as unknown as LegacyPropositionMapping;
  const checked = planLegacyPropositionMapping({
    owner_account_id: context.account_id,
    legacy_source_id: request.legacy_source_id,
    item_tombstoned: false,
    existing_mapping: mapping,
    proposed_random_opaque_proposition_id: null,
  });
  if (checked.kind !== "reuse_mapping") fail("invalid_resume_outcome");
  if (row["kind"] === "inserted"
    && (request.proposed_random_opaque_proposition_id === null
      || checked.mapping.proposition_id !== request.proposed_random_opaque_proposition_id)) {
    fail("invalid_resume_outcome");
  }
  return Object.freeze({ kind: row["kind"], mapping: checked.mapping });
};

const tombstoneOutcome = (value: unknown): LegacyMigrationTombstoneOutcome => {
  const common = commonOutcome(value);
  if (common) return common;
  const row = exactRecord(value, ["kind"], "invalid_tombstone_outcome");
  if (row["kind"] !== "recorded" && row["kind"] !== "replayed") {
    fail("invalid_tombstone_outcome");
  }
  return Object.freeze({ kind: row["kind"] });
};

export const defineLegacyPropositionMigrationRepository = (
  implementationValue: LegacyPropositionMigrationImplementation,
): LegacyPropositionMigrationRepository => {
  const implementation = exactRecord(implementationValue, [
    "resumeMapping", "recordTombstone",
  ], "invalid_implementation");
  const resume = implementation["resumeMapping"];
  const tombstone = implementation["recordTombstone"];
  if (typeof resume !== "function" || isProxy(resume) || typeof tombstone !== "function" || isProxy(tombstone)) {
    fail("invalid_implementation");
  }
  return Object.freeze({
    [PORT]: true as const,
    async resumeMapping(contextValue, requestValue) {
      const context = assertAuthorizedLedgerWriteContext(contextValue);
      if (context.capability !== CAPABILITY) fail("capability_denied");
      const request = resumeRequest(context, requestValue);
      return resumeOutcome(context, request, await Reflect.apply(
        resume, implementationValue, [context, request],
      ));
    },
    async recordTombstone(contextValue, requestValue) {
      const context = assertAuthorizedLedgerWriteContext(contextValue);
      if (context.capability !== CAPABILITY) fail("capability_denied");
      const request = tombstoneRequest(context, requestValue);
      return tombstoneOutcome(await Reflect.apply(
        tombstone, implementationValue, [context, request],
      ));
    },
  });
};
