// domain-pending(UNK-DOMAPPS-001)

/**
 * Sibling identity and entitlement projections for the Settings surface.
 *
 * The account-control projection remains deliberately untouched. This port
 * supplies one coherent Settings read while also exposing the exact same
 * entitlement projection to enforcement consumers. A Settings-only copy would
 * be capable of drifting from the fence and is therefore not representable.
 */

export interface SettingsIdentityProjection {
  readonly displayName: string;
  readonly email: string;
}

// domain-pending(UNK-DOMAPPS-001)
export interface SettingsEntitlementProjection {
  readonly planLabel: string;
  readonly limitKey: string;
  readonly used: number;
  readonly limit: number | null;
  readonly limitReached: boolean;
  readonly upgradeAvailable: boolean;
}

// domain-pending(UNK-DOMAPPS-001)
export interface SettingsProjectionSnapshot {
  readonly identity: SettingsIdentityProjection;
  readonly entitlement: SettingsEntitlementProjection | null;
}

export type SettingsProjectionRead =
  | { readonly status: "available"; readonly snapshot: SettingsProjectionSnapshot }
  | { readonly status: "unavailable" }
  | { readonly status: "forbidden" };

// domain-pending(UNK-DOMAPPS-001)
export interface EntitlementProjectionReader {
  /** The authoritative projection used by enforcement; null means absent. */
  readEntitlement(accountId: string): SettingsEntitlementProjection | null;
}

// domain-pending(UNK-DOMAPPS-001)
export interface SettingsProjectionReader extends EntitlementProjectionReader {
  /** One coherent read. Missing required identity state is unavailable. */
  readSettings(accountId: string): SettingsProjectionRead;
}

// domain-pending(UNK-DOMAPPS-001)
export interface SettingsProjectionStore extends SettingsProjectionReader {
  putIdentity(accountId: string, projection: SettingsIdentityProjection): void;
  putEntitlement(accountId: string, projection: SettingsEntitlementProjection | null): void;
  /**
   * Adds real consumed transcription seconds to this same projection.
   *
   * Returning null preserves the distinction between an absent entitlement
   * projection and an explicitly unmetered one. Callers must never manufacture
   * an "unlimited" sentinel to fill that gap.
   */
  consumeTranscriptionSeconds(
    accountId: string,
    amount: number,
  ): SettingsEntitlementProjection | null;
}

const detachedIdentity = (projection: SettingsIdentityProjection): SettingsIdentityProjection => {
  if (typeof projection.displayName !== "string" || typeof projection.email !== "string") {
    throw new TypeError("invalid settings identity projection");
  }
  return Object.freeze({ displayName: projection.displayName, email: projection.email });
};

// domain-pending(UNK-DOMAPPS-001)
export const detachedEntitlement = (
  projection: SettingsEntitlementProjection,
): SettingsEntitlementProjection => {
  if (typeof projection.planLabel !== "string" || typeof projection.limitKey !== "string"
    || typeof projection.used !== "number" || !Number.isFinite(projection.used)
    || projection.used < 0
    || (projection.limit !== null
      && (typeof projection.limit !== "number" || !Number.isFinite(projection.limit)
        || projection.limit < 0))
    || typeof projection.limitReached !== "boolean"
    || typeof projection.upgradeAvailable !== "boolean"
    || (projection.limit === null && projection.limitReached)) {
    throw new TypeError("invalid settings entitlement projection");
  }
  return Object.freeze({
    planLabel: projection.planLabel,
    limitKey: projection.limitKey,
    used: projection.used,
    limit: projection.limit,
    limitReached: projection.limitReached,
    upgradeAvailable: projection.upgradeAvailable,
  });
};

const assertConsumedSeconds = (amount: number): number => {
  if (typeof amount !== "number" || !Number.isFinite(amount) || amount < 0) {
    throw new TypeError("invalid consumed transcription seconds");
  }
  return amount;
};

/** In-memory adapter used by the hermetic local composition. */
export const createInMemorySettingsProjectionStore = (): SettingsProjectionStore => {
  const identities = new Map<string, SettingsIdentityProjection>();
  const entitlements = new Map<string, SettingsEntitlementProjection>();

  return Object.freeze({
    putIdentity(accountId: string, projection: SettingsIdentityProjection): void {
      identities.set(accountId, detachedIdentity(projection));
    },

    putEntitlement(accountId: string, projection: SettingsEntitlementProjection | null): void {
      if (projection === null) {
        entitlements.delete(accountId);
        return;
      }
      entitlements.set(accountId, detachedEntitlement(projection));
    },

    readEntitlement(accountId: string): SettingsEntitlementProjection | null {
      return entitlements.get(accountId) ?? null;
    },

    consumeTranscriptionSeconds(
      accountId: string,
      amount: number,
    ): SettingsEntitlementProjection | null {
      const increment = assertConsumedSeconds(amount);
      const current = entitlements.get(accountId);
      if (current === undefined) return null;
      const used = current.used + increment;
      const next = detachedEntitlement({
        ...current,
        used,
        limitReached: current.limit !== null && used >= current.limit,
      });
      entitlements.set(accountId, next);
      return next;
    },

    readSettings(accountId: string): SettingsProjectionRead {
      const identity = identities.get(accountId);
      if (identity === undefined) return Object.freeze({ status: "unavailable" });
      return Object.freeze({
        status: "available",
        snapshot: Object.freeze({
          identity,
          entitlement: entitlements.get(accountId) ?? null,
        }),
      });
    },
  });
};
