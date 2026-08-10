import { createHash } from "node:crypto";

import type { DevPrincipal } from "./dev-token";

export type DevTokenResolver = (token: string) => DevPrincipal | null;

export type CurrentSessionRevocation =
  | { readonly status: "revoked" }
  | { readonly status: "already_revoked" }
  | { readonly status: "unrecognized" };

/**
 * Current-session authentication and revocation over the dev-token seam.
 *
 * The port never widens a token into an account-wide operation. Adapters retain
 * only a one-way digest of the presented handle, enough to reject later use and
 * recognize a replayed DELETE without persisting the credential itself.
 */
export interface CurrentSessionPort {
  authenticate(token: string, resolveDevToken: DevTokenResolver): DevPrincipal | null;
  revoke(token: string, resolveDevToken: DevTokenResolver): CurrentSessionRevocation;
}

export const digestSessionHandle = (token: string): string =>
  createHash("sha256").update(token, "utf8").digest("hex");

/** In-memory current-session adapter for the default local service. */
export const createInMemoryCurrentSessionPort = (): CurrentSessionPort => {
  const revokedHandles = new Set<string>();

  return Object.freeze({
    authenticate(token: string, resolveDevToken: DevTokenResolver): DevPrincipal | null {
      if (revokedHandles.has(digestSessionHandle(token))) return null;
      return resolveDevToken(token);
    },

    revoke(token: string, resolveDevToken: DevTokenResolver): CurrentSessionRevocation {
      const digest = digestSessionHandle(token);
      if (revokedHandles.has(digest)) return Object.freeze({ status: "already_revoked" });
      if (resolveDevToken(token) === null) return Object.freeze({ status: "unrecognized" });
      revokedHandles.add(digest);
      return Object.freeze({ status: "revoked" });
    },
  });
};
