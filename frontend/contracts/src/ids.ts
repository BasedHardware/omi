/**
 * Record identifiers — ADR-006 (word slugs) + its 2026-08-06 rollout amendment.
 *
 * Every surface we control GENERATES slug ids (`flying-dragon-vibrant`) and
 * ACCEPTS `legacy-UUID | slug` for as long as any released UUID writer is
 * supported. Slug-only validation is forbidden anywhere — server, client,
 * codegen. Servers treat ids as opaque strings; this grammar is a
 * client/codegen contract, not a server parse.
 */

/** 3–5 lowercase ASCII words, kebab-joined, from the versioned wordlist. */
export const SLUG_PATTERN = /^[a-z]{2,12}(?:-[a-z]{2,12}){2,4}$/;

/** RFC 4122 shape, any version — the released writers' format. */
export const LEGACY_UUID_PATTERN =
  /^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/;

/**
 * Server-assigned opaque ids (Firestore doc ids, content hashes) — the ids
 * the legacy backend mints today. ADR-006 makes servers id-opaque, so the
 * client boundary must ACCEPT them; the slug grammar governs only what WE
 * generate. Safe charset, bounded length — no path or markup characters.
 * (Found by the first store integration test: every real server row was
 * being dropped as unparseable.)
 */
export const LEGACY_OPAQUE_PATTERN = /^[A-Za-z0-9_-]{4,128}$/;

declare const RecordIdBrand: unique symbol;

/**
 * A validated record id: slug or legacy UUID. The brand means "this string
 * went through `parseRecordId`" — raw strings from the wire or the UI must be
 * parsed at the boundary, never cast.
 */
export type RecordId = string & { readonly [RecordIdBrand]: true };

export type RecordIdKind = "slug" | "legacy-uuid" | "legacy-opaque";

/** The one sanctioned way to obtain a RecordId from a raw string. */
export function parseRecordId(raw: string): { id: RecordId; kind: RecordIdKind } | null {
  if (SLUG_PATTERN.test(raw)) return { id: raw as RecordId, kind: "slug" };
  if (LEGACY_UUID_PATTERN.test(raw)) return { id: raw as RecordId, kind: "legacy-uuid" };
  if (LEGACY_OPAQUE_PATTERN.test(raw)) return { id: raw as RecordId, kind: "legacy-opaque" };
  return null;
}

/**
 * Entropy contract (ADR-006 §1): per-user domains use 3 words from the
 * curated ~4k wordlist (~36 bits) with create-if-absent collision retry.
 * The wordlist is a versioned, append-only artifact shipped with codegen —
 * generation lives in `@omi-core/kernel`, never inline.
 */
export const SLUG_WORDS_PER_USER_DOMAIN = 3;
