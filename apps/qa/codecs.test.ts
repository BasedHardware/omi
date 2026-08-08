import { describe, expect, test } from "bun:test";

import { createQaReferenceCodecs, type QaCodecKeyMaterial } from "./codecs";

const VISIBLE_KEY = /^vk1_[a-f0-9]{64}$/;
const ITEM_REF = /^mem1_[a-f0-9]{64}$/;
const CITATION_REF = /^cit1_[a-f0-9]{64}$/;
const TRACE_REF = /^tr1_[a-f0-9]{64}$/;

const SAMPLE_INPUT = "candidate:render:abc123";

const keyMaterial = (overrides: Partial<QaCodecKeyMaterial> = {}): QaCodecKeyMaterial => ({
  secret: new Uint8Array(32).fill(42),
  reader_scope: "reader-scope-alpha",
  ...overrides,
});

const digestHex = (encoded: string): string => encoded.slice(encoded.indexOf("_") + 1);

describe("createQaReferenceCodecs", () => {
  test("grammar: every codec output matches its exact regex", () => {
    const codecs = createQaReferenceCodecs(keyMaterial());
    expect(codecs.encodeVisibleKey(SAMPLE_INPUT)).toMatch(VISIBLE_KEY);
    expect(codecs.encodeItemRef(SAMPLE_INPUT)).toMatch(ITEM_REF);
    expect(codecs.encodeCitationRef(SAMPLE_INPUT)).toMatch(CITATION_REF);
    expect(codecs.encodeTraceRef(SAMPLE_INPUT)).toMatch(TRACE_REF);
  });

  test("determinism: equal key material yields equal outputs", () => {
    const left = createQaReferenceCodecs(keyMaterial());
    const right = createQaReferenceCodecs(keyMaterial());
    expect(left.encodeVisibleKey(SAMPLE_INPUT)).toBe(right.encodeVisibleKey(SAMPLE_INPUT));
    expect(left.encodeItemRef(SAMPLE_INPUT)).toBe(right.encodeItemRef(SAMPLE_INPUT));
    expect(left.encodeCitationRef(SAMPLE_INPUT)).toBe(right.encodeCitationRef(SAMPLE_INPUT));
    expect(left.encodeTraceRef(SAMPLE_INPUT)).toBe(right.encodeTraceRef(SAMPLE_INPUT));
  });

  test("domain separation: the same input through all four codecs yields four distinct digests", () => {
    // red-proof: reusing one domain label for every codec makes all four digests identical.
    const codecs = createQaReferenceCodecs(keyMaterial());
    const digests = [
      digestHex(codecs.encodeVisibleKey(SAMPLE_INPUT)),
      digestHex(codecs.encodeItemRef(SAMPLE_INPUT)),
      digestHex(codecs.encodeCitationRef(SAMPLE_INPUT)),
      digestHex(codecs.encodeTraceRef(SAMPLE_INPUT)),
    ];
    expect(new Set(digests).size).toBe(4);
  });

  test("reader scoping: different reader_scope values yield different digests", () => {
    // red-proof: omitting reader_scope from the HMAC message makes both scopes collide.
    const left = createQaReferenceCodecs(keyMaterial({ reader_scope: "reader-a" }));
    const right = createQaReferenceCodecs(keyMaterial({ reader_scope: "reader-b" }));
    expect(left.encodeItemRef(SAMPLE_INPUT)).not.toBe(right.encodeItemRef(SAMPLE_INPUT));
    expect(digestHex(left.encodeItemRef(SAMPLE_INPUT))).not.toBe(digestHex(right.encodeItemRef(SAMPLE_INPUT)));
  });

  test("key separation: different secrets yield different digests for the same input", () => {
    const left = createQaReferenceCodecs(keyMaterial({ secret: new Uint8Array(32).fill(1) }));
    const right = createQaReferenceCodecs(keyMaterial({ secret: new Uint8Array(32).fill(2) }));
    expect(digestHex(left.encodeTraceRef(SAMPLE_INPUT))).not.toBe(digestHex(right.encodeTraceRef(SAMPLE_INPUT)));
  });

  test("injectivity: delimiter-colliding scope/input pairs yield different digests", () => {
    // red-proof: naive `scope + ":" + input` concatenation maps ("a:b", "c") and ("a", "b:c") to the same bytes.
    const leftScoped = createQaReferenceCodecs(keyMaterial({ reader_scope: "a:b" })).encodeCitationRef("c");
    const rightScoped = createQaReferenceCodecs(keyMaterial({ reader_scope: "a" })).encodeCitationRef("b:c");
    expect(digestHex(leftScoped)).not.toBe(digestHex(rightScoped));
  });

  test("defensive copy: mutating caller secret after construction does not change outputs", () => {
    const secret = new Uint8Array(32).fill(9);
    const codecs = createQaReferenceCodecs({ secret, reader_scope: "reader-stable" });
    const before = codecs.encodeVisibleKey(SAMPLE_INPUT);
    secret.fill(0);
    expect(codecs.encodeVisibleKey(SAMPLE_INPUT)).toBe(before);
  });

  test("factory rejects a 31-byte secret and an empty reader scope", () => {
    expect(() => createQaReferenceCodecs({
      secret: new Uint8Array(31).fill(7),
      reader_scope: "reader-scope-alpha",
    })).toThrow(TypeError);
    expect(() => createQaReferenceCodecs({
      secret: new Uint8Array(32).fill(7),
      reader_scope: "",
    })).toThrow(TypeError);
  });
});
