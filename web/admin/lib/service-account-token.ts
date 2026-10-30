import { OAuth2Client } from "google-auth-library";

// Reuse the client: google-auth-library caches Google's signing certificates
// according to Cache-Control and refreshes them after expiry.
const googleIdentity = new OAuth2Client();
const GOOGLE_ISSUERS = ["accounts.google.com", "https://accounts.google.com"];

export type ServiceAccountReason =
  | "disabled"
  | "invalid_token"
  | "expired"
  | "email_unverified"
  | "reader_not_allowed";

export type ServiceAccountResult =
  | { ok: true; email: string; sub: string }
  | { ok: false; reason: ServiceAccountReason };

/** Comma or whitespace separated service-account emails. */
export function parseAllowlist(value: string | undefined): string[] {
  return (value ?? "").split(/[,\s]+/).filter(Boolean);
}

/**
 * Verify a Google-signed ID token minted for an allowlisted service account:
 * signature, Google issuer, exact audience, actual expiry (without the SDK's
 * clock-skew grace), verified email and exact allowlist membership. Both the
 * audience and the allowlist must be nonempty, otherwise the caller is disabled.
 */
export async function verifyServiceAccountToken(
  token: string,
  config: { audience: string | undefined; allowlist: string | undefined }
): Promise<ServiceAccountResult> {
  const audience = config.audience?.trim();
  const allowed = parseAllowlist(config.allowlist);
  if (!audience || !allowed.length) return { ok: false, reason: "disabled" };

  try {
    const ticket = await googleIdentity.verifyIdToken({
      idToken: token,
      audience,
    });
    const claims = ticket.getPayload();
    if (
      !claims ||
      !GOOGLE_ISSUERS.includes(claims.iss) ||
      claims.aud !== audience ||
      !claims.sub
    ) {
      return { ok: false, reason: "invalid_token" };
    }
    if (!Number.isFinite(claims.exp) || claims.exp <= Date.now() / 1000)
      return { ok: false, reason: "expired" };
    if (claims.email_verified !== true)
      return { ok: false, reason: "email_unverified" };
    if (
      !claims.email?.endsWith(".gserviceaccount.com") ||
      !allowed.includes(claims.email)
    ) {
      return { ok: false, reason: "reader_not_allowed" };
    }
    return { ok: true, email: claims.email, sub: claims.sub };
  } catch {
    return { ok: false, reason: "invalid_token" };
  }
}
