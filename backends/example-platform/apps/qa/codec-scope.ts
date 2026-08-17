// domain-pending(DIV-DOMAPPS-001)
// domain-pending(DIV-DOMAPPS-006)
// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMX-001)

/**
 * QA CODEC KEY MATERIAL.
 *
 * Reader SCOPING no longer lives here. This module used to derive a
 * `qaReaderScope(principal)` string for the MCP door's own codec factory, while
 * the REST door scoped its codecs by the authorization boundary's
 * `principal_digest` — two derivations of one cross-door contract, which is
 * precisely why the two doors minted different public ids for the same memory.
 *
 * The scope is now derived in exactly one place: the authorization boundary
 * (`inspectApplicationMemoryReadAuthorization(...).principal_digest`, over
 * owner/app/key), read by the single composition in
 * `apps/service/composition/memory-read.ts`. That is strictly better than a
 * caller-assembled string, because it cannot drift from the credential the read
 * actually validated. `qaReaderScope` and the QA codec factory are deleted.
 */

/**
 * Fixed QA codec secret.
 *
 * Deliberately a constant: this surface binds loopback, issues its own dev
 * tokens, and seeds deterministically, so a rotating secret would only make QA
 * runs non-reproducible. It is NOT a credential and no production key may ever
 * be placed here.
 */
export const QA_CODEC_SECRET: Uint8Array = new Uint8Array(32).fill(0x3c);
