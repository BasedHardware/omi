import { createHash, randomBytes, timingSafeEqual } from "crypto";
import { DEV_BYPASS_ENABLED } from "@/lib/dev-auth";
import { getDb } from "@/lib/firebase/admin";
import { accessFor, hasScope } from "@/lib/admin-access";

export const TV_LINKS_COLLECTION = "admin_tv_links";
export const DEFAULT_TV_LINK_TTL_DAYS = 90;
/**
 * TV links open the `omi-tv-v2` Business board (revenue, MRR, cost panels),
 * so they carry the issuer's finance:read: issuing requires it, and the
 * kiosk re-checks the issuer still holds it on every view.
 */
export const TV_LINK_BOARD_SCOPE = "finance:read" as const;
// The issuer's access lives here (same collection as lib/team/roster's).
const ADMIN_COLLECTION = "adminData";

export type TvLinkRecord = {
  tokenHash: string;
  /** Full token so admins can re-copy the kiosk URL anytime. */
  token: string;
  prefix: string;
  label: string;
  createdBy: string;
  createdAt: number;
  expiresAt: number | null;
  revokedAt: number | null;
  lastUsedAt: number | null;
};

export type TvLinkPublic = {
  id: string;
  prefix: string;
  token: string | null;
  path: string | null;
  label: string;
  createdBy: string;
  createdAt: number;
  expiresAt: number | null;
  revokedAt: number | null;
  lastUsedAt: number | null;
  status: "active" | "expired" | "revoked";
};

export function hashTvToken(token: string): string {
  return createHash("sha256").update(token, "utf8").digest("hex");
}

export function generateTvToken(): {
  token: string;
  tokenHash: string;
  prefix: string;
} {
  const token = randomBytes(32).toString("base64url");
  const tokenHash = hashTvToken(token);
  return { token, tokenHash, prefix: token.slice(0, 8) };
}

export function tvLinkStatus(
  link: Pick<TvLinkRecord, "revokedAt" | "expiresAt">,
  now = Date.now()
): "active" | "expired" | "revoked" {
  if (link.revokedAt != null) return "revoked";
  if (link.expiresAt != null && link.expiresAt <= now) return "expired";
  return "active";
}

export function isTvLinkActive(
  link: Pick<TvLinkRecord, "revokedAt" | "expiresAt">,
  now = Date.now()
): boolean {
  return tvLinkStatus(link, now) === "active";
}

/** Constant-time compare of hex digests. */
export function safeEqualHex(a: string, b: string): boolean {
  try {
    const ba = Buffer.from(a, "hex");
    const bb = Buffer.from(b, "hex");
    if (ba.length !== bb.length || ba.length === 0) return false;
    return timingSafeEqual(ba, bb);
  } catch {
    return false;
  }
}

function toPublic(
  id: string,
  data: TvLinkRecord,
  revealToken = true
): TvLinkPublic {
  const token =
    revealToken && typeof data.token === "string" && data.token.length >= 16
      ? data.token
      : null;
  return {
    id,
    prefix: data.prefix,
    token,
    path: token ? `/tv/view/${token}` : null,
    label: data.label,
    createdBy: data.createdBy,
    createdAt: data.createdAt,
    expiresAt: data.expiresAt,
    revokedAt: data.revokedAt,
    lastUsedAt: data.lastUsedAt,
    status: tvLinkStatus(data),
  };
}

/**
 * List TV links newest-first. Pages through Firestore so older active links
 * remain revocable (a hard limit would hide leaked long-lived URLs).
 * `revealTokens: false` strips the share tokens (the capability itself) for
 * callers without finance:read; metadata and revocation stay available.
 */
export async function listTvLinks(
  options: { revealTokens?: boolean } = {}
): Promise<TvLinkPublic[]> {
  const pageSize = 200;
  const maxPages = 25; // hard cap 5_000 rows
  const out: TvLinkPublic[] = [];
  let last: FirebaseFirestore.QueryDocumentSnapshot | undefined;

  for (let page = 0; page < maxPages; page++) {
    let q = getDb()
      .collection(TV_LINKS_COLLECTION)
      .orderBy("createdAt", "desc")
      .limit(pageSize);
    if (last) q = q.startAfter(last);
    const snap = await q.get();
    if (snap.empty) break;
    for (const d of snap.docs) {
      const pub = toPublic(
        d.id,
        d.data() as TvLinkRecord,
        options.revealTokens ?? true
      );
      if (pub.status === "revoked") continue;
      out.push(pub);
    }
    last = snap.docs[snap.docs.length - 1];
    if (snap.size < pageSize) break;
  }
  return out;
}

export async function createTvLink(input: {
  label: string;
  createdBy: string;
  ttlDays?: number | null;
}): Promise<{ link: TvLinkPublic; token: string; path: string }> {
  const label = input.label.trim() || "Office TV";
  const { token, tokenHash, prefix } = generateTvToken();
  const now = Date.now();
  let ttlDays: number | null;
  if (input.ttlDays === null) {
    ttlDays = null;
  } else if (typeof input.ttlDays === "number") {
    if (
      !Number.isFinite(input.ttlDays) ||
      !Number.isInteger(input.ttlDays) ||
      input.ttlDays < 1
    ) {
      throw new Error("ttlDays must be a positive integer or null");
    }
    ttlDays = input.ttlDays;
  } else {
    ttlDays = DEFAULT_TV_LINK_TTL_DAYS;
  }
  const expiresAt =
    ttlDays == null ? null : now + ttlDays * 24 * 60 * 60 * 1000;

  const record: TvLinkRecord = {
    tokenHash,
    token,
    prefix,
    label,
    createdBy: input.createdBy,
    createdAt: now,
    expiresAt,
    revokedAt: null,
    lastUsedAt: null,
  };

  await getDb().collection(TV_LINKS_COLLECTION).doc(tokenHash).set(record);
  return {
    link: toPublic(tokenHash, record),
    token,
    path: `/tv/view/${token}`,
  };
}

export async function revokeTvLink(
  id: string,
  options: { revealToken?: boolean } = {}
): Promise<TvLinkPublic | null> {
  const ref = getDb().collection(TV_LINKS_COLLECTION).doc(id);
  const snap = await ref.get();
  if (!snap.exists) return null;
  const data = snap.data() as TvLinkRecord;
  if (data.revokedAt == null) {
    const revokedAt = Date.now();
    await ref.update({ revokedAt });
    data.revokedAt = revokedAt;
  }
  return toPublic(id, data, options.revealToken ?? true);
}

export type ResolvedTvLink = {
  id: string;
  label: string;
};

/**
 * The link's authority is its issuer's finance:read, not the token alone:
 * the issuer must still be an admin and still hold it. A revoked or demoted
 * issuer's links stop opening the Business board immediately.
 */
export async function issuerHoldsBoardScope(
  createdBy: string
): Promise<boolean> {
  if (!createdBy) return false;
  try {
    const snap = await getDb()
      .collection(ADMIN_COLLECTION)
      .doc(createdBy)
      .get();
    if (!snap.exists) return false;
    return hasScope(accessFor(snap.data()), TV_LINK_BOARD_SCOPE);
  } catch (error) {
    console.error("resolve TV issuer:", error);
    return false;
  }
}

/**
 * Resolve a raw TV path token to an active link.
 * Updates lastUsedAt at most once per minute.
 */
export async function resolveActiveTvToken(
  rawToken: string
): Promise<ResolvedTvLink | null> {
  // ponytail: local QA only — production disables DEV_BYPASS. Use Firestore tokens in prod.
  if (DEV_BYPASS_ENABLED && rawToken === "dev-kiosk") {
    return { id: "dev-kiosk", label: "Dev TV" };
  }
  // Reject junk before a Firestore read (base64url from generateTvToken).
  if (!/^[A-Za-z0-9_-]{32,64}$/.test(rawToken)) return null;
  try {
    const tokenHash = hashTvToken(rawToken);
    const ref = getDb().collection(TV_LINKS_COLLECTION).doc(tokenHash);
    const snap = await ref.get();
    if (!snap.exists) return null;
    const data = snap.data() as TvLinkRecord;
    if (!safeEqualHex(data.tokenHash || tokenHash, tokenHash)) return null;
    if (!isTvLinkActive(data)) return null;
    // Re-validate the issuer before the link can refresh anything: a link
    // outlives its issuer's access only if the issuer still holds finance:read.
    if (!(await issuerHoldsBoardScope(data.createdBy))) return null;

    const now = Date.now();
    if (!data.lastUsedAt || now - data.lastUsedAt > 60_000) {
      await ref.update({ lastUsedAt: now }).catch(() => undefined);
    }

    return { id: snap.id, label: data.label };
  } catch (error) {
    console.error("resolve TV token:", error);
    return null;
  }
}
