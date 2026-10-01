import type { SourceIdentityRef } from "../core/schema";

export const source = (namespace_instance_ref: string, local_key: string, producer_ref: string | null = "producer:fixture", contract_ref: string | null = "contract:v1"): SourceIdentityRef => ({
  namespace_instance_ref, local_key, producer: { producer_ref, contract_ref }, asserted_identity: { domain: "real-world-subject", scope_ref: "owner:fixture" },
});

/** Synthetic-only D47 threat corpus: renderings are deliberately non-unique. */
export const identityThreatFixtures = {
  same_display_different_namespaces: [source("namespace:camera-a", "42"), source("namespace:camera-b", "42")],
  colliding_person_id_different_producers: [source("namespace:producer-a", "42", "producer:a"), source("namespace:producer-b", "42", "producer:b")],
  repeated_same_namespace_key: [source("namespace:stable", "42"), source("namespace:stable", "42")],
  unknown_provenance: [source("unscoped:session-a:turn-1", "m-1", null, null), source("unscoped:session-b:turn-1", "m-1", null, null)],
  owner_confirmation: { source_identity_ref: source("namespace:owner-confirmed", "owner"), confirmation_ref: "confirmation:owner-confirmed" },
  conflicting_same_distinct: [source("namespace:conflict", "left"), source("namespace:conflict", "right")],
  two_slot_mixed_authorization: [source("namespace:two-slot", "authorized"), source("namespace:two-slot", "unsupported")],
  renderings: { latin: "David", cyrillic: "Давид" },
} as const;

/** Tests use this around any fixture pipeline: an accidental network call fails immediately. */
export const withFetchDisabled = async <T>(run: () => Promise<T> | T): Promise<T> => {
  const prior = globalThis.fetch;
  globalThis.fetch = (() => { throw new Error("network disabled by hermetic identity fixture"); }) as typeof fetch;
  try { return await run(); } finally { globalThis.fetch = prior; }
};
