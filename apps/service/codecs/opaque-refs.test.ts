// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMCORE-012)
// domain-pending(DIV-DOMCORE-006)
// domain-pending(DIV-DOMCORE-008)
// domain-pending(DIV-DOMTASK-004)
// domain-pending(DIV-DOMAPPS-001)
// domain-pending(DIV-DOMAPPS-006)
// domain-pending(DIV-DOMX-001)
// domain-pending(DIV-DOMX-005)
// domain-pending(DIV-DOMX-006)
import { createHash } from "node:crypto";
import { describe, expect, test } from "bun:test";
import {
  parseCitationRef,
  parseSynthesizedItemId,
} from "@omi-core/ratified-contracts/projections/synthesized";

import {
  createReaderScopedOpaqueCodecs,
  type ReaderScopedOpaqueCodecConfig,
} from "./opaque-refs";

const STABLE_VISIBLE_KEY = /^vk1_[a-f0-9]{64}$/;
const ITEM_REF = /^mem1_[a-f0-9]{64}$/;
const CITATION_REF = /^cit1_[a-f0-9]{64}$/;
const TRACE_REF = /^tr1_[a-f0-9]{64}$/;

const digest = (value: string): string => createHash("sha256").update(value).digest("hex");

const ROOT_SECRET = new Uint8Array(32).fill(41);
const READER_A = digest("reader-projection-a");
const READER_B = digest("reader-projection-b");

const config = (
  overrides: Partial<ReaderScopedOpaqueCodecConfig> = {},
): ReaderScopedOpaqueCodecConfig => ({
  root_secret: new Uint8Array(ROOT_SECRET),
  reader_projection_digest: READER_A,
  ...overrides,
});

const leaksForbiddenRef = (value: string, forbidden: ReadonlySet<string>): boolean => {
  for (const raw of forbidden) {
    if (value === raw || (raw.length >= 3 && value.includes(raw))) return true;
  }
  return false;
};

const hexDigest = (opaque: string): string => opaque.slice(opaque.indexOf("_") + 1);

describe("reader-scoped opaque reference codecs", () => {
  test("emits the fixed opaque grammars accepted by application-read and ratified parsers", () => {
    // red-proof: change any prefix (e.g. mem1_ -> item1_) and the regex / ratified parser assertions fail
    const codecs = createReaderScopedOpaqueCodecs(config());
    const input = "render:canonical-internal-ref";

    const visible = codecs.encodeVisibleKey(input);
    const item = codecs.encodeItemRef(input);
    const citation = codecs.encodeCitationRef(input);
    const trace = codecs.encodeTraceRef(input);

    expect(STABLE_VISIBLE_KEY.test(visible)).toBeTrue();
    expect(ITEM_REF.test(item)).toBeTrue();
    expect(CITATION_REF.test(citation)).toBeTrue();
    expect(TRACE_REF.test(trace)).toBeTrue();

    expect(parseSynthesizedItemId(item)).not.toBeNull();
    expect(parseCitationRef(citation)).not.toBeNull();
    expect(String(parseSynthesizedItemId(item))).toBe(item);
    expect(String(parseCitationRef(citation))).toBe(citation);
  });

  test("domain-separates digests so the same input never collides across codecs", () => {
    // red-proof: drop the domain-separation label and the cross-codec collision test fails
    const codecs = createReaderScopedOpaqueCodecs(config());
    const input = "shared-internal-coordinate";

    const digests = [
      hexDigest(codecs.encodeVisibleKey(input)),
      hexDigest(codecs.encodeItemRef(input)),
      hexDigest(codecs.encodeCitationRef(input)),
      hexDigest(codecs.encodeTraceRef(input)),
    ];
    expect(new Set(digests).size).toBe(4);
  });

  test("never leaks the raw input through the opaque handle", () => {
    // red-proof: return the raw input (or concatenate it) and leaksForbiddenRef becomes true
    const codecs = createReaderScopedOpaqueCodecs(config());
    const raw = "render:secret-owner-account-id-xyz";
    const forbidden = new Set<string>([raw]);

    for (const encoded of [
      codecs.encodeVisibleKey(raw),
      codecs.encodeItemRef(raw),
      codecs.encodeCitationRef(raw),
      codecs.encodeTraceRef(raw),
    ]) {
      expect(leaksForbiddenRef(encoded, forbidden)).toBeFalse();
      expect(encoded.includes(raw)).toBeFalse();
    }
  });

  test("scopes opaque refs to the reader and stays deterministic for one reader", () => {
    // red-proof: ignore reader_projection_digest in key derivation and cross-reader inequality fails
    const readerA = createReaderScopedOpaqueCodecs(config({ reader_projection_digest: READER_A }));
    const readerB = createReaderScopedOpaqueCodecs(config({ reader_projection_digest: READER_B }));
    const input = "candidate:render:shared-across-readers";

    const aItem = readerA.encodeItemRef(input);
    const bItem = readerB.encodeItemRef(input);
    expect(aItem).not.toBe(bItem);
    expect(readerA.encodeVisibleKey(input)).not.toBe(readerB.encodeVisibleKey(input));
    expect(readerA.encodeCitationRef(input)).not.toBe(readerB.encodeCitationRef(input));
    expect(readerA.encodeTraceRef(input)).not.toBe(readerB.encodeTraceRef(input));

    // red-proof: inject Math.random or Date.now into the digest and same-reader equality fails
    expect(readerA.encodeItemRef(input)).toBe(aItem);
    expect(readerA.encodeVisibleKey(input)).toBe(readerA.encodeVisibleKey(input));
    expect(readerA.encodeCitationRef(input)).toBe(readerA.encodeCitationRef(input));
    expect(readerA.encodeTraceRef(input)).toBe(readerA.encodeTraceRef(input));
  });

  test("source-impact refs and cursors are reader-scoped, domain-separated, and stateless", () => {
    const first = createReaderScopedOpaqueCodecs(config());
    const independent = createReaderScopedOpaqueCodecs(config());
    const otherReader = createReaderScopedOpaqueCodecs(config({
      reader_projection_digest: READER_B,
    }));
    const binding = digest("source-impact-binding");
    const after = `3:${digest("source-impact-after")}`;
    const cursor = first.issueSourceImpactCursor(binding, after);

    expect(first.encodeSourceImpactRef("canonical_claim", "claim:1"))
      .toMatch(/^si1_[a-f0-9]{64}$/);
    expect(first.encodeSourceImpactRef("canonical_claim", "claim:1"))
      .toBe(independent.encodeSourceImpactRef("canonical_claim", "claim:1"));
    expect(first.encodeSourceImpactRef("canonical_claim", "claim:1"))
      .not.toBe(first.encodeSourceImpactRef("evidence", "claim:1"));
    expect(cursor).toMatch(/^sic1_[a-f0-9]{64}$/);
    expect(independent.verifySourceImpactCursor(cursor, binding, after)).toBe(true);
    expect(otherReader.verifySourceImpactCursor(cursor, binding, after)).toBe(false);
    expect(first.verifySourceImpactCursor(cursor, digest("other-binding"), after)).toBe(false);
    expect(first.verifySourceImpactCursor(cursor, binding, `2:${digest("source-impact-after")}`)).toBe(false);
    expect(first.verifySourceImpactCursor(`sic1_${"0".repeat(64)}`, binding, after)).toBe(false);
  });

  test("rejects short secrets and hostile config shapes without reading accessors", () => {
    // red-proof: accept secrets shorter than 32 bytes and the short-secret TypeError assertion fails
    expect(() => createReaderScopedOpaqueCodecs(config({ root_secret: new Uint8Array(31) })))
      .toThrow(TypeError);

    let secretGetterCalls = 0;
    let digestGetterCalls = 0;
    const accessorConfig = {} as Record<string, unknown>;
    Object.defineProperty(accessorConfig, "root_secret", {
      enumerable: true,
      get: () => {
        secretGetterCalls += 1;
        return new Uint8Array(32).fill(7);
      },
    });
    Object.defineProperty(accessorConfig, "reader_projection_digest", {
      enumerable: true,
      get: () => {
        digestGetterCalls += 1;
        return READER_A;
      },
    });
    expect(() => createReaderScopedOpaqueCodecs(
      accessorConfig as unknown as ReaderScopedOpaqueCodecConfig,
    )).toThrow(TypeError);
    expect(secretGetterCalls).toBe(0);
    expect(digestGetterCalls).toBe(0);

    const withSymbol = {
      root_secret: new Uint8Array(32).fill(9),
      reader_projection_digest: READER_A,
      [Symbol("extra")]: true,
    };
    expect(() => createReaderScopedOpaqueCodecs(
      withSymbol as unknown as ReaderScopedOpaqueCodecConfig,
    )).toThrow(TypeError);

    expect(() => createReaderScopedOpaqueCodecs(
      new Proxy(config(), {}) as ReaderScopedOpaqueCodecConfig,
    )).toThrow(TypeError);

    expect(() => createReaderScopedOpaqueCodecs({
      root_secret: new Uint8Array(32).fill(3),
      reader_projection_digest: READER_A,
      extra: true,
    } as unknown as ReaderScopedOpaqueCodecConfig)).toThrow(TypeError);

    expect(() => createReaderScopedOpaqueCodecs({
      root_secret: new Uint8Array(32).fill(3),
      reader_projection_digest: "not-a-digest",
    })).toThrow(TypeError);
  });

  test("copies the root secret so later mutation cannot retarget encodings", () => {
    // red-proof: skip the Uint8Array copy and mutating the caller's secret changes later encodings
    const mutableSecret = new Uint8Array(32).fill(55);
    const codecs = createReaderScopedOpaqueCodecs({
      root_secret: mutableSecret,
      reader_projection_digest: READER_A,
    });
    const before = codecs.encodeItemRef("stable-input");
    mutableSecret.fill(0);
    expect(codecs.encodeItemRef("stable-input")).toBe(before);
  });
});
