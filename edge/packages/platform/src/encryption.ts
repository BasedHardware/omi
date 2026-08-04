/**
 * Per-user AES-256-GCM + HKDF-SHA256 — wire-compatible with backend/utils/encryption.py
 *
 * String payload: base64(nonce12 || ciphertext||tag)
 * Audio chunk: be32(len) || nonce12 || ciphertext||tag
 */

const INFO = new TextEncoder().encode("user-data-encryption");

function requireSecret(secret: string): Uint8Array {
  const bytes = new TextEncoder().encode(secret);
  if (bytes.length < 32) {
    throw new Error("ENCRYPTION_SECRET not set or too short (need >= 32 bytes)");
  }
  return bytes;
}

export async function deriveKey(secret: string, uid: string): Promise<CryptoKey> {
  const master = requireSecret(secret);
  const baseKey = await crypto.subtle.importKey("raw", master, "HKDF", false, ["deriveKey"]);
  return crypto.subtle.deriveKey(
    {
      name: "HKDF",
      hash: "SHA-256",
      salt: new TextEncoder().encode(uid),
      info: INFO,
    },
    baseKey,
    { name: "AES-GCM", length: 256 },
    true,
    ["encrypt", "decrypt"],
  );
}

export async function deriveKeyRaw(secret: string, uid: string): Promise<Uint8Array> {
  const key = await deriveKey(secret, uid);
  return new Uint8Array(await crypto.subtle.exportKey("raw", key));
}

function b64Encode(bytes: Uint8Array): string {
  let s = "";
  for (let i = 0; i < bytes.length; i++) s += String.fromCharCode(bytes[i]!);
  return btoa(s);
}

function b64Decode(data: string): Uint8Array {
  const bin = atob(data);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

export async function encrypt(data: string, uid: string, secret: string): Promise<string> {
  if (!data) return data;
  const key = await deriveKey(secret, uid);
  const nonce = crypto.getRandomValues(new Uint8Array(12));
  const plaintext = new TextEncoder().encode(data);
  const ciphertext = new Uint8Array(
    await crypto.subtle.encrypt({ name: "AES-GCM", iv: nonce }, key, plaintext),
  );
  const payload = new Uint8Array(nonce.length + ciphertext.length);
  payload.set(nonce, 0);
  payload.set(ciphertext, nonce.length);
  return b64Encode(payload);
}

export async function decrypt(encryptedData: string, uid: string, secret: string): Promise<string> {
  if (!encryptedData) return encryptedData;
  try {
    const key = await deriveKey(secret, uid);
    const payload = b64Decode(encryptedData);
    const nonce = payload.slice(0, 12);
    const ciphertext = payload.slice(12);
    const plain = await crypto.subtle.decrypt({ name: "AES-GCM", iv: nonce }, key, ciphertext);
    return new TextDecoder().decode(plain);
  } catch {
    // Match Python: fail-open return ciphertext on decrypt error
    return encryptedData;
  }
}

export async function encryptAudioChunk(data: Uint8Array, uid: string, secret: string): Promise<Uint8Array> {
  const key = await deriveKey(secret, uid);
  const nonce = crypto.getRandomValues(new Uint8Array(12));
  const ciphertext = new Uint8Array(
    await crypto.subtle.encrypt({ name: "AES-GCM", iv: nonce }, key, data),
  );
  const encryptedPayload = new Uint8Array(nonce.length + ciphertext.length);
  encryptedPayload.set(nonce, 0);
  encryptedPayload.set(ciphertext, nonce.length);
  const out = new Uint8Array(4 + encryptedPayload.length);
  const view = new DataView(out.buffer);
  view.setUint32(0, encryptedPayload.length, false);
  out.set(encryptedPayload, 4);
  return out;
}

export async function decryptAudioChunk(
  encryptedData: Uint8Array,
  uid: string,
  secret: string,
  offset = 0,
): Promise<{ data: Uint8Array; bytesConsumed: number }> {
  const view = new DataView(encryptedData.buffer, encryptedData.byteOffset, encryptedData.byteLength);
  const length = view.getUint32(offset, false);
  const start = offset + 4;
  const encryptedPayload = encryptedData.slice(start, start + length);
  const nonce = encryptedPayload.slice(0, 12);
  const ciphertext = encryptedPayload.slice(12);
  const key = await deriveKey(secret, uid);
  const plain = new Uint8Array(
    await crypto.subtle.decrypt({ name: "AES-GCM", iv: nonce }, key, ciphertext),
  );
  return { data: plain, bytesConsumed: 4 + length };
}

export async function decryptAudioFile(
  encryptedData: Uint8Array,
  uid: string,
  secret: string,
): Promise<Uint8Array> {
  const chunks: Uint8Array[] = [];
  let offset = 0;
  let total = 0;
  while (offset < encryptedData.length) {
    const { data, bytesConsumed } = await decryptAudioChunk(encryptedData, uid, secret, offset);
    chunks.push(data);
    total += data.length;
    offset += bytesConsumed;
  }
  const out = new Uint8Array(total);
  let o = 0;
  for (const c of chunks) {
    out.set(c, o);
    o += c.length;
  }
  return out;
}
