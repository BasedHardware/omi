import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { decrypt, deriveKeyRaw, encrypt } from "../src/encryption.js";
import { sanitize, sanitizePii } from "../src/sanitize.js";

const dir = dirname(fileURLToPath(import.meta.url));
const vectors = JSON.parse(readFileSync(join(dir, "python_vectors.json"), "utf8")) as {
  secret_utf8: string;
  uid: string;
  plaintext: string;
  ciphertext_b64: string;
  derived_key_b64: string;
  sanitize: { in: string; out: string }[];
  sanitize_pii: { in: string; out: string }[];
};

function b64(bytes: Uint8Array): string {
  let s = "";
  for (let i = 0; i < bytes.length; i++) s += String.fromCharCode(bytes[i]!);
  return btoa(s);
}

describe("encryption parity with Python", () => {
  it("matches HKDF derived key", async () => {
    const raw = await deriveKeyRaw(vectors.secret_utf8, vectors.uid);
    expect(b64(raw)).toBe(vectors.derived_key_b64);
  });

  it("decrypts Python ciphertext", async () => {
    const plain = await decrypt(vectors.ciphertext_b64, vectors.uid, vectors.secret_utf8);
    expect(plain).toBe(vectors.plaintext);
  });

  it("round-trips encrypt/decrypt", async () => {
    const ct = await encrypt(vectors.plaintext, vectors.uid, vectors.secret_utf8);
    const plain = await decrypt(ct, vectors.uid, vectors.secret_utf8);
    expect(plain).toBe(vectors.plaintext);
  });
});

describe("sanitize parity with Python", () => {
  for (const row of vectors.sanitize) {
    it(`sanitize(${JSON.stringify(row.in)})`, () => {
      expect(sanitize(row.in)).toBe(row.out);
    });
  }
  for (const row of vectors.sanitize_pii) {
    it(`sanitizePii(${JSON.stringify(row.in)})`, () => {
      expect(sanitizePii(row.in)).toBe(row.out);
    });
  }
});
