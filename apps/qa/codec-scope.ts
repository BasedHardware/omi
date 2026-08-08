// domain-pending(DIV-DOMAPPS-001)
// domain-pending(DIV-DOMAPPS-006)
// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMX-001)

/**
 * SHARED CODEC SCOPING — canonical derivation for both doors.
 *
 * The reference codecs (`vk1_`/`mem1_`/`cit1_`/`tr1_`) are keyed and
 * reader-scoped, so the *scope string* is part of the public identifier: the
 * same internal ref under two different scopes produces two different public
 * ids.
 *
 * That makes scope derivation a cross-door contract, not an implementation
 * detail. If the REST door scopes by `owner|app|key` and the MCP door scopes by
 * `owner`, the two return **different ids for the same memory**, and every
 * node-level cross-door assertion still passes while it happens — the divergence
 * hides one layer below where anyone is looking.
 *
 * So it is derived in exactly one place, here, and both doors call it.
 *
 * The encoding is length-prefixed rather than delimiter-joined: `owner:a` +
 * `app:b` and `owner` + `a:app:b` must not collapse to the same scope, or two
 * different readers share an identifier space.
 */

export interface QaCodecPrincipal {
  readonly owner_account_id: string;
  // domain-pending(DIV-DOMAPPS-001)
  readonly app_id: string;
  // domain-pending(DIV-DOMAPPS-006)
  readonly key_id: string;
}

const framed = (parts: readonly string[]): string =>
  parts.map((part) => `${part.length}:${part}`).join("");

/**
 * The reader scope for one principal.
 *
 * Includes app and key, not just the account: two credentials on one account are
 * different readers, and a memory's public id must not be correlatable across
 * them. `noninterference.test.ts` proves that end to end.
 */
export const qaReaderScope = (principal: QaCodecPrincipal): string => {
  // Validate exactly the three fields this reads, not every own property:
  // callers legitimately pass a superset (a principal also carrying `scopes`),
  // and rejecting extras made the shared derivation unusable from the one place
  // that most needed it.
  const parts = [principal.owner_account_id, principal.app_id, principal.key_id];
  const names = ["owner_account_id", "app_id", "key_id"] as const;
  parts.forEach((value, index) => {
    if (typeof value !== "string" || value.length === 0) {
      throw new TypeError(`QA reader scope requires a non-empty ${names[index]}`);
    }
  });
  return `qa-reader-scope-v1|${framed(parts)}`;
};

/**
 * Fixed QA codec secret.
 *
 * Deliberately a constant: this surface binds loopback, issues its own dev
 * tokens, and seeds deterministically, so a rotating secret would only make QA
 * runs non-reproducible. It is NOT a credential and no production key may ever
 * be placed here.
 */
export const QA_CODEC_SECRET: Uint8Array = new Uint8Array(32).fill(0x3c);
