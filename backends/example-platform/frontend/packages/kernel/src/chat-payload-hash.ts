/**
 * The chat write contract's payload hash — ADR-005 idempotency.
 *
 * Lives in the kernel for exactly the reason `classifyStatus` does: it is not
 * one adapter's business, it is the single shared definition every transport
 * binding and the projection codec must agree on, and it is a pure function of
 * its input with no clock, no randomness and no I/O.
 *
 * It was briefly reachable only through an injected function port, which is a
 * footgun rather than a seam: the entire value of this digest is that the
 * CLIENT and the SERVER compute the same one, so a caller able to supply a
 * different implementation is a caller able to silently break idempotency at
 * precisely the moment a retry matters. There is one definition, and this is it.
 *
 * Canonical JSON uses sorted object keys, compact separators, UTF-8, then
 * SHA-256 prefixed with `sha256:`. The ratified wire adds the authored ordered
 * attachment id list to that identity payload. The cross-check against
 * `node:crypto` lives in `packages/testkit/src/test/chat-codec.test.ts`.
 *
 * SHA-256 is implemented here rather than taken from `node:crypto` because this
 * package is also bundled for the browser, where `node:crypto` does not exist
 * and `crypto.subtle` is async — and an async digest would make the projection
 * codec's `applyOp` async, which it cannot be.
 */

/** Fields the backend folds into `client_message_payload_hash`. */
export interface ChatMessageHashPayload {
  text: string;
  sender: string;
  appId: string | null;
  /** Wire `session_id` — same value as `chatSessionId` on the record. */
  sessionId: string | null;
  metadata: string | null;
  messageSource: string;
  /** Authored order is identity-bearing; it is never sorted or truncated. */
  attachmentIds: readonly string[];
}


/**
 * Stable digest matching the desktop write path:
 * `sha256:` + hex of canonical JSON with sorted keys, no ASCII escapes.
 */
export function chatMessagePayloadHash(payload: ChatMessageHashPayload): string {
  const wire: Record<string, string | readonly string[] | null> = {
    attachment_ids: payload.attachmentIds,
    app_id: payload.appId,
    message_source: payload.messageSource,
    metadata: payload.metadata,
    sender: payload.sender,
    session_id: payload.sessionId,
    text: payload.text,
  };
  const canonical = JSON.stringify(wire, Object.keys(wire).sort());
  return `sha256:${sha256Hex(utf8Bytes(canonical))}`;
}

// ─── Pure SHA-256 (no wall clock, no Math.random, no ambient Node crypto) ───

/** UTF-8 encode without depending on DOM `TextEncoder` typings in domain. */
function utf8Bytes(s: string): Uint8Array {
  const out: number[] = [];
  for (let i = 0; i < s.length; i++) {
    let c = s.charCodeAt(i);
    if (c >= 0xd800 && c <= 0xdbff && i + 1 < s.length) {
      const d = s.charCodeAt(i + 1);
      if (d >= 0xdc00 && d <= 0xdfff) {
        c = 0x10000 + ((c - 0xd800) << 10) + (d - 0xdc00);
        i++;
      }
    }
    if (c <= 0x7f) out.push(c);
    else if (c <= 0x7ff) {
      out.push(0xc0 | (c >> 6), 0x80 | (c & 0x3f));
    } else if (c <= 0xffff) {
      out.push(0xe0 | (c >> 12), 0x80 | ((c >> 6) & 0x3f), 0x80 | (c & 0x3f));
    } else {
      out.push(
        0xf0 | (c >> 18),
        0x80 | ((c >> 12) & 0x3f),
        0x80 | ((c >> 6) & 0x3f),
        0x80 | (c & 0x3f),
      );
    }
  }
  return Uint8Array.from(out);
}

function sha256Hex(data: Uint8Array): string {
  const H = new Uint32Array([
    0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19,
  ]);
  const K = new Uint32Array([
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
    0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
    0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
    0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
    0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
    0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
  ]);

  const bitLen = data.length * 8;
  const withPad = data.length + 1 + 8;
  const paddedLen = Math.ceil(withPad / 64) * 64;
  const buf = new Uint8Array(paddedLen);
  buf.set(data);
  buf[data.length] = 0x80;
  const view = new DataView(buf.buffer);
  // high 32 bits of length are 0 for messages we hash (<< 2^32 bits)
  view.setUint32(paddedLen - 4, bitLen >>> 0, false);

  const w = new Uint32Array(64);
  for (let i = 0; i < paddedLen; i += 64) {
    for (let j = 0; j < 16; j++) w[j] = view.getUint32(i + j * 4, false);
    for (let j = 16; j < 64; j++) {
      const v1 = w[j - 15]!;
      const v2 = w[j - 2]!;
      const s0 = rotr(v1, 7) ^ rotr(v1, 18) ^ (v1 >>> 3);
      const s1 = rotr(v2, 17) ^ rotr(v2, 19) ^ (v2 >>> 10);
      w[j] = (w[j - 16]! + s0 + w[j - 7]! + s1) >>> 0;
    }
    let [a, b, c, d, e, f, g, h] = H;
    for (let j = 0; j < 64; j++) {
      const S1 = rotr(e!, 6) ^ rotr(e!, 11) ^ rotr(e!, 25);
      const ch = (e! & f!) ^ (~e! & g!);
      const t1 = (h! + S1 + ch + K[j]! + w[j]!) >>> 0;
      const S0 = rotr(a!, 2) ^ rotr(a!, 13) ^ rotr(a!, 22);
      const maj = (a! & b!) ^ (a! & c!) ^ (b! & c!);
      const t2 = (S0 + maj) >>> 0;
      h = g;
      g = f;
      f = e;
      e = (d! + t1) >>> 0;
      d = c;
      c = b;
      b = a;
      a = (t1 + t2) >>> 0;
    }
    H[0] = (H[0]! + a!) >>> 0;
    H[1] = (H[1]! + b!) >>> 0;
    H[2] = (H[2]! + c!) >>> 0;
    H[3] = (H[3]! + d!) >>> 0;
    H[4] = (H[4]! + e!) >>> 0;
    H[5] = (H[5]! + f!) >>> 0;
    H[6] = (H[6]! + g!) >>> 0;
    H[7] = (H[7]! + h!) >>> 0;
  }

  let out = "";
  for (let i = 0; i < 8; i++) out += H[i]!.toString(16).padStart(8, "0");
  return out;
}

function rotr(x: number, n: number): number {
  return ((x >>> n) | (x << (32 - n))) >>> 0;
}
