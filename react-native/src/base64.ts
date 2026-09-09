import {fromByteArray, toByteArray} from 'base64-js';

export function encodeBase64(bytes: Uint8Array): string {
  return fromByteArray(bytes);
}

export function decodeBase64(value: string): Uint8Array {
  // Native and server wires use canonical padded Base64. base64-js alone also
  // accepts URL-safe and malformed input, so validate before consuming bytes.
  if (value.length % 4 !== 0 || !/^[A-Za-z0-9+/]*={0,2}$/.test(value)) {
    throw new Error('Base64 data is invalid');
  }
  const bytes = toByteArray(value);
  if (fromByteArray(bytes) !== value) {
    throw new Error('Base64 data is not canonical');
  }
  return bytes;
}
