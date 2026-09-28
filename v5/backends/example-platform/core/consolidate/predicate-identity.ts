import { sha256CanonicalRedacted } from "../ledger";
import type { Predicate } from "../schema";

/**
 * Predicate identity normalization v2. The version lives in the digest input,
 * so any future semantic normalization is a migration instead of a silent
 * rewrite of existing vocabulary coordinates.
 */
export const normalizePredicateName = (name: string): string =>
  name.trim().toLowerCase().replace(/[\s\-]+/g, "_");

/** A predicate is its normalized relation name, never a window-local slot set. */
export const predicateIdForName = (name: string): string => {
  const normalized = normalizePredicateName(name);
  if (!normalized) throw new Error("predicate identity requires a non-empty normalized name");
  return `predicate:${sha256CanonicalRedacted({ kind: "predicate-name-v2", name: normalized })}`;
};

export interface PredicateObservation {
  owner_account_id: string;
  predicate_id: string;
  display_name: string;
  /** Semantic argument roles observed in this claim, never slot ordinals. */
  roles: readonly string[];
  lifecycle?: Predicate["lifecycle"];
}

export interface StoredPredicateObservation extends PredicateObservation {
  /** Historical name-plus-window-slot claims carry this exact slot set. */
  legacy_slot_ids: readonly string[];
}

/**
 * One name may be observed with several optional role sets and renderings.
 * Each varying content shape receives its own immutable revision while all
 * revisions share the name-only predicate id.
 */
export const predicateRevisionForObservation = (input: PredicateObservation): { revision_id: string; predicate: Predicate } => {
  const identity_name = normalizePredicateName(input.display_name);
  const expectedPredicateId = predicateIdForName(input.display_name);
  if (input.predicate_id !== expectedPredicateId) {
    throw new Error("predicate observation id does not match normalized name identity");
  }
  const observed_roles = [...new Set(input.roles.map((role) => role.trim()).filter(Boolean))].sort();
  const revisionDigest = sha256CanonicalRedacted({
    kind: "predicate-revision-v2",
    owner_account_id: input.owner_account_id,
    predicate_id: input.predicate_id,
    identity_version: "name-v2",
    identity_name,
    display_name: input.display_name,
    observed_roles,
    lifecycle: input.lifecycle ?? "canonical",
  });
  const revision_id = `${input.predicate_id}:revision:${revisionDigest}`;
  return {
    revision_id,
    predicate: {
      predicate_id: input.predicate_id,
      owner_account_id: input.owner_account_id,
      predicate_revision_id: revision_id,
      identity_version: "name-v2",
      identity_name,
      display_name: input.display_name,
      lifecycle: input.lifecycle ?? "canonical",
      slot_ids: [],
      observed_roles,
    },
  };
};

/**
 * Compatibility constructor for already-queued claims. New formation always
 * emits the name-v2 id, but durable pre-migration STM may still carry the old
 * name-plus-slot id. Preserve that coordinate as an explicitly legacy
 * revision; never rewrite the claim or pretend it was formed under v2.
 */
export const predicateRevisionForStoredObservation = (
  input: StoredPredicateObservation,
): { revision_id: string; predicate: Predicate } => {
  if (input.predicate_id === predicateIdForName(input.display_name)) {
    return predicateRevisionForObservation(input);
  }
  const slot_ids = [...new Set(input.legacy_slot_ids.map((slot) => slot.trim()).filter(Boolean))].sort();
  const lifecycle = input.lifecycle ?? "canonical";
  const revisionDigest = sha256CanonicalRedacted({
    kind: "predicate-revision-name-slots-v1-compat",
    owner_account_id: input.owner_account_id,
    predicate_id: input.predicate_id,
    identity_name: input.display_name,
    display_name: input.display_name,
    slot_ids,
    lifecycle,
  });
  const revision_id = `${input.predicate_id}:legacy-revision:${revisionDigest}`;
  return {
    revision_id,
    predicate: {
      predicate_id: input.predicate_id,
      owner_account_id: input.owner_account_id,
      predicate_revision_id: revision_id,
      identity_version: "name-slots-v1",
      identity_name: input.display_name,
      display_name: input.display_name,
      lifecycle,
      slot_ids,
    },
  };
};
