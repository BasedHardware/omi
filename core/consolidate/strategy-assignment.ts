import { createHash, createHmac } from "node:crypto";
import { isProxy } from "node:util/types";

import type { DurableMemoryWorkKind } from "./state-machine";
import { sha256CanonicalContent } from "../retrieve/content-digest";

export const MEMORY_STRATEGY_VERSION = "memory-strategy-v1" as const;
export const MEMORY_STRATEGY_ASSIGNMENT_POLICY_VERSION = "memory-strategy-assignment-policy-v1" as const;
export const MEMORY_STRATEGY_ASSIGNMENT_VERSION = "memory-strategy-assignment-v1" as const;

export type MemoryStrategyAssignmentUnitKind = "account" | "session" | "work";
export type MemoryStrategyAssignmentMode = "authority" | "shadow";
export type MemoryStrategyKind = DurableMemoryWorkKind | "retrieval" | "composition";

export interface MemoryStrategyCoordinates {
  readonly strategy_version: string;
  readonly model_version: string;
  readonly prompt_version: string;
  readonly policy_version: string;
  readonly code_version: string;
  readonly schema_version: string;
  readonly tokenizer_version: string;
  readonly tool_version: string;
  readonly result_contract_version: string;
  readonly speaker_strategy_version: string;
  readonly boundary_strategy_version: string;
}

export interface MemoryStrategyDefinition {
  readonly version: typeof MEMORY_STRATEGY_VERSION;
  readonly strategy_id: string;
  readonly work_kind: MemoryStrategyKind;
  readonly coordinates: Readonly<MemoryStrategyCoordinates>;
}

export interface RegisteredMemoryStrategy extends MemoryStrategyDefinition {
  readonly execution_contract_digest: string;
}

export interface MemoryStrategyShadowPolicyEntry {
  readonly strategy_id: string;
  readonly execution_contract_digest: string;
  readonly basis_points: number;
}

export interface MemoryStrategyAssignmentPolicy {
  readonly version: typeof MEMORY_STRATEGY_ASSIGNMENT_POLICY_VERSION;
  readonly policy_id: string;
  readonly policy_digest: string;
  readonly work_kind: MemoryStrategyKind;
  readonly unit_kind: MemoryStrategyAssignmentUnitKind;
  readonly key_version: string;
  readonly authority_strategy_id: string;
  readonly authority_execution_contract_digest: string;
  readonly shadow_candidates: readonly Readonly<MemoryStrategyShadowPolicyEntry>[];
}

export interface MemoryStrategyAssignmentEntry {
  readonly assignment_id: string;
  readonly mode: MemoryStrategyAssignmentMode;
  readonly strategy_id: string;
  readonly execution_contract_digest: string;
  readonly bucket: number | null;
  readonly basis_points: number | null;
}

export interface MemoryStrategyAssignmentBundle {
  readonly version: typeof MEMORY_STRATEGY_ASSIGNMENT_VERSION;
  readonly assignment_bundle_id: string;
  readonly assignment_bundle_digest: string;
  readonly owner_account_id: string;
  readonly work_kind: MemoryStrategyKind;
  readonly unit_kind: MemoryStrategyAssignmentUnitKind;
  readonly unit_digest: string;
  readonly policy: Readonly<MemoryStrategyAssignmentPolicy>;
  readonly strategies: readonly Readonly<RegisteredMemoryStrategy>[];
  readonly authority: Readonly<MemoryStrategyAssignmentEntry>;
  readonly shadows: readonly Readonly<MemoryStrategyAssignmentEntry>[];
}

export interface MemoryStrategyAssignmentPolicyInput {
  readonly policy_id: string;
  readonly work_kind: MemoryStrategyKind;
  readonly unit_kind: MemoryStrategyAssignmentUnitKind;
  readonly key_version: string;
  readonly authority_strategy_id: string;
  readonly shadow_candidates: readonly Readonly<{
    strategy_id: string;
    basis_points: number;
  }>[];
}

const TOKEN = /^[\x21-\x7e]{1,256}$/;
const DIGEST = /^[a-f0-9]{64}$/;
const WORK_KINDS = new Set<MemoryStrategyKind>([
  "formation", "promotion", "identity_cluster", "predicate_batch", "retrieval", "composition",
]);
const UNIT_KINDS = new Set<MemoryStrategyAssignmentUnitKind>(["account", "session", "work"]);
const COORDINATE_KEYS = [
  "strategy_version", "model_version", "prompt_version", "policy_version",
  "code_version", "schema_version", "tokenizer_version", "tool_version",
  "result_contract_version", "speaker_strategy_version", "boundary_strategy_version",
] as const satisfies readonly (keyof MemoryStrategyCoordinates)[];
const mintedAssignments = new WeakSet<object>();

const fail = (code: string): never => { throw new TypeError(`memory strategy ${code}`); };

const exactRecord = (value: unknown, keys: readonly string[], code: string): Record<string, unknown> => {
  if (value === null || typeof value !== "object" || Array.isArray(value)) fail(code);
  const objectValue = value as object;
  if (isProxy(objectValue) || Object.getPrototypeOf(objectValue) !== Object.prototype) fail(code);
  const ownKeys = Reflect.ownKeys(objectValue);
  if (ownKeys.some((key) => typeof key !== "string")) fail(code);
  const actual = (ownKeys as string[]).sort();
  const expected = [...keys].sort();
  if (actual.length !== expected.length || actual.some((key, index) => key !== expected[index])) fail(code);
  for (const key of actual) {
    const descriptor = Object.getOwnPropertyDescriptor(objectValue, key);
    if (!descriptor || !("value" in descriptor) || !descriptor.enumerable) fail(code);
  }
  return value as Record<string, unknown>;
};

const exactArray = (value: unknown, maximum: number, code: string): readonly unknown[] => {
  if (!Array.isArray(value)) fail(code);
  const arrayValue = value as unknown[];
  if (isProxy(arrayValue) || Object.getPrototypeOf(arrayValue) !== Array.prototype
    || arrayValue.length > maximum) fail(code);
  const keys = Reflect.ownKeys(arrayValue);
  if (keys.length !== arrayValue.length + 1) fail(code);
  const output: unknown[] = [];
  for (let index = 0; index < arrayValue.length; index += 1) {
    const descriptor = Object.getOwnPropertyDescriptor(arrayValue, String(index));
    if (!descriptor || !("value" in descriptor) || !descriptor.enumerable) fail(code);
    output.push((descriptor as PropertyDescriptor & { value: unknown }).value);
  }
  if (keys.some((key) => typeof key !== "string"
    || (key !== "length" && (!/^(0|[1-9]\d*)$/.test(key) || Number(key) >= arrayValue.length)))) fail(code);
  return output;
};

const token = (value: unknown, code: string): string => {
  if (typeof value !== "string" || !TOKEN.test(value)) fail(code);
  return value as string;
};

const digest = (value: unknown, code: string): string => {
  if (typeof value !== "string" || !DIGEST.test(value)) fail(code);
  return value as string;
};

const workKind = (value: unknown, code: string): MemoryStrategyKind => {
  if (typeof value !== "string" || !WORK_KINDS.has(value as MemoryStrategyKind)) fail(code);
  return value as MemoryStrategyKind;
};

const unitKind = (value: unknown, code: string): MemoryStrategyAssignmentUnitKind => {
  if (typeof value !== "string" || !UNIT_KINDS.has(value as MemoryStrategyAssignmentUnitKind)) fail(code);
  return value as MemoryStrategyAssignmentUnitKind;
};

const basisPoints = (value: unknown): number => {
  if (!Number.isSafeInteger(value) || (value as number) < 0 || (value as number) > 10_000) {
    fail("invalid_basis_points");
  }
  return value as number;
};

const compareStrings = (left: string, right: string): number => left < right ? -1 : left > right ? 1 : 0;

const freezeCoordinates = (value: unknown): Readonly<MemoryStrategyCoordinates> => {
  const input = exactRecord(value, COORDINATE_KEYS, "invalid_coordinates");
  const coordinates = Object.fromEntries(COORDINATE_KEYS.map((key) => [
    key, token(input[key], "invalid_coordinates"),
  ])) as unknown as MemoryStrategyCoordinates;
  return Object.freeze(coordinates);
};

export const memoryStrategyExecutionContractDigest = (definition: MemoryStrategyDefinition): string => {
  const normalized = normalizeMemoryStrategyDefinition(definition);
  return sha256CanonicalContent({
    contract_version: MEMORY_STRATEGY_VERSION,
    strategy_id: normalized.strategy_id,
    work_kind: normalized.work_kind,
    coordinates: normalized.coordinates,
  });
};

const normalizeMemoryStrategyDefinition = (value: unknown): Readonly<MemoryStrategyDefinition> => {
  const input = exactRecord(value, ["version", "strategy_id", "work_kind", "coordinates"], "invalid_definition");
  if (input["version"] !== MEMORY_STRATEGY_VERSION) fail("invalid_definition");
  return Object.freeze({
    version: MEMORY_STRATEGY_VERSION,
    strategy_id: token(input["strategy_id"], "invalid_definition"),
    work_kind: workKind(input["work_kind"], "invalid_definition"),
    coordinates: freezeCoordinates(input["coordinates"]),
  });
};

export const registerMemoryStrategy = (value: MemoryStrategyDefinition): Readonly<RegisteredMemoryStrategy> => {
  const definition = normalizeMemoryStrategyDefinition(value);
  return Object.freeze({
    ...definition,
    execution_contract_digest: memoryStrategyExecutionContractDigest(definition),
  });
};

const normalizeRegisteredStrategy = (value: unknown): Readonly<RegisteredMemoryStrategy> => {
  const input = exactRecord(value, [
    "version", "strategy_id", "work_kind", "coordinates", "execution_contract_digest",
  ], "invalid_registered_strategy");
  const definition = normalizeMemoryStrategyDefinition({
    version: input["version"],
    strategy_id: input["strategy_id"],
    work_kind: input["work_kind"],
    coordinates: input["coordinates"],
  });
  const actualDigest = digest(input["execution_contract_digest"], "invalid_registered_strategy");
  const expectedDigest = memoryStrategyExecutionContractDigest(definition);
  if (actualDigest !== expectedDigest) fail("strategy_digest_mismatch");
  return Object.freeze({ ...definition, execution_contract_digest: actualDigest });
};

/** Strict plain-data validation for a registry adapter or worker composition. */
export const parseRegisteredMemoryStrategy = (
  value: unknown,
): Readonly<RegisteredMemoryStrategy> => normalizeRegisteredStrategy(value);

const normalizeRegistry = (
  value: readonly RegisteredMemoryStrategy[],
  expectedWorkKind?: MemoryStrategyKind,
): readonly Readonly<RegisteredMemoryStrategy>[] => {
  const strategies = exactArray(value, 128, "invalid_registry")
    .map(normalizeRegisteredStrategy)
    .sort((left, right) => compareStrings(left.strategy_id, right.strategy_id));
  if (strategies.length === 0) fail("empty_registry");
  for (let index = 0; index < strategies.length; index += 1) {
    const strategy = strategies[index]!;
    if (expectedWorkKind && strategy.work_kind !== expectedWorkKind) fail("strategy_work_kind_mismatch");
    if (index > 0 && strategies[index - 1]!.strategy_id === strategy.strategy_id) fail("duplicate_strategy_id");
  }
  return Object.freeze(strategies);
};

export const defineMemoryStrategyAssignmentPolicy = (
  value: MemoryStrategyAssignmentPolicyInput,
  registryValue: readonly RegisteredMemoryStrategy[],
): Readonly<MemoryStrategyAssignmentPolicy> => {
  const input = exactRecord(value, [
    "policy_id", "work_kind", "unit_kind", "key_version",
    "authority_strategy_id", "shadow_candidates",
  ], "invalid_policy");
  const normalizedWorkKind = workKind(input["work_kind"], "invalid_policy");
  const registry = normalizeRegistry(registryValue, normalizedWorkKind);
  const byId = new Map(registry.map((strategy) => [strategy.strategy_id, strategy]));
  const authorityStrategyId = token(input["authority_strategy_id"], "invalid_policy");
  const authority = byId.get(authorityStrategyId);
  if (!authority) fail("unknown_authority_strategy");
  const shadowCandidates = exactArray(input["shadow_candidates"], 32, "invalid_policy")
    .map((candidate) => {
      const item = exactRecord(candidate, ["strategy_id", "basis_points"], "invalid_policy");
      const strategyId = token(item["strategy_id"], "invalid_policy");
      if (strategyId === authorityStrategyId) fail("authority_cannot_be_shadow");
      const strategy = byId.get(strategyId);
      if (!strategy) fail("unknown_shadow_strategy");
      return Object.freeze({
        strategy_id: strategyId,
        execution_contract_digest: strategy!.execution_contract_digest,
        basis_points: basisPoints(item["basis_points"]),
      });
    })
    .sort((left, right) => compareStrings(left.strategy_id, right.strategy_id));
  for (let index = 1; index < shadowCandidates.length; index += 1) {
    if (shadowCandidates[index - 1]!.strategy_id === shadowCandidates[index]!.strategy_id) {
      fail("duplicate_shadow_strategy");
    }
  }
  const policyCore = Object.freeze({
    version: MEMORY_STRATEGY_ASSIGNMENT_POLICY_VERSION,
    policy_id: token(input["policy_id"], "invalid_policy"),
    work_kind: normalizedWorkKind,
    unit_kind: unitKind(input["unit_kind"], "invalid_policy"),
    key_version: token(input["key_version"], "invalid_policy"),
    authority_strategy_id: authorityStrategyId,
    authority_execution_contract_digest: authority!.execution_contract_digest,
    shadow_candidates: Object.freeze(shadowCandidates),
  });
  return Object.freeze({
    ...policyCore,
    policy_digest: sha256CanonicalContent(policyCore),
  });
};

const hmacHex = (key: Uint8Array, value: unknown): string => createHmac("sha256", key)
  .update(JSON.stringify(value)).digest("hex");

const assignmentId = (value: unknown): string => `msa1_${sha256CanonicalContent(value)}`;

export interface MemoryStrategyAssigner {
  assign(input: MemoryStrategyAssignmentInput): Readonly<MemoryStrategyAssignmentBundle>;
}

export type MemoryStrategyAssignmentInput = Readonly<{
  owner_account_id: string;
  unit_ref: string;
  policy: MemoryStrategyAssignmentPolicy;
  strategies: readonly RegisteredMemoryStrategy[];
}>;

export const createMemoryStrategyAssigner = (secretValue: Uint8Array): MemoryStrategyAssigner => {
  if (!(secretValue instanceof Uint8Array) || isProxy(secretValue)
    || secretValue.byteLength < 32 || secretValue.byteLength > 128) fail("invalid_assignment_secret");
  const secret = Uint8Array.from(secretValue);
  return Object.freeze({
    assign(value: MemoryStrategyAssignmentInput) {
      const input = exactRecord(value, ["owner_account_id", "unit_ref", "policy", "strategies"], "invalid_assignment");
      const ownerAccountId = token(input["owner_account_id"], "invalid_assignment");
      const unitRef = token(input["unit_ref"], "invalid_assignment");
      const policy = normalizeMemoryStrategyAssignmentPolicy(input["policy"]);
      const strategies = normalizeRegistry(input["strategies"] as readonly RegisteredMemoryStrategy[], policy.work_kind);
      const byId = new Map(strategies.map((strategy) => [strategy.strategy_id, strategy]));
      const authorityStrategy = byId.get(policy.authority_strategy_id);
      if (!authorityStrategy
        || authorityStrategy.execution_contract_digest !== policy.authority_execution_contract_digest) {
        fail("authority_strategy_mismatch");
      }
      for (const candidate of policy.shadow_candidates) {
        const strategy = byId.get(candidate.strategy_id);
        if (!strategy || strategy.execution_contract_digest !== candidate.execution_contract_digest) {
          fail("shadow_strategy_mismatch");
        }
      }
      const unitDigest = hmacHex(secret, {
        contract_version: MEMORY_STRATEGY_ASSIGNMENT_VERSION,
        owner_account_id: ownerAccountId,
        unit_kind: policy.unit_kind,
        unit_ref: unitRef,
      });
      const authority = Object.freeze({
        assignment_id: assignmentId({
          owner_account_id: ownerAccountId,
          policy_digest: policy.policy_digest,
          unit_digest: unitDigest,
          mode: "authority",
          strategy_id: authorityStrategy!.strategy_id,
          execution_contract_digest: authorityStrategy!.execution_contract_digest,
        }),
        mode: "authority" as const,
        strategy_id: authorityStrategy!.strategy_id,
        execution_contract_digest: authorityStrategy!.execution_contract_digest,
        bucket: null,
        basis_points: null,
      });
      const shadows = policy.shadow_candidates.flatMap((candidate) => {
        const bucketHex = hmacHex(secret, {
          contract_version: MEMORY_STRATEGY_ASSIGNMENT_VERSION,
          owner_account_id: ownerAccountId,
          unit_kind: policy.unit_kind,
          unit_ref: unitRef,
          policy_digest: policy.policy_digest,
          strategy_id: candidate.strategy_id,
        });
        const bucket = Number(BigInt(`0x${bucketHex.slice(0, 16)}`) % 10_000n);
        if (bucket >= candidate.basis_points) return [];
        return [Object.freeze({
          assignment_id: assignmentId({
            owner_account_id: ownerAccountId,
            policy_digest: policy.policy_digest,
            unit_digest: unitDigest,
            mode: "shadow",
            strategy_id: candidate.strategy_id,
            execution_contract_digest: candidate.execution_contract_digest,
            bucket,
            basis_points: candidate.basis_points,
          }),
          mode: "shadow" as const,
          strategy_id: candidate.strategy_id,
          execution_contract_digest: candidate.execution_contract_digest,
          bucket,
          basis_points: candidate.basis_points,
        })];
      });
      const bundleCore = Object.freeze({
        version: MEMORY_STRATEGY_ASSIGNMENT_VERSION,
        owner_account_id: ownerAccountId,
        work_kind: policy.work_kind,
        unit_kind: policy.unit_kind,
        unit_digest: unitDigest,
        policy,
        strategies,
        authority,
        shadows: Object.freeze(shadows),
      });
      const assignmentBundleDigest = sha256CanonicalContent(bundleCore);
      const bundle = Object.freeze({
        ...bundleCore,
        assignment_bundle_id: `msb1_${assignmentBundleDigest}`,
        assignment_bundle_digest: assignmentBundleDigest,
      });
      mintedAssignments.add(bundle);
      return bundle;
    },
  });
};

const normalizeMemoryStrategyAssignmentPolicy = (value: unknown): Readonly<MemoryStrategyAssignmentPolicy> => {
  const input = exactRecord(value, [
    "version", "policy_id", "policy_digest", "work_kind", "unit_kind", "key_version",
    "authority_strategy_id", "authority_execution_contract_digest", "shadow_candidates",
  ], "invalid_policy");
  if (input["version"] !== MEMORY_STRATEGY_ASSIGNMENT_POLICY_VERSION) fail("invalid_policy");
  const candidates = exactArray(input["shadow_candidates"], 32, "invalid_policy")
    .map((candidate) => {
      const item = exactRecord(candidate, [
        "strategy_id", "execution_contract_digest", "basis_points",
      ], "invalid_policy");
      return Object.freeze({
        strategy_id: token(item["strategy_id"], "invalid_policy"),
        execution_contract_digest: digest(item["execution_contract_digest"], "invalid_policy"),
        basis_points: basisPoints(item["basis_points"]),
      });
    })
    .sort((left, right) => compareStrings(left.strategy_id, right.strategy_id));
  for (let index = 0; index < candidates.length; index += 1) {
    if (candidates[index]!.strategy_id === input["authority_strategy_id"]) {
      fail("authority_cannot_be_shadow");
    }
    if (index > 0 && candidates[index - 1]!.strategy_id === candidates[index]!.strategy_id) {
      fail("duplicate_shadow_strategy");
    }
  }
  const core = Object.freeze({
    version: MEMORY_STRATEGY_ASSIGNMENT_POLICY_VERSION,
    policy_id: token(input["policy_id"], "invalid_policy"),
    work_kind: workKind(input["work_kind"], "invalid_policy"),
    unit_kind: unitKind(input["unit_kind"], "invalid_policy"),
    key_version: token(input["key_version"], "invalid_policy"),
    authority_strategy_id: token(input["authority_strategy_id"], "invalid_policy"),
    authority_execution_contract_digest: digest(input["authority_execution_contract_digest"], "invalid_policy"),
    shadow_candidates: Object.freeze(candidates),
  });
  const policyDigest = digest(input["policy_digest"], "invalid_policy");
  if (sha256CanonicalContent(core) !== policyDigest) fail("policy_digest_mismatch");
  return Object.freeze({ ...core, policy_digest: policyDigest });
};

/** Only assignments minted by the injected deterministic selector enter evaluation or work acceptance. */
export const assertMintedMemoryStrategyAssignment = (
  value: unknown,
): Readonly<MemoryStrategyAssignmentBundle> => {
  if (value === null || typeof value !== "object" || !mintedAssignments.has(value)) {
    fail("unminted_assignment");
  }
  return value as Readonly<MemoryStrategyAssignmentBundle>;
};
