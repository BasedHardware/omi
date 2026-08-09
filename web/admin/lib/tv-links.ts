import { createHash, randomBytes, timingSafeEqual } from "crypto";
import { getDb } from "@/lib/firebase/admin";

export const TV_LINKS_COLLECTION = "admin_tv_links";
export const DEFAULT_TV_LINK_TTL_DAYS = 90;

export type TvLinkRecord = {
  tokenHash: string;
  prefix: string;
  label: string;
  createdBy: string;
  createdAt: number;
  expiresAt: number | null;
  revokedAt: number | null;
  lastUsedAt: number | null;
  includeRevenue: boolean;
};

export type TvLinkPublic = {
  id: string;
  prefix: string;
  label: string;
  createdBy: string;
  createdAt: number;
  expiresAt: number | null;
  revokedAt: number | null;
  lastUsedAt: number | null;
  includeRevenue: boolean;
  status: "active" | "expired" | "revoked";
};

export function hashTvToken(token: string): string {
  return createHash("sha256").update(token, "utf8").digest("hex");
}

export function generateTvToken(): { token: string; tokenHash: string; prefix: string } {
  const token = randomBytes(32).toString("base64url");
  const tokenHash = hashTvToken(token);
  return { token, tokenHash, prefix: token.slice(0, 8) };
}

export function tvLinkStatus(
  link: Pick<TvLinkRecord, "revokedAt" | "expiresAt">,
  now = Date.now(),
): "active" | "expired" | "revoked" {
  if (link.revokedAt != null) return "revoked";
  if (link.expiresAt != null && link.expiresAt <= now) return "expired";
  return "active";
}

export function isTvLinkActive(
  link: Pick<TvLinkRecord, "revokedAt" | "expiresAt">,
  now = Date.now(),
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

function toPublic(id: string, data: TvLinkRecord): TvLinkPublic {
  return {
    id,
    prefix: data.prefix,
    label: data.label,
    createdBy: data.createdBy,
    createdAt: data.createdAt,
    expiresAt: data.expiresAt,
    revokedAt: data.revokedAt,
    lastUsedAt: data.lastUsedAt,
    includeRevenue: data.includeRevenue !== false,
    status: tvLinkStatus(data),
  };
}

export async function listTvLinks(): Promise<TvLinkPublic[]> {
  const snap = await getDb()
    .collection(TV_LINKS_COLLECTION)
    .orderBy("createdAt", "desc")
    .limit(100)
    .get();
  return snap.docs.map((d) => toPublic(d.id, d.data() as TvLinkRecord));
}

export async function createTvLink(input: {
  label: string;
  createdBy: string;
  ttlDays?: number | null;
  includeRevenue?: boolean;
}): Promise<{ link: TvLinkPublic; token: string; path: string }> {
  const label = input.label.trim() || "Office TV";
  const { token, tokenHash, prefix } = generateTvToken();
  const now = Date.now();
  const ttlDays =
    input.ttlDays === null
      ? null
      : typeof input.ttlDays === "number"
        ? input.ttlDays
        : DEFAULT_TV_LINK_TTL_DAYS;
  const expiresAt =
    ttlDays == null || ttlDays <= 0 ? null : now + ttlDays * 24 * 60 * 60 * 1000;

  const record: TvLinkRecord = {
    tokenHash,
    prefix,
    label,
    createdBy: input.createdBy,
    createdAt: now,
    expiresAt,
    revokedAt: null,
    lastUsedAt: null,
    includeRevenue: input.includeRevenue !== false,
  };

  await getDb().collection(TV_LINKS_COLLECTION).doc(tokenHash).set(record);
  return {
    link: toPublic(tokenHash, record),
    token,
    path: `/tv/view/${token}`,
  };
}

export async function revokeTvLink(id: string): Promise<TvLinkPublic | null> {
  const ref = getDb().collection(TV_LINKS_COLLECTION).doc(id);
  const snap = await ref.get();
  if (!snap.exists) return null;
  const data = snap.data() as TvLinkRecord;
  if (data.revokedAt == null) {
    const revokedAt = Date.now();
    await ref.update({ revokedAt });
    data.revokedAt = revokedAt;
  }
  return toPublic(id, data);
}

export type ResolvedTvLink = {
  id: string;
  includeRevenue: boolean;
  label: string;
};

/**
 * Resolve a raw TV bearer/path token to an active link.
 * Updates lastUsedAt at most once per minute.
 */
export async function resolveActiveTvToken(
  rawToken: string,
): Promise<ResolvedTvLink | null> {
  if (!rawToken || rawToken.length < 16) return null;
  const tokenHash = hashTvToken(rawToken);
  const ref = getDb().collection(TV_LINKS_COLLECTION).doc(tokenHash);
  const snap = await ref.get();
  if (!snap.exists) return null;
  const data = snap.data() as TvLinkRecord;
  if (!safeEqualHex(data.tokenHash || tokenHash, tokenHash)) return null;
  if (!isTvLinkActive(data)) return null;

  const now = Date.now();
  if (!data.lastUsedAt || now - data.lastUsedAt > 60_000) {
    void ref.update({ lastUsedAt: now }).catch(() => undefined);
  }

  return {
    id: snap.id,
    includeRevenue: data.includeRevenue !== false,
    label: data.label,
  };
}
