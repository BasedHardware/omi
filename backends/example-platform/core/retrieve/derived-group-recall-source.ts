import { isProxy } from "node:util/types";

import { sha256CanonicalContent } from "./content-digest";
import {
  parseProductGroupProjection,
  type ProductGroupProjection,
} from "./product-projection";

export const DERIVED_GROUP_RECALL_SOURCE_VERSION = "derived-group-recall-source-v1" as const;

export interface DerivedGroupRecallMember {
  readonly group: ProductGroupProjection;
  readonly rendered_text: string;
}

export interface DerivedGroupRecallCandidate {
  readonly trace_ref: `tr1_${string}`;
  readonly text: string;
  readonly group_projection_id: string;
  readonly contributing_subject_classes: readonly ["derived_group"];
}

const TRACE_REF = /^tr1_[a-f0-9]{64}$/;
const MAX_TEXT = 65_536;
const MAX_GROUPS = 256;

const fail = (code: string): never => { throw new TypeError(`derived group recall source ${code}`); };

const exactRecord = (value: unknown, keys: readonly string[], code: string): Record<string, unknown> => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype) fail(code);
  const ownKeys = Reflect.ownKeys(value as object);
  if (ownKeys.length !== keys.length || ownKeys.some((key) => typeof key !== "string" || !keys.includes(key))) {
    fail(code);
  }
  for (const key of keys) {
    const descriptor = Object.getOwnPropertyDescriptor(value, key);
    if (!descriptor || !("value" in descriptor) || !descriptor.enumerable) fail(code);
  }
  return value as Record<string, unknown>;
};

const boundedText = (value: unknown, code: string): string => {
  if (typeof value !== "string" || value.length === 0 || value !== value.trim()
    || [...value].length > MAX_TEXT || /[\p{Cc}\p{Cs}]/u.test(value)) return fail(code);
  return value;
};

export const derivedGroupRecallTraceRef = (
  group: ProductGroupProjection,
): `tr1_${string}` => {
  const parsed = parseProductGroupProjection(group);
  const digest = sha256CanonicalContent({
    contract_version: DERIVED_GROUP_RECALL_SOURCE_VERSION,
    group_projection_id: parsed.group_projection_id,
  });
  return `tr1_${digest}`;
};

export const parseDerivedGroupRecallMembers = (
  value: unknown,
): readonly DerivedGroupRecallMember[] => {
  if (!Array.isArray(value) || isProxy(value) || value.length > MAX_GROUPS) fail("invalid_members");
  const members = (value as unknown[]).map((item) => {
    const input = exactRecord(item, ["group", "rendered_text"], "invalid_members");
    return Object.freeze({
      group: parseProductGroupProjection(input["group"]),
      rendered_text: boundedText(input["rendered_text"], "invalid_members"),
    });
  });
  const ids = members.map((member) => member.group.group_projection_id);
  if (new Set(ids).size !== ids.length) fail("duplicate_group");
  return Object.freeze(members);
};

/**
 * Product recall candidates are derived groups only. Unconsolidated card bags
 * are rejected by requiring ProductGroupProjection members.
 */
export const buildDerivedGroupRecallCandidates = (
  membersValue: unknown,
): readonly DerivedGroupRecallCandidate[] => {
  const members = parseDerivedGroupRecallMembers(membersValue);
  const candidates = members.map((member) => {
    const traceRef = derivedGroupRecallTraceRef(member.group);
    if (!TRACE_REF.test(traceRef)) fail("invalid_trace");
    return Object.freeze({
      trace_ref: traceRef,
      text: member.rendered_text,
      group_projection_id: member.group.group_projection_id,
      contributing_subject_classes: Object.freeze(["derived_group"] as const),
    });
  }).sort((left, right) => left.trace_ref < right.trace_ref ? -1 : left.trace_ref > right.trace_ref ? 1 : 0);
  return Object.freeze(candidates);
};

export const derivedGroupRecallProjectedContentDigest = (
  membersValue: unknown,
): string => {
  const members = parseDerivedGroupRecallMembers(membersValue);
  return sha256CanonicalContent({
    contract_version: DERIVED_GROUP_RECALL_SOURCE_VERSION,
    groups: members.map((member) => Object.freeze({
      group_projection_id: member.group.group_projection_id,
      result_digest: member.group.result_digest,
      input_frontier: member.group.input_frontier,
      rendered_text: member.rendered_text,
    })).sort((left, right) => left.group_projection_id < right.group_projection_id
      ? -1 : left.group_projection_id > right.group_projection_id ? 1 : 0),
  });
};

export const derivedGroupRecallInputFrontierDigest = (
  membersValue: unknown,
): string => {
  const members = parseDerivedGroupRecallMembers(membersValue);
  const frontiers = [...new Set(members.map((member) => member.group.input_frontier))].sort();
  if (frontiers.length !== 1) fail("mixed_frontier");
  return sha256CanonicalContent({
    contract_version: DERIVED_GROUP_RECALL_SOURCE_VERSION,
    input_frontier: frontiers[0],
  });
};
